"""验证文档计数与真实 CLI 的接受、拒绝及只读行为。"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/verify_doc_budgets.py'


class BudgetTests(unittest.TestCase):
    def run_gate(self, root, *args):
        return subprocess.run([sys.executable, '-X', 'utf8', '-B', str(SCRIPT),
                               '--root', str(root), *args], capture_output=True, text=True,
                              encoding='utf-8')

    def fixture(self, root, text='中文 Python 3.11', limit=5):
        (root / 'scripts').mkdir()
        (root / 'page.md').write_text(text, encoding='utf-8')
        manifest = root / 'scripts/doc-budgets.manifest.json'
        manifest.write_text(json.dumps({'page.md': limit}), encoding='utf-8')
        return manifest

    def test_count_chinese_english_mixed_and_supplementary_han(self):
        self.assertTrue(SCRIPT.is_file(), '缺少预算检查器')
        spec = importlib.util.spec_from_file_location('doc_budgets', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for text, expected in [('中文', 2), ('RAG模块', 3), ('Python 3.11', 3),
                               ('foo_bar 123', 2), ('𠀀', 1), ('，。 # * 😀', 0),
                               ('```py\nprint("你好")\n```', 4),
                               ('[说明](docs/usage.md)', 5)]:
            with self.subTest(text=text):
                self.assertEqual(module.count_units(text), expected)

    def test_cli_boundary_and_overflow_without_rewriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.fixture(root)
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result = self.run_gate(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('5 / 5', result.stdout)
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
            manifest.write_text('{"page.md": 4}', encoding='utf-8')
            result = self.run_gate(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn('page.md', result.stdout)
            self.assertIn('超限', result.stdout)
            listed = self.run_gate(root, '--list')
            self.assertEqual(listed.returncode, 0)
            self.assertIn('余量 -1', listed.stdout)

    def test_missing_file_and_invalid_budgets_are_rejected_even_when_listing(self):
        for value in [0, -1, True, '10', 2.5]:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root, limit=value)
                for flags in [(), ('--list',)]:
                    result = self.run_gate(root, *flags)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn('预算', result.stderr)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / 'page.md').unlink()
            result = self.run_gate(root, '--list')
            self.assertEqual(result.returncode, 1)
            self.assertIn('缺失', result.stderr)

    def test_malformed_empty_duplicate_and_outside_manifest_are_rejected(self):
        for document in ['{', '[]', '{}', '{"page.md": 5, "page.md": 6}',
                         '{"../outside.md": 10}']:
            with self.subTest(document=document), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = self.fixture(root)
                manifest.write_text(document, encoding='utf-8')
                result = self.run_gate(root)
                self.assertEqual(result.returncode, 1)
                self.assertTrue(result.stderr.strip())


if __name__ == '__main__':
    unittest.main()
