import unittest

from Benchmarks.reports import make_report
from Benchmarks.support.common import RunStore, read_json, summarize
from Benchmarks.support.testing import ReplayHarness


class ReportTests(ReplayHarness, unittest.TestCase):
    def test_missing_conformance_is_not_inferred_from_legacy_correctness(self):
        rows = [{"correct": True}, {"correct": False}, {"conformance_status": "passed"},
                {"conformance_status": "failed"}, {"conformance_status": "not_evaluated"}]
        summary = summarize(rows)
        self.assertEqual(summary["correct"], 1)
        self.assertEqual(summary["incorrect"], 1)
        self.assertEqual(summary.get("conformance"), {"total": 5, "passed": 1, "failed": 1,
                                                     "not_evaluated": 1, "not_recorded": 2})

    def test_new_and_legacy_reports_preserve_sources_and_separate_declarations(self):
        adaptation = {"target": "synthetic-sdk 1.0", "ownership": {"loop": "candidate", "history": "adapter", "recovery": "shared"},
                      "changes": [], "effort_notes": "Synthetic effort declaration"}
        paths = []
        for name, metadata, rows in (
                ("new", {"evaluation_profile": "fixed-history-v0", "adapters": [{"id": "sdk", "adaptation": adaptation}]},
                 [{"adapter_id": "sdk", "correct": True, "conformance_status": "passed"},
                  {"adapter_id": "transport_replay", "correct": True, "conformance_status": "passed", "fixture_only": True}]),
                ("old", {"adapters": [{"id": "legacy"}]}, [{"adapter_id": "legacy", "correct": False}])):
            store = RunStore(self.root / name, {"suite": "core", **metadata})
            for index, row in enumerate(rows):
                store.result({"sample_id": str(index), "execution_status": "completed", **row})
            store.finish("completed")
            paths.append(store.path)
        before = {p: p.read_bytes() for run in paths for p in run.rglob("*") if p.is_file()}
        output = make_report(paths, self.root / "report")
        current, legacy = read_json(output / "summary.json")["runs"]
        self.assertEqual(current.get("evaluation_profile"), "fixed-history-v0")
        self.assertEqual(current["conformance"]["passed"], 2)
        self.assertEqual(current["groups"][0].get("adaptation"), {"status": "declared", "declaration": adaptation})
        self.assertTrue(current["groups"][1]["fixture_only"])
        self.assertEqual(current["groups"][1].get("adaptation"), {"status": "not_recorded"})
        self.assertIsNone(legacy.get("evaluation_profile"))
        self.assertEqual(legacy["incorrect"], 1)
        self.assertEqual(legacy["conformance"]["failed"], 0)
        self.assertEqual(legacy["conformance"]["not_recorded"], 1)
        report = (output / "report.md").read_text(encoding="utf-8")
        for text in ("V0 协议符合性", "历史口径未声明", "未记录", "人工声明", "synthetic-sdk 1.0",
                     "Synthetic effort declaration", "transport_replay", "回放", "声明没有修改默认行为"):
            self.assertIn(text, report)
        self.assertNotIn("Core correct", report)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
