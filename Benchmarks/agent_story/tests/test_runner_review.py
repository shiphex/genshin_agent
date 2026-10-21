from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from Benchmarks.support.common import read_json, read_rows, write_json, file_hash
from Benchmarks.support.testing import ReplayHarness
from Benchmarks.agent_story.providers import QwenClient, SYSTEM
from Benchmarks.agent_story.runner import run_agent
from Benchmarks.agent_story.review import export_review, import_review
from Benchmarks.reports import make_report
from Benchmarks.support.protocol import ProtocolError, ProviderDeadlineError


class RunnerTests(ReplayHarness, unittest.TestCase):
    def agent_run(self, adaptation=None, mutate=None, transport=None):
        scene = {"id": "demo", "group": "memory", "title": "synthetic", "question_ids": [],
                 "reference_material": [], "criteria": [{"id": "c1", "text": "use supplied evidence", "required": True}],
                 "forbidden": [], "turns": [{"content": "first"}, {"content": "followup"}]}
        corpus = [{"id": "doc1", "title": "甘雨", "text": "synthetic evidence", "source_file": "parsed/a.json",
                   "source_pointer": ["/text"], "source_kind": "wiki_excerpt"}]
        tape, history = [], [{"role": "system", "content": SYSTEM}]
        for text in ("first", "followup"):
            history.append({"role": "user", "content": text})
            tape.append({"actions": [{"provider": "model", "payload": {"messages": deepcopy(history)}}],
                         "result": {"status": "completed", "content": "scripted answer"}})
            history.append({"role": "assistant", "content": "scripted answer"})
        adapter = self.adapter({"demo": tape})
        if adaptation is not None:
            adapter["adaptation"] = adaptation
        if mutate:
            mutate(tape)
            write_json(self.root / "fixture.json", {"demo": tape})
        def default_transport(*args):
            return {"choices": [{"message": {"role": "assistant", "content": "scripted answer"}, "finish_reason": "stop"}]}
        client = QwenClient({"base_url": "http://127.0.0.1:9999/v1", "model": "fake"}, transport=transport or default_transport)
        return run_agent([adapter], self.root / "agent", {"scenarios": [scene]}, corpus, client,
                         raw_root=self.root, repeats=3, preflight=False)

    def test_agent_repeats_are_clean_and_usage_is_not_fabricated(self):
        path = self.agent_run()
        rows = read_rows(path / "results.jsonl")
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r["execution_status"] == "completed" for r in rows))
        self.assertTrue(all(len(r["turns"]) == 2 for r in rows))
        self.assertTrue(all(r["usage_totals"]["total_tokens"] is None for r in rows))
        self.assertEqual([r["repeat"] for r in rows], [1, 2, 3])

    def test_profile_and_adaptation_survive_run_without_entering_review_package(self):
        adaptation = {"target": "PRIVATE_SYNTHETIC_SDK 1.0", "ownership": {
            "loop": "candidate", "history": "adapter", "recovery": "shared"}, "changes": [],
            "effort_notes": "PRIVATE_SYNTHETIC_EFFORT"}
        run = self.agent_run(adaptation=adaptation)
        manifest = read_json(run / "manifest.json")
        self.assertEqual(manifest.get("evaluation_profile"), "fixed-history-v0")
        self.assertEqual(manifest["adapters"][0]["adaptation"], adaptation)
        self.assertEqual([r.get("conformance_status") for r in read_rows(run / "results.jsonl")], ["passed"] * 3)
        package = export_review(run, self.root / "private-review")
        for name in ("package.json", "review-template.json"):
            text = (package / name).read_text(encoding="utf-8")
            self.assertNotIn("PRIVATE_SYNTHETIC", text)
            self.assertNotIn("adaptation", text)

    def test_story_still_rejects_summarized_history(self):
        def mutate(tape):
            tape[1]["actions"][0]["payload"]["messages"] = [{"role": "user", "content": "summary"}]
        run = self.agent_run(mutate=mutate)
        for row in read_rows(run / "results.jsonl"):
            self.assertEqual(row.get("conformance_status"), "failed")
            self.assertEqual(row["execution_status"], "incomplete")
            self.assertIn("conversation_changed", row["violations"])

    def test_story_protocol_error_is_distinct_from_timeout(self):
        for error, expected in ((ProtocolError("bad ID"), "failed"), (TimeoutError("wait"), "not_evaluated")):
            with self.subTest(error=type(error).__name__):
                # Each run needs a new exclusive directory.
                with tempfile.TemporaryDirectory() as tmp:
                    original_root = self.root
                    self.root = Path(tmp)
                    try:
                        with patch("Benchmarks.agent_story.runner._worker", side_effect=error):
                            run = self.agent_run()
                        rows = read_rows(run / "results.jsonl")
                        self.assertTrue(all(r.get("conformance_status") == expected for r in rows))
                        self.assertTrue(all(r["execution_status"] == "failed" for r in rows))
                    finally:
                        self.root = original_root

    def test_model_service_failure_is_not_a_conformance_failure(self):
        def mutate(tape):
            tape[0]["result"] = {"status": "failed", "content": ""}
        def transport(*args):
            raise TimeoutError("synthetic model service failure")
        run = self.agent_run(mutate=mutate, transport=transport)
        for row in read_rows(run / "results.jsonl"):
            self.assertEqual(row.get("conformance_status"), "not_evaluated")
            self.assertEqual(row["execution_status"], "incomplete")
            self.assertEqual(row["violations"], [])
            self.assertEqual(row["model_failed"], 1)

    def test_cleanup_wrapper_preserves_protocol_evidence_and_stops_story_run(self):
        for cause, expected in ((ProtocolError("bad session"), "failed"),
                                (TimeoutError("provider wait"), "not_evaluated")):
            with self.subTest(cause=type(cause).__name__), tempfile.TemporaryDirectory() as tmp:
                original_root = self.root
                self.root = Path(tmp)
                try:
                    wrapped = ProviderDeadlineError("provider exceeded cleanup")
                    wrapped.__cause__ = cause
                    with patch("Benchmarks.agent_story.runner._worker", side_effect=wrapped), self.assertRaises(ProviderDeadlineError):
                        self.agent_run()
                    rows = read_rows(self.root / "agent/results.jsonl")
                    self.assertEqual(rows[0].get("conformance_status"), expected)
                    self.assertEqual(rows[0]["error"], "ProviderDeadlineError")
                    self.assertEqual([r["execution_status"] for r in rows[1:]], ["not_started"] * 2)
                    self.assertEqual([r.get("conformance_status") for r in rows[1:]], ["not_evaluated"] * 2)
                finally:
                    self.root = original_root

    def test_legacy_run_review_import_is_read_only(self):
        run = self.agent_run()
        manifest = read_json(run / "manifest.json")
        manifest.pop("layout_version")
        write_json(run / "manifest.json", manifest)
        package = export_review(run, self.root / "legacy-package")
        before = {p.relative_to(run): file_hash(p) for p in run.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(ValueError, "read-only"):
            import_review(package, package / "review-template.json", "ai")
        self.assertEqual(before, {p.relative_to(run): file_hash(p) for p in run.rglob("*") if p.is_file()})

    def test_pi_export_import_preserves_ai_and_human_and_validates_binding(self):
        run = self.agent_run()
        package = export_review(run, self.root / "review")
        public = read_json(package / "package.json")
        template = read_json(package / "review-template.json")
        self.assertNotIn("fixture", json.dumps(public))
        for sample in template["samples"]:
            for criterion in sample["criteria"]:
                criterion.update(verdict="pass", rationale="Synthetic demonstration only.", evidence_refs=["turn:1"])
        template["reviewer"] = "third-party-ai"
        input_path = self.root / "scoring.json"
        write_json(input_path, template)
        ai = import_review(package, input_path, "ai")
        template["reviewer"] = "human-reviewer"
        template["samples"][0]["criteria"][0]["verdict"] = "uncertain"
        write_json(input_path, template)
        human = import_review(package, input_path, "human")
        self.assertTrue(ai.exists() and human.exists())
        report = make_report([run], self.root / "report")
        summary = read_json(report / "summary.json")["runs"][0]
        self.assertEqual(summary["semantic"]["ai"]["passed"], 3)
        self.assertEqual(summary["semantic"]["human"]["uncertain"], 1)
        self.assertEqual(summary["groups"][0]["semantic"]["ai"]["passed"], 3)
        self.assertEqual(summary["user_acceptance"], "not_evaluated")
        with (run / "trace.jsonl").open("a") as handle:
            handle.write('{}\n')
        with self.assertRaisesRegex(ValueError, "identity"):
            import_review(package, input_path, "ai")

    def test_review_rejects_unknown_criterion_and_evidence(self):
        package = export_review(self.agent_run(), self.root / "review")
        template = read_json(package / "review-template.json")
        template["reviewer"] = "ai"
        for sample in template["samples"]:
            for criterion in sample["criteria"]:
                criterion.update(verdict="pass", rationale="reason", evidence_refs=["source:absent"])
        path = self.root / "bad.json"
        write_json(path, template)
        with self.assertRaisesRegex(ValueError, "evidence"):
            import_review(package, path, "ai")
        template["samples"][0]["criteria"][0]["id"] = "invented"
        write_json(path, template)
        with self.assertRaises(ValueError):
            import_review(package, path, "ai")
