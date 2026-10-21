"""Deterministic oracles observe requests; they never execute an agent loop."""
from copy import deepcopy
import json
import threading

from Benchmarks.support.common import encoded
from Benchmarks.support.contracts import normal_messages, validate_policy


ECHO_TOOL = {"type": "function", "function": {"name": "echo", "description": "Return text unchanged.",
             "parameters": {"type": "object", "properties": {"text": {"type": "string"}},
                            "required": ["text"], "additionalProperties": False}}}


def _case(number, kind, title, turns=None):
    return {"id": f"c{number:02}", "kind": kind, "title": title, "max_steps": 3,
            "context_limit": 100 if kind.startswith("context_") else 10000,
            "turns": turns or [{"session_id": "A", "content": title, "reset": True}]}


CASES = [
    _case(1, "direct", "direct completion"),
    _case(2, "single", "single tool"),
    _case(3, "multi", "nonpositional multiple tool IDs"),
    _case(4, "unknown", "unknown tool"),
    _case(5, "arguments", "invalid arguments"),
    _case(6, "timeout", "tool timeout"),
    _case(7, "exception", "tool exception"),
    _case(8, "invalid", "invalid tool output"),
    _case(9, "loop_normal", "normal multi-step completion"),
    _case(10, "loop_limit", "continuous tool requests"),
    _case(11, "context_exact", "exact context budget", [{"session_id": "A", "content": "x" * 96 + "KEEP", "reset": True}]),
    _case(12, "context_over", "context overflow", [{"session_id": "A", "content": "x" * 97 + "KEEP", "reset": True}]),
    _case(13, "sessions", "interleaved independent sessions", [
        {"session_id": "A", "content": "A_SECRET", "reset": True},
        {"session_id": "B", "content": "B_SECRET", "reset": True},
        {"session_id": "A", "content": "recall A"}, {"session_id": "B", "content": "recall B"}]),
    _case(14, "reset", "reset clears prior state", [
        {"session_id": "A", "content": "OLD_SECRET", "reset": True},
        {"session_id": "A", "content": "NEW_STATE", "reset": True}]),
    _case(15, "overhead", "fixed model-tool-model workload"),
]
ERRORS = {"unknown": "unknown_tool", "arguments": "invalid_arguments", "timeout": "timeout",
          "exception": "tool_exception", "invalid": "invalid_result"}





def context_units(messages):
    """Mock-only budget: Unicode code points in content, not model tokens."""
    return sum(len(m.get("content") or "") for m in messages)


def tool_call(identity, text, name="echo"):
    return {"id": identity, "type": "function", "function": {"name": name,
            "arguments": encoded({"text": text})}}





