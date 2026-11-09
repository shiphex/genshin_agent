import unittest
from probes.structured_rag_validation import stages


class StageTests(unittest.TestCase):
    def test_unreviewed_or_insufficient_oracle_cannot_seed_correct_history(self):
        rows = [{'sample_id': 't1-oracle', 'hits': [{'id': 'proof'}]},
                {'sample_id': 't1-direct', 'hits': [{'id': 'fallback'}]}]
        with self.assertRaisesRegex(ValueError, 'reviewed'):
            stages.select_evidence(rows, {}, 1)
        review = {'queries': {'t1-oracle': {'semantic_sufficiency': 'insufficient', 'supporting_ids': []},
                  't1-direct': {'semantic_sufficiency': 'sufficient', 'supporting_ids': ['fallback'], 'reason': 'frozen source'}}}
        hits, identity, origin = stages.select_evidence(rows, review, 1)
        self.assertEqual(identity, 'fallback')
        self.assertEqual(origin, 't1-direct')
        self.assertEqual(hits[0]['id'], identity)

    def test_declared_support_must_refer_to_actual_frozen_hits(self):
        review = {'queries': {'t1-oracle': {'semantic_sufficiency': 'sufficient',
                  'supporting_ids': ['invented'], 'reason': 'bad'}}}
        with self.assertRaises(ValueError):
            stages.select_evidence([{'sample_id': 't1-oracle', 'hits': [{'id': 'real'}]}], review, 1)

    def test_third_question_presentation_has_only_correct_first_answer_in_history(self):
        hit = {'id': 'proof', 'source': {'kind': 'wiki_excerpt'}, 'content': {'turns': [], 'sections': []}}
        messages, indices = stages.presentation_messages(['首问', '身份追问', '效忠追问'],
                                                         [hit], 'proof', [hit], 3)
        assistants = [m['content'] for m in messages if m['role'] == 'assistant' and m['content']]
        self.assertEqual(len(assistants), 1)
        self.assertIn('女士', assistants[0])
        self.assertNotIn('女皇', assistants[0])
        self.assertEqual(indices, [3, 7])
        self.assertEqual(messages[5]['content'], '效忠追问')


if __name__ == '__main__':
    unittest.main()
