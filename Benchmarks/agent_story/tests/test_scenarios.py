from pathlib import Path
import tempfile
import unittest
from Benchmarks.support.common import ROOT
from Benchmarks.agent_story.scenarios import load_scenarios, public_turns


class ScenarioTests(unittest.TestCase):
    def test_frozen_scene_quotas_and_reference_material_never_leak(self):
        suite = load_scenarios(ROOT)
        self.assertEqual(len(suite["scenarios"]), 16)
        self.assertEqual([sum(s["group"] == g for s in suite["scenarios"])
                          for g in ("tools", "memory", "boundary")], [5, 6, 5])
        for scene in suite["scenarios"]:
            public = public_turns(scene)
            self.assertTrue(scene["criteria"])
            self.assertFalse({"answer", "criteria", "forbidden", "reference_material"}
                             & set(public[0]))
            if scene["group"] == "memory":
                self.assertIn(len(public), range(2, 5))

    def test_changed_question_fingerprint_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "rag/eval").mkdir(parents=True)
            (root / "rag/eval/questions.json").write_text('{"questions": []}')
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                load_scenarios(root)
