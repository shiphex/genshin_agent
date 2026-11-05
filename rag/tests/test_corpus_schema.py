import copy
import json
import unittest

from rag.scripts import full_corpus


class StructuredCorpusTests(unittest.TestCase):
    def extract(self, source, family='archon-quests', size=800):
        extractor = full_corpus.Extractor(source, 'parsed/' + family + '/test.json', family, '测试', size,
                                          snapshot='snapshot-a', source_sha256='a' * 64)
        extractor.run()
        return extractor.records

    def test_speech_narration_choices_and_unknown_keep_original_roles(self):
        rows = [
            {'说话者': '女士', '内容': '温迪，你好。', '类型': 'character', '所属任务流程': '门前'},
            {'说话者': '', '内容': '风吹过。', '类型': 'narration', '所属任务流程': '门前'},
            {'类型': '选项', '选项': ['左边？', '右边？'], '所属任务流程': '门前'},
            {'说话者': '', '内容': '未知记录。', '类型': 'unrecognized', '所属任务流程': '门前'},
        ]
        record = self.extract({'所属版本': '1.0', '对话': rows})[0]
        self.assertEqual(record['schema_version'], 2)
        self.assertEqual(record['source']['snapshot'], 'snapshot-a')
        turns = record['content']['turns']
        self.assertEqual([t['kind'] for t in turns], ['speech', 'narration', 'choice', 'unknown'])
        self.assertEqual(turns[0]['speaker'], '女士')
        self.assertEqual(turns[0]['text'], '温迪，你好。')
        self.assertEqual(turns[0]['row_pointer'], '/对话/0')
        self.assertEqual([o['text'] for o in turns[2]['options']], ['左边？', '右边？'])
        self.assertEqual(turns[2]['options'][1]['pointer'], '/对话/2/选项/1')
        self.assertEqual(turns[3]['source_type'], 'unrecognized')
        self.assertEqual(record['metadata']['source_version'], '1.0')

    def test_choice_group_cannot_be_split_by_chunk_budget(self):
        records = self.extract({'对话': [{'类型': '选项', '选项': ['甲' * 30, '乙' * 30],
                                        '所属任务流程': '选择'}]}, size=10)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(records[0]['content']['turns'][0]['options']), 2)

    def test_metadata_sections_and_ids_are_snapshot_bound(self):
        source = {'所属版本': '1.2', '名称': '剑', '介绍': '介绍。', '故事': '往事。' * 20}
        records = self.extract(source, 'weapons', 20)
        self.assertEqual(records[0]['metadata']['entity'], {'type': 'weapon', 'name': '剑'})
        self.assertEqual(records[0]['content']['sections'][0]['field'], '介绍')
        self.assertGreater(len(records), 2)
        self.assertEqual(records, self.extract(source, 'weapons', 20))
        other = full_corpus.Extractor(source, 'parsed/weapons/test.json', 'weapons', '测试', 20,
                                      snapshot='snapshot-b', source_sha256='a' * 64)
        other.run()
        self.assertNotEqual(records[0]['id'], other.records[0]['id'])

    def test_projection_and_validation_preserve_structure_without_duplicate_body(self):
        from rag.scripts import corpus_schema as schema
        from rag.scripts.evaluate_rag_mvp import make_messages
        record = self.extract({'对话': [{'说话者': '女士', '内容': '仅此一份台词。',
                                        '类型': 'character', '所属任务流程': '门前'}]})[0]
        schema.validate_record(record)
        evidence = schema.to_model_evidence({**record, 'score': 99})
        self.assertNotIn('text', evidence)
        self.assertNotIn('score', evidence)
        self.assertNotIn('file_sha256', evidence['source'])
        payload = json.dumps(make_messages('谁说的？', [record]), ensure_ascii=False)
        self.assertEqual(payload.count('仅此一份台词。'), 1)
        self.assertIn('speaker', payload)
        broken = copy.deepcopy(record)
        broken['content']['turns'][0]['span']['end'] = -1
        with self.assertRaises(ValueError):
            schema.validate_record(broken)
        broken = {**record, 'schema_version': 999}
        with self.assertRaises(ValueError):
            schema.to_model_evidence(broken)

    def test_legacy_is_read_without_inventing_turns(self):
        from rag.scripts import corpus_schema as schema
        row = {'id': 'old', 'title': '旧资料', 'text': '原始展示文本', 'source_file': 'parsed/a.json',
               'source_pointer': ['/正文'], 'source_spans': [{'start': 0, 'end': 6}],
               'source_kind': 'wiki_excerpt'}
        self.assertEqual(schema.to_model_evidence(row)['text'], '原始展示文本')
        self.assertNotIn('content', schema.to_model_evidence(row))
        self.assertEqual(list(schema.iter_locations(row))[0][1], '/正文')

    def test_snapshot_mismatch_rejects_valid_but_unrelated_pointers(self):
        from rag.scripts import corpus_schema as schema
        row = self.extract({'名称': '剑', '故事': '往事。'}, 'weapons')[0]
        with self.assertRaises(ValueError):
            schema.assert_snapshot_match([row], 'data/raw/other')
        schema.assert_snapshot_match([row], 'data/raw/snapshot-a')

    def test_frozen_benchmark_sources_reject_new_raw_before_reading_any_file(self):
        from pathlib import Path
        from Benchmarks.agent_story.providers import freeze_sources
        with self.assertRaisesRegex(ValueError, 'snapshot mismatch'):
            freeze_sources({'source_snapshot': 'old-snapshot', 'reference_material': []}, Path('new-snapshot'))

    def test_provider_sends_structured_evidence_in_native_tool_history(self):
        from Benchmarks.agent_story.providers import LiveProvider, QwenClient
        row = self.extract({'对话': [{'说话者': '女士', '内容': '仅此一份台词。',
                                        '类型': 'character', '所属任务流程': '门前'}]})[0]
        seen = []
        call = {'id': 't', 'type': 'function', 'function': {'name': 'search_story', 'arguments': '{"query":"女士"}'}}
        def transport(endpoint, payload, timeout):
            seen.append(copy.deepcopy(payload))
            return {'choices': [{'message': {'role': 'assistant', 'content': None, 'tool_calls': [call]},
                                 'finish_reason': 'tool_calls'}]} if len(seen) == 1 else {
                'choices': [{'message': {'role': 'assistant', 'content': '女士 [id]'}, 'finish_reason': 'stop'}]}
        provider = LiveProvider(QwenClient({'base_url': 'http://127.0.0.1:8000/v1', 'model': 'fake'}, transport=transport), [row])
        provider.begin('s', '女士说了什么？', 1)
        messages = [{'role': 'user', 'content': '女士说了什么？'}]
        model = provider.provide('model', {'messages': messages}, 's', 1)
        messages.append(model['result']['message'])
        tool = provider.provide('tool', {'call_id': 't', 'name': 'search_story', 'arguments': {'query': '女士'}}, 's', 1)
        self.assertTrue(tool['ok'])
        self.assertNotIn('text', tool['result']['evidence'][0])
        self.assertIn('content', tool['result']['evidence'][0])
        messages.append({'role': 'tool', 'tool_call_id': 't', 'content': json.dumps(tool, ensure_ascii=False)})
        self.assertTrue(provider.provide('model', {'messages': messages}, 's', 1)['ok'])
        payload = json.dumps(seen[-1], ensure_ascii=False)
        self.assertEqual(payload.count('仅此一份台词。'), 1)
        self.assertIn('speaker', payload)
        self.assertEqual(provider.evidence[row['id']]['source']['file_sha256'], 'a' * 64)

    def test_confirmed_source_review_marks_but_never_repairs_upstream_row(self):
        row = {'说话者': '', '内容': '丝柯克:原台词。', '类型': 'narration', '所属任务流程': '交谈'}
        source = {'对话': [row]}
        extractor = full_corpus.Extractor(source, 'parsed/archon-quests/test.json', 'archon-quests', '测试', 800,
            snapshot='snapshot-a', source_sha256='a' * 64,
            source_review={'/对话/0': ['upstream_attribution_pending']})
        extractor.run()
        turn = extractor.records[0]['content']['turns'][0]
        self.assertEqual(turn['speaker'], '')
        self.assertEqual(turn['kind'], 'narration')
        self.assertEqual(turn['text'], '丝柯克:原台词。')
        self.assertIn('upstream_attribution_pending', turn['quality_flags'])
