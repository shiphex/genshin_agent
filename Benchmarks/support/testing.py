"""Finite replay setup shared by offline Core and story tests."""
import sys
import tempfile
from pathlib import Path
from .common import BENCH, write_json

POLICY = {"tool_error": "recover", "context": "truncate", "tool_execution": "serial", "max_tool_retries": 0}
FIXTURE = BENCH / "support/replay_worker.py"


class ReplayHarness:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def adapter(self, tape, identity="fixture"):
        path = self.root / f"{identity}.json"
        write_json(path, tape)
        return {"id": identity, "command": [sys.executable, "-B", str(FIXTURE), "--tape", str(path)],
                "policies": dict(POLICY), "fixture_only": True, "identity": {"revision": "test", "files": [str(path), str(FIXTURE)]}}
