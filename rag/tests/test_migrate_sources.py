import unittest


class SourceMigrationTests(unittest.TestCase):
    def test_ruby_comparison_keeps_original_parentheses_without_duplicating_them(self):
        from rag.scripts.migrate_sources import comparison_text
        self.assertEqual(comparison_text('「龙王」( 尼伯龙根 )'),
                         comparison_text('<ruby>「龙王」<rp>(</rp><rt> 尼伯龙根 </rt><rp>)</rp></ruby>'))
    def migrate(self, old, new, sources):
        from rag.scripts.migrate_sources import migrate_document
        document = {'version': '0.5', 'source_snapshot': 'old', 'questions': [
            {'id': 'q', 'question': '谁说的？', 'answer': '甲说的', 'criteria': ['归属甲'], 'sources': sources}]}
        return migrate_document(document, lambda _: old, lambda _: new, 'new')

    def test_relocation_uses_full_row_not_a_constant_offset_or_text_only(self):
        old_row = {'说话者': '甲', '类型': 'character', '内容': '你好。', '所属任务流程': '交谈'}
        new = {'对话': [{'说话者': '乙', '类型': 'character', '内容': '你好。'}, old_row]}
        migrated, report = self.migrate({'对话': [old_row]}, new,
                                       [{'file': 'parsed/a.json', 'pointer': '/对话/0/内容'}])
        self.assertEqual(migrated['questions'][0]['sources'][0]['pointer'], '/对话/1/内容')
        self.assertEqual(migrated['questions'][0]['answer'], '甲说的')
        self.assertEqual(report[0]['status'], 'exact_row')

    def test_upstream_narration_regression_is_located_but_not_repaired(self):
        old = {'对话': [{'说话者': '甲', '类型': 'character', '内容': '你好。'}]}
        new = {'对话': [{'说话者': '', '类型': 'narration', '内容': '甲:你好。'}]}
        migrated, report = self.migrate(old, new, [{'file': 'parsed/a.json', 'pointer': '/对话/0/内容', 'text': '你好。'}])
        self.assertEqual(migrated['questions'][0]['sources'][0]['text'], '甲:你好。')
        self.assertEqual(report[0]['status'], 'upstream_attribution_pending')
        self.assertEqual(report[0]['new_row']['说话者'], '')

    def test_duplicate_rows_and_missing_text_remain_unresolved(self):
        row = {'说话者': '甲', '类型': 'character', '内容': '你好。'}
        for new in [{'对话': [row, row]}, {'对话': []}]:
            migrated, report = self.migrate({'对话': [row]}, new,
                                           [{'file': 'parsed/a.json', 'pointer': '/对话/0/内容'}])
            self.assertEqual(report[0]['status'], 'unresolved')
            self.assertIsNone(migrated)

    def test_display_changes_are_comparison_only_and_frozen_text_is_verified(self):
        old = {'volumes': [{'content': '前往{{颜色|描述|营地}}。\n'}]}
        new = {'volumes': [{'content': '前往营地。'}]}
        _, report = self.migrate(old, new, [{'file': 'parsed/a.json', 'pointer': '/volumes/0/content'}])
        self.assertEqual(report[0]['status'], 'display_change')
        with self.assertRaises(ValueError):
            self.migrate(old, new, [{'file': 'parsed/a.json', 'pointer': '/volumes/0/content', 'text': '伪造'}])

    def test_incomplete_candidate_marks_old_pointer_and_cannot_false_hit_new_text(self):
        from rag.scripts.migrate_sources import migrate_document
        from rag.scripts.evaluate_retrieval import score_locations
        old = {'对话': [{'说话者': '甲', '类型': 'character', '内容': '缺失台词。'}]}
        new = {'对话': [{'说话者': '乙', '类型': 'character', '内容': '另一台词。'}]}
        document = {'source_snapshot': 'old', 'questions': [{'id': 'q', 'sources': [
            {'file': 'parsed/a.json', 'pointer': '/对话/0/内容'}]}]}
        candidate, _ = migrate_document(document, lambda _: old, lambda _: new, 'new', allow_incomplete=True)
        sources = candidate['questions'][0]['sources']
        self.assertEqual(sources[0]['migration_status'], 'unresolved')
        hit = {'id': 'c', 'source_file': 'parsed/a.json', 'source_pointer': ['/对话/0/内容']}
        score = score_locations(sources, [hit], {('parsed/a.json', '/对话/0/内容')})
        self.assertEqual(score['annotated_locations'], 1)
        self.assertEqual(score['matched_locations'], 0)
        self.assertEqual(score['unmapped_locations'], 1)
