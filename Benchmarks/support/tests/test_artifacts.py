import json
from pathlib import Path
import tempfile
import unittest
from Benchmarks.support.common import RunStore, digest, summarize


class ArtifactTests(unittest.TestCase):
    def test_runs_are_exclusive_and_completed_records_survive_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            store = RunStore(output, {"suite": "core"})
            store.result({"sample_id": "s1", "execution_status": "completed"})
            store.finish("failed", "deliberate")
            with self.assertRaises(FileExistsError):
                RunStore(output, {})
            self.assertEqual(len((output / "results.jsonl").read_text().splitlines()), 1)
            self.assertEqual(json.loads((output / "manifest.json").read_text())["status"], "failed")

    def test_summary_keeps_failures_and_unjudged_in_denominator(self):
        rows = [{"execution_status": "completed", "correct": True, "elapsed_ms": 1},
                {"execution_status": "failed", "correct": False, "elapsed_ms": 9},
                {"execution_status": "completed", "correct": None, "elapsed_ms": 3}]
        summary = summarize(rows)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["correct"], 1)
        self.assertEqual(summary["unjudged"], 1)
        self.assertEqual(summary["elapsed_ms"]["median"], 3)
        self.assertNotEqual(digest(rows), digest(list(reversed(rows))))

    def test_interrupted_schedule_keeps_unstarted_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RunStore(Path(tmp) / "run", {"planned_samples": [{"sample_id": "one"}, {"sample_id": "two"}]})
            store.result({"sample_id": "one", "execution_status": "completed", "correct": True})
            store.finish("interrupted")
            rows = [json.loads(line) for line in (store.path / "results.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["execution_status"], "not_started")
