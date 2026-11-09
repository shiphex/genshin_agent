"""Probe-specific conversion and SDK execution checks; shared oracle stays authoritative."""
from copy import deepcopy
import unittest

from probes.core_sdk.agent import CoreAgent, from_chat, to_chat


POLICIES = {"tool_execution": "serial", "tool_error": "recover", "context": "error", "max_tool_retries": 0}
TOOL = {"type": "function", "function": {"name": "echo", "description": "Echo text",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}}


def config(**changes):
    return {"system": "", "tools": [TOOL], "max_steps": 3, "context_limit": 10000,
            "context_counter": "unicode_content_codepoints_v1", "policies": POLICIES, **changes}


class BridgeTests(unittest.TestCase):
    def test_story_service_managed_context_uses_existing_provider_checks(self):
        from Benchmarks.agent_story.providers import LiveProvider, QwenClient, SEARCH_TOOL

        responses = iter([
            {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "story-9", "type": "function", "function": {"name": "search_story", "arguments": '{"query":"甘雨"}'}}]},
                "finish_reason": "tool_calls"}]},
            {"choices": [{"message": {"role": "assistant", "content": "answer [c1]"}, "finish_reason": "stop"}]},
            {"choices": [{"message": {"role": "assistant", "content": "continued [c1]"}, "finish_reason": "stop"}]},
        ])
        client = QwenClient({"base_url": "http://127.0.0.1:9999/v1", "model": "synthetic", "timeout": 1},
                            transport=lambda *args: next(responses))
        provider = LiveProvider(client, [{"id": "c1", "title": "甘雨", "text": "synthetic evidence"}],
                                max_steps=8, system="system", policies=POLICIES)
        agent = CoreAgent(config(system="system", tools=[SEARCH_TOOL], max_steps=8, context_limit=None,
                                 context_counter="service_managed"),
                          lambda kind, payload: provider.provide(kind, payload, "s", 1))
        for number, content in enumerate(("question", "continue"), 1):
            provider.begin("s", content, number)
            result = agent.turn("s", content)
            provider.end(result)
            self.assertEqual(result["status"], "completed")
        self.assertEqual(provider.stats()["violations"], [])
        self.assertEqual(provider.stats()["model_calls"], 3)
        self.assertEqual(provider.stats()["tool_calls"], 1)

    def test_roundtrip_keeps_null_content_and_raw_arguments(self):
        raw = {"role": "assistant", "content": None, "tool_calls": [{"id": "call-7", "type": "function",
               "function": {"name": "echo", "arguments": '{ "text": "你好" }'}}]}
        self.assertEqual(to_chat([from_chat(raw)]), [raw])

    def test_malformed_arguments_recover_inside_sdk_without_provider_tool(self):
        requests = []

        def broker(provider, payload):
            requests.append((provider, deepcopy(payload)))
            self.assertEqual(provider, "model")
            if len(requests) == 1:
                message = {"role": "assistant", "content": None, "tool_calls": [{"id": "broken", "type": "function",
                           "function": {"name": "echo", "arguments": "{bad"}}]}
                return {"ok": True, "result": {"message": message, "finish_reason": "tool_calls"}}
            self.assertEqual(payload["messages"][-1], {"role": "tool", "tool_call_id": "broken",
                             "content": '{"ok":false,"error":{"code":"invalid_arguments"}}'})
            return {"ok": True, "result": {"message": {"role": "assistant", "content": "recovered"}, "finish_reason": "stop"}}

        agent = CoreAgent(config(), broker)
        self.assertEqual(agent.turn("A", "hello"), {"status": "completed", "content": "recovered"})
        self.assertEqual(len(requests), 2)

    def test_provider_failure_ends_turn_and_reset_clears_failed_history(self):
        requests = []

        def broker(provider, payload):
            requests.append(deepcopy(payload))
            if len(requests) == 1:
                return {"ok": False, "error": {"code": "model_error"}}
            self.assertEqual(payload["messages"], [{"role": "system", "content": "system"},
                             {"role": "user", "content": "new"}])
            return {"ok": True, "result": {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}}

        agent = CoreAgent(config(system="system"), broker)
        self.assertEqual(agent.turn("A", "old")["status"], "failed")
        agent.reset("A")
        self.assertEqual(agent.turn("A", "new"), {"status": "completed", "content": "ok"})

    def test_truncated_model_reply_is_retained_without_claiming_completion(self):
        requests = []

        def broker(provider, payload):
            requests.append(deepcopy(payload))
            if len(requests) == 1:
                return {"ok": True, "result": {"message": {"role": "assistant", "content": "partial"}, "finish_reason": "length"}}
            self.assertEqual(payload["messages"][-2], {"role": "assistant", "content": "partial"})
            return {"ok": True, "result": {"message": {"role": "assistant", "content": "done"}, "finish_reason": "stop"}}

        agent = CoreAgent(config(), broker)
        self.assertEqual(agent.turn("A", "first")["status"], "failed")
        self.assertEqual(agent.turn("A", "continue"), {"status": "completed", "content": "done"})

    def test_abnormal_model_finish_keeps_raw_reply_without_tool_dispatch(self):
        call = {"id": "truncated-9", "type": "function",
                "function": {"name": "echo", "arguments": '{ "text": "partial" }'}}
        cases = [(reason, {"role": "assistant", "content": None, "tool_calls": [call]})
                 for reason in ("length", "content_filter", "stop", None)]
        cases.append(("stop", {"role": "assistant", "content": None}))
        for reason, raw in cases:
            with self.subTest(finish_reason=reason, has_tools=bool(raw.get("tool_calls"))):
                sequence = []

                def broker(provider, payload):
                    sequence.append(provider)
                    if provider == "tool":
                        return {"ok": True, "result": {"text": "partial"}}
                    if len(sequence) == 1:
                        return {"ok": True, "result": {"message": deepcopy(raw), "finish_reason": reason}}
                    return {"ok": True, "result": {"message": {"role": "assistant", "content": "done"},
                                                    "finish_reason": "stop"}}

                agent = CoreAgent(config(), broker)
                result = agent.turn("A", "first")
                self.assertEqual(sequence, ["model"])
                self.assertEqual(result, {"status": "failed", "content": ""})
                self.assertEqual(to_chat(agent.histories["A"])[-1], raw)


if __name__ == "__main__":
    unittest.main()
