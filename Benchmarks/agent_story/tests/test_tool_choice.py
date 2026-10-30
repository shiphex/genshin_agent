"""Observe the real client's wire payload and rejection of ignored controls."""
from copy import deepcopy
import unittest

from Benchmarks.agent_story.providers import QwenClient, SEARCH_TOOL


FORCED = {"type": "function", "function": {"name": "search_story"}}
OTHER = {"type": "function", "function": {"name": "other_tool", "parameters": {"type": "object"}}}


def response(name="search_story", arguments='{"query":"test"}', finish="tool_calls"):
    return {"choices": [{"finish_reason": finish, "message": {
        "role": "assistant", "content": None, "tool_calls": [
            {"id": "call-1", "type": "function", "function": {"name": name, "arguments": arguments}}]}}]}


class ToolChoiceTests(unittest.TestCase):
    def client(self, reply=None, mode=None):
        self.sent = []
        def transport(endpoint, payload, timeout):
            self.sent.append(deepcopy(payload))
            return deepcopy(response() if reply is None else reply)
        config = {"base_url": "http://127.0.0.1:9999/v1", "model": "fake"}
        if mode is not None:
            config["tool_choice_mode"] = mode
        return QwenClient(config, transport=transport)

    def test_native_default_preserves_named_request_and_records_actual_payload(self):
        result = self.client().chat([], [OTHER, SEARCH_TOOL], 1, FORCED)
        self.assertEqual(self.sent[0]["tool_choice"], FORCED)
        self.assertEqual(self.sent[0]["tools"], [OTHER, SEARCH_TOOL])
        self.assertEqual(result["request"]["tool_choice_mode"], "native")
        self.assertEqual(result["request"]["payload"], self.sent[0])

    def test_adapter_filters_only_this_request_and_keeps_inputs_unchanged(self):
        client = self.client(mode="required_single_tool")
        tools, messages, requested = [OTHER, SEARCH_TOOL], [{"role": "user", "content": "hello"}], deepcopy(FORCED)
        original = deepcopy((tools, messages, requested))
        result = client.chat(messages, tools, 1, requested)
        self.assertEqual(self.sent[0]["tools"], [SEARCH_TOOL])
        self.assertEqual(self.sent[0]["tool_choice"], "required")
        self.assertNotIn("tool_choice_mode", self.sent[0])
        self.assertEqual(result["request"], {"tool_choice_mode": "required_single_tool",
            "requested_tool_choice": FORCED, "payload": self.sent[0]})
        client.chat(messages, tools, 1)
        self.assertNotIn("tool_choice", self.sent[1])
        self.assertEqual(self.sent[1]["tools"], [OTHER, SEARCH_TOOL])
        self.assertEqual((tools, messages, requested), original)

    def test_string_choices_are_not_converted(self):
        for mode in ("required_single_tool", "required_single_tool_prefill"):
            for value in ("auto", "none", "required"):
                with self.subTest(mode=mode, value=value):
                    self.client(mode=mode).chat([], [OTHER, SEARCH_TOOL], 1, value)
                    self.assertEqual(self.sent[0]["tool_choice"], value)
                    self.assertEqual(self.sent[0]["tools"], [OTHER, SEARCH_TOOL])
                    self.assertNotIn("continue_final_message", self.sent[0])

    def test_prefill_named_call_enters_tool_format_without_changing_user_history(self):
        client = self.client(mode="required_single_tool_prefill")
        messages = [{"role": "system", "content": "original system"}, {"role": "user", "content": "original question"}]
        original = deepcopy(messages)
        result = client.chat(messages, [OTHER, SEARCH_TOOL], 1, FORCED)
        payload = self.sent[0]
        self.assertEqual(payload["messages"], original + [{"role": "assistant", "content": "<tool_call>\n"}])
        self.assertEqual(payload["tool_choice"], "required")
        self.assertEqual(payload["tools"], [SEARCH_TOOL])
        self.assertFalse(payload["add_generation_prompt"])
        self.assertEqual(payload["continue_final_message"], "content")
        self.assertEqual(result["request"]["payload"], payload)
        self.assertEqual(messages, original)
        client.chat(messages, [OTHER, SEARCH_TOOL], 1)
        self.assertEqual(self.sent[1]["messages"], original)
        self.assertEqual(self.sent[1]["tools"], [OTHER, SEARCH_TOOL])
        self.assertNotIn("continue_final_message", self.sent[1])

    def test_prefilled_forced_request_explicitly_skips_thinking_but_followup_uses_profile(self):
        client = self.client(mode="required_single_tool_prefill")
        client.config.update(enable_thinking=True, thinking_budget_tokens=32, max_tokens=100)
        messages = [{"role": "user", "content": "question"}]
        client.chat(messages, [SEARCH_TOOL], 1, FORCED)
        client.chat(messages, [SEARCH_TOOL], 1)
        self.assertFalse(self.sent[0]["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(self.sent[0]["thinking_budget_tokens"], 0)
        self.assertEqual(self.sent[0]["max_tokens"], 100)
        self.assertTrue(self.sent[1]["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(self.sent[1]["thinking_budget_tokens"], 32)
        self.assertTrue(client.config["enable_thinking"])
        self.assertEqual(client.config["thinking_budget_tokens"], 32)

    def test_prefill_requires_a_user_or_tool_tail_before_any_request(self):
        for messages in ([], [{"role": "assistant", "content": "existing partial"}], [{"role": "system", "content": "system"}]):
            with self.subTest(messages=messages):
                client = self.client(mode="required_single_tool_prefill")
                with self.assertRaises(ValueError):
                    client.chat(messages, [SEARCH_TOOL], 1, FORCED)
                self.assertEqual(self.sent, [])

    def test_prefill_accepts_tool_result_tail_and_rejects_ignored_response(self):
        messages = [{"role": "tool", "tool_call_id": "previous", "content": "result"}]
        self.client(mode="required_single_tool_prefill").chat(messages, [SEARCH_TOOL], 1, FORCED)
        self.assertEqual(self.sent[0]["messages"][-2], messages[0])
        reply = {"choices": [{"finish_reason": "length", "message": {"role": "assistant", "content": "prose"}}]}
        client = self.client(reply, "required_single_tool_prefill")
        with self.assertRaises(ValueError):
            client.chat(messages, [SEARCH_TOOL], 1, FORCED)
        self.assertEqual(len(self.sent), 1)

    def test_transport_and_caller_mutations_cannot_change_inputs_or_request_snapshot(self):
        def transport(endpoint, payload, timeout):
            payload["messages"][0]["content"] = "transport mutation"
            payload["tools"][0]["function"]["name"] = "transport mutation"
            return response()
        client = QwenClient({"base_url": "http://127.0.0.1:9999/v1", "model": "fake",
                             "tool_choice_mode": "required_single_tool"}, transport=transport)
        messages, tools, requested = [{"role": "user", "content": "original"}], deepcopy([SEARCH_TOOL]), deepcopy(FORCED)
        result = client.chat(messages, tools, 1, requested)
        self.assertEqual(messages[0]["content"], "original")
        self.assertEqual(tools[0]["function"]["name"], "search_story")
        messages[0]["content"] = "caller mutation"
        tools[0]["function"]["name"] = "caller mutation"
        requested["function"]["name"] = "caller mutation"
        self.assertEqual(result["request"]["payload"]["messages"][0]["content"], "original")
        self.assertEqual(result["request"]["payload"]["tools"][0]["function"]["name"], "search_story")
        self.assertEqual(result["request"]["requested_tool_choice"]["function"]["name"], "search_story")

    def test_invalid_named_target_fails_before_transport(self):
        for tools, choice in (([OTHER], FORCED), ([SEARCH_TOOL, SEARCH_TOOL], FORCED),
                              ([SEARCH_TOOL], {"type": "function", "function": {"name": ""}}),
                              ([SEARCH_TOOL], {"type": "invalid"})):
            with self.subTest(tools=tools, choice=choice):
                client = self.client()
                with self.assertRaises(ValueError):
                    client.chat([], tools, 1, choice)
                self.assertEqual(self.sent, [])

    def test_ignored_wrong_or_unfinished_named_calls_fail_without_retry(self):
        prose = {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "hello"}}]}
        for mode in (None, "required_single_tool", "required_single_tool_prefill"):
            for reply in (prose, response(name="other_tool"), response(finish="length"),
                          response(arguments="[]"), response(arguments="invalid json")):
                with self.subTest(mode=mode, reply=reply):
                    client = self.client(reply, mode)
                    with self.assertRaises(ValueError):
                        client.chat([{"role": "user", "content": "question"}], [SEARCH_TOOL, OTHER], 1, FORCED)
                    self.assertEqual(len(self.sent), 1)

    def test_invalid_mode_is_rejected_before_transport(self):
        with self.assertRaises(ValueError):
            self.client(mode="silently_auto")
