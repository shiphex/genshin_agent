from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import threading
import unittest
from unittest.mock import patch
from Benchmarks.support.common import read_json, read_rows, write_json, file_hash
from Benchmarks.support.testing import POLICY
from Benchmarks.agent_story.providers import LiveProvider, QwenClient
from Benchmarks.agent_story.review import export_review, import_review, semantic_summary
from Benchmarks.reports import make_report
from . import test_runner_review as runner_tests


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.harness = runner_tests.RunnerTests()
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        self.path = self.harness.root

    def scored_package(self, run):
        package = export_review(run, self.path / "review")
        scoring = read_json(package / "review-template.json")
        scoring["reviewer"] = "synthetic-reviewer"
        for sample in scoring["samples"]:
            for criterion in sample["criteria"]:
                criterion.update(verdict="pass", rationale="synthetic test", evidence_refs=["turn:1"])
        return package, scoring

    def test_edited_private_mapping_cannot_redirect_scores(self):
        package, scoring = self.scored_package(self.harness.agent_run())
        binding = read_json(package / "binding.json")
        binding["mapping"]["sample-0001"] = "different-candidate:demo:1"
        write_json(package / "binding.json", binding)
        path = self.path / "scoring.json"
        write_json(path, scoring)
        with self.assertRaisesRegex(ValueError, "mapping"):
            import_review(package, path, "ai")

    def test_disputes_are_limited_to_the_requested_group(self):
        run = self.harness.agent_run()
        package, scoring = self.scored_package(run)
        path = self.path / "scoring.json"
        write_json(path, scoring)
        import_review(package, path, "ai")
        scoring["samples"] = [scoring["samples"][1]]
        scoring["samples"][0]["criteria"][0]["verdict"] = "fail"
        write_json(path, scoring)
        import_review(package, path, "human")
        self.assertEqual(semantic_summary(run, read_rows(run / "results.jsonl")[:1])["disputed_samples"], 0)

    def test_package_rubric_must_match_frozen_run_even_if_local_hash_is_edited(self):
        package, scoring = self.scored_package(self.harness.agent_run())
        public = read_json(package / "package.json")
        public["samples"][0]["criteria"][0]["text"] = "edited criterion"
        write_json(package / "package.json", public)
        binding = read_json(package / "binding.json")
        binding["package_sha256"] = file_hash(package / "package.json")
        scoring["package_sha256"] = binding["package_sha256"]
        write_json(package / "binding.json", binding)
        path = self.path / "scoring.json"
        write_json(path, scoring)
        with self.assertRaisesRegex(ValueError, "materials"):
            import_review(package, path, "ai")

    def test_agent_interrupt_keeps_partial_sample_and_phase_denominators(self):
        original = LiveProvider.begin
        def interrupt(provider, session, content, number):
            if number == 2:
                raise KeyboardInterrupt
            return original(provider, session, content, number)
        with patch.object(LiveProvider, "begin", interrupt), self.assertRaises(KeyboardInterrupt):
            self.harness.agent_run()
        run = self.path / "agent"
        rows = read_rows(run / "results.jsonl")
        self.assertEqual(rows[0]["execution_status"], "interrupted")
        self.assertEqual(len(rows[0]["turns"]), 1)
        self.assertEqual(rows[0]["model_calls"], 1)
        self.assertEqual([r["execution_status"] for r in rows[1:]], ["not_started", "not_started"])
        report = make_report([run], self.path / "report")
        groups = read_json(report / "summary.json")["runs"][0]["groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["measure"], "timing")
        self.assertEqual(groups[0]["total"], 3)



class LivePolicyTests(unittest.TestCase):
    def test_http_slow_stream_has_an_absolute_deadline(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        stopped = threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.end_headers()
                try:
                    self.wfile.write(b'{')
                    while not stopped.wait(0.01):
                        self.wfile.write(b' ')
                        self.wfile.flush()
                    self.wfile.write(b'}')
                except OSError:
                    pass
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        guard = threading.Timer(2, stopped.set)
        guard.start()
        try:
            client = QwenClient({"base_url": f"http://127.0.0.1:{server.server_port}/v1", "model": "fake"})
            with self.assertRaises(TimeoutError):
                client.chat([{"role": "user", "content": "x"}], [], remaining=0.3)
            self.assertFalse(stopped.is_set())
        finally:
            stopped.set()
            guard.cancel()
            guard.join()
            server.shutdown()
            thread.join(timeout=2)

    def provider(self, policy, calls=None):
        calls = calls or [{"id": "t1", "type": "function", "function": {
            "name": "search_story", "arguments": '{"query":"x"}'}}]
        def transport(*args):
            return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": calls},
                                 "finish_reason": "tool_calls"}]}
        client = QwenClient({"base_url": "http://127.0.0.1:9999/v1", "model": "fake"}, transport=transport)
        provider = LiveProvider(client, [{"id": "d", "title": "x", "text": "x"}], policies=policy)
        provider.begin("s", "x", 1)
        messages = [{"role": "user", "content": "x"}]
        reply = provider.provide("model", {"messages": deepcopy(messages)}, "s", 1)
        messages.append(reply["result"]["message"])
        return provider, messages

    def test_failed_tool_may_retry_within_declared_budget(self):
        provider, _ = self.provider({**POLICY, "max_tool_retries": 1})
        with patch.object(provider.index, "search", side_effect=[RuntimeError("synthetic"), []]):
            payload = {"call_id": "t1", "name": "search_story", "arguments": {"query": "x"}}
            self.assertEqual(provider.provide("tool", payload, "s", 1)["error"]["code"], "tool_exception")
            self.assertTrue(provider.provide("tool", payload, "s", 1)["ok"])
        self.assertFalse(provider.violations)

    def test_terminate_policy_cannot_continue_model_recovery(self):
        provider, messages = self.provider({**POLICY, "tool_error": "terminate"})
        with patch.object(provider.index, "search", side_effect=RuntimeError("synthetic")):
            result = provider.provide("tool", {"call_id": "t1", "name": "search_story", "arguments": {"query": "x"}}, "s", 1)
        messages.append({"role": "tool", "tool_call_id": "t1", "content": json.dumps(result)})
        response = provider.provide("model", {"messages": messages}, "s", 1)
        self.assertFalse(response["ok"])
        self.assertIn("termination_policy_violated", provider.violations)

    def test_parallel_declared_tools_are_not_serialized_by_provider(self):
        calls = [{"id": f"t{i}", "type": "function", "function": {"name": "search_story", "arguments": '{"query":"x"}'}} for i in (1, 2)]
        provider, _ = self.provider({**POLICY, "tool_execution": "parallel"}, calls)
        barrier = threading.Barrier(2)
        def search(*args):
            barrier.wait(timeout=2)
            return []
        with patch.object(provider.index, "search", side_effect=search), ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(provider.provide, "tool", {"call_id": f"t{i}", "name": "search_story",
                       "arguments": {"query": "x"}}, "s", 3) for i in (1, 2)]
            self.assertTrue(all(f.result()["ok"] for f in futures))
