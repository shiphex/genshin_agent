from copy import deepcopy
import json
import unittest
from Benchmarks.support.common import read_json, read_rows, write_json, file_hash
from Benchmarks.support.testing import ReplayHarness
from Benchmarks.agent_story.providers import QwenClient, SYSTEM
from Benchmarks.agent_story.runner import run_agent
from Benchmarks.agent_story.review import export_review, import_review
from Benchmarks.reports import make_report


class RunnerTests(ReplayHarness, unittest.TestCase):
    def agent_run(self):
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
        def transport(*args):
            return {"choices": [{"message": {"role": "assistant", "content": "scripted answer"}, "finish_reason": "stop"}]}
        client = QwenClient({"base_url": "http://127.0.0.1:9999/v1", "model": "fake"}, transport=transport)
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
