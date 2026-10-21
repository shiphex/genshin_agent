import unittest
from Benchmarks.support.common import read_rows
from Benchmarks.support.testing import POLICY, ReplayHarness
from Benchmarks.agent_core.runner import run_perf
from Benchmarks.agent_core.cases import CASES
from Benchmarks.agent_core.tapes import core_tape


class PerfFailureTests(ReplayHarness, unittest.TestCase):
    def test_failed_perf_batch_keeps_completed_iterations_and_resources(self):
        adapter = self.adapter(core_tape(CASES[-1], POLICY) * 2)
        path = run_perf([adapter], self.root / "partial-perf", rounds=1, batch=3, warmup=0)
        row = read_rows(path / "results.jsonl")[0]
        self.assertEqual(row["execution_status"], "failed")
        self.assertEqual(len(row["iterations_ms"]), 2)
        self.assertIn("resources", row)
        self.assertIn("startup_ms", row)
