"""Build the full snapshot's traceable lore corpus without third-party dependencies."""

from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import re
import time

if __package__:
    from .prepare_rag_mvp import GAMEPLAY, read_json, resolve_pointer
else:
    from prepare_rag_mvp import GAMEPLAY, read_json, resolve_pointer

METADATA_TYPES = {"archon-quest-index", "character-quest-index"}
COMPILATIONS = {"chronicles", "north-library"}
DESCRIPTIONS = {
    "weapons": ["介绍", "故事"], "items": ["介绍"], "materials": ["介绍"],
    "monsters": ["description"], "wildlife": ["描述"], "namecards": ["描述"],
    "quest-items": ["描述", "内容"], "secret-items": ["介绍"],
}
CATEGORY_TYPES = {"书籍": "books", "任务道具": "quest-items", "传说任务": "character-quests",
                  "部族纪闻": "character-quests", "名片": "namecards", "圣遗物套装": "artifacts",
                  "怪物": "monsters", "材料": "materials", "武器": "weapons", "活动事件": "event-quests",
                  "秘境": "secret-items", "角色": "characters", "道具": "items", "野生生物": "wildlife", "食物": "foods"}
PROFILE_FIELDS = ["名称", "称号", "全名", "所属", "出身", "种族", "介绍", "性别", "昵称/外号", "归属", "职业"]
POWER_STORIES = {"神之眼", "神之心", "蛇之七变", "月之轮", "其他故事", "三相月临", "古龙大权"}
SUPPORTED = set(DESCRIPTIONS) | COMPILATIONS | {"artifacts", "characters", "books", "foods",
                                                "archon-quests", "character-quests", "event-quests"}
TAG = r"(?:br|p|div|span|b|strong|i|em|u|s|small|sup|sub|font|a|ref|center)"
LINK = re.compile(r"\[\[([^\[\]\n|]+)(?:\|([^\[\]\n|]+))?\]\]")
PROTECTED = re.compile(r"<!--[\s\S]*?-->|\[\[[^\[\]]*\]\]|<[^>]*>|&(?:#\d+|#x[0-9a-fA-F]+|[A-Za-z]+);")
FULL_GAMEPLAY = re.compile(
    GAMEPLAY.pattern + r"|抗性[^。！？\n]{0,25}\d+(?:\.\d+)?\s*[%％]"
    r"|\d+(?:\.\d+)?\s*[%％]\s*(?:生命值|攻击力|防御力|伤害|抗性)"
    r"|\d+(?:\.\d+)?\s*单位\s*(?:[火水冰雷风岩草]元素|护甲|元素量)"
    r"|冷却时间|无敌帧|削韧|伤害倍率|元素附着量|护盾强效", re.IGNORECASE)
MONSTER_GUIDE = re.compile(r"锁血|元素附着|伤害免疫效果|月曜反应伤害|攻击模式|战斗机制"
                           r"|抗性(?:巨幅|大幅)?(?:提升|提高|降低)|(?:火|水|雷|冰|风|岩|草)抗性")
PAGE_STYLE = re.compile(r"(?:^|\n)\s*(?:body|html|[.#][\w-]+)\s*\{[^}]*"
                        r"(?:background(?:-size|-image)?|font-size|display)\s*:[^}]*\}", re.IGNORECASE)


def excluded_text_reason(text, family):
    if PAGE_STYLE.search(text):
        return "page_style"
    if FULL_GAMEPLAY.search(text) or (family == "monsters" and MONSTER_GUIDE.search(text)):
        return "mixed_gameplay"
    return None


