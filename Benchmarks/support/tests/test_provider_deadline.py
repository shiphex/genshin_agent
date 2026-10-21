import sys
import threading
import unittest
from Benchmarks.support.common import write_json
from Benchmarks.support.protocol import Worker
from Benchmarks.support.testing import FIXTURE, ReplayHarness


class ProviderDeadlineTests(ReplayHarness, unittest.TestCase):
    def test_blocked_provider_cannot_hold_turn_cleanup_past_deadline(self):
        import sys
        tape = self.root / "blocked.json"
        write_json(tape, [{"actions": [{"provider": "tool", "payload": {}}],
                           "result": {"status": "completed", "content": "x"}}])
        release, exited = threading.Event(), threading.Event()
        def provide(*args):
            release.wait(timeout=5)
            exited.set()
            return {"ok": True}
        guard = threading.Timer(2, release.set)
        guard.start()
        try:
            with Worker([sys.executable, "-B", str(FIXTURE), "--tape", str(tape)], self.root / "stderr.txt") as worker:
                worker.request("init", "control", {"protocol_version": 1})
                with self.assertRaises(TimeoutError):
                    worker.request("turn", "s", {}, provider=provide, timeout=0.05)
                self.assertFalse(release.is_set(), "transport waited for the provider instead of its deadline")
        finally:
            release.set()
            guard.cancel()
            guard.join()
            self.assertTrue(exited.wait(timeout=2))
