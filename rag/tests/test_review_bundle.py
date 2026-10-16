"""Publication must preserve answers and reject unsafe or corrupted archives."""
import importlib.util
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/export_review_bundle.py'


class PublicationTests(unittest.TestCase):
    def exporter(self):
        self.assertTrue(SCRIPT.exists(), 'publication exporter missing')
        spec = importlib.util.spec_from_file_location('review_export', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_answer_roundtrip_preserves_wrong_citations_and_truncation(self):
        m = self.exporter()
        text = 'wrong [f123]\n```\n trailing  \n'
        rendered = m.answer_block({'text': text, 'status': 'truncated', 'finish_reason': 'length'})
        self.assertEqual(m.extract_blocks(rendered, 'answer'), [text])
        self.assertIn('length', rendered)

    def test_archive_rejects_traversal_before_writing(self):
        m = self.exporter()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            for bad in ('../escape', '/absolute', 'C:/escape', 'a\\..\\escape'):
                archive = p / 'bad.zip'
                with zipfile.ZipFile(archive, 'w') as z:
                    z.writestr(bad, 'evil')
                with self.assertRaises(ValueError):
                    m.verify_archive(archive, p / 'restored')
                self.assertFalse((p / 'restored').exists())

    def test_archive_hash_mismatch_rejected(self):
        m = self.exporter()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.zip'
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr('a.txt', 'changed')
                z.writestr('bundle_manifest.json', json.dumps({'files': [{'path': 'a.txt', 'sha256': '0' * 64, 'bytes': 7}]}))
            with self.assertRaises(ValueError):
                m.verify_archive(p)

    def test_unknown_data_and_secrets_not_selected(self):
        m = self.exporter()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('data/raw/genshin_wiki_data_20260605/parsed/a.json',
                         'rag/data/full/genshin_wiki_data_20260605/corpus.jsonl',
                         'rag/data/full_validation/20261010_105700/.env',
                         'rag/data/full_validation/20261010_105700/__pycache__/a.pyc',
                         'rag/data/unapproved/a.json'):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('{}', encoding='utf-8')
            selected = m.data_files(root, full=True)
            self.assertEqual(len(selected), 2)
            self.assertTrue(all('.env' not in str(p) and '__pycache__' not in str(p) for p in selected))

    def test_published_bytes_use_lf_to_match_git_tree_hashes(self):
        m = self.exporter()
        self.assertTrue(hasattr(m, 'write_utf8'), 'deterministic publication writer missing')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'case.md'
            m.write_utf8(path, 'answer\nwrong citation [f123]\n')
            self.assertEqual(path.read_bytes(), b'answer\nwrong citation [f123]\n')

    def test_old_absolute_inputs_resolve_under_a_new_checkout(self):
        m = self.exporter()
        self.assertTrue(hasattr(m, 'historical_relative'), 'portable historical input mapping missing')
        rel = 'rag/experiments/generation_diagnosis/cases.jsonl'
        for old in ('E:\\old\\genshin_agent\\' + rel.replace('/', '\\'), '/different/checkout/' + rel, rel):
            self.assertEqual(m.historical_relative(old), rel)
        with self.assertRaises(ValueError):
            m.historical_relative('C:/personal/secret.json')

    def test_archive_rejects_windows_aliases_and_device_names(self):
        m = self.exporter()
        with tempfile.TemporaryDirectory() as tmp:
            for names in (('A.txt', 'a.txt'), ('CON.txt',), ('dir /a.txt',), ('a.txt.',)):
                with self.subTest(names=names):
                    archive = Path(tmp) / 'unsafe.zip'
                    entries = []
                    with zipfile.ZipFile(archive, 'w') as z:
                        for name in names:
                            z.writestr(name, b'x')
                            entries.append({'path': name, 'sha256': hashlib.sha256(b'x').hexdigest(), 'bytes': 1})
                        z.writestr('bundle_manifest.json', json.dumps({'files': entries}))
                    with self.assertRaises(ValueError):
                        m.verify_archive(archive)

    def test_bundle_output_cannot_nest_in_original_experiments(self):
        m = self.exporter()
        self.assertTrue(hasattr(m, 'validate_bundle_output'), 'historical output protection missing')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in (m.FULL_RUN, m.DIAG_RUN, 'rag/data/mvp', 'rag/data/full/genshin_wiki_data_20260605'):
                with self.assertRaises(ValueError):
                    m.validate_bundle_output(root, root / rel / 'publish')
            m.validate_bundle_output(root, root / 'rag/data/releases/review/v4')

    def test_compact_excerpt_is_exact_and_rejects_changed_answer(self):
        m = self.exporter()
        self.assertTrue(hasattr(m, 'checked_excerpt'), 'compact excerpt verifier missing')
        original = 'before\nwrong [f123]  \nafter'
        quote = 'wrong [f123]  '
        selection = {'start': 7, 'end': 7 + len(quote), 'sha256': hashlib.sha256(quote.encode()).hexdigest()}
        self.assertEqual(m.checked_excerpt(original, selection), quote)
        with self.assertRaises(ValueError):
            m.checked_excerpt(original.replace('f123', 'f456'), selection)

    def test_compact_view_preserves_conditions_status_and_only_selected_text(self):
        m = self.exporter()
        self.assertTrue(hasattr(m, 'render_compact_case'), 'compact renderer missing')
        text = 'unselected long context\nwrong [f123]\nunselected ending'
        quote = 'wrong [f123]'
        calls = [{'condition': 'baseline', 'seed': 42,
                  'answer': {'text': text, 'status': 'truncated', 'finish_reason': 'length', 'citation_audit': {'has_citations': True, 'unknown_ids': ['f123']}},
                  'excerpt': {'start': text.index(quote), 'end': text.index(quote) + len(quote), 'sha256': hashlib.sha256(quote.encode()).hexdigest()},
                  'review': {'notes': 'Initial review, pending acceptance'}}]
        page = m.render_compact_case('q', 'question', calls, [])
        self.assertEqual(m.extract_blocks(page, 'excerpt'), [quote])
        self.assertIn('length', page)
        self.assertIn('baseline', page)
        self.assertIn('42', page)
        self.assertNotIn('unselected long context', page)
        self.assertNotIn('"source_spans"', page)

    def test_compact_diagnosis_cannot_drop_a_seed(self):
        m = self.exporter()
        self.assertTrue(hasattr(m, 'validate_compact_matrix'), 'compact matrix validator missing')
        rows = [{'condition': c, 'seed': s} for c in ('R0', 'C0', 'R1', 'C1') for s in ((42,) if c.endswith('0') else (42, 43, 44))]
        m.validate_compact_matrix(rows, diagnosis=True)
        with self.assertRaises(ValueError):
            m.validate_compact_matrix(rows[:-1], diagnosis=True)

    def test_compact_reference_cannot_mislabel_source_kind_or_pointer(self):
        m = self.exporter()
        self.assertTrue(hasattr(m, 'validate_reference'), 'compact provenance validator missing')
        row = {'id': 'e1', 'source_file': 'parsed/a.json', 'source_kind': 'wiki_compilation',
               'source_pointer': ['/text'], 'source_spans': [{'start': 0, 'end': 20}]}
        ref = {'source_id': 'e1', 'source_file': 'parsed/a.json', 'source_kind': 'wiki_compilation', 'pointer': '/text', 'start': 1, 'end': 10}
        m.validate_reference(ref, row)
        for change in ({'source_kind': 'wiki_excerpt'}, {'pointer': '/unrelated'}, {'source_id': 'wrong'}):
            with self.assertRaises(ValueError):
                m.validate_reference(dict(ref, **change), row)

    def test_git_checkout_keeps_publication_lf_with_autocrlf_enabled(self):
        attrs = SCRIPT.parents[2] / '.gitattributes'
        self.assertTrue(attrs.exists(), 'publication Git EOL policy missing')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                subprocess.run(['git', '-C', str(root), '-c', 'core.autocrlf=true',
                                '-c', 'user.name=Publication test', '-c', 'user.email=test@example.invalid',
                                *args], check=True, capture_output=True)
            git('init', '--quiet')
            (root / '.gitattributes').write_bytes(attrs.read_bytes())
            paths = ['rag/reports/full_validation_20261010_105700/cases/q01.md',
                     'rag/reports/manifest.json', 'rag/reports/inputs/excerpts_v3.json']
            for rel in paths:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'original\nsecond line\n')
            git('add', '.')
            git('commit', '--quiet', '-m', 'fixture')
            for rel in paths:
                (root / rel).unlink()
            git('checkout', '--', *paths)
            for rel in paths:
                self.assertEqual((root / rel).read_bytes(), b'original\nsecond line\n')

    def test_speaker_label_must_match_original_parent_record(self):
        m = self.exporter()
        self.assertTrue(hasattr(m, 'validate_speaker'), 'source speaker validator missing')
        m.validate_speaker({'speaker': 'Zhongli'}, {'角色': 'Zhongli'})
        with self.assertRaises(ValueError):
            m.validate_speaker({'speaker': 'Paimon'}, {'角色': 'Zhongli'})

    def test_report_location_uses_catalog_but_preserves_old_package_layout(self):
        m = self.exporter()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = 'full_validation_20261010_105700'
            self.assertEqual(m.report_case_path(root, legacy, 'q01'),
                             root / 'rag/reports' / legacy / 'cases/q01.md')
            (root / 'rag').mkdir()
            catalog = {'schema_version': 1, 'datasets': {}, 'experiments': {}, 'reviews': {},
                       'runs': {'model_comparison/r001': {'legacy_id': legacy, 'report': 'rag/reports/model_comparison/r001'}}}
            (root / 'rag/catalog.json').write_text(json.dumps(catalog), encoding='utf-8')
            self.assertEqual(m.report_case_path(root, legacy, 'q01'),
                             root / 'rag/reports/model_comparison/r001/cases/q01.md')
            with self.assertRaises(ValueError):
                m.report_case_path(root, 'unknown', 'q01')


if __name__ == '__main__':
    unittest.main()
