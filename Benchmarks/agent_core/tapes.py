"""Precompiled finite conversations, with no runtime inference or decisions."""
from copy import deepcopy
import json

from Benchmarks.support.common import encoded


def core_tape(case, policy):
    tape, histories = [], {}
    for turn in case["turns"]:
        sid, text = turn["session_id"], turn["content"]
        if turn.get("reset"):
            histories.pop(sid, None)
        messages = deepcopy(histories.get(sid, [])) + [{"role": "user", "content": text}]
        actions = []
        kind = case["kind"]
        if kind == "context_over" and policy["context"] == "error":
            tape.append({"actions": [], "result": {"status": "context_limit", "content": ""}})
            continue
        if kind == "context_over":
            messages[-1]["content"] = text[-100:] if policy["context"] == "truncate" else "summary KEEP"
        has_tool = kind in {"single", "multi", "unknown", "arguments", "timeout", "exception", "invalid", "overhead", "loop_normal", "loop_limit"}
        count = 3 if kind.startswith("loop_") else 2 if has_tool else 1
        result = {"status": "completed", "content": "DONE"}
        for step in range(1, count + 1):
            actions.append({"provider": "model", "payload": {"messages": deepcopy(messages)}})
            tool_step = has_tool and (step < count or kind == "loop_limit")
            if not tool_step:
                messages.append({"role": "assistant", "content": "DONE"})
                break
            calls = [{"id": f"z-{step}", "type": "function", "function": {
                "name": "missing" if kind == "unknown" else "echo",
                "arguments": encoded({"text": 23 if kind == "arguments" else "left"})}}]
            if kind == "multi":
                calls.append({"id": "a-9", "type": "function", "function": {"name": "echo", "arguments": encoded({"text": "right"})}})
            messages.append({"role": "assistant", "content": None, "tool_calls": calls})
            for call in reversed(calls):
                actions.append({"provider": "tool", "payload": {"call_id": call["id"], "name": call["function"]["name"],
                                                                "arguments": json.loads(call["function"]["arguments"])}})
                error = {"unknown": "unknown_tool", "arguments": "invalid_arguments", "timeout": "timeout",
                         "exception": "tool_exception", "invalid": "invalid_result"}.get(kind)
                value = {"ok": False, "error": {"code": error}} if error else {
                    "ok": True, "result": {"text": json.loads(call["function"]["arguments"])["text"]}}
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": encoded(value)})
            if error and policy["tool_error"] == "terminate":
                result = {"status": "tool_error", "content": ""}
                break
            if kind == "loop_limit" and step == count:
                result = {"status": "step_limit", "content": ""}
        histories[sid] = messages
        tape.append({"actions": actions, "result": result})
    return tape
