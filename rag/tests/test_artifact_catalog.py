"""Run identities preserve history and keep execution separate from acceptance."""
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'rag').mkdir()
        self.document = {
            'schema_version': 1,
            'experiments': {'model_comparison': {'state': 'frozen', 'inputs': {'questions': 'rag/input.json'}}},
            'runs': {'model_comparison/r001': {'experiment_id': 'model_comparison', 'run_id': 'r001',
                     'legacy_id': 'old-date-id', 'artifacts': 'rag/data/old',
                     'report': 'rag/reports/model_comparison/r001', 'execution_status': 'completed',
                     'review_status': 'not_reviewed', 'publication_status': 'pending_upload'}},
            'reviews': {}, 'datasets': {},
        }
        self.write(self.document)
        self.module = importlib.import_module('rag.scripts.artifact_catalog')

    def write(self, doc):
        (self.root / 'rag/catalog.json').write_text(json.dumps(doc), encoding='utf-8')

    def test_run_allocation_skips_history_and_unregistered_output_without_overwriting(self):
        orphan = self.root / 'rag/data/runs/model_comparison/r002'
        orphan.mkdir(parents=True)
        (orphan / 'answer.txt').write_text('unique output')
        key, output = self.module.reserve_run(self.root, 'model_comparison')
        self.assertEqual(key, 'model_comparison/r003')
        self.assertEqual(output, self.root / 'rag/data/runs/model_comparison/r003')
        self.assertEqual((orphan / 'answer.txt').read_text(), 'unique output')
        self.assertEqual(self.module.load_catalog(self.root)['runs']['model_comparison/r001'], self.document['runs']['model_comparison/r001'])

    def test_existing_explicit_output_is_rejected_without_registry_or_file_changes(self):
        existing = self.root / 'rag/data/kept'
        existing.mkdir(parents=True)
        (existing / 'answer.txt').write_text('original')
        before = (self.root / 'rag/catalog.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.module.reserve_run(self.root, 'model_comparison', existing)
        self.assertEqual((self.root / 'rag/catalog.json').read_bytes(), before)
        self.assertEqual((existing / 'answer.txt').read_text(), 'original')

    def test_parallel_reservations_receive_distinct_numbers(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.module.reserve_run(self.root, 'model_comparison'), range(4)))
        self.assertEqual(len({key for key, _ in results}), 4)
        self.assertEqual(len(self.module.load_catalog(self.root)['runs']), 5)

    def test_failed_and_interrupted_runs_keep_numbers_and_do_not_mark_review_passed(self):
        key, _ = self.module.reserve_run(self.root, 'model_comparison')
        self.module.finish_run(self.root, key, 'failed')
        key2, _ = self.module.reserve_run(self.root, 'model_comparison')
        self.module.finish_run(self.root, key2, 'interrupted')
        key3, _ = self.module.reserve_run(self.root, 'model_comparison')
        self.assertEqual(key3, 'model_comparison/r004')
        catalog = self.module.load_catalog(self.root)
        self.assertEqual(catalog['runs'][key]['review_status'], 'not_reviewed')
        self.assertEqual(catalog['runs'][key2]['publication_status'], 'not_published')
        with self.assertRaises(ValueError):
            self.module.finish_run(self.root, key, 'running')

    def test_input_manifest_stores_fingerprints_without_copying_secrets(self):
        source = self.root / 'rag/input.json'
        source.write_text('{"api_key":"private-value","question":"source"}')
        runner = self.root / 'rag/scripts/runner.py'
        runner.parent.mkdir()
        runner.write_bytes(b'print("executed source")\n')
        key, output = self.module.reserve_run(self.root, 'model_comparison')
        self.module.seal_inputs(self.root, key, [source, runner], {'limit': 1})
        text = (output / 'run_manifest.json').read_text()
        self.assertNotIn('private-value', text)
        manifest = json.loads(text)
        self.assertEqual(manifest['inputs'][0]['path'], 'rag/input.json')
        self.assertEqual(len(manifest['inputs'][0]['sha256']), 64)
        self.assertEqual(manifest['parameters']['limit'], 1)
        self.assertEqual((output / 'executed_source/rag/scripts/runner.py').read_bytes(), runner.read_bytes())

    def test_legacy_alias_resolves_report_without_changing_frozen_id(self):
        self.assertEqual(self.module.report_directory(self.root, 'old-date-id'), 'rag/reports/model_comparison/r001')
        with self.assertRaises(ValueError):
            self.module.report_directory(self.root, 'unknown-date-id')
        doc = self.module.load_catalog(self.root)
        doc['runs']['model_comparison/r002'] = dict(doc['runs']['model_comparison/r001'], run_id='r002')
        self.write(doc)
        with self.assertRaises(ValueError):
            self.module.report_directory(self.root, 'old-date-id')

    def test_invalid_id_and_paths_cannot_write_outside_local_data(self):
        for experiment in ('../raw', 'unknown', 'model_comparison/extra'):
            with self.assertRaises(ValueError):
                self.module.reserve_run(self.root, experiment)
        with self.assertRaises(ValueError):
            self.module.reserve_run(self.root, 'model_comparison', self.root / 'rag/input')
        with self.assertRaises(ValueError):
            self.module.reserve_run(self.root, 'model_comparison', self.root / 'rag/data/loose-output')
        self.document['runs']['model_comparison/r001']['report'] = '../outside'
        self.write(self.document)
        with self.assertRaises(ValueError):
            self.module.report_directory(self.root, 'old-date-id')

    def test_legacy_absolute_data_paths_use_longest_prefix_without_editing_records(self):
        self.document['legacy_paths'] = {
            'rag/data/full/snapshot': 'rag/data/corpora/story_full/v1',
            'rag/data/full/snapshot/retrieval': 'rag/data/runs/full_retrieval/r001'}
        self.write(self.document)
        old = r'E:\old\project\rag\data\full\snapshot\retrieval\results.jsonl'
        self.assertEqual(self.module.resolve_data_path(self.root, old),
                         self.root / 'rag/data/runs/full_retrieval/r001/results.jsonl')
        self.assertEqual(self.module.resolve_data_path(self.root, 'rag/data/full/snapshot/corpus.jsonl'),
                         self.root / 'rag/data/corpora/story_full/v1/corpus.jsonl')
        self.assertEqual(old, r'E:\old\project\rag\data\full\snapshot\retrieval\results.jsonl')
        for invalid in ('../../secret', 'C:/private/secret', 'rag/data/../secret', 'C:/drag/data/private'):
            with self.assertRaises(ValueError):
                self.module.resolve_data_path(self.root, invalid)

    def test_failed_corpus_build_does_not_replace_current_version_or_reuse_number(self):
        self.document['datasets']['full_corpus'] = {'kind': 'corpus', 'resource_id': 'story_full',
            'version': 'v1', 'path': 'rag/data/corpora/story_full/v1/corpus.jsonl'}
        self.write(self.document)
        version, output = self.module.reserve_corpus(self.root, 'full_corpus')
        self.assertEqual(version, 'v2')
        self.module.finish_corpus(self.root, 'full_corpus', version, 'failed')
        self.assertEqual(self.module.load_catalog(self.root)['datasets']['full_corpus']['version'], 'v1')
        version2, _ = self.module.reserve_corpus(self.root, 'full_corpus')
        self.assertEqual(version2, 'v3')
        before = (self.root / 'rag/catalog.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.module.reserve_corpus(self.root, 'full_corpus', output)
        self.assertEqual((self.root / 'rag/catalog.json').read_bytes(), before)

    def test_prepared_copies_are_numbered_per_dataset_version_and_never_overwritten(self):
        self.document['datasets']['story_dev'] = {'kind': 'question_set', 'path': 'rag/input.json', 'version': '0.5'}
        self.write(self.document)
        key, output = self.module.reserve_prepared(self.root, 'story_dev', '0.5')
        self.assertEqual(key, 'story_dev/v0.5/r001')
        self.assertEqual(output, self.root / 'rag/data/prepared/story_dev/v0.5/r001/questions.json')
        output.write_text('unique prepared text')
        self.module.finish_prepared(self.root, key, 'completed')
        self.assertEqual(self.module.load_catalog(self.root)['datasets']['story_dev']['prepared_current'], key)
        key2, _ = self.module.reserve_prepared(self.root, 'story_dev', '0.5')
        self.assertEqual(key2, 'story_dev/v0.5/r002')
        self.module.finish_prepared(self.root, key2, 'failed')
        self.assertEqual(self.module.load_catalog(self.root)['datasets']['story_dev']['prepared_current'], key)
        before = (self.root / 'rag/catalog.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.module.reserve_prepared(self.root, 'story_dev', '0.5', output)
        self.assertEqual((self.root / 'rag/catalog.json').read_bytes(), before)
        self.assertEqual(output.read_text(), 'unique prepared text')

    def test_prepare_cli_builds_a_new_version_and_preserves_existing_corpus(self):
        from rag.scripts import prepare_rag_mvp as prepare, evaluate_rag_mvp as evaluate
        raw = self.root / 'data/raw/snapshot'
        source = raw / 'parsed/weapons/a.json'
        source.parent.mkdir(parents=True)
        source.write_text(json.dumps({'名称': '石锁', '故事': '古老的故事。'}, ensure_ascii=False), encoding='utf-8')
        (raw / 'pages').mkdir()
        (raw / 'pages/a.json').write_text(json.dumps({'query': {'pages': {'1': {
            'pageid': 1, 'ns': 0, 'title': '石锁', 'revisions': [{'slots': {'main': {'*': '{{武器}}'}}}]}}}}), encoding='utf-8')
        selection = self.root / 'selection.json'
        selection.write_text(json.dumps({'entries': [{'id': 'l01', 'source_file': 'parsed/weapons/a.json', 'source_pointer': ['/故事']}]}))
        original = self.root / 'rag/data/corpora/story_sample/v1/corpus.jsonl'
        original.parent.mkdir(parents=True)
        original.write_bytes(b'original corpus')
        self.document['datasets']['sample_corpus'] = {'kind': 'corpus', 'resource_id': 'story_sample', 'version': 'v1',
                                                     'path': original.relative_to(self.root).as_posix()}
        self.write(self.document)
        with patch.object(prepare, 'PROJECT', self.root), patch.object(prepare, 'RAG_ROOT', self.root / 'rag'), \
             patch.object(prepare, 'DEFAULT_OUTPUT', self.root / 'rag/data/mvp'), \
             patch.object(evaluate, 'PROJECT', self.root), patch.object(evaluate, 'RAG_ROOT', self.root / 'rag'), \
             patch('sys.argv', ['prepare', '--raw-root', str(raw), '--selection', str(selection)]):
            self.assertEqual(prepare.main(), 0)
        self.assertEqual(original.read_bytes(), b'original corpus')
        new = self.root / 'rag/data/corpora/story_sample/v2/corpus.jsonl'
        self.assertTrue(new.is_file())
        self.assertEqual(json.loads(new.read_text(encoding='utf-8'))['id'], 'l01')
        self.assertEqual(self.module.load_catalog(self.root)['datasets']['sample_corpus']['version'], 'v2')
        self.assertEqual(self.module.load_catalog(self.root)['datasets']['sample_corpus']['manifest'],
                         (new.parent / 'corpus_manifest.json').relative_to(self.root).as_posix())


if __name__ == '__main__':
    unittest.main()
