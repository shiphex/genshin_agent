import unittest
from Benchmarks.support.common import read_json, read_rows
from Benchmarks.support.testing import POLICY, ReplayHarness
from Benchmarks.agent_core.runner import run_core, run_perf
from Benchmarks.agent_core.cases import CASES
from Benchmarks.agent_core.tapes import core_tape


class RunnerTests(ReplayHarness, unittest.TestCase):
    def test_core_run_saves_all_cases_and_trace(self):
        adapter = self.adapter({c["id"]: core_tape(c, POLICY) for c in CASES})
        path = run_core([adapter], self.root / "core")
        rows = read_rows(path / "results.jsonl")
        self.assertEqual(len(rows), 15)
        self.assertTrue(all(r["correct"] for r in rows))
        self.assertTrue(read_rows(path / "trace.jsonl"))
        self.assertEqual(read_json(path / "manifest.json")["status"], "completed")

    def test_performance_records_alternation_baseline_and_all_rounds(self):
        tape = core_tape(CASES[-1], POLICY) * 4
        adapters = [self.adapter(tape, "A"), self.adapter(tape, "B")]
        path = run_perf(adapters, self.root / "perf", rounds=2, batch=2, warmup=1)
        rows = read_rows(path / "results.jsonl")
        self.assertEqual(len(rows), 6)
        self.assertEqual([r["adapter_id"] for r in rows if not r["is_baseline"]], ["A", "B", "B", "A"])
        self.assertTrue(all(r["correct"] for r in rows))
        self.assertTrue(all(len(r["iterations_ms"]) == 2 for r in rows))
        self.assertTrue(all(r["startup_ms"] >= 0 for r in rows))
