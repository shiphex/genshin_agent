"""The current baseline is immutable; new outputs are isolated and never reused."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from rag.scripts import artifact_catalog as catalog


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'rag/data/corpus').mkdir(parents=True)
        corpus = self.root / 'rag/data/corpus/corpus.jsonl'
        corpus.write_bytes(b'baseline\n')
        self.document = {
            'schema_version': 2, 'baseline_id': 'current-001',
            'datasets': {'full_corpus': {'path': 'rag/data/corpus/corpus.jsonl'}},
            'files': {'rag/data/corpus/corpus.jsonl': {
                'bytes': 9, 'sha256': hashlib.sha256(corpus.read_bytes()).hexdigest()}},
        }
        self.path = self.root / 'rag/catalog.json'
        self.path.write_text(json.dumps(self.document), encoding='utf-8')

    def test_resolves_current_baseline_without_old_version_registry(self):
        self.assertEqual(catalog.dataset_path(self.root, 'full_corpus'), self.root / 'rag/data/corpus/corpus.jsonl')
        self.assertEqual(catalog.check_catalog(self.root)['verified_files'], 1)

    def test_detects_changed_baseline_bytes(self):
        (self.root / 'rag/data/corpus/corpus.jsonl').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash|fingerprint'):
            catalog.check_catalog(self.root)

    def test_parallel_outputs_are_distinct_and_do_not_change_catalog(self):
        before = self.path.read_bytes()
        with ThreadPoolExecutor(max_workers=4) as pool:
            outputs = list(pool.map(lambda _: catalog.reserve_output(self.root, 'retrieval'), range(4)))
        self.assertEqual(len(set(outputs)), 4)
        self.assertTrue(all(p.parent == self.root / 'rag/data/outputs/retrieval' for p in outputs))
        self.assertEqual(self.path.read_bytes(), before)

    def test_rejects_baseline_raw_escape_and_existing_explicit_outputs(self):
        for path in [self.root / 'rag/data/corpus/nested', self.root / 'data/raw/new',
                     self.root / 'rag/data/outputs/retrieval/../../corpus/new']:
            with self.assertRaises(ValueError):
                catalog.reserve_output(self.root, 'retrieval', path)
        existing = catalog.reserve_output(self.root, 'retrieval')
        with self.assertRaises(FileExistsError):
            catalog.reserve_output(self.root, 'retrieval', existing)

    def test_failed_output_reserves_number_and_never_upgrades_acceptance(self):
        output = catalog.reserve_output(self.root, 'model')
        catalog.finish_output(self.root, output, 'failed')
        next_output = catalog.reserve_output(self.root, 'model')
        self.assertEqual(next_output.name, 'r002')
        manifest = json.loads((output / 'run_manifest.json').read_text())
        self.assertEqual(manifest['review_status'], 'not_reviewed')
        with self.assertRaises(ValueError):
            catalog.finish_output(self.root, output, 'completed')

    def test_seals_executed_source_without_config_credentials(self):
        script = self.root / 'rag/scripts/worker.py'
        script.parent.mkdir()
        script.write_bytes(b'print(1)\n')
        config = self.root / 'rag/config.json'
        config.write_text('{"password":"secret-test-value"}')
        output = catalog.reserve_output(self.root, 'model')
        catalog.seal_inputs(self.root, output, [script, config], {'limit': 3})
        catalog.finish_output(self.root, output, 'completed')
        self.assertEqual((output / 'executed_source/worker.py').read_bytes(), script.read_bytes())
        self.assertNotIn('secret-test-value', (output / 'run_manifest.json').read_text())
        self.assertEqual(self.path.read_text(), json.dumps(self.document))

    def test_rejects_catalog_path_traversal(self):
        self.document['datasets']['full_corpus']['path'] = 'rag/../secret'
        self.path.write_text(json.dumps(self.document))
        with self.assertRaises(ValueError):
            catalog.dataset_path(self.root, 'full_corpus')

    def test_cannot_nest_outputs_inside_hf_release_or_partial_release(self):
        release = self.root / 'rag/data/outputs/hf/release'
        (release / 'data').mkdir(parents=True)
        (release / 'data/corpus.jsonl').write_bytes(b'original')
        for with_manifest in (False, True):
            if with_manifest:
                (release / 'manifest.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'existing|nested'):
                catalog.reserve_output(self.root, 'hf', release / 'nested')
            self.assertEqual((release / 'data/corpus.jsonl').read_bytes(), b'original')
            self.assertFalse((release / 'nested').exists())

    def test_review_output_preserves_previous_review_and_current_baseline(self):
        before = self.path.read_bytes()
        output = catalog.reserve_output(self.root, 'review')
        result = output / 'review.json'
        result.write_bytes(b'{"results":[]}\n')
        catalog.finish_output(self.root, output, 'completed')
        following = catalog.reserve_output(self.root, 'review')
        self.assertEqual(output, self.root / 'rag/data/outputs/review/r001')
        self.assertEqual(following.name, 'r002')
        self.assertEqual(result.read_bytes(), b'{"results":[]}\n')
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
