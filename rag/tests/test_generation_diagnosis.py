"""Behavior checks for controlled evidence/sampling diagnosis."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evaluate_rag_mvp as evaluate


def response():
    return {"choices": [{"finish_reason": "stop", "message": {"content": "answer [a]"}}]}


class GenerationOverridesTests(unittest.TestCase):
    def test_optional_sampling_changes_outbound_request_without_changing_defaults(self):
        config = {"base_url": "http://127.0.0.1:8000/v1", "model": "local", "max_tokens": 1536}
        messages = [{"role": "user", "content": "evidence"}]
        calibrated = {"temperature": 0.7, "seed": 43, "top_p": 0.8, "top_k": 20,
                      "min_p": 0, "presence_penalty": 1.5, "frequency_penalty": 0, "repeat_penalty": 1}
        seen = []
        def request(cfg, endpoint, payload):
            seen.append(payload)
            return response()
        with patch.object(evaluate, "api_request", side_effect=request):
            old = evaluate.chat(config, messages)
            try:
                new = evaluate.chat(config, messages, generation=calibrated)
            except TypeError as exc:
                self.fail(f"chat does not support controlled sampling overrides: {exc}")
        self.assertEqual(seen[0], {"model": "local", "messages": messages, "stream": False,
                                  "temperature": 0, "seed": 42, "max_tokens": 1536,
                                  "chat_template_kwargs": {"enable_thinking": False}})
        self.assertEqual({k: seen[1][k] for k in calibrated}, calibrated)
        self.assertEqual(seen[1]["messages"], messages)
        self.assertEqual(seen[1]["max_tokens"], 1536)
        self.assertEqual(seen[1]["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(old, new)

    def test_unknown_override_cannot_replace_messages_model_or_credentials(self):
        with patch.object(evaluate, "api_request") as request:
            for key in ("messages", "model", "api_key", "max_tokens", "chat_template_kwargs"):
                try:
                    with self.assertRaises(ValueError):
                        evaluate.chat({"model": "local"}, [], generation={key: "bad"})
                except TypeError as exc:
                    self.fail(f"sampling whitelist is unavailable: {exc}")
            request.assert_not_called()


class DiagnosisRunnerTests(unittest.TestCase):
    def diagnosis(self):
        try:
            import diagnose_rag_generation
        except ModuleNotFoundError:
            self.fail("controlled diagnosis runner is not implemented")
        return diagnose_rag_generation

    def fixture(self):
        corpus = [
            {"id": "a", "title": "alpha", "text": "alpha retrieved evidence", "source_kind": "wiki_excerpt"},
            {"id": "b", "title": "beta", "text": "beta curated evidence", "source_kind": "wiki_excerpt"},
        ]
        cases = [{"id": f"q{i}", "question": "alpha", "category": "fact",
                  "curated_ids": ["b", "b"], "expected_evidence": [["b"]],
                  "checks": ["SECRET_REVIEW_CRITERION"], "reference_answer": "SECRET_REFERENCE_ANSWER"}
                 for i in range(6)]
        profiles = {"current": {"temperature": 0}, "calibrated": {"temperature": 0.7, "presence_penalty": 1.5}}
        return corpus, cases, profiles

    def test_matrix_keeps_evidence_fixed_and_never_leaks_reference_answer(self):
        module = self.diagnosis()
        trials = module.prepare_trials(*self.fixture())
        self.assertEqual(len(trials), 48)
        for i in range(6):
            own = [t for t in trials if t["question_id"] == f"q{i}"]
            self.assertEqual(len(own), 8)
            by = {c: [t for t in own if t["condition"] == c] for c in ("R0", "C0", "R1", "C1")}
            self.assertEqual([t["seed"] for t in by["R0"]], [42])
            self.assertEqual([t["seed"] for t in by["C0"]], [42])
            self.assertEqual([t["seed"] for t in by["R1"]], [42, 43, 44])
            self.assertEqual([t["seed"] for t in by["C1"]], [42, 43, 44])
            for t in by["R1"]:
                self.assertEqual(t["messages"], by["R0"][0]["messages"])
            for t in by["C1"]:
                self.assertEqual(t["messages"], by["C0"][0]["messages"])
                self.assertEqual(t["evidence_ids"], ["b"])
                self.assertEqual(t["evidence_coverage"]["recall"], 1)
            for t in own:
                self.assertNotIn("SECRET_", json.dumps(t["messages"]))
                self.assertEqual(t["generation"]["seed"], t["seed"])

    def test_bad_curated_id_or_missing_evidence_group_fails_before_api(self):
        module = self.diagnosis()
        corpus, cases, profiles = self.fixture()
        cases[0]["curated_ids"] = ["missing"]
        with self.assertRaises(ValueError):
            module.prepare_trials(corpus, cases, profiles)
        cases[0]["curated_ids"] = ["a"]
        with self.assertRaises(ValueError):
            module.prepare_trials(corpus, cases, profiles)

    def test_each_completed_answer_survives_interruption_and_outputs_are_not_overwritten(self):
        module = self.diagnosis()
        trials = module.prepare_trials(*self.fixture())[:3]
        calls = []
        def interrupted(config, messages, generation=None):
            calls.append(generation)
            if len(calls) == 2:
                raise KeyboardInterrupt()
            return {"text": "evidence [a]", "status": "ok", "finish_reason": "stop", "usage": {}}
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "diagnosis"
            with self.assertRaises(KeyboardInterrupt):
                module.run_trials(trials, {"model": "test", "max_tokens": 1536}, output, chat_fn=interrupted)
            saved = [json.loads(s) for s in (output / "results.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["answer"]["status"], "ok")
            self.assertEqual(len((output / "requests.jsonl").read_text(encoding="utf-8").splitlines()), 2)
            self.assertFalse((output / "summary.json").exists())
            with self.assertRaises(FileExistsError):
                module.run_trials(trials, {"model": "test"}, output, chat_fn=interrupted)
            self.assertEqual(len(calls), 2)

    def test_errors_and_truncation_are_retained_and_separate_from_semantic_quality(self):
        module = self.diagnosis()
        trials = module.prepare_trials(*self.fixture())[:3]
        answers = [OSError("secret response body"),
                   {"text": "cut off", "status": "truncated", "finish_reason": "length", "usage": {}},
                   {"text": "answer [a]", "status": "ok", "finish_reason": "stop", "usage": {}}]
        def chat(config, messages, generation=None):
            value = answers.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "diagnosis"
            summary = module.run_trials(trials, {"model": "test", "max_tokens": 1536}, output, chat_fn=chat)
            self.assertEqual(summary["call_statuses"], {"error": 1, "truncated": 1, "ok": 1})
            self.assertEqual(summary["semantic_evaluation"], "pending_source_review")
            self.assertNotIn("secret response body", (output / "results.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(len((output / "results.jsonl").read_text(encoding="utf-8").splitlines()), 3)

    def test_valid_source_ranges_cannot_hide_fabricated_curated_text(self):
        module = self.diagnosis()
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp)
            source_file = "parsed/characters/test.json"
            path = raw / source_file
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"story": "actual source"}), encoding="utf-8")
            anchor = {"source_file": source_file, "source_pointer": "/story",
                      "start": 0, "end": 6, "quote": "actual"}
            row = {"id": "a", "text": "actual source", "source_kind": "wiki_excerpt",
                   "source_file": source_file, "source_pointer": ["/story"],
                   "source_spans": [{"start": 0, "end": 13}]}
            case = {"id": "q", "curated_ids": ["a"], "expected_source_evidence": [[anchor]]}
            self.assertEqual(module.validate_sources([row], [case], raw)["reference_anchors_checked"], 1)
            tampered = {**row, "text": "fabricated unrelated replacement"}
            with self.assertRaises(ValueError):
                module.validate_sources([tampered], [case], raw)
            bad_retrieved = {**tampered, "id": "b", "source_kind": "wiki_compilation"}
            with self.assertRaises(ValueError):
                module.validate_sources([row, bad_retrieved], [case], raw, selected_ids=["b"])


if __name__ == "__main__":
    unittest.main()
