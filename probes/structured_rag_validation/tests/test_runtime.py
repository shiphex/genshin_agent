import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from Benchmarks.support.common import read_json, read_rows, write_json, file_hash
from probes.a06_diagnosis.controls import ObservedClient
from probes.structured_rag_validation import artifacts, runtime, preparation, service


class RuntimeTests(unittest.TestCase):
    def test_native_preflight_is_a_planned_forced_request(self):
        with tempfile.TemporaryDirectory() as directory:
            store = artifacts.new_store(Path(directory) / 'preflight', 'preflight')
            raw = {'choices': [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant',
                'content': None, 'tool_calls': [{'id': 'p', 'type': 'function', 'function': {
                    'name': 'search_story', 'arguments': '{"query":"甘雨"}'}}]}}]}
            client = runtime.observed_client(artifacts.experimental_config({
                'base_url': 'http://localhost/v1', 'model': 'm'}), store, lambda *args: raw)
            self.assertTrue(client.preflight()['native_tool_calling'])

    def test_optional_private_config_absence_does_not_orphan_started_process(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            config = project / 'public.json'; config.write_text('{}', encoding='utf-8')
            model = project / 'model.gguf'; model.write_bytes(b'weights')
            binary = project / 'server.exe'; binary.write_bytes(b'binary')
            launcher = project / 'rag/scripts/serve_local_model.py'
            launcher.parent.mkdir(parents=True); launcher.write_text('# launcher', encoding='utf-8')
            command = [str(binary.resolve()), '--model', str(model)]
            owner = Mock(pid=123); owner.create_time.return_value = 1
            child = Mock(pid=456); child.create_time.return_value = 2
            child.exe.return_value = str(binary); child.cmdline.return_value = list(command)
            owner.children.return_value = [child]
            process = Mock(pid=123); process.poll.return_value = None
            reference = {'deployment': {'model_sha256': file_hash(model), 'server_sha256': file_hash(binary)}}
            settings = {'base_url': 'http://127.0.0.1/v1', 'model': 'm', 'api_key_env': None}
            with patch.object(service, 'read_json', return_value=reference), \
                 patch.object(service, 'load_settings', return_value=settings), \
                 patch.object(service, 'server_command', return_value=command), \
                 patch.object(service.subprocess, 'Popen', return_value=process), \
                 patch.object(service.psutil, 'Process', return_value=owner), \
                 patch.object(service, 'QwenClient', return_value=Mock(transport=Mock(
                     side_effect=[ConnectionError(), {'data': [{'id': 'm'}]}]))):
                result = service.start(project, project / 'service', config)
            self.assertEqual(result['status'], 'ready')
            self.assertIsNone(result['private_config_sha256'])

    def test_required_anchors_are_relocated_by_migration_not_old_indices(self):
        anchors = [{'source_file': 'f', 'source_pointer': '/对话/86/内容', 'ids': ['s2-new']}]
        entries = [{'question_id': 'gq2-001', 'input': 'questions.json', 'file': 'f',
                    'old_pointer': '/对话/46/内容', 'new_pointer': '/对话/86/内容', 'status': 'exact_row'}]
        groups = preparation.relocate_required(anchors, entries, [[46]])
        self.assertEqual(groups[0][0]['ids'], ['s2-new'])
        with self.assertRaises(ValueError):
            preparation.relocate_required(anchors, [], [[46]])

    def test_changed_server_command_cannot_pass_deployment_identity(self):
        reference = {'model_sha256': 'm', 'server_sha256': 's'}
        service.validate_deployment(['server', '--ctx-size', '16384'],
            ['server', '--ctx-size', '16384'], 'm', 's', reference)
        with self.assertRaisesRegex(ValueError, 'deployment'):
            service.validate_deployment(['server', '--ctx-size', '8192'],
                ['server', '--ctx-size', '16384'], 'm', 's', reference)

    def test_actual_suite_binding_is_frozen_and_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bank, template = root / 'bank.json', root / 'template.json'
            write_json(bank, {'source_snapshot': 'new', 'questions': []})
            write_json(template, {'question_bank_sha256': 'old', 'scenarios': [], 'story_cutoff': 'frozen'})
            bound = artifacts.bind_suite(template, bank, root / 'bound.json')
            self.assertEqual(bound['question_bank_sha256'], file_hash(bank))
            self.assertEqual(read_json(template)['question_bank_sha256'], 'old')
            artifacts.seal(root)
            bank.write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'changed'):
                artifacts.assert_sealed(root)

    def test_model_request_parameters_are_frozen_independently_of_default_profile(self):
        config = artifacts.experimental_config({'base_url': 'http://localhost:8000/v1', 'model': 'm',
            'api_key_env': None, 'profile': 'standard', 'max_tokens': 3072,
            'generation': {'temperature': 1.0}, 'enable_thinking': True})
        self.assertEqual(config['max_tokens'], 1536)
        self.assertEqual(config['temperature'], 0)
        self.assertNotIn('generation', config)
        self.assertNotIn('profile', config)

    def test_real_worker_retains_tool_results_and_records_unexecuted_turns(self):
        config = artifacts.experimental_config({'base_url': 'http://localhost/v1', 'model': 'm', 'api_key_env': None})
        responses = iter([
            {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'one', 'type': 'function',
              'function': {'name': 'search_story', 'arguments': json.dumps({'query': '女士'})}}]},
            {'role': 'assistant', 'content': '女士。[proof]'},
            {'role': 'assistant', 'content': '身份未确认。'},
            {'role': 'assistant', 'content': '来源未确认。'}])
        def transport(endpoint, payload, timeout):
            message = next(responses)
            return {'choices': [{'message': message, 'finish_reason': 'tool_calls' if message.get('tool_calls') else 'stop'}]}
        scene = {'id': 'a06', 'reference_material': [], 'turns': [
            {'content': '谁夺走？'}, {'content': '她身份？'}, {'content': '谁说的？'}]}
        corpus = [{'id': 'proof', 'title': '女士', 'text': '女士夺走。', 'source_file': 'a',
                   'source_pointer': '/x', 'source_kind': 'wiki_excerpt'}]
        with tempfile.TemporaryDirectory() as directory:
            store = artifacts.new_store(Path(directory) / 'A', 'A')
            client = ObservedClient(config, lambda event: store.append('api.jsonl', event), transport)
            row = runtime.run_sample(store, scene, corpus, client, condition='A')
            self.assertEqual(row['execution_status'], 'completed')
            self.assertEqual(row['unexecuted_turns'], [])
            self.assertTrue(all(t['exact_match'] for t in row['transfers']))
            self.assertEqual(row['force_status'], 'succeeded')
            requests = [r for r in read_rows(store.path / 'api.jsonl') if r['event'] == 'request']
            self.assertEqual(len(requests), 4)
            self.assertIn('tool_choice', requests[0]['payload'])
            self.assertNotIn('tool_choice', requests[1]['payload'])


if __name__ == '__main__':
    unittest.main()
