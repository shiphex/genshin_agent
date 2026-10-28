"""Candidate-only gaps: native Story history, malformed calls and failures."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from Benchmarks.agent_story.providers import LiveProvider, SEARCH_TOOL, SYSTEM
from Benchmarks.support.protocol import Worker


POLICY = {"tool_execution": "serial", "tool_error": "recover", "context": "error", "max_tool_retries": 0}
SCRIPT = Path(__file__).resolve().parents[1] / "worker.py"


def completion(content="答复🌙"):
    return {"ok": True, "result": {"message": {"role": "assistant", "content": content},
            "finish_reason": "stop", "usage": None, "raw_response": {"audit_only": True}}}


def call(arguments='{"query":"甘雨🌙"}'):
    return {"role": "assistant", "content": None, "tool_calls": [{"id": "native-月",
            "type": "function", "function": {"name": "search_story", "arguments": arguments}}]}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.worker = Worker([sys.executable, "-B", str(SCRIPT)], Path(self.tmp.name) / "stderr.txt", timeout=5)
        self.addCleanup(self.worker.close)

    def init(self, context_limit=None, system=SYSTEM):
        self.worker.request("init", "control", {"protocol_version": 1, "suite": "bridge-test",
            "scenario_id": "arbitrary-unseen-input", "policies": POLICY, "system": system,
            "tools": [SEARCH_TOOL], "max_steps": 3, "context_limit": context_limit,
            "context_counter": "service_managed" if context_limit is None else "unicode_content_codepoints_v1"})

    def test_live_provider_unicode_system_evidence_and_multiturn(self):
        self.init()
        histories = []

        class Client:
            def chat(self, messages, tools, remaining):
                histories.append(deepcopy(messages))
                if len(histories) == 1:
                    return {"message": call(), "finish_reason": "tool_calls", "usage": None,
                            "raw_response": {"audit_only": True}}
                return completion()["result"]

        corpus = [{"id": "e-月", "title": "甘雨", "text": "甘雨资料🌙", "source_file": "parsed/a.json",
                   "source_pointer": ["/text"], "source_kind": "wiki_excerpt"}]
        provider = LiveProvider(Client(), corpus, system=SYSTEM, policies=POLICY)
        for index, text in enumerate(["甘雨是谁🌙？", "接着解释"], 1):
            provider.begin("独立会话", text, index)
            result = self.worker.request("turn", "独立会话", {"content": text}, provider=provider.provide)
            provider.end(result)
            self.assertEqual((result["status"], result["content"]), ("completed", "答复🌙"))
        self.assertEqual(provider.violations, [])
        self.assertEqual(histories[0][0], {"role": "system", "content": SYSTEM})
        self.assertEqual(histories[1][2], call())
        tool = histories[1][3]
        self.assertEqual(tool["tool_call_id"], "native-月")
        self.assertEqual(set(json.loads(tool["content"])), {"ok", "result"})
        self.assertEqual(json.loads(tool["content"])["result"]["evidence"][0]["id"], "e-月")
        self.assertEqual(histories[2][:-1], histories[1] + [{"role": "assistant", "content": "答复🌙"}])

    def test_malformed_arguments_recover_without_dispatch(self):
        self.init()
        histories = []

        def provider(kind, payload, session, remaining):
            self.assertEqual(kind, "model")
            histories.append(deepcopy(payload["messages"]))
            if len(histories) == 1:
                return {"ok": True, "result": {"message": call('{"query":'), "finish_reason": "tool_calls"}}
            return completion()

        result = self.worker.request("turn", "A", {"content": "ask"}, provider=provider)
        self.assertEqual(result["status"], "completed")
        tool = histories[1][-1]
        self.assertEqual(tool["tool_call_id"], "native-月")
        self.assertEqual(json.loads(tool["content"]), {"ok": False, "error": {"code": "invalid_arguments"}})

    def test_nullable_tool_calls_complete_and_remain_in_history(self):
        self.init()
        histories = []
        response = completion()
        response["result"]["message"]["tool_calls"] = None

        def provider(kind, payload, session, remaining):
            self.assertEqual(kind, "model")
            histories.append(deepcopy(payload["messages"]))
            return response

        for content in ("first", "follow-up"):
            result = self.worker.request("turn", "A", {"content": content}, provider=provider)
            self.assertEqual(result["status"], "completed")
        self.assertEqual(histories[1][2], response["result"]["message"])

    def test_model_error_and_truncation_are_failed_without_retry(self):
        self.init()
        for response in [{"ok": False, "error": {"code": "model_error"}},
                         {"ok": True, "result": {"message": {"role": "assistant", "content": "partial"},
                                                  "finish_reason": "length"}}]:
            with self.subTest(response=response):
                self.worker.request("reset", "A", {})
                calls = []

                def provider(kind, payload, session, remaining):
                    calls.append(kind)
                    return response

                result = self.worker.request("turn", "A", {"content": "ask"}, provider=provider)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(calls, ["model"])

    def test_context_checked_again_after_tool_content_growth(self):
        self.init(context_limit=10, system="")
        calls = []

        def provider(kind, payload, session, remaining):
            calls.append(kind)
            if kind == "model":
                return {"ok": True, "result": {"message": call(), "finish_reason": "tool_calls"}}
            return {"ok": True, "result": {"text": "x" * 20}}

        result = self.worker.request("turn", "A", {"content": "ask"}, provider=provider)
        self.assertEqual(result["status"], "context_limit")
        self.assertEqual(calls, ["model", "tool"])


if __name__ == "__main__":
    unittest.main()
