"""Configuration behavior uses synthetic files, never local weights or a live model."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rag.scripts import local_model_config as config
from rag.scripts import evaluate_rag_mvp as evaluate


class LocalModelConfigTests(unittest.TestCase):
    def settings(self):
        return {"base_url": "http://127.0.0.1:8000/v1", "model": "story-model", "top_k": 5,
                "generation": {"temperature": 1.0, "top_k": 20, "top_p": 0.95, "min_p": 0},
                "profile": "standard", "profiles": {
                    "simple": {"enable_thinking": False, "thinking_budget_tokens": 0,
                               "max_tokens": 1024, "timeout": 30},
                    "standard": {"enable_thinking": True, "thinking_budget_tokens": 1024,
                                 "max_tokens": 3072, "timeout": 90},
                    "deep": {"enable_thinking": True, "thinking_budget_tokens": 8192,
                             "max_tokens": 12288, "timeout": 600}},
                "llama_cpp": {"ctx_size": 16384, "parallel": 1, "model_path": None, "device": None}}

    def test_profiles_separate_retrieval_from_sampling_and_keep_launch_details_out(self):
        settings = self.settings()
        settings["llama_cpp"].update(model_path="private-model.gguf", executable="private-server")
        standard = config.api_config(settings)
        deep = config.api_config(settings, "deep")
        self.assertEqual(standard["top_k"], 5)
        options = config.generation_options(standard)
        self.assertEqual(options["top_k"], 20)
        self.assertEqual(options["thinking_budget_tokens"], 1024)
        self.assertTrue(options["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual((deep["max_tokens"], deep["timeout"]), (12288, 600))
        self.assertNotIn("private", json.dumps(deep))
        self.assertNotIn("llama_cpp", standard)
        self.assertNotIn("profiles", standard)
        self.assertEqual(settings["profile"], "standard")

    def test_local_overlay_merges_nested_values_without_modifying_shared_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "api.json"
            original = json.dumps(self.settings())
            path.write_text(original, encoding="utf-8")
            local = path.with_name("api.local.json")
            local.write_text(json.dumps({"llama_cpp": {"model_path": "private.gguf", "device": "test-gpu"}}))
            settings = config.load_settings(path)
            self.assertEqual(settings["llama_cpp"]["ctx_size"], 16384)
            self.assertEqual(settings["llama_cpp"]["model_path"], "private.gguf")
            self.assertNotIn("private", json.dumps(config.load_api_config(path)))
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_legacy_config_keeps_thinking_disabled_without_requiring_a_server_block(self):
        api = config.api_config({"base_url": "http://localhost:8000/v1", "max_tokens": 1536, "top_k": 5})
        options = config.generation_options(api)
        self.assertFalse(options["chat_template_kwargs"]["enable_thinking"])
        self.assertNotIn("thinking_budget_tokens", options)
        self.assertNotIn("top_k", options)

    def test_unknown_profile_fields_and_invalid_budget_fail_before_any_request(self):
        for mutation in (lambda s: s.update(api_key="secret"),
                         lambda s: s["llama_cpp"].update(password="secret"),
                         lambda s: s["generation"].update(access_token="secret"),
                         lambda s: s["profiles"]["standard"].update(max_tokens=1024),
                         lambda s: s["profiles"]["standard"].update(thinking_budget_tokens=True),
                         lambda s: s["generation"].update(temperature=float("nan")),
                         lambda s: s["profiles"]["standard"].update(enable_thinking="true")):
            settings = self.settings()
            mutation(settings)
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                config.api_config(settings)
        with self.assertRaises(ValueError):
            config.api_config(self.settings(), "typo")

    def test_local_overlay_rejects_secrets_instead_of_silently_discarding_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "api.json"
            path.write_text(json.dumps(self.settings()))
            path.with_name("api.local.json").write_text('{"api_key":"secret-test"}')
            with self.assertRaises(ValueError):
                config.load_api_config(path)

    def test_rag_request_uses_selected_thinking_budget_and_returns_only_final_content(self):
        received = []
        def transport(settings, endpoint, payload):
            received.append(payload)
            return {"choices": [{"message": {"content": "final answer", "reasoning_content": "private thought"},
                                 "finish_reason": "stop"}]}
        with patch.object(evaluate, "api_request", side_effect=transport):
            answer = evaluate.chat(config.api_config(self.settings()), [{"role": "user", "content": "test"}])
        self.assertEqual(answer["text"], "final answer")
        self.assertEqual(received[0]["thinking_budget_tokens"], 1024)
        self.assertEqual(received[0]["temperature"], 1.0)
        self.assertEqual(received[0]["top_k"], 20)
        self.assertTrue(received[0]["chat_template_kwargs"]["enable_thinking"])


if __name__ == "__main__":
    unittest.main()
