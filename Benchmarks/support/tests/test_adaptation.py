from copy import deepcopy
import unittest

from Benchmarks.support.common import write_json
from Benchmarks.support.execution import load_adapters
from Benchmarks.support.testing import ReplayHarness


ADAPTATION = {
    "target": "synthetic-sdk 1.0",
    "ownership": {"loop": "candidate", "history": "shared", "recovery": "adapter"},
    "changes": [{"area": "history", "default_behavior": "SDK retains structured items",
                 "adapted_behavior": "Convert items to chat messages", "reason": "fixed-history interface"}],
    "effort_notes": "Synthetic declaration, not a measured implementation cost.",
}


class AdaptationTests(ReplayHarness, unittest.TestCase):
    def load(self, record):
        adapter = self.adapter([])
        adapter.update(record)
        path = self.root / "adapters.json"
        write_json(path, {"schema_version": 1, "adapters": [adapter]})
        return load_adapters(path)

    def test_optional_record_and_explicit_no_changes_are_preserved(self):
        self.assertNotIn("adaptation", self.load({})[0])
        record = {**ADAPTATION, "changes": []}
        adapters = self.load({"adaptation": record})
        self.assertEqual(adapters[0]["adaptation"], record)

    def test_invalid_records_identify_adapter_and_field(self):
        invalid = [(None, "adaptation"), ({}, "target"),
                   ({**ADAPTATION, "target": " "}, "target"),
                   ({**ADAPTATION, "ownership": []}, "ownership"),
                   ({**ADAPTATION, "ownership": {"loop": "candidate"}}, "ownership.history"),
                   ({**ADAPTATION, "ownership": {**ADAPTATION["ownership"], "history": "native"}}, "ownership.history"),
                   ({**ADAPTATION, "changes": {}}, "changes"),
                   ({**ADAPTATION, "changes": [None]}, "changes[0]"),
                   ({**ADAPTATION, "changes": [{"area": "history"}]}, "changes[0].default_behavior"),
                   ({**ADAPTATION, "effort_notes": " "}, "effort_notes"),
                   ({**ADAPTATION, "unexpected": "x"}, "unexpected")]
        for record, field in invalid:
            with self.subTest(field=field):
                with self.assertRaises(ValueError) as caught:
                    self.load({"adaptation": deepcopy(record)})
                self.assertIn("fixture", str(caught.exception))
                self.assertIn(field, str(caught.exception))