def clean_markup(text):
    """Strip only understood display syntax; never interpret Wiki templates."""
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    if "<!--" in text or "-->" in text:
        raise ValueError("incomplete_comment")
    if "{{" in text or "}}" in text:
        raise ValueError("unknown_template")
    def display(match):
        if re.match(r"(?:File|Image|文件|图像):", match[1], re.IGNORECASE):
            raise ValueError("embedded_media")
        return match[2] if match[2] is not None else match[1]
    text = LINK.sub(display, text)
    if "[[" in text or "]]" in text:
        raise ValueError("incomplete_or_complex_link")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(?:p|div)\b[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?" + TAG + r"\b[^>]*>", "", text, flags=re.IGNORECASE)
    if re.search(r"<[!/?A-Za-z]", text):
        raise ValueError("unresolved_html")
    return html.unescape(text).strip()


def escape_pointer(key):
    return str(key).replace("~", "~0").replace("/", "~1")


def paragraph_spans(text):
    protected = [(m.start(), m.end()) for m in PROTECTED.finditer(text)]
    def inside(position):
        return next(((a, b) for a, b in protected if a < position < b), None)
    breaks = [0]
    for match in re.finditer(r"\n[ \t\r]*\n(?:[ \t\r]*\n)*|<br\s*/?>", text, re.IGNORECASE):
        if not inside(match.start()):
            breaks.extend([match.start(), match.end()])
    breaks.append(len(text))
    return [(breaks[i], breaks[i + 1]) for i in range(0, len(breaks) - 1, 2)]


def split_spans(text, max_chars):
    """Split original text, keeping display tokens intact and original offsets."""
    protected = [(m.start(), m.end()) for m in PROTECTED.finditer(text)]
    def inside(position):
        return next(((a, b) for a, b in protected if a < position < b), None)
    paragraphs = paragraph_spans(text)
    for start, end in paragraphs:
        while start < end:
            stop = min(start + max_chars, end)
            token = inside(stop)
            if token:
                stop = token[0] if token[0] > start else token[1]
            if stop < end:
                sentence_ends = [m.end() for m in re.finditer(r"[。！？.!?]", text[start:stop])
                                 if not inside(start + m.end())]
                if sentence_ends:
                    stop = start + sentence_ends[-1]
            if text[start:stop].strip():
                yield start, stop
            start = stop


def render_ref(source, pointer, span):
    raw = resolve_pointer(source, pointer)
    if not isinstance(raw, str) or not 0 <= span["start"] <= span["end"] <= len(raw):
        raise ValueError("invalid_source_span")
    text = clean_markup(raw[span["start"]:span["end"]])
    dialogue = re.fullmatch(r"(.*/对话/\d+)/(内容|选项/\d+)", pointer)
    if dialogue:
        row = resolve_pointer(source, dialogue[1])
        if row.get("类型") in ("option", "选项"):
            return "[玩家选项；分支关系未知] " + text
        if row.get("类型") in ("narration", "旁白"):
            return "[旁白] " + text
        speaker = row.get("说话者", "")
        if not isinstance(speaker, str):
            raise ValueError("invalid_speaker")
        return (clean_markup(speaker) or "[原文说话者为空]") + "：" + text
    if pointer.startswith("/角色/"):
        return pointer.rsplit("/", 1)[-1].replace("~1", "/") + "：" + text
    return text


def reconstruct_record(source, record):
    if len(record["source_pointer"]) != len(record["source_spans"]):
        raise ValueError("source pointer/span counts differ")
    return "\n\n".join(render_ref(source, pointer, span)
                       for pointer, span in zip(record["source_pointer"], record["source_spans"]))


class Extractor:
    def __init__(self, source, relative, family, title, max_chars):
        self.source, self.relative, self.family = source, relative, family
        self.title, self.max_chars = title, max_chars
        self.records, self.issues = [], []

    def issue(self, reason, pointer=None, span=None):
        issue = {"source_file": self.relative, "type": self.family, "reason": reason,
                 "source_pointer": pointer}
        if span is not None:
            issue["source_span"] = span
        self.issues.append(issue)

    def block(self, label, pointers, dialogue=False):
        try:
            label = clean_markup(label)
        except ValueError:
            self.issue("unresolved_label_markup")
            return
        pieces, size = [], 0
        def flush():
            nonlocal pieces, size
            if not pieces:
                return
            positions = [{"start": a, "end": b} for _, a, b, _ in pieces]
            paths = [p for p, _, _, _ in pieces]
            identity = json.dumps([self.relative, paths, positions], ensure_ascii=False, separators=(",", ":"))
            self.records.append({"id": "f" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
                "title": self.title + " / " + label, "type": self.family, "parent_id": self.relative,
                "text": "\n\n".join(t for _, _, _, t in pieces), "source_file": self.relative,
                "source_pointer": paths, "source_spans": positions,
                "source_kind": "wiki_compilation" if self.family in COMPILATIONS else "wiki_excerpt"})
            pieces, size = [], 0
        for pointer in pointers:
            try:
                raw = resolve_pointer(self.source, pointer)
                if not isinstance(raw, str):
                    raise ValueError("invalid_text")
                clean = clean_markup(raw)
                if not clean:
                    raise ValueError("empty_text")
                reason = excluded_text_reason(clean, self.family)
                if reason and dialogue:
                    self.issue(reason, pointer, {"start": 0, "end": len(raw)})
                    flush()
                    continue
                if reason:
                    spans = []
                    for a, b in paragraph_spans(raw):
                        paragraph = clean_markup(raw[a:b])
                        bad = excluded_text_reason(paragraph, self.family)
                        if bad:
                            spans.append((a, b, bad))
                        else:
                            if reason == "page_style":
                                footer = re.search(r"(?:^|\n)[ \t]*来源[ \t]*$", raw[a:b])
                                if footer:
                                    self.issue("page_footer_heading", pointer, {"start": a + footer.start(), "end": b})
                                    b = a + footer.start()
                            parts = [(0, b - a)] if len(paragraph) <= self.max_chars else split_spans(raw[a:b], self.max_chars)
                            spans.extend((a + x, a + y, None) for x, y in parts)
                else:
                    parts = [(0, len(raw))] if dialogue or len(clean) <= self.max_chars else split_spans(raw, self.max_chars)
                    spans = [(a, b, None) for a, b in parts]
                for start, end, bad in spans:
                    if bad:
                        flush()
                        self.issue(bad, pointer, {"start": start, "end": end})
                        continue
                    text = render_ref(self.source, pointer, {"start": start, "end": end})
                    if not text.strip():
                        self.issue("empty_display_fragment", pointer, {"start": start, "end": end})
                        continue
                    addition = len(text) + (2 if pieces else 0)
                    if pieces and size + addition > self.max_chars:
                        flush()
                        addition = len(text)
                    pieces.append((pointer, start, end, text))
                    size += addition
            except (KeyError, IndexError, TypeError, ValueError) as error:
                flush()
                self.issue(str(error) if isinstance(error, ValueError) else "invalid_field", pointer)
        flush()

    def fields(self, source, base, names, label=None):
        for key in names:
            if key in source:
                self.block(label or key, [base + "/" + escape_pointer(key)])

    def dialogue(self, rows, base, outer_stage=None):
        if not isinstance(rows, list):
            self.issue("invalid_dialogue", base)
            return
        if not rows:
            self.issue("no_dialogue_in_parsed", base)
            return
        if outer_stage is not None:
            try:
                clean_markup(outer_stage)
            except (TypeError, ValueError):
                self.issue("unresolved_stage_markup", base.rsplit("/对话", 1)[0] + "/任务流程")
                self.issues[-1]["affected_dialogue_rows"] = len(rows)
                return
        stage, pointers = object(), []
        def flush():
            if pointers:
                self.block(str(stage or "流程未标明"), pointers, dialogue=True)
        for i, row in enumerate(rows):
            pointer = base + "/" + str(i)
            if not isinstance(row, dict):
                flush(); pointers = []
                self.issue("invalid_dialogue_row", pointer)
                continue
            current_stage = outer_stage if outer_stage is not None else row.get("所属任务流程")
            if not isinstance(current_stage, str):
                current_stage = ""
            try:
                clean_markup(current_stage)
            except ValueError:
                flush(); pointers = []
                self.issue("unresolved_stage_markup", pointer + "/所属任务流程")
                continue
            speaker = row.get("说话者", "")
            try:
                if not isinstance(speaker, str):
                    raise ValueError("invalid speaker")
                clean_markup(speaker)
            except ValueError:
                flush(); pointers = []
                self.issue("unresolved_speaker_markup", pointer + "/说话者")
                continue
            if current_stage != stage:
                flush(); pointers = []; stage = current_stage
            if not current_stage:
                self.issue("missing_dialogue_stage", pointer)
            kind = row.get("类型")
            if kind not in ("character", "traveler", "option", "narration", "角色/NPC", "旅行者", "选项", "旁白"):
                flush(); pointers = []
                self.issue("unknown_dialogue_type", pointer)
            elif kind == "选项":
                options = row.get("选项")
                if not isinstance(options, list) or not options:
                    self.issue("invalid_options", pointer)
                else:
                    pointers.extend(pointer + "/选项/" + str(j) for j in range(len(options)))
            else:
                pointers.append(pointer + "/内容")
        flush()

    def tree(self, nodes, base, trail, library=False):
        if not isinstance(nodes, list):
            self.issue("invalid_tree", base)
            return
        for i, node in enumerate(nodes):
            pointer = base + "/" + str(i)
            if not isinstance(node, dict):
                self.issue("invalid_tree_node", pointer)
                continue
            name = node.get("title") or "未命名条目"
            path = trail + [str(name)]
            key = "text" if library else "content"
            child_keys = ["children"] if library else ["subsections", "items", "entries"]
            if node.get(key) or not any(node.get(k) for k in child_keys):
                self.block(" / ".join(path), [pointer + "/" + key])
            for child in child_keys:
                if child in node:
                    self.tree(node[child], pointer + "/" + child, path, library)

    def run(self):
        value, family = self.source, self.family
        if family in DESCRIPTIONS:
            for field in DESCRIPTIONS[family]:
                label = field
                related = value.get("相关任务")
                if isinstance(related, str) and related.strip():
                    label += " / 相关任务：" + related.strip()
                self.fields(value, "", [field], label)
        elif family == "artifacts":
            for part in ("时之沙", "死之羽", "理之冠", "生之花", "空之杯"):
                node = value.get(part)
                if isinstance(node, dict):
                    pointers = ["/" + part + "/" + key for key in ("名称", "描述", "故事") if key in node]
                    self.block(part + " / " + str(node.get("名称", "")), pointers)
        elif family == "characters":
            profile = value.get("角色", {})
            if isinstance(profile, dict):
                self.block("人物资料", ["/角色/" + escape_pointer(k) for k in PROFILE_FIELDS if profile.get(k)])
            for section in ("角色故事", "角色语音", "冒险笔记", "权能"):
                node = value.get(section, {})
                if not isinstance(node, dict):
                    self.issue("invalid_section", "/" + section)
                    continue
                for key in sorted(node):
                    pointer = "/" + section + "/" + escape_pointer(key)
                    if section == "权能" and key not in POWER_STORIES:
                        self.issue("unrecognized_power_field", pointer)
                    elif section == "角色故事" and not re.fullmatch(r"角色详细|角色故事[1-5]", key):
                        self.issue("unrecognized_story_field", pointer)
                    else:
                        self.block(section + " / " + key, [pointer])
            for key in ("壹·人物", "贰·故事"):
                if value.get(key):
                    self.issue("presentation_section_not_used", "/" + key)
        elif family == "books":
            volumes = value.get("volumes", [])
            if not isinstance(volumes, list):
                self.issue("invalid_volumes", "/volumes")
            else:
                for i, volume in enumerate(volumes):
                    if not isinstance(volume, dict):
                        self.issue("invalid_volume", "/volumes/" + str(i)); continue
                    self.block(str(volume.get("name") or f"卷 {i + 1}"), [f"/volumes/{i}/content"])
        elif family == "foods":
            intro = value.get("介绍")
            if isinstance(intro, dict):
                for key in sorted(intro):
                    self.block(key, ["/介绍/" + escape_pointer(key)])
            elif intro is not None:
                self.block("介绍", ["/介绍"])
        elif family in ("archon-quests", "character-quests", "event-quests"):
            self.fields(value, "", ["描述"] if family == "archon-quests" else ["任务描述"])
            if family == "event-quests":
                groups = value.get("剧情对话", [])
                if not groups:
                    self.issue("no_dialogue_in_parsed", "/剧情对话")
                if not isinstance(groups, list):
                    self.issue("invalid_dialogue", "/剧情对话")
                else:
                    for i, group in enumerate(groups):
                        if isinstance(group, dict):
                            self.dialogue(group.get("对话", []), f"/剧情对话/{i}/对话", group.get("任务流程", ""))
                        else:
                            self.issue("invalid_dialogue_group", f"/剧情对话/{i}")
            else:
                self.dialogue(value.get("对话", []), "/对话")
        elif family == "chronicles":
            if value.get("intro"):
                self.block("简介", ["/intro"])
            self.tree(value.get("sections", []), "/sections", [])
        elif family == "north-library":
            if value.get("summary"):
                self.block("简介", ["/summary"])
            self.tree(value.get("nodes", []), "/nodes", [], library=True)


def source_page(root, file, family):
    page_file = root / "pages" / file.name
    if not page_file.exists():
        raise ValueError("missing_raw_page")
    pages = read_json(page_file).get("query", {}).get("pages", {})
    if len(pages) != 1:
        raise ValueError("ambiguous_raw_page")
    page = next(iter(pages.values()))
    if page.get("ns") != 0 or "missing" in page:
        raise ValueError("non_content_page")
    revisions = page.get("revisions") or []
    if not revisions:
        raise ValueError("missing_raw_revision")
    raw = revisions[0].get("slots", {}).get("main", {}).get("*", "")
    if not isinstance(raw, str) or not raw:
        raise ValueError("missing_raw_revision")
    if re.match(r"\s*#(?:REDIRECT|重定向)", raw, re.IGNORECASE):
        raise ValueError("redirect_page")
    if family.endswith("-quests") and not re.search(r"\{\{\s*任务(?:\s|\||\})", raw):
        raise ValueError("wrong_task_page")
    return page


def build_full(root, max_chars=800):
    root = Path(root).resolve()
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if not (root / "parsed").is_dir() or not (root / "pages").is_dir():
        raise ValueError("snapshot must contain parsed and pages directories")
    started = time.monotonic()
    files = sorted((root / "parsed").rglob("*.json"))
    if not files:
        raise ValueError("no parsed JSON files found")
    records, issues, ledger = [], [], []
    for file in files:
        family = file.relative_to(root / "parsed").parts[0]
        relative = file.relative_to(root).as_posix()
        before_records, before_issues = len(records), len(issues)
        status = None
        try:
            if not file.resolve().is_relative_to(root / "parsed"):
                raise ValueError("source_outside_parsed")
            value = read_json(file)
            if family in METADATA_TYPES:
                status = "metadata"
            else:
                if family not in SUPPORTED:
                    raise ValueError("unsupported_type")
                if not isinstance(value, dict):
                    raise ValueError("invalid_document")
                page = source_page(root, file, family)
                quest_title = value.get("任务标题", {})
                profile = value.get("角色", {})
                title = value.get("title") or value.get("名称") or value.get("任务名称")
                title = title or (quest_title.get("中文") if isinstance(quest_title, dict) else None)
                title = title or (profile.get("名称") if isinstance(profile, dict) else None) or page.get("title")
                if not isinstance(title, str) or not title.strip():
                    raise ValueError("missing_title")
                hierarchy = [value.get(k) for k in ("章节", "章节名称", "幕", "幕名称", "所属章", "所属幕", "所属幕名称")]
                title = " / ".join([str(v).strip() for v in hierarchy if isinstance(v, str) and v.strip()] + [title])
                extractor = Extractor(value, relative, family, title, max_chars)
                extractor.run()
                if not extractor.records:
                    extractor.issue("no_usable_narrative")
                records.extend(extractor.records)
                issues.extend(extractor.issues)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
            issues.append({"source_file": relative, "type": family, "source_pointer": None,
                           "reason": str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError)
                           else "invalid_or_missing_source"})
        count, bad = len(records) - before_records, len(issues) - before_issues
        status = status or ("partial" if count and bad else "admitted" if count else "excluded")
        ledger.append({"source_file": relative, "type": family, "status": status,
                       "chunks": count, "issues": bad})
    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate generated chunk IDs")
    parsed_names = {f.name for f in files}
    unparsed = sorted(p.name for p in (root / "pages").glob("*.json") if p.name not in parsed_names)
    categories = []
    page_titles = {}
    for file in files:
        try:
            pages = read_json(root / "pages" / file.name).get("query", {}).get("pages", {})
            if len(pages) == 1:
                title = next(iter(pages.values())).get("title")
                if isinstance(title, str):
                    page_titles.setdefault(file.relative_to(root / "parsed").parts[0], set()).add(title)
        except (OSError, ValueError, AttributeError, TypeError):
            pass  # Source failures have already been recorded in the file ledger.
    for file in sorted((root / "category_members").glob("*.json")):
        try:
            members = read_json(file)
            if not isinstance(members, list) or not all(isinstance(v, str) for v in members):
                raise ValueError("invalid category list")
            kind = CATEGORY_TYPES.get(file.stem.rsplit("__", 1)[0])
            matched = set(members) & page_titles.get(kind, set())
            categories.append({"source_file": file.relative_to(root).as_posix(), "members": len(members),
                               "matched_parsed_titles": len(matched), "unmatched_titles": sorted(set(members) - matched),
                               "note": "分类包含系列、索引及模板，成员数不是剧情完成率"})
        except (OSError, ValueError, TypeError):
            categories.append({"source_file": file.relative_to(root).as_posix(), "error": "invalid_category"})
    by_type = {}
    for directory in sorted((root / "parsed").iterdir()):
        if directory.is_dir():
            by_type[directory.name] = {"input_files": 0, "admitted": 0, "partial": 0, "excluded": 0, "metadata": 0, "chunks": 0}
    for row in ledger:
        stats = by_type[row["type"]]
        stats["input_files"] += 1
        stats[row["status"]] += 1
        stats["chunks"] += row["chunks"]
    audit = {"snapshot": root.name, "max_chars": max_chars, "files_scanned": len(files),
             "chunks": len(records), "text_characters": sum(len(r["text"]) for r in records),
             "file_statuses": dict(Counter(r["status"] for r in ledger)), "by_type": by_type,
             "source_kinds": dict(Counter(r["source_kind"] for r in records)),
             "issue_counts": dict(Counter(r["reason"] for r in issues)), "files": ledger,
             "unparsed_pages": unparsed, "categories": categories,
             "semantic_review": "pending_human_review", "elapsed_seconds": round(time.monotonic() - started, 3)}
    return records, issues, audit


