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
        for value in ("auto", "none", "required"):
            with self.subTest(value=value):
                self.client(mode="required_single_tool").chat([], [OTHER, SEARCH_TOOL], 1, value)
                self.assertEqual(self.sent[0]["tool_choice"], value)
                self.assertEqual(self.sent[0]["tools"], [OTHER, SEARCH_TOOL])

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
        for mode in (None, "required_single_tool"):
            for reply in (prose, response(name="other_tool"), response(finish="length"),
                          response(arguments="[]"), response(arguments="invalid json")):
                with self.subTest(mode=mode, reply=reply):
                    client = self.client(reply, mode)
                    with self.assertRaises(ValueError):
                        client.chat([], [SEARCH_TOOL, OTHER], 1, FORCED)
                    self.assertEqual(len(self.sent), 1)

    def test_invalid_mode_is_rejected_before_transport(self):
        with self.assertRaises(ValueError):
            self.client(mode="silently_auto")
