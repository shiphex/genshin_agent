import json
from pathlib import Path
import tempfile
import threading
import unittest
from Benchmarks.agent_story.providers import LiveProvider, QwenClient, freeze_sources, SEARCH_TOOL


class ProviderTests(unittest.TestCase):
    def config(self):
        return {"base_url": "http://127.0.0.1:9999/v1", "model": "fake-qwen", "timeout": 1,
                "max_tokens": 100, "temperature": 0, "seed": 42}

    def test_unknown_credential_fields_cannot_enter_a_run_manifest(self):
        with self.assertRaises(ValueError):
            QwenClient({**self.config(), "access_token": "synthetic-value"})

    def test_selected_generation_reaches_native_tool_request_without_leaking_thought_history(self):
        received = []
        def transport(path, payload, timeout):
            received.append((payload, timeout))
            return {"choices": [{"message": {"role": "assistant", "content": "answer",
                                              "reasoning_content": "internal thought"}, "finish_reason": "stop"}]}
        settings = {**self.config(), "max_tokens": 3072, "enable_thinking": True,
                    "thinking_budget_tokens": 1024, "profile": "standard", "top_k": 5,
                    "generation": {"temperature": 1, "top_k": 20}}
        result = QwenClient(settings, transport=transport).chat([], [SEARCH_TOOL], 0.5)
        payload, deadline = received[0]
        self.assertEqual(payload["top_k"], 20)
        self.assertEqual(payload["temperature"], 1)
        self.assertEqual(payload["thinking_budget_tokens"], 1024)
        self.assertTrue(payload["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(deadline, 0.5)
        self.assertNotIn("reasoning_content", result["message"])
        self.assertEqual(result["raw_response"]["choices"][0]["message"]["reasoning_content"], "internal thought")

    def test_preflight_requires_native_function_call(self):
        def transport(path, payload, timeout):
            return {"choices": [{"message": {"role": "assistant", "content": "pretend tool call"}, "finish_reason": "stop"}]}
        client = QwenClient(self.config(), transport=transport)
        with self.assertRaisesRegex(ValueError, "native tool"):
            client.preflight()

    def test_thought_only_response_is_not_a_usable_answer(self):
        for content in (None, "", "  "):
            def transport(*args):
                return {"choices": [{"message": {"role": "assistant", "content": content,
                                                  "reasoning_content": "still thinking"}, "finish_reason": "length"}]}
            with self.subTest(content=content), self.assertRaises(ValueError):
                QwenClient(self.config(), transport=transport).chat([], [], 1)

    def test_http_preflight_uses_native_tools_against_only_a_loopback_fake(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import json
        import threading
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                response = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "preflight-1", "type": "function", "function": {
                        "name": "search_story", "arguments": '{"query":"甘雨"}'}}
                ]}, "finish_reason": "tool_calls"}]}
                body = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        try:
            config = {**self.config(), "base_url": f"http://127.0.0.1:{server.server_port}/v1"}
            self.assertTrue(QwenClient(config).preflight()["native_tool_calling"])
        finally:
            server.shutdown()
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(received[0]["tool_choice"]["function"]["name"], "search_story")
        self.assertEqual(received[0]["tools"], [SEARCH_TOOL])

    def test_tool_calls_and_missing_usage_survive_client_normalization(self):
        observed = []
        def transport(path, payload, timeout):
            observed.append(payload)
            return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "x", "type": "function", "function": {"name": "search_story", "arguments": '{"query":"甘雨"}'}}
            ]}, "finish_reason": "tool_calls"}]}
        result = QwenClient(self.config(), transport=transport).chat([{"role": "user", "content": "hi"}], [SEARCH_TOOL], 1)
        self.assertIsNone(result["usage"])
        self.assertEqual(result["message"]["tool_calls"][0]["id"], "x")
        self.assertEqual(observed[0]["seed"], 42)

    def test_provider_checks_issued_ids_and_step_budget_and_retains_usage_absence(self):
        def transport(path, payload, timeout):
            return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "t", "type": "function", "function": {"name": "search_story", "arguments": '{"query":"甘雨"}'}}
            ]}, "finish_reason": "tool_calls"}]}
        corpus = [{"id": "c1", "title": "甘雨", "text": "甘雨资料", "source_file": "parsed/a.json",
                   "source_pointer": ["/text"], "source_kind": "wiki_excerpt"}]
        provider = LiveProvider(QwenClient(self.config(), transport=transport), corpus, top_k=1, max_steps=1)
        provider.begin("s", "甘雨是谁？", 1)
        self.assertFalse(provider.provide("tool", {"call_id": "invented", "name": "search_story", "arguments": {"query": "甘雨"}}, "s", 1)["ok"])
        self.assertTrue(provider.provide("model", {"messages": [{"role": "user", "content": "甘雨是谁？"}]}, "s", 1)["ok"])
        self.assertTrue(provider.provide("tool", {"call_id": "t", "name": "search_story", "arguments": {"query": "甘雨"}}, "s", 1)["ok"])
        self.assertFalse(provider.provide("model", {"messages": []}, "s", 1)["ok"])
        stats = provider.stats()
        self.assertEqual(stats["usage_missing_calls"], 1)
        self.assertIsNone(stats["usage_totals"]["total_tokens"])
        self.assertTrue(stats["violations"])

    def test_frozen_sources_are_read_only_and_bound_to_file_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "parsed").mkdir()
            path = root / "parsed/a.json"
            path.write_text('{"text":"frozen excerpt"}')
            before = path.read_bytes()
            scene = {"reference_material": [{"id": "q", "sources": [{"file": "parsed/a.json", "pointer": "/text"}]}]}
            material = freeze_sources(scene, root)
            self.assertEqual(material[0]["text"], "frozen excerpt")
            self.assertEqual(path.read_bytes(), before)
            scene["reference_material"][0]["sources"][0]["file"] = "../outside.json"
            with self.assertRaises(ValueError):
                freeze_sources(scene, root)

    def test_live_rag_roundtrip_preserves_tool_ids_evidence_and_native_history(self):
        import json
        call = {"id": "t9", "type": "function", "function": {"name": "search_story", "arguments": '{"query":"甘雨"}'}}
        responses = iter([
            {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "finish_reason": "tool_calls"}],
             "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}},
            {"choices": [{"message": {"role": "assistant", "content": "answer [c1]"}, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}}])
        client = QwenClient(self.config(), transport=lambda *args: next(responses))
        corpus = [{"id": "c1", "title": "甘雨", "text": "synthetic evidence"}]
        provider = LiveProvider(client, corpus, max_steps=2)
        provider.begin("s", "question", 1)
        messages = [{"role": "user", "content": "question"}]
        model = provider.provide("model", {"messages": messages}, "s", 1)
        messages.append(model["result"]["message"])
        tool = provider.provide("tool", {"call_id": "t9", "name": "search_story", "arguments": {"query": "甘雨"}}, "s", 1)
        messages.append({"role": "tool", "tool_call_id": "t9", "content": json.dumps(tool)})
        self.assertTrue(provider.provide("model", {"messages": messages}, "s", 1)["ok"])
        provider.end({"status": "completed", "content": "answer [c1]"})
        self.assertEqual(provider.stats()["usage_totals"]["total_tokens"], 12)
        self.assertFalse(provider.violations)
        self.assertIn("c1", provider.evidence)

    def test_truncated_response_is_separate_from_api_completion(self):
        client = QwenClient(self.config(), transport=lambda *args: {"choices": [{
            "message": {"role": "assistant", "content": "unfinished"}, "finish_reason": "length"}]})
        provider = LiveProvider(client, [{"id": "c1", "title": "x", "text": "x"}])
        provider.begin("s", "x", 1)
        provider.provide("model", {"messages": [{"role": "user", "content": "x"}]}, "s", 1)
        provider.end({"status": "completed", "content": "unfinished"})
        self.assertEqual(provider.stats()["model_truncated"], 1)
        self.assertEqual(provider.stats()["model_api_completed"], 0)
        self.assertTrue(provider.violations)
