import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rag.scripts import evaluate_rag_mvp as evaluate


class EvaluationTests(unittest.TestCase):
    def test_evaluation_cannot_write_inside_a_raw_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "raw"
            (snapshot / "parsed").mkdir(parents=True)
            (snapshot / "pages").mkdir()
            original = snapshot / "original.json"
            original.write_text("original", encoding="utf-8")
            before = sorted(str(p.relative_to(snapshot)) for p in snapshot.rglob("*"))
            with self.assertRaises(ValueError):
                evaluate.validate_output_dir(snapshot / "reports", raw_root=snapshot)
            self.assertEqual(original.read_text(encoding="utf-8"), "original")
            self.assertEqual(sorted(str(p.relative_to(snapshot)) for p in snapshot.rglob("*")), before)

    def test_bigrams_do_not_cross_punctuation_and_ascii_words_are_matched(self):
        self.assertEqual(evaluate.tokenize("钟离，契约 QWEN 4B"), {"钟离", "契约", "qwen", "4b"})

    def test_retrieval_finds_evidence_and_does_not_pad_with_zero_matches(self):
        corpus = [{"id": "a", "title": "故事", "text": "归离原得名于归终与岩王的讨论。"},
                  {"id": "b", "title": "其他", "text": "蒙德的蒲公英。"}]
        self.assertEqual([x["id"] for x in evaluate.search("归离原得名", corpus)], ["a"])
        self.assertEqual(evaluate.search("nonsense", corpus), [])

    def test_multi_source_coverage_requires_every_evidence_group(self):
        result = evaluate.evidence_coverage([["a", "b"], ["c"]], [{"id": "b"}])
        self.assertEqual(result, {"covered_groups": 1, "total_groups": 2, "recall": 0.5, "all_covered": False})
        self.assertIsNone(evaluate.evidence_coverage([], []))

    def test_citation_ids_must_belong_to_context_and_faithfulness_is_not_auto_scored(self):
        result = evaluate.citation_audit("原文如此 [l01]，还有 [l99]。", [{"id": "l01"}])
        self.assertEqual(result["unknown_ids"], ["l99"])
        self.assertEqual(result["known_ids"], ["l01"])
        self.assertEqual(result["semantic_verdict"], "pending_human_review")

    def test_prompts_share_policy_and_never_leak_gold_answers(self):
        baseline = evaluate.make_messages("测试问题")
        rag = evaluate.make_messages("测试问题", [{"id": "l01", "title": "故事", "text": "只有原文"}])
        self.assertEqual(baseline[0], rag[0])
        self.assertNotIn("只有原文", str(baseline))
        self.assertIn("[l01]", str(rag))
        self.assertIn("分支", rag[0]["content"])

    def test_http_chat_uses_configured_local_api_and_rejects_empty_content(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                answer = "证据 [l01]" if len(seen) == 1 else ""
                self.wfile.write(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": answer}}]}).encode())
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = {"base_url": f"http://127.0.0.1:{server.server_port}/v1", "model": "local-test", "timeout": 5}
            answer = evaluate.chat(config, evaluate.make_messages("测试"))
            self.assertEqual(answer["text"], "证据 [l01]")
            self.assertEqual(answer["status"], "ok")
            self.assertEqual(seen[0]["model"], "local-test")
            self.assertEqual(seen[0]["chat_template_kwargs"], {"enable_thinking": False})
            with self.assertRaises(ValueError):
                evaluate.chat(config, evaluate.make_messages("测试"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_truncated_answers_are_preserved_but_not_reported_as_success(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"choices": [{"finish_reason": "length", "message": {
                    "content": "尚未完成 [l01]"}}], "usage": {"completion_tokens": 8}}).encode())
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = {"base_url": f"http://127.0.0.1:{server.server_port}/v1", "model": "test", "timeout": 5}
            question = {"id": "q", "category": "fact", "question": "契约", "expected_evidence": [["l01"]], "reference_answer": "参考"}
            corpus = [{"id": "l01", "title": "契约", "text": "证据", "source_file": "test.json", "source_pointer": ["/text"]}]
            results = evaluate.evaluate(corpus, [question], config)
            with tempfile.TemporaryDirectory() as output:
                root = Path(output)
                (root / 'rag').mkdir()
                (root / 'rag/catalog.json').write_text(json.dumps({'schema_version': 2,
                    'baseline_id': 'test', 'datasets': {}, 'files': {}}), encoding='utf-8')
                with patch.object(evaluate, 'PROJECT', root):
                    reserved = evaluate.artifact_catalog.reserve_output(root, 'model')
                    summary = evaluate.write_report(reserved, results, config, False)
            self.assertEqual(results[0]["answers"]["rag"]["status"], "truncated")
            self.assertEqual(results[0]["answers"]["rag"]["text"], "尚未完成 [l01]")
            self.assertEqual(results[0]["answers"]["rag"]["finish_reason"], "length")
            self.assertEqual(summary["successful_model_calls"], 0)
            self.assertEqual(summary["truncated_model_calls"], 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_incomplete_http_response_does_not_lose_previous_answers(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                requests.append(self.path)
                self.send_response(200)
                if len(requests) == 2:
                    self.send_header("Content-Length", "999")
                    self.end_headers()
                    self.wfile.write(b"{")
                    self.close_connection = True
                else:
                    self.end_headers()
                    self.wfile.write(json.dumps({"choices": [{"finish_reason": "stop", "message": {
                        "content": "已完成 [l01]"}}]}).encode())
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = {"base_url": f"http://127.0.0.1:{server.server_port}/v1", "model": "test", "timeout": 5}
            corpus = [{"id": "l01", "title": "契约", "text": "原文"}]
            question = {"id": "q", "category": "fact", "question": "契约", "expected_evidence": [["l01"]], "reference_answer": "参考"}
            results = evaluate.evaluate(corpus, [question], config)
            self.assertEqual(results[0]["answers"]["baseline"]["text"], "已完成 [l01]")
            self.assertEqual(results[0]["answers"]["rag"]["status"], "error")
            self.assertEqual(results[0]["answers"]["rag"]["error"], "IncompleteRead")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
