from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from Benchmarks.support.common import RunStore, file_hash, read_json, write_json
from Benchmarks.agent_story.scenarios import load_scenarios, public_turns
from Benchmarks.agent_story.review import export_review, import_review, semantic_summary


class ForbiddenTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        questions = self.root / "rag/eval/questions.json"
        questions.parent.mkdir(parents=True)
        write_json(questions, {"questions": [{"id": "q1", "question": "synthetic question",
                                            "criteria": ["attribute the source"]}]})
        self.suite_path = self.root / "scenarios.json"
        write_json(self.suite_path, {"question_bank_sha256": file_hash(questions), "scenarios": [{
            "id": "demo", "group": "boundary", "question_ids": ["q1"],
            "turns": [{"question_id": "q1"}, {"content": "synthetic followup"}],
            "required_criteria": ["state the supplied fact"],
            "forbidden": ["invent a name", "invent a date"]}]})

    def scene(self):
        return load_scenarios(self.root, self.suite_path)["scenarios"][0]

    def review_package(self, scene=None, status="completed"):
        scene = self.scene() if scene is None else scene
        store = RunStore(self.root / "run", {"suite": "agent"})
        write_json(store.path / "materials.json", {"demo": {"scenario": scene, "frozen_sources": []}})
        row = {"sample_id": "synthetic:demo:1", "adapter_id": "synthetic", "scenario_id": "demo",
               "repeat": 1, "execution_status": status,
               "turns": [{"content": "synthetic first answer"}, {"content": "synthetic followup answer"}]}
        store.result(row)
        store.finish("completed")
        self.run, self.rows = store.path, [row]
        self.frozen_hashes = {name: file_hash(self.run / name) for name in
                              ("manifest.json", "materials.json", "results.jsonl", "trace.jsonl")}
        self.package = export_review(self.run, self.root / "review")
        scoring = read_json(self.package / "review-template.json")
        scoring["reviewer"] = "synthetic-reviewer"
        for criterion in scoring["samples"][0]["criteria"]:
            criterion.update(verdict="pass", rationale="Synthetic review only.", evidence_refs=["turn:2"])
        return scoring

    def import_scoring(self, scoring):
        path = self.root / "scored.json"
        write_json(path, scoring)
        import_review(self.package, path, "ai")
        return semantic_summary(self.run, self.rows)["ai"]

    def test_each_forbidden_constraint_is_required_without_renumbering_existing_criteria(self):
        scene = self.scene()
        self.assertEqual([c["id"] for c in scene["criteria"]], ["c1", "q1-c1", "f1", "f2"])
        self.assertEqual([c["text"] for c in scene["criteria"][:2]],
                         ["state the supplied fact", "attribute the source"])
        for criterion, forbidden in zip(scene["criteria"][2:], ["invent a name", "invent a date"]):
            self.assertTrue(criterion["required"])
            self.assertIn(forbidden, criterion["text"])
        self.assertEqual(public_turns(scene), [{"content": "synthetic question"},
                                              {"content": "synthetic followup"}])

    def test_empty_forbidden_adds_no_criteria(self):
        suite = read_json(self.suite_path)
        suite["scenarios"][0]["forbidden"] = []
        write_json(self.suite_path, suite)
        self.assertEqual([c["id"] for c in self.scene()["criteria"]], ["c1", "q1-c1"])

    def test_export_includes_all_forbidden_verdicts(self):
        self.review_package()
        template = read_json(self.package / "review-template.json")
        self.assertEqual([c["id"] for c in template["samples"][0]["criteria"]],
                         ["c1", "q1-c1", "f1", "f2"])
        self.assertTrue(all(c["verdict"] == "uncertain" for c in template["samples"][0]["criteria"]))

    def test_import_rejects_an_omitted_forbidden_verdict(self):
        scoring = self.review_package()
        scoring["samples"][0]["criteria"] = [c for c in scoring["samples"][0]["criteria"] if c["id"] != "f1"]
        with self.assertRaisesRegex(ValueError, "complete sample rubric"):
            self.import_scoring(scoring)

    def test_forbidden_fail_blocks_semantic_pass(self):
        self.assert_forbidden_summary("fail", "failed")

    def test_forbidden_uncertain_blocks_semantic_pass(self):
        self.assert_forbidden_summary("uncertain", "uncertain")

    def assert_forbidden_summary(self, verdict, expected):
        scoring = self.review_package()
        criteria = {c["id"]: c for c in scoring["samples"][0]["criteria"]}
        self.assertIn("f1", criteria)
        criteria["f1"]["verdict"] = verdict
        summary = self.import_scoring(scoring)
        self.assertEqual(summary[expected], 1)
        self.assertEqual(summary["passed"], 0)

    def test_all_constraints_pass_requires_completed_execution(self):
        scoring = self.review_package(status="incomplete")
        summary = self.import_scoring(scoring)
        self.assertEqual(summary["passed"], 0)
        self.assertEqual(summary["uncertain"], 1)

    def test_all_constraints_pass_with_completed_execution(self):
        summary = self.import_scoring(self.review_package())
        self.assertEqual(summary["passed"], 1)

    def test_existing_frozen_rubric_is_not_augmented_or_rewritten(self):
        scene = deepcopy(self.scene())
        scene["criteria"] = [{"id": "c1", "text": "state the supplied fact", "required": True},
                             {"id": "q1-c1", "text": "attribute the source", "required": True}]
        scoring = self.review_package(scene)
        self.assertEqual([c["id"] for c in scoring["samples"][0]["criteria"]], ["c1", "q1-c1"])
        self.import_scoring(scoring)
        self.assertEqual(read_json(self.package / "package.json")["samples"][0]["forbidden"],
                         ["invent a name", "invent a date"])
        self.assertEqual(self.frozen_hashes, {name: file_hash(self.run / name) for name in self.frozen_hashes})
