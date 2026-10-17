import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rag.scripts import full_corpus as full
from rag.scripts import evaluate_rag_mvp as evaluate
from rag.scripts import prepare_rag_mvp as prepare


class FullCorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "parsed").mkdir()
        (self.root / "pages").mkdir()

    def add(self, family, name, value, raw="{{任务\n|任务名称=测试}}", ns=0):
        path = self.root / "parsed" / family / (name + ".json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        page = {"query": {"pages": {"1": {"pageid": 1, "ns": ns, "title": name,
                "revisions": [{"slots": {"main": {"*": raw}}}]}}}}
        (self.root / "pages" / path.name).write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
        return path

    def test_display_cleanup_keeps_text_but_rejects_unknown_templates(self):
        self.assertEqual(full.clean_markup("甲<!--注释-->[[钟离|岩王]]<br>乙&amp;丙"), "甲岩王\n乙&丙")
        with self.assertRaises(ValueError):
            full.clean_markup("{{黑幕|玩家的猜测}}")
        with self.assertRaises(ValueError):
            full.clean_markup("残缺[[链接")

    def test_all_new_description_families_exclude_mechanics(self):
        fixtures = [
            ("items", {"名称": "道具", "介绍": "故友遗留的物品。", "用途": "伤害提高20%"}),
            ("materials", {"名称": "材料", "介绍": "古代祭礼的残片。", "用途": "武器突破"}),
            ("monsters", {"title": "怪物", "description": "它守护过古城。", "drop_materials": ["秘密掉落"]}),
            ("wildlife", {"名称": "生物", "描述": "栖居于古老森林。", "钓鱼信息": {"钓鱼鱼饵": "秘密鱼饵"}}),
            ("namecards", {"名称": "名片", "描述": "故乡的记忆。", "获取方式": "秘密任务"}),
            ("quest-items", {"名称": "纸条", "描述": "未寄出的信。", "内容": "他曾击败魔物。", "获取方式": "秘密攻略"}),
            ("secret-items", {"名称": "秘境", "介绍": "龙王安眠的地方。", "掉落": {"材料": "秘密掉落"}}),
            ("foods", {"名称": "料理", "介绍": {"普通料理": "她为故友烹调的汤。"}, "所需食材": "秘密配方"}),
        ]
        for family, value in fixtures:
            self.add(family, family, value)
        records, issues, audit = full.build_full(self.root)
        self.assertEqual({r["type"] for r in records}, {f for f, _ in fixtures})
        text = "\n".join(r["text"] for r in records)
        for excluded in ["伤害提高20%", "武器突破", "秘密掉落", "秘密鱼饵", "秘密任务", "秘密攻略", "秘密配方"]:
            self.assertNotIn(excluded, text)
        self.assertIn("击败魔物", text)
        self.assertEqual(audit["files_scanned"], 8)

    def test_character_adventure_and_power_stories_are_included(self):
        self.add("characters", "角色", {"角色": {"名称": "甲", "介绍": "她是冒险家。", "命之座": "数值标签"},
                 "冒险笔记": {"纪念物": "她给故友写了一封信。"}, "权能": {"古龙大权": "他并不需要神之眼。"},
                 "贰·故事": {"贰·故事": "前端损坏的重复展示"}})
        records, issues, audit = full.build_full(self.root)
        text = "\n".join(r["text"] for r in records)
        self.assertIn("故友写了一封信", text)
        self.assertIn("不需要神之眼", text)
        self.assertNotIn("数值标签", text)
        self.assertNotIn("前端损坏", text)
        self.assertTrue(any(x["reason"] == "presentation_section_not_used" for x in issues))

    def test_long_field_is_split_without_loss_and_reconstructs_original_spans(self):
        story = "第一段。" * 17 + "\n\n" + "第二段故事。" * 13
        value = {"名称": "书卷", "故事": story, "介绍": "背景。"}
        self.add("weapons", "长文", value)
        records, issues, audit = full.build_full(self.root, max_chars=45)
        story_records = [r for r in records if "/故事" in r["source_pointer"]]
        self.assertGreater(len(story_records), 1)
        spans = []
        for record in story_records:
            self.assertEqual(record["text"], full.reconstruct_record(value, record))
            self.assertLessEqual(len(record["text"]), 45)
            for span in record["source_spans"]:
                spans.append((span["start"], span["end"]))
        actual = "".join(story[start:end].strip() for start, end in spans)
        self.assertEqual(actual, story.replace("\n\n", ""))
        self.assertTrue(all(end <= following for (_, end), (following, _) in zip(spans, spans[1:])))

    def test_long_single_dialogue_is_not_split_and_stages_do_not_mix(self):
        rows = [{"类型": "character", "说话者": "？？？", "内容": "力量" * 30, "所属任务流程": "甲场景"},
                {"类型": "option", "说话者": "", "内容": "为什么？", "所属任务流程": "乙场景"},
                {"类型": "character", "说话者": "乙", "内容": "仍有未知。", "所属任务流程": ""}]
        value = {"任务名称": "任务", "对话": rows, "任务描述": "背景"}
        self.add("character-quests", "任务", value)
        records, issues, audit = full.build_full(self.root, max_chars=30)
        dialogue = [r for r in records if any(p.startswith("/对话/") for p in r["source_pointer"])]
        self.assertEqual(len(dialogue), 3)
        self.assertIn("？？？：" + "力量" * 30, dialogue[0]["text"])
        self.assertIn("分支关系未知", dialogue[1]["text"])
        self.assertTrue(any(x["reason"] == "missing_dialogue_stage" for x in issues))
        for record in records:
            self.assertEqual(record["text"], full.reconstruct_record(value, record))

    def test_event_options_keep_their_own_source_locations(self):
        value = {"任务名称": "活动", "剧情对话": [{"任务流程": "场景", "对话": [
            {"类型": "选项", "选项": ["问候。", "离开。"]}, {"类型": "旁白", "内容": "暮色降临。"}]}]}
        self.add("event-quests", "活动", value)
        records, issues, audit = full.build_full(self.root)
        text = "\n".join(r["text"] for r in records)
        self.assertIn("[玩家选项；分支关系未知] 问候。", text)
        self.assertIn("[旁白] 暮色降临。", text)
        self.assertTrue(any("/剧情对话/0/对话/0/选项/1" in r["source_pointer"] for r in records))
        for record in records:
            self.assertEqual(record["text"], full.reconstruct_record(value, record))

    def test_compilation_trees_keep_hierarchy_and_uncertainty(self):
        self.add("chronicles", "编年史", {"title": "编年史", "sections": [{"title": "古代", "content": "",
                 "subsections": [{"title": "事件", "content": "也许发生过此事。", "items": [], "subsections": []}]}]})
        self.add("north-library", "图书馆", {"title": "图书馆", "nodes": [{"title": "概念", "text": "这是推测。", "children": []}]})
        records, issues, audit = full.build_full(self.root)
        self.assertEqual({r["source_kind"] for r in records}, {"wiki_compilation"})
        self.assertTrue(any("古代 / 事件" in r["title"] for r in records))
        self.assertIn("也许发生过此事。", "\n".join(r["text"] for r in records))

    def test_bad_field_does_not_remove_good_text_in_same_file(self):
        self.add("weapons", "混合", {"名称": "武器", "介绍": "纪念先人的遗物。", "故事": "攻击力提高20%。"})
        records, issues, audit = full.build_full(self.root)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["text"], "纪念先人的遗物。")
        self.assertTrue(any(x["reason"] == "mixed_gameplay" for x in issues))
        self.assertEqual(audit["files"][0]["status"], "partial")

    def test_long_display_markup_does_not_split_a_short_cleaned_word(self):
        value = {"名称": "武器", "故事": "契<!--" + "备注" * 100 + "-->约"}
        self.add("weapons", "注释", value)
        records, issues, audit = full.build_full(self.root, max_chars=30)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["text"], "契约")
        self.assertEqual(full.reconstruct_record(value, records[0]), "契约")

    def test_category_matching_does_not_equate_landing_pages_with_missing_quests(self):
        self.add("books", "书籍", {"title": "书籍", "volumes": [{"name": "卷", "content": "正文。"}]})
        (self.root / "category_members").mkdir()
        (self.root / "category_members/书籍__abc.json").write_text(json.dumps(["书籍", "未解析系列页"], ensure_ascii=False), encoding="utf-8")
        _, _, audit = full.build_full(self.root)
        self.assertEqual(audit["categories"][0]["matched_parsed_titles"], 1)
        self.assertEqual(audit["categories"][0]["unmatched_titles"], ["未解析系列页"])

    def test_monster_element_units_and_reverse_stat_percentages_are_quarantined(self):
        descriptions = ["具有96单位火元素，使全部抗性提升120%。",
                        "每3秒修复6单位护甲，损失12.5%生命值。",
                        "终结技使所有场上角色倒下，无视护盾和任何无敌帧。"]
        for i, description in enumerate(descriptions):
            self.add("monsters", str(i), {"title": "怪物", "description": description})
        records, issues, _ = full.build_full(self.root)
        self.assertEqual(records, [])
        self.assertEqual(sum(x["reason"] == "mixed_gameplay" for x in issues), 3)

    def test_mechanics_paragraph_is_removed_without_losing_neighboring_lore(self):
        value = {"title": "古城守卫", "description": "它守护古城多年。\n\n每3秒修复6单位护甲。\n\n它还记得故友的名字。"}
        self.add("monsters", "混合段落", value)
        records, issues, _ = full.build_full(self.root)
        text = "\n".join(r["text"] for r in records)
        self.assertIn("守护古城", text)
        self.assertIn("故友的名字", text)
        self.assertNotIn("单位护甲", text)
        self.assertTrue(any(x["reason"] == "mixed_gameplay" and x.get("source_span") for x in issues))
        for record in records:
            self.assertEqual(record["text"], full.reconstruct_record(value, record))

    def test_speaker_and_stage_templates_do_not_enter_text_or_titles(self):
        rows = [{"类型": "character", "说话者": "{{#tag:tabber|分支", "内容": "模板内文字", "所属任务流程": "阶段"},
                {"类型": "character", "说话者": "甲", "内容": "受污染的阶段", "所属任务流程": "{{颜色|蓝|夜晚}}"},
                {"类型": "character", "说话者": "？？？", "内容": "可靠的对白。", "所属任务流程": "阶段"}]
        self.add("character-quests", "元数据标记", {"任务名称": "任务", "对话": rows})
        records, issues, _ = full.build_full(self.root)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["text"], "？？？：可靠的对白。")
        self.assertNotIn("{{", records[0]["title"])
        self.assertEqual({i["reason"] for i in issues}, {"unresolved_speaker_markup", "unresolved_stage_markup"})

    def test_invalid_event_stage_is_reported_at_the_group_field_once(self):
        value = {"任务名称": "任务", "任务描述": "仍保留背景。", "剧情对话": [{
            "任务流程": "{{颜色|蓝|夜晚}}", "对话": [
                {"类型": "角色/NPC", "说话者": "甲", "内容": "第一句。"},
                {"类型": "角色/NPC", "说话者": "乙", "内容": "第二句。"}]}]}
        self.add("event-quests", "无效流程", value)
        records, issues, _ = full.build_full(self.root)
        problems = [i for i in issues if i["reason"] == "unresolved_stage_markup"]
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["source_pointer"], "/剧情对话/0/任务流程")
        self.assertEqual(problems[0]["affected_dialogue_rows"], 2)
        self.assertEqual(records[0]["text"], "仍保留背景。")

    def test_page_css_is_quarantined_and_story_percentage_is_preserved(self):
        value = {"title": "史书", "sections": [{"title": "事件", "content":
                 "故事中记录了0.073%的变化。\n\n来源\nbody{background:url('image.png') no-repeat fixed 50% 0;background-size: cover;}",
                 "subsections": [], "items": []}]}
        self.add("chronicles", "页面样式", value)
        records, issues, _ = full.build_full(self.root)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["text"], "故事中记录了0.073%的变化。")
        self.assertTrue(any(x["reason"] == "page_style" for x in issues))
        self.assertEqual(full.reconstruct_record(value, records[0]), records[0]["text"])

    def test_full_prepare_refuses_another_snapshot_with_custom_input(self):
        self.add("weapons", "资料", {"名称": "武器", "介绍": "原始叙事。"})
        with tempfile.TemporaryDirectory() as directory:
            other_snapshot = Path(directory)
            (other_snapshot / "parsed").mkdir()
            (other_snapshot / "pages").mkdir()
            original = sorted(str(p.relative_to(other_snapshot)) for p in other_snapshot.rglob("*"))
            with patch("sys.argv", ["prepare", "--all", "--raw-root", str(self.root), "--output-dir", str(other_snapshot)]):
                self.assertEqual(prepare.main(), 1)
            self.assertEqual(sorted(str(p.relative_to(other_snapshot)) for p in other_snapshot.rglob("*")), original)

    def test_every_file_and_unparsed_page_is_accounted_for(self):
        self.add("weapons", "好资料", {"名称": "武器", "介绍": "古代故事。"})
        self.add("weapons", "模板", {"名称": "模板", "故事": "不得入库"}, ns=10)
        self.add("archon-quest-index", "索引", [{"title": "任务"}])
        extra = self.root / "pages" / "未解析.json"
        extra.write_text("{}", encoding="utf-8")
        records, issues, audit = full.build_full(self.root)
        self.assertEqual(audit["files_scanned"], 3)
        self.assertEqual(len(audit["files"]), 3)
        self.assertEqual({x["status"] for x in audit["files"]}, {"admitted", "excluded", "metadata"})
        self.assertIn("未解析.json", audit["unparsed_pages"])
        self.assertNotIn("不得入库", "\n".join(r["text"] for r in records))

    def test_repeated_builds_keep_ids_and_corpus_identical(self):
        self.add("books", "书籍", {"title": "书籍", "volumes": [{"name": "卷一", "content": "古老的故事。" * 10}]})
        a, issues_a, _ = full.build_full(self.root, max_chars=45)
        b, issues_b, _ = full.build_full(self.root, max_chars=45)
        self.assertEqual(a, b)
        self.assertEqual(issues_a, issues_b)
        self.assertEqual(len({r["id"] for r in a}), len(a))
        self.assertTrue(all(set(r) == {"id", "title", "type", "parent_id", "text", "source_file",
                                      "source_pointer", "source_spans", "source_kind"} for r in a))


