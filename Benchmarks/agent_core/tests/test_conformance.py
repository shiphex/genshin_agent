from copy import deepcopy
import unittest
from unittest.mock import patch

from Benchmarks.support.common import read_json, read_rows
from Benchmarks.support.protocol import ProtocolError, ProviderDeadlineError
from Benchmarks.support.testing import POLICY, ReplayHarness
from Benchmarks.agent_core.cases import CASES
from Benchmarks.agent_core.runner import run_core, run_perf
from Benchmarks.agent_core.tapes import core_tape


class ConformanceTests(ReplayHarness, unittest.TestCase):
    def test_all_cases_pass_under_declared_profile(self):
        adapter = self.adapter({c["id"]: core_tape(c, POLICY) for c in CASES})
        run = run_core([adapter], self.root / "core")
        self.assertEqual(read_json(run / "manifest.json")["evaluation_profile"], "fixed-history-v0")
        self.assertEqual([r.get("conformance_status") for r in read_rows(run / "results.jsonl")], ["passed"] * 15)

    def test_summarized_or_cropped_history_remains_a_failure(self):
        for name, replacement in (("summary", [{"role": "user", "content": "summary"}]),
                                  ("crop", [])):
            with self.subTest(name=name):
                tape = core_tape(CASES[12], POLICY)
                tape[2]["actions"][0]["payload"]["messages"] = deepcopy(replacement)
                adapter = self.adapter({"c13": tape}, name)
                run = run_core([adapter], self.root / name, cases=[CASES[12]])
                row = read_rows(run / "results.jsonl")[0]
                self.assertEqual(row["execution_status"], "completed")
                self.assertFalse(row["correct"])
                self.assertEqual(row.get("conformance_status"), "failed")
                self.assertIn("history changed or session pollution", row["checks_failed"])

    def test_transport_errors_and_unobserved_failures_are_distinct(self):
        adapter = self.adapter([])
        for number, (error, expected) in enumerate(((ProtocolError("bad ID"), "failed"),
                (TimeoutError("service wait"), "not_evaluated"), (OSError("spawn"), "not_evaluated"))):
            with self.subTest(error=type(error).__name__):
                with patch("Benchmarks.agent_core.runner._worker", side_effect=error):
                    run = run_core([adapter], self.root / f"failure-{number}", cases=[CASES[0]])
                row = read_rows(run / "results.jsonl")[0]
                self.assertEqual(row["execution_status"], "failed")
                self.assertFalse(row["correct"])
                self.assertEqual(row.get("conformance_status"), expected)
                self.assertEqual(row["error"], type(error).__name__)

    def test_interrupt_and_unstarted_samples_keep_full_denominator(self):
        adapter = self.adapter([])
        with patch("Benchmarks.agent_core.runner._worker", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            run_core([adapter], self.root / "interrupt", cases=CASES[:2])
        rows = read_rows(self.root / "interrupt/results.jsonl")
        self.assertEqual([r["execution_status"] for r in rows], ["interrupted", "not_started"])
        self.assertEqual([r.get("conformance_status") for r in rows], ["not_evaluated"] * 2)
        summary = read_json(self.root / "interrupt/summary.json")
        self.assertEqual(summary.get("conformance"), {"total": 2, "passed": 0, "failed": 0,
                                                     "not_evaluated": 2, "not_recorded": 0})

    def test_perf_declares_profile_and_retains_success_filter(self):
        adapter = self.adapter(core_tape(CASES[-1], POLICY))
        run = run_perf([adapter], self.root / "perf", rounds=1, batch=1, warmup=0)
        self.assertEqual(read_json(run / "manifest.json")["evaluation_profile"], "fixed-history-v0")
        self.assertEqual([r.get("conformance_status") for r in read_rows(run / "results.jsonl")], ["passed"] * 2)

    def test_perf_protocol_and_runtime_errors_have_different_verdicts(self):
        adapter = self.adapter([])
        for number, (error, expected) in enumerate(((ProtocolError("bad message"), "failed"),
                                                  (TimeoutError("wait"), "not_evaluated"))):
            with patch("Benchmarks.agent_core.runner._worker", side_effect=error):
                run = run_perf([adapter], self.root / f"perf-{number}", rounds=1, batch=1, warmup=0)
            rows = read_rows(run / "results.jsonl")
            self.assertTrue(all(r.get("conformance_status") == expected for r in rows))
            self.assertTrue(all(r["correct"] is False for r in rows))

    def test_cleanup_wrapper_preserves_protocol_evidence_and_stops_run(self):
        adapter = self.adapter([])
        for runner, kwargs in ((run_core, {"cases": CASES[:2]}),
                               (run_perf, {"rounds": 1, "batch": 1, "warmup": 0})):
            for cause, expected in ((ProtocolError("bad session"), "failed"),
                                    (TimeoutError("provider wait"), "not_evaluated")):
                with self.subTest(runner=runner.__name__, cause=type(cause).__name__):
                    wrapped = ProviderDeadlineError("provider exceeded cleanup")
                    wrapped.__cause__ = cause
                    output = self.root / f"{runner.__name__}-{type(cause).__name__}"
                    with patch("Benchmarks.agent_core.runner._worker", side_effect=wrapped), self.assertRaises(ProviderDeadlineError):
                        runner([adapter], output, **kwargs)
                    rows = read_rows(output / "results.jsonl")
                    self.assertEqual(rows[0].get("conformance_status"), expected)
                    self.assertEqual(rows[0]["error"], "ProviderDeadlineError")
                    self.assertEqual(rows[1]["execution_status"], "not_started")
                    self.assertEqual(rows[1].get("conformance_status"), "not_evaluated")

    def test_observed_violation_remains_failed_after_interrupt(self):
        adapter = self.adapter([])
        def interrupt(worker, oracle, turn):
            oracle.check(False, "observed mismatch")
            raise KeyboardInterrupt
        with patch("Benchmarks.agent_core.runner._core_turn", side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
            run_core([adapter], self.root / "observed-interrupt", cases=[CASES[0]])
        row = read_rows(self.root / "observed-interrupt/results.jsonl")[0]
        self.assertEqual(row["execution_status"], "interrupted")
        self.assertEqual(row.get("conformance_status"), "failed")
        self.assertEqual(row["checks_failed"], ["observed mismatch"])
