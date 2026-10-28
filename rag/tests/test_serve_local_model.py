"""Build launch arguments without starting a server or requiring a GPU."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rag.scripts import serve_local_model as serve


class ServerCommandTests(unittest.TestCase):
    def settings(self):
        return {"base_url": "http://127.0.0.1:8000/v1", "model": "story-test", "max_tokens": 3072,
                "enable_thinking": True, "thinking_budget_tokens": 1024,
                "llama_cpp": {"executable": "private/server.exe", "model_path": "private/model.gguf",
                              "device": "test-device", "ctx_size": 16384, "gpu_layers": "all",
                              "parallel": 1, "batch_size": 256, "ubatch_size": 128,
                              "flash_attn": "auto", "cache_type_k": "f16", "cache_type_v": "f16"}}

    def test_launch_matches_client_endpoint_and_explicit_single_device_text_only_settings(self):
        settings = self.settings()
        command = serve.server_command(settings)
        self.assertEqual(command[0], "private/server.exe")
        for flag, value in {"--model": "private/model.gguf", "--host": "127.0.0.1", "--port": "8000",
                            "--alias": "story-test", "--device": "test-device", "--split-mode": "none",
                            "--ctx-size": "16384", "--parallel": "1", "--batch-size": "256",
                            "--ubatch-size": "128", "--reasoning-budget": "1024", "--fit": "off"}.items():
            self.assertEqual(command[command.index(flag) + 1], value)
        self.assertIn("--no-mmproj", command)
        self.assertIn("--offline", command)
        self.assertNotIn("--hf-repo", command)

    def test_rejects_missing_private_settings_remote_endpoint_and_incompatible_sizes(self):
        mutations = (lambda s: s["llama_cpp"].update(model_path=None),
                     lambda s: s["llama_cpp"].update(device=None),
                     lambda s: s.update(base_url="http://example.invalid:8000/v1"),
                     lambda s: s.update(base_url="http://127.0.0.1:8000/v1?token=secret"),
                     lambda s: s["llama_cpp"].update(ctx_size=1024),
                     lambda s: s["llama_cpp"].update(ubatch_size=512),
                     lambda s: s["llama_cpp"].update(cache_type_k="typo"))
        for mutate in mutations:
            settings = self.settings()
            mutate(settings)
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                serve.server_command(settings)

    def test_dry_run_checks_files_but_never_starts_process_or_prints_private_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.settings()
            executable = Path(tmp) / "private-server.exe"
            model = Path(tmp) / "private-model.gguf"
            executable.touch()
            model.touch()
            settings["llama_cpp"].update(executable=str(executable), model_path=str(model))
            path = Path(tmp) / "api.json"
            path.write_text(json.dumps(settings))
            output = io.StringIO()
            with patch.object(serve.subprocess, "run") as start, contextlib.redirect_stdout(output):
                self.assertEqual(serve.main(["--config", str(path), "--dry-run"]), 0)
            start.assert_not_called()
            self.assertNotIn(tmp, output.getvalue())
            self.assertNotIn("test-device", output.getvalue())
            self.assertIn("--ctx-size", output.getvalue())


if __name__ == "__main__":
    unittest.main()
