import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
from Benchmarks.support.common import write_json

from probes.structured_rag_validation.reporting import semantic_status, import_assessment, validate_query_audit
from probes.structured_rag_validation.artifacts import new_store, seal
from probes.structured_rag_validation.reporting import report, presentation_groups


class ReportingTests(unittest.TestCase):
    def test_presentation_report_keeps_question_and_arm_separate_and_missing_usage_unknown(self):
        rows = [{'turn': 1, 'arm': 'structured', 'result': {'usage': {'prompt_tokens': 10, 'completion_tokens': 2}}},
                {'turn': 3, 'arm': 'structured', 'result': {}}]
        groups = presentation_groups(rows, ['pass', 'fail'])
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]['pass'], 1)
        self.assertEqual(groups[1]['fail'], 1)
        self.assertIsNone(groups[1]['prompt_tokens'])

    def test_report_counts_provider_tool_calls_instead_of_a_nonexistent_field(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = new_store(root / 'O-r001', 'O')
            stage.manifest['planned_samples'] = [{'sample_id': 's'}]
            stage.result({'sample_id': 's', 'scenario_id': 'a06', 'execution_status': 'completed',
                          'tool_calls': 2, 'turns': [], 'correct': None})
            stage.finish('completed'); seal(stage.path)
            with patch('probes.structured_rag_validation.reporting.load_run',
                       return_value=({}, {'a06': {'criteria': []}}, {'a06': {'frozen_sources': []}})), \
                 patch('probes.structured_rag_validation.reporting.execution_sources', return_value={}):
                output = report(root, root / 'report')
            from Benchmarks.support.common import read_json
            self.assertEqual(read_json(output / 'comparison.json')['stages'][0]['tool_requests'], 2)

    def test_final_query_audit_cannot_omit_an_actual_call_or_its_origin(self):
        expected = [{'origin_stage': 'A-r001', 'turn': 3, 'query': '女士'}]
        with self.assertRaisesRegex(ValueError, 'actual query'):
            validate_query_audit(expected, [])
        validate_query_audit(expected, [{'kind': 'actual', **expected[0]}])

    def test_invalid_first_turn_gate_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = new_store(root / 'A', 'A'); store.finish('completed'); seal(store.path)
            source = root / 'review.json'
            write_json(source, {'reviewer': 'independent', 'first_turn': {
                'supported_correct': 'true', 'reason': 'invalid type'},
                'stage_hashes_sha256': __import__('hashlib').sha256((store.path / 'hashes.json').read_bytes()).hexdigest()})
            with self.assertRaisesRegex(ValueError, 'first.turn'):
                import_assessment(store.path, source)

    def test_review_bound_to_another_run_is_rejected_instead_of_rebound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = new_store(root / 'A', 'A'); store.finish('completed'); seal(store.path)
            source = root / 'review.json'
            write_json(source, {'reviewer': 'independent', 'stage_hashes_sha256': 'another-run',
                                'first_turn': {'supported_correct': True, 'reason': 'stale'}})
            with self.assertRaisesRegex(ValueError, 'binding'):
                import_assessment(store.path, source)

    def test_api_completion_cannot_substitute_for_criteria_review(self):
        row = {'sample_id': 's', 'execution_status': 'completed', 'turns': []}
        self.assertEqual(semantic_status(row, [{'id': 'c1'}], {}), 'unreviewed')

    def test_missing_criterion_or_unresolvable_reference_is_rejected(self):
        row = {'sample_id': 's', 'execution_status': 'completed', 'turns': [{'turn': 1}]}
        review = {'samples': {'s': {'criteria': [
            {'id': 'c1', 'verdict': 'pass', 'rationale': '有据', 'evidence_refs': ['turn:1']}]}}}
        self.assertEqual(semantic_status(row, [{'id': 'c1'}], review), 'pass')
        with self.assertRaises(ValueError):
            semantic_status(row, [{'id': 'c1'}, {'id': 'f1'}], review)
        review['samples']['s']['criteria'][0]['evidence_refs'] = ['turn:99']
        with self.assertRaises(ValueError):
            semantic_status(row, [{'id': 'c1'}], review)

    def test_uncertain_or_incomplete_never_passes(self):
        row = {'sample_id': 's', 'execution_status': 'incomplete', 'turns': []}
        review = {'samples': {'s': {'criteria': [
            {'id': 'c1', 'verdict': 'pass', 'rationale': '部分输出', 'evidence_refs': ['sample:execution']}]}}}
        self.assertEqual(semantic_status(row, [{'id': 'c1'}], review), 'incomplete')


if __name__ == '__main__':
    unittest.main()
