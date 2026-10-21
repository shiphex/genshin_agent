from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from Benchmarks.support.protocol import Worker
from Benchmarks.support.testing import POLICY, FIXTURE
from Benchmarks.agent_core.cases import CASES, CoreOracle
from Benchmarks.agent_core.tapes import core_tape


class OracleTests(unittest.TestCase):
    def execute(self, case, policy=POLICY, mutate=None):
        oracle = CoreOracle(case, policy)
        tape = core_tape(case, policy)
        if mutate:
            mutate(tape)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            tape_path = path / "tape.json"
            tape_path.write_text(json.dumps(tape))
            with Worker([sys.executable, "-B", str(FIXTURE), "--tape", str(tape_path)],
                        path / "stderr.txt", timeout=3) as worker:
                worker.request("init", "control", {"protocol_version": 1})
                for turn in case["turns"]:
                    if turn.get("reset"):
                        worker.request("reset", turn["session_id"], {})
                        oracle.reset(turn["session_id"])
                    oracle.begin(turn)
                    reply = worker.request("turn", turn["session_id"], {"content": turn["content"]},
                                           provider=oracle.provide)
                    oracle.end(reply)
        return oracle.verdict()

    def test_all_fifteen_cases_have_observable_success(self):
        self.assertEqual(len(CASES), 15)
        for case in CASES:
            with self.subTest(case=case["id"]):
                verdict = self.execute(case)
                self.assertTrue(verdict["correct"], verdict)

    def test_declared_termination_and_context_strategies(self):
        for cid in ("c04", "c05", "c06", "c07", "c08", "c12"):
            case = next(c for c in CASES if c["id"] == cid)
            for context in ("error", "truncate", "compress"):
                policy = {**POLICY, "tool_error": "terminate", "context": context}
                with self.subTest(case=cid, context=context):
                    self.assertTrue(self.execute(case, policy)["correct"])

    def test_swapped_tool_results_and_session_pollution_are_detected(self):
        def swap(tape):
            messages = tape[0]["actions"][-1]["payload"]["messages"]
            messages[-1]["content"], messages[-2]["content"] = messages[-2]["content"], messages[-1]["content"]
        self.assertFalse(self.execute(CASES[2], mutate=swap)["correct"])
        def pollute(tape):
            tape[2]["actions"][0]["payload"]["messages"].insert(0, {"role": "user", "content": "B_SECRET"})
        self.assertFalse(self.execute(CASES[12], mutate=pollute)["correct"])

    def test_extra_model_request_after_step_limit_is_detected(self):
        def extra(tape):
            tape[0]["actions"].append(deepcopy(tape[0]["actions"][0]))
        self.assertFalse(self.execute(CASES[9], mutate=extra)["correct"])
