from pathlib import Path
import tempfile
import unittest

from Benchmarks.support.common import ROOT, read_json, write_json, encoded, file_hash
from rag.scripts.full_corpus import Extractor
from probes.structured_rag_validation.preparation import prepare, load_run, execution_sources
from probes.structured_rag_validation.artifacts import new_store, seal


class PreparationTests(unittest.TestCase):
    def test_postprocessing_uses_archived_execution_code_without_relaxing_live_source_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'execution.py'; source.write_text('original', encoding='utf-8')
            store = new_store(root / 'run', 'inputs', paths=[source])
            store.finish('completed'); seal(store.path)
            source.write_text('postprocessing revision', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'execution source changed'):
                execution_sources(store.path, require_current=True)
            status = execution_sources(store.path, require_current=False)
            self.assertIn(str(source), status['changed_sources'])
            archived = store.path / 'sources' / (next(
                sha for name, sha in store.manifest['provenance']['files'].items() if name == str(source)) + '-execution.py')
            archived.write_text('tampered', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'archive'):
                execution_sources(store.path, require_current=False)

    def test_prepared_suite_loads_and_changed_private_endpoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            raw = project / 'data/raw/new-snapshot'
            raw.mkdir(parents=True)
            source_file = 'parsed/archon-quests/source.json'
            (raw / source_file).parent.mkdir(parents=True)
            document = {'对话': [{'类型': 'character', '说话者': '甲', '内容': f'原文{i}',
                                '所属任务流程': '步骤'} for i in range(100)]}
            write_json(raw / source_file, document)
            extractor = Extractor(document, source_file, 'archon-quests', '标题', 800,
                                  snapshot='new-snapshot', source_sha256=file_hash(raw / source_file))
            extractor.run()
            corpus = project / 'corpus.jsonl'
            corpus.write_text(''.join(encoded(r) + '\n' for r in extractor.records), encoding='utf-8')
            bank = read_json(ROOT / 'rag/eval/questions.json')
            bank['source_snapshot'] = 'new-snapshot'
            for q in bank['questions']:
                q['sources'] = [{'file': source_file, 'pointer': f'/对话/{i}/内容'} for i in (86, 87, 91)]
            original = project / 'rag/eval/questions.json'
            original.parent.mkdir(parents=True)
            write_json(original, bank)
            questions = project / 'questions.json'; write_json(questions, bank)
            write_json(project / 'migration_report.json', {'entries': [
                {'question_id': 'gq2-001', 'input': 'questions.json', 'file': source_file,
                 'old_pointer': f'/对话/{old}/内容', 'new_pointer': f'/对话/{new}/内容', 'status': 'exact_row'}
                for old, new in ((46, 86), (47, 87), (50, 91))]})
            write_json(project / 'rag/catalog.json', {'files': {}})
            config = project / 'config.json'
            write_json(config, {'base_url': 'http://127.0.0.1:8000/v1', 'model': 'm'})
            private = project / 'config.local.json'
            write_json(private, {'base_url': 'http://127.0.0.1:8001/v1'})
            output = project / 'run'
            prepare(project, output, config=config, corpus=corpus, questions=questions, raw_root=raw)
            binding, scenes, materials = load_run(output)
            self.assertEqual(set(scenes), {'a06', 'a07', 'a10', 'a11'})
            self.assertEqual(binding['model_config']['base_url'], 'http://127.0.0.1:8001/v1')
            self.assertIn(str(private.resolve()), binding['input_hashes'])
            write_json(private, {'base_url': 'http://127.0.0.1:8002/v1'})
            with self.assertRaisesRegex(ValueError, 'fingerprint changed'):
                load_run(output)


if __name__ == '__main__':
    unittest.main()
