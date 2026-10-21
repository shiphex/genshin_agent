"""The public dispatcher must preserve ownership and run identity after a move."""
import ast
from pathlib import Path
import unittest

from Benchmarks.support.common import BENCH, ROOT, output_path, provenance


class LayoutTests(unittest.TestCase):
    def test_default_outputs_have_category_and_purpose(self):
        for purpose, category in (("core", "agent_core"), ("perf", "agent_core"),
                                  ("agent", "agent_story"), ("review", "agent_story"),
                                  ("preflight", "agent_story")):
            self.assertEqual(output_path(purpose, category=category).parent, BENCH / "outputs" / category / purpose)
        self.assertEqual(output_path("reports").parent, BENCH / "outputs/reports")

    def test_provenance_records_owner_shared_and_root_configuration(self):
        files = provenance(implementation=BENCH / "agent_core")["files"]
        for name in ("pyproject.toml", "uv.lock", ".python-version",
                     "Benchmarks/agent_core/runner.py", "Benchmarks/support/protocol.py",
                     "Benchmarks/__main__.py"):
            self.assertIn(name, files)
        self.assertNotIn("Benchmarks/agent_story/providers.py", files)
        self.assertEqual(ROOT, BENCH.parent)

    def test_support_has_no_category_imports(self):
        for path in (BENCH / "support").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse(any(part in {"agent_core", "agent_story"}
                                         for part in (node.module or "").split(".")), path)


if __name__ == "__main__":
    unittest.main()