class CoreOracle:
    def __init__(self, case, policy):
        validate_policy(policy)
        self.case, self.policy = case, policy
        self.histories, self.errors = {}, []
        self.model_calls, self.tool_calls = 0, 0
        self.lock = threading.Lock()

    def reset(self, session):
        self.histories.pop(session, None)

    def begin(self, turn):
        self.session, self.input = turn["session_id"], turn["content"]
        self.messages = deepcopy(self.histories.get(self.session, [])) + [{"role": "user", "content": self.input}]
        self.steps, self.pending, self.attempts = 0, [], {}
        self.final, self.last = False, None

    def check(self, condition, reason):
        if not condition:
            self.errors.append(reason)

    def provide(self, provider, payload, session, remaining):
        with self.lock:
            self.check(session == self.session, "provider session mismatch")
            try:
                return self._model(payload) if provider == "model" else self._tool(payload)
            except (KeyError, TypeError, ValueError) as exc:
                self.errors.append("invalid provider payload: " + type(exc).__name__)
                return {"ok": False, "error": {"code": "invalid_request"}}

    def _model(self, payload):
        self.steps += 1
        self.model_calls += 1
        self.check(self.steps <= self.case["max_steps"], "model request after step limit")
        self.check(not self.final, "model request after completion")
        messages = payload["messages"]
        kind = self.case["kind"]
        if kind == "context_over" and self.steps == 1:
            self.check(self.policy["context"] != "error", "model called despite context error policy")
            self.check(context_units(messages) <= self.case["context_limit"], "context budget exceeded")
            self.check(messages[-1]["role"] == "user" and "KEEP" in messages[-1]["content"],
                       "context handling lost required tail")
            if self.policy["context"] == "truncate":
                self.check(messages == [{"role": "user", "content": self.input[-100:]}], "truncate must retain tail")
            self.messages = deepcopy(messages)
        elif self.pending:
            prefix = messages[:-len(self.pending)]
            self.check(normal_messages(prefix) == normal_messages(self.messages), "history changed or session pollution")
            suffix = messages[-len(self.pending):]
            self.check(len({m.get("tool_call_id") for m in suffix}) == len(self.pending), "duplicate tool result ID")
            actual = {m.get("tool_call_id"): m for m in suffix}
            for call in self.pending:
                cid = call["id"]
                expected = self._expected_result(call)
                self.check(cid in actual and actual[cid].get("role") == "tool" and
                           json.loads(actual[cid]["content"]) == expected, "tool result ID/content mismatch")
                if kind not in {"unknown", "arguments"}:
                    self.check(self.attempts.get(cid, 0) > 0, "tool result fabricated without execution")
            self.messages.extend(deepcopy(suffix))
        else:
            self.check(normal_messages(messages) == normal_messages(self.messages), "history changed or session pollution")
        self.check(context_units(messages) <= self.case["context_limit"], "context budget exceeded")
        if kind in ERRORS and self.steps > 1:
            self.check(self.policy["tool_error"] == "recover", "recovery violates declared termination")
        self.pending = []
        call_step = (kind in {"single", "multi", "unknown", "arguments", "timeout", "exception", "invalid", "overhead"}
                     and self.steps == 1) or (kind == "loop_normal" and self.steps < 3) or kind == "loop_limit"
        if call_step:
            calls = [tool_call(f"z-{self.steps}", 23 if kind == "arguments" else "left",
                               "missing" if kind == "unknown" else "echo")]
            if kind == "multi":
                calls.append(tool_call("a-9", "right"))
            message = {"role": "assistant", "content": None, "tool_calls": calls}
            self.pending = calls
        else:
            message = {"role": "assistant", "content": "DONE"}
            self.final = True
        self.messages.append(deepcopy(message))
        self.last = message
        return {"ok": True, "result": {"message": message, "finish_reason": "tool_calls" if call_step else "stop",
                                        "usage": None}}

    def _expected_result(self, call):
        if self.case["kind"] in ERRORS:
            return {"ok": False, "error": {"code": ERRORS[self.case["kind"]]}}
        return {"ok": True, "result": {"text": json.loads(call["function"]["arguments"])["text"]}}

    def _tool(self, payload):
        self.tool_calls += 1
        cid = payload["call_id"]
        call = next((c for c in self.pending if c["id"] == cid), None)
        self.check(call is not None, "tool request not issued by model")
        if call is None:
            return {"ok": False, "error": {"code": "unknown_call"}}
        self.attempts[cid] = self.attempts.get(cid, 0) + 1
        self.check(self.attempts[cid] <= 1 + self.policy.get("max_tool_retries", 0), "retry budget exceeded")
        if self.case["kind"] not in ERRORS:
            self.check(self.attempts[cid] == 1, "successful tool executed more than once")
        self.check(payload["name"] == call["function"]["name"] and payload["arguments"] ==
                   json.loads(call["function"]["arguments"]), "tool arguments or ID mismatch")
        if self.case["kind"] == "invalid":
            return {"ok": True, "result": "not-an-object"}
        return self._expected_result(call)

    def end(self, result):
        kind = self.case["kind"]
        if kind == "context_over" and self.policy["context"] == "error":
            self.check(result["status"] == "context_limit" and self.steps == 0, "context failure not bounded")
        elif kind in ERRORS and self.policy["tool_error"] == "terminate":
            self.check(result["status"] == "tool_error" and self.steps == 1, "tool failure not terminated")
            if kind not in {"unknown", "arguments"}:
                self.check(any(self.attempts.values()), "tool failure fabricated without invocation")
        elif kind == "loop_limit":
            self.check(result["status"] == "step_limit" and self.steps == self.case["max_steps"], "wrong loop limit behavior")
        else:
            self.check(result["status"] == "completed" and self.final and result["content"] == "DONE",
                       "final result does not match model completion")
            self.histories[self.session] = deepcopy(self.messages)

    def verdict(self):
        return {"correct": not self.errors, "checks_failed": self.errors,
                "model_calls": self.model_calls, "tool_calls": self.tool_calls}