class FullRetrievalTests(unittest.TestCase):


    def test_reused_index_keeps_ranking_and_does_not_return_zero_matches(self):
        corpus = [{"id": "a", "title": "归离原", "text": "归离原的往事。"},
                  {"id": "b", "title": "璃月", "text": "璃月的往事。"}]
        index = evaluate.LexicalIndex(corpus)
        self.assertEqual([r["id"] for r in index.search("归离原")], ["a"])
        self.assertEqual(index.search("nothing"), [])
        self.assertEqual(index.search("归离原"), index.search("归离原"))

    def test_source_anchor_mapping_requires_the_original_character_range(self):
        corpus = [{"id": "f1", "source_file": "parsed/books/a.json", "source_pointer": ["/volumes/0/content"],
                   "source_spans": [{"start": 0, "end": 20}], "text": "原文"},
                  {"id": "f2", "source_file": "parsed/books/a.json", "source_pointer": ["/volumes/0/content"],
                   "source_spans": [{"start": 20, "end": 40}], "text": "后文"}]
        questions = [{"id": "q", "expected_source_evidence": [[{
            "source_file": "parsed/books/a.json", "source_pointer": "/volumes/0/content", "start": 22, "end": 30}]]}]
        self.assertEqual(evaluate.map_source_evidence(questions, corpus)[0]["expected_evidence"], [["f2"]])
        questions[0]["expected_source_evidence"][0][0]["end"] = 50
        with self.assertRaises(ValueError):
            evaluate.map_source_evidence(questions, corpus)

    def test_prompt_marks_compilation_and_preserves_its_original_uncertainty(self):
        messages = evaluate.make_messages("时间", [{"id": "f1", "title": "编年史", "text": "大概率在此时。",
                                                       "source_kind": "wiki_compilation"}])
        self.assertIn("Wiki 编纂", messages[1]["content"])
        self.assertIn("大概率在此时。", messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