def write_full(output, records, issues, audit):
    """Write staged files; make the audit ledger available alongside the corpus."""
    output = Path(output)
    if __package__:
        from .evaluate_rag_mvp import validate_output_dir
    else:
        from evaluate_rag_mvp import validate_output_dir
    validate_output_dir(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, data in (("corpus.jsonl", records), ("exclusions.jsonl", issues)):
        temporary = output / (name + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for row in data:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        temporary.replace(output / name)
    temporary = output / "audit.json.tmp"
    temporary.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output / "audit.json")
    lines = ["# 全量剧情语料覆盖审计", "", f"扫描 {audit['files_scanned']} 个 parsed 文件，生成 {len(records)} 个片段。",
             "", "全量表示扫描并交代全部输入，不表示完整游戏剧情或全部内容可靠。Wiki 编纂和摘录均待语义复核。",
             "", "| 类型 | 输入 | 入库 | 部分入库 | 排除 | 元数据 | 片段 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for kind, s in audit["by_type"].items():
        lines.append(f"| {kind} | {s['input_files']} | {s['admitted']} | {s['partial']} | {s['excluded']} | {s['metadata']} | {s['chunks']} |")
    lines.extend(["", "## 问题分类", ""])
    lines.extend(f"- {reason}：{count}" for reason, count in sorted(audit["issue_counts"].items()))
    lines.extend(["", "具体文件、字段与字符范围见 exclusions.jsonl；文件逐项处理状态见 audit.json。",
                  "", "## 分类名单审计", "", "分类成员可能是系列页或模板，未匹配标题不能直接算作缺失任务。", ""])
    for category in audit["categories"]:
        if "error" in category:
            lines.append(f"- `{category['source_file']}`：无法读取分类名单")
        else:
            lines.append(f"- `{category['source_file']}`：{category['members']} 个成员，"
                         f"{category['matched_parsed_titles']} 个对应 parsed 标题，"
                         f"{len(category['unmatched_titles'])} 个未匹配。完整标题列表见 audit.json。")
    lines.extend(["", "## 各类型抽检", ""])
    for kind in audit["by_type"]:
        samples = [r for r in records if r["type"] == kind][:2]
        if not samples:
            continue
        lines.extend(["### " + kind, ""])
        for row in samples:
            lines.extend([f"- [{row['id']}] {row['title']} · {row['source_kind']}",
                          f"  - 来源 `{row['source_file']}`，Pointer `{row['source_pointer']}`，范围 `{row['source_spans']}`",
                          "", row["text"], ""])
    lines.extend(["## 典型问题", ""])
    seen = set()
    for issue in issues:
        if issue["reason"] not in seen:
            seen.add(issue["reason"])
            lines.append(f"- {issue['reason']}：`{issue['source_file']}` / `{issue.get('source_pointer')}`")
    lines.extend(["", "## 尚未解析的原网页", "", "以下页面只审计，未新增 WikiText 解析或猜测补全：", ""])
    lines.extend("- `" + name + "`" for name in audit["unparsed_pages"])
    temporary = output / "coverage.md.tmp"
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(output / "coverage.md")
