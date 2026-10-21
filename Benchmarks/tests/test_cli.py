"""The CLI must work offline and reject unsafe outputs before execution."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Benchmarks.__main__ import main
from Benchmarks.support.common import file_hash, read_json, read_rows, write_json
from Benchmarks.support.testing import FIXTURE, POLICY
from Benchmarks.agent_core.cases import CASES
from Benchmarks.agent_core.tapes import core_tape


class CliTests(unittest.TestCase):
    def test_dispatch_writes_new_layout_and_root_config_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            tape = base / "tape.json"
            write_json(tape, {"c01": core_tape(CASES[0], POLICY)})
            adapters = base / "adapters.json"
            write_json(adapters, {"adapters": [{"id": "fixture", "command": ["{python}", "-B", str(FIXTURE), "--tape", str(tape)],
                "policies": POLICY, "fixture_only": True,
                "identity": {"revision": "test", "files": [str(FIXTURE), str(tape)]}}]})
            with patch("Benchmarks.support.common.BENCH", base), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["core", "--adapters", str(adapters), "--case", "c01"]), 0)
            run, = (base / "outputs/agent_core/core").iterdir()
            manifest = read_json(run / "manifest.json")
            self.assertEqual(manifest["layout_version"], 2)
            self.assertTrue(read_rows(run / "results.jsonl")[0]["correct"])
            for name in ("pyproject.toml", "uv.lock", ".python-version"):
                sha = manifest["provenance"]["files"][name]
                self.assertEqual(file_hash(run / "sources" / (sha + "-" + name)), sha)

    def test_list_exposes_all_cases_without_reading_model_config(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["list"]), 0)
        self.assertIn('"core_cases": 15', output.getvalue())
        self.assertIn('"agent_scenarios": 16', output.getvalue())

    def test_core_rejects_output_outside_outputs_before_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["core", "--adapters", "missing.json", "--output", tmp]), 2)
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
