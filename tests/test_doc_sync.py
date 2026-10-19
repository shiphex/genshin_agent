"""Exercise real documentation CLIs against isolated Git repositories."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
BEGIN = '<!-- BEGIN GENERATED: retrieval-cli -->'
END = '<!-- END GENERATED: retrieval-cli -->'


class DocSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True,
                       capture_output=True, timeout=20)
        self.write('scripts/doc-budgets.manifest.json', json.dumps({'README.md': 1000}))
        self.write('README.md', '# Home\n\n[CLI](rag/README.md#cli)\n')
        self.write('rag/README.md', '# CLI\n\n' + BEGIN + '\n' + END + '\nManual tail.\n')
        self.source = self.root / 'rag/scripts/evaluate_retrieval.py'
        self.write('rag/scripts/evaluate_retrieval.py',
                   (PROJECT / 'rag/scripts/evaluate_retrieval.py').read_text(encoding='utf-8'))

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def run_cli(self, script, *args):
        return subprocess.run([sys.executable, '-X', 'utf8', '-B',
                               str(PROJECT / script), '--root', str(self.root), *args],
                              capture_output=True, text=True, encoding='utf-8', timeout=20)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file() and '.git' not in p.parts}

    def generate(self):
        result = self.run_cli('rag/scripts/gen_retrieval_cli.py')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_cli_roundtrip_detects_source_drift_and_regeneration(self):
        self.generate()
        page = (self.root / 'rag/README.md').read_text(encoding='utf-8')
        self.assertIn('| `--top-k` | `int` | `5` |', page)
        self.assertIn('| `--corpus` | `Path` | `None` |', page)
        self.assertTrue(page.endswith('Manual tail.\n'))
        before = self.snapshot()
        result = self.run_cli('rag/scripts/gen_retrieval_cli.py', '--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, self.snapshot())
        # No help text lists this real default: source AST must detect it.
        self.source.write_text(self.source.read_text(encoding='utf-8').replace(
            "'--top-k', type=int, default=5", "'--top-k', type=int, default=7"), encoding='utf-8')
        before = self.snapshot()
        result = self.run_cli('rag/scripts/gen_retrieval_cli.py', '--check')
        self.assertEqual(result.returncode, 1)
        self.assertIn('rag/README.md', result.stderr)
        self.assertEqual(before, self.snapshot())
        self.generate()
        self.assertIn('| `--top-k` | `int` | `7` |',
                      (self.root / 'rag/README.md').read_text(encoding='utf-8'))
        self.assertEqual(self.run_cli('rag/scripts/gen_retrieval_cli.py', '--check').returncode, 0)
        before = self.snapshot()
        self.generate()
        self.assertEqual(before, self.snapshot())

    def test_generated_content_tampering_and_invalid_markers_fail_readonly(self):
        self.generate()
        path = self.root / 'rag/README.md'
        good = path.read_text(encoding='utf-8')
        for case, bad in [('tamper', good.replace('`5`', '`9`')),
                          ('missing', good.replace(END, '')),
                          ('duplicate', good + BEGIN),
                          ('reversed', END + '\n' + BEGIN + '\n')]:
            with self.subTest(case=case):
                path.write_text(bad, encoding='utf-8')
                before = self.snapshot()
                result = self.run_cli('rag/scripts/gen_retrieval_cli.py', '--check')
                self.assertEqual(result.returncode, 1)
                self.assertEqual(before, self.snapshot())

    def test_crlf_checkout_is_fresh_and_generation_preserves_manual_bytes(self):
        self.generate()
        path = self.root / 'rag/README.md'
        path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        before = path.read_bytes()
        result = self.run_cli('rag/scripts/gen_retrieval_cli.py', '--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, path.read_bytes())
        self.source.write_text(self.source.read_text(encoding='utf-8').replace(
            'default=5', 'default=7'), encoding='utf-8')
        self.generate()
        after = path.read_bytes()
        self.assertTrue(after.startswith(b'# CLI\r\n\r\n'))
        self.assertTrue(after.endswith(b'Manual tail.\r\n'))
        self.assertEqual(after.count(b'\n'), after.count(b'\r\n'))

    def test_ast_does_not_import_source_and_rejects_unsupported_definitions(self):
        original = self.source.read_text(encoding='utf-8')
        self.source.write_text("raise RuntimeError('must not execute')\n" + original, encoding='utf-8')
        self.generate()
        for mutation in [original.replace('default=5', 'default=read_default()'),
                         original.replace("type=int, default=5", "type=int, default=5, choices=[3, 5]"),
                         original.replace("parser.add_argument('--top-k'", "other.add_argument('--top-k'")]:
            with self.subTest(mutation=mutation):
                self.source.write_text(mutation, encoding='utf-8')
                result = self.run_cli('rag/scripts/gen_retrieval_cli.py', '--check')
                self.assertEqual(result.returncode, 1)
                self.assertIn('evaluate_retrieval.py', result.stderr)

    def test_links_missing_file_anchor_and_moved_source_fail(self):
        target = self.write('scripts/api.py', '# public API\n')
        self.write('README.md', '[API](scripts/api.py)\n[CLI](rag/README.md#cli)\n')
        self.assertEqual(self.run_cli('scripts/verify_md_links.py').returncode, 0)
        target.rename(target.with_name('moved.py'))
        result = self.run_cli('scripts/verify_md_links.py')
        self.assertEqual(result.returncode, 1)
        self.assertIn('README.md:1', result.stderr)
        self.assertIn('scripts/api.py', result.stderr)
        self.write('README.md', '[broken](rag/README.md#absent)\n')
        result = self.run_cli('scripts/verify_md_links.py')
        self.assertEqual(result.returncode, 1)
        self.assertIn('anchor', result.stderr)

    def test_markdown_links_references_images_and_heading_slugs(self):
        self.write('guide (v0).md', '# 中文 `API` & **默认**\n## Repeat\n## Repeat-1\n## Repeat\n'
                   'Setext\n------\n<a id="Exact"></a>\n')
        self.write('img.svg', '<svg/>')
        self.write('README.md', '# Home\n'
                   '[encoded](guide%20%28v0%29.md?view=1#中文-api--默认)\n'
                   '[balanced](guide%20(v0).md#repeat-2)\n'
                   '[titled](<guide (v0).md> "title")\n'
                   '[setext](<guide (v0).md#セット>)\n'.replace('セット', 'setext') +
                   '[exact][ref]\n[ref]: <guide (v0).md#Exact> "title"\n'
                   '![image](img.svg)\n[Home][]\n[Home]: #home\n'
                   '[Home]\n[external](https://example.invalid/no#missing)\n'
                   '`[sample](missing.py)`\n<!-- [comment](missing.md) -->\n'
                   '~~~md\n[code](missing.md)\n## Fake\n~~~\n')
        result = self.run_cli('scripts/verify_md_links.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write('README.md', '[missing][undefined]\n![broken](missing.png)\n[case](guide%20(v0).md#exact)\n')
        result = self.run_cli('scripts/verify_md_links.py')
        self.assertEqual(result.returncode, 1)
        for value in ['undefined', 'missing.png', '#exact']:
            self.assertIn(value, result.stderr)

    def test_local_data_exemption_is_visible_but_ignored_code_is_not_valid(self):
        self.write('.gitignore', '/data/\n/rag/data/\n/secret.py\n')
        self.write('secret.py', '# present only locally\n')
        self.write('README.md', '[raw](data/raw/absent.json)\n[local](rag/data/review20/summary.md#old)\n')
        before = self.snapshot()
        result = self.run_cli('scripts/verify_md_links.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('LOCAL', result.stdout)
        self.assertEqual(before, self.snapshot())
        self.write('README.md', '[ignored](secret.py)\n[typo](rag/typo.py)\n[out](../outside.md)\n')
        result = self.run_cli('scripts/verify_md_links.py')
        self.assertEqual(result.returncode, 1)
        for value in ['secret.py', 'rag/typo.py', '../outside.md']:
            self.assertIn(value, result.stderr)

    def test_repository_and_local_data_directory_roots_are_valid(self):
        self.write('README.md', '[root](.)\n[root2](./)\n[data](data/)\n[ragdata](rag/data/)\n')
        result = self.run_cli('scripts/verify_md_links.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('LOCAL'), 2)

    def test_rendered_heading_emphasis_references_and_link_titles(self):
        self.write('api.md', '# _API_\n## __Fields__\n## [Usage][ref]\n'
                   '## `_code_`\n[ref]: api.md\n')
        self.write('README.md', '[API](api.md#api "Example [literal](missing.md)")\n'
                   '[fields](api.md#fields)\n[usage](api.md#usage)\n'
                   '[code](api.md#_code_)\n')
        result = self.run_cli('scripts/verify_md_links.py')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_new_docs_are_discovered_and_frozen_sources_are_explicit(self):
        self.write('docs/new.md', '[broken](missing.py)\n')
        result = self.run_cli('scripts/verify_md_links.py')
        self.assertEqual(result.returncode, 1)
        self.assertIn('docs/new.md:1', result.stderr)
        (self.root / 'docs/new.md').unlink()
        frozen = 'rag/docs/recovery/crawler_handoff.md'
        self.write(frozen, '[old](obsolete.md)\n')
        result = self.run_cli('scripts/verify_md_links.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('FROZEN', result.stdout)
        self.write('README.md', f'[frozen]({frozen}#absent)\n')
        self.assertEqual(self.run_cli('scripts/verify_md_links.py').returncode, 1)

    def test_aggregate_passes_without_data_and_propagates_each_failure_readonly(self):
        self.generate()
        before = self.snapshot()
        result = self.run_cli('scripts/doc_sync.py')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, self.snapshot())
        cases = [('README.md', '[bad](missing.py)\n', 'markdown-links'),
                 ('README.md', 'word ' * 1001, 'doc-budgets'),
                 ('rag/README.md', '# CLI\n' + BEGIN + '\nold\n' + END, 'retrieval-cli')]
        for path, content, gate in cases:
            with self.subTest(gate=gate):
                original = (self.root / path).read_bytes()
                self.write(path, content)
                before = self.snapshot()
                result = self.run_cli('scripts/doc_sync.py')
                self.assertEqual(result.returncode, 1)
                self.assertIn('FAIL ' + gate, result.stdout)
                self.assertEqual(before, self.snapshot())
                (self.root / path).write_bytes(original)


if __name__ == '__main__':
    unittest.main()
