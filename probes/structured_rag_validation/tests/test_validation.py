import copy
import json
from pathlib import Path
import tempfile
import unittest

from Benchmarks.agent_story.scenarios import load_scenarios
from Benchmarks.support.common import file_hash, write_json
from probes.structured_rag_validation import evidence, validation


class ValidationTests(unittest.TestCase):
    def test_explicit_question_bank_does_not_change_default_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bank = root / 'candidate.json'
            write_json(bank, {'source_snapshot': 'new', 'questions': [
                {'id': 'q', 'question': '问', 'criteria': ['答'], 'sources': []}]})
            suite = root / 'suite.json'
            write_json(suite, {'question_bank_sha256': file_hash(bank), 'scenarios': [
                {'id': 'a06', 'group': 'memory', 'question_ids': ['q'],
                 'turns': [{'question_id': 'q'}], 'required_criteria': [], 'forbidden': []}]})
            self.assertEqual(load_scenarios(root, suite, questions_path=bank)['source_snapshot'], 'new')
            with self.assertRaises(FileNotFoundError):
                load_scenarios(root, suite)
            bank.write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'fingerprint'):
                load_scenarios(root, suite, questions_path=bank)

    def test_text_render_is_lossless_for_null_empty_and_grouped_options(self):
        content = {'turns': [
            {'kind': 'speech', 'speaker': None, 'text': '', 'pointer': '/a', 'span': [0, 0]},
            {'kind': 'choice', 'speaker': '', 'options': [
                {'text': '甲\n乙', 'pointer': '/b/0', 'span': [0, 3]},
                {'text': '丙', 'pointer': '/b/1', 'span': [0, 1]}],
             'quality_flags': ['upstream_uncertain']}], 'sections': []}
        rendered = evidence.render_content(content)
        self.assertEqual(evidence.parse_content(rendered), content)
        self.assertIn('speaker: null', rendered)
        self.assertIn('speaker: ""', rendered)
        self.assertIn('option 2', rendered)

    def test_text_render_preserves_section_fields_and_unicode(self):
        content = {'turns': [], 'sections': [
            {'field': '故事', 'text': '“或许”\n不能省略', 'pointer': '/故事', 'span': [2, 12]}]}
        self.assertEqual(evidence.parse_content(evidence.render_content(content)), content)

    def test_presentation_changes_only_content_and_never_local_audit_fields(self):
        model = {'id': 's2-x', 'title': '例', 'knowledge_type': 'dialogue',
                 'source': {'snapshot': 'new', 'file': 'x.json', 'kind': 'wiki_excerpt'},
                 'metadata': {'context': {}},
                 'content': {'turns': [{'speaker': '女士', 'text': '女皇', 'kind': 'speech',
                                       'pointer': '/a', 'span': [0, 2]}], 'sections': []}}
        flat = evidence.as_text(model)
        self.assertEqual({k: v for k, v in flat.items() if k != 'text'},
                         {k: v for k, v in model.items() if k != 'content'})
        self.assertEqual(evidence.parse_content(flat['text']), model['content'])
        before = {'messages': [{'role': 'tool', 'content': json.dumps({'ok': True, 'result': {'evidence': [model]}})}]}
        after = copy.deepcopy(before)
        after['messages'][0]['content'] = json.dumps({'ok': True, 'result': {'evidence': [flat]}})
        validation.assert_presentation_pair(before, after, [0])
        after['model'] = 'different'
        with self.assertRaises(ValueError):
            validation.assert_presentation_pair(before, after, [0])

    def test_force_expected_from_plan_even_when_all_force_fields_are_missing(self):
        ordinary = {'messages': [{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'q'}],
                    'tools': [{'type': 'function', 'function': {'name': 'search_story'}}],
                    'chat_template_kwargs': {'enable_thinking': False}}
        with self.assertRaisesRegex(ValueError, 'forced'):
            validation.validate_request(ordinary, forced=True)
        forced = copy.deepcopy(ordinary)
        forced.update(tool_choice='required', continue_final_message='content', add_generation_prompt=False)
        forced['messages'].append({'role': 'assistant', 'content': '<tool_call>\n'})
        validation.validate_request(forced, forced=True)
        with self.assertRaisesRegex(ValueError, 'leak'):
            validation.validate_request(forced, forced=False)

    def test_candidate_snapshot_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            validation.validate_inputs([{'schema_version': 2, 'source': {'snapshot': 'old'}}],
                                       {'source_snapshot': 'new'}, Path('new'))

    def test_empty_source_mapping_cannot_claim_covered(self):
        with self.assertRaisesRegex(ValueError, 'anchor'):
            evidence.require_mapped([{'ids': [], 'source_pointer': '/对话/1/内容'}])

    def test_controlled_first_answer_does_not_answer_followups(self):
        history = evidence.correct_history('问题', [{'id': 's2-proof', 'knowledge_type': 'wiki_compilation'}], 's2-proof', 'sys')
        answer = history['messages'][-1]['content']
        self.assertIn('女士', answer)
        self.assertIn('Wiki', answer)
        self.assertNotIn('第八席', answer)
        self.assertNotIn('女皇', answer)
        self.assertEqual(history['messages'][-2]['role'], 'tool')

    def test_presentation_pair_rejects_removed_speaker(self):
        model = {'id': 's2-x', 'content': {'turns': [{'speaker': '女士', 'text': '女皇'}], 'sections': []}}
        flat = evidence.as_text(model)
        flat['text'] = evidence.render_content({'turns': [{'text': '女皇'}], 'sections': []})
        def payload(value):
            return {'messages': [{'role': 'tool', 'content': json.dumps({'ok': True, 'result': {'evidence': [value]}})}]}
        with self.assertRaises(ValueError):
            validation.assert_presentation_pair(payload(model), payload(flat), [0])


if __name__ == '__main__':
    unittest.main()
