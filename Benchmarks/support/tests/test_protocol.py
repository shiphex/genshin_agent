import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import psutil
from Benchmarks.support.protocol import Worker, ProtocolError
from Benchmarks.support.testing import FIXTURE


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)

    def worker(self, mode="normal", tape=None, child=False):
        worker_path = self.path / str(len(list(self.path.iterdir())))
        worker_path.mkdir()
        tape_path = worker_path / "tape.json"
        tape_path.write_text(json.dumps(tape or [{"result": {"status": "completed", "content": "ok"}}]))
        command = [sys.executable, "-B", str(FIXTURE), "--tape", str(tape_path), "--mode", mode]
        if child:
            command += ["--child-pid", str(self.path / "child.pid")]
        worker = Worker(command, worker_path / "stderr.txt", timeout=3)
        self.addCleanup(worker.close)
        worker.request("init", "control", {"protocol_version": 1})
        return worker

    def test_roundtrip_and_shutdown_release_handles(self):
        worker = self.worker()
        response = worker.request("turn", "s", {"content": "hi"})
        self.assertEqual(response["content"], "ok")
        worker.close()
        self.assertIsNotNone(worker.process.poll())
        self.assertFalse(worker.reader.is_alive())

    def test_wrong_session_and_malformed_messages_are_not_results(self):
        for mode in ("wrong_session", "invalid", "crash"):
            with self.subTest(mode=mode):
                worker = self.worker(mode)
                with self.assertRaises(ProtocolError):
                    worker.request("turn", "s", {})
                worker.close()

    def test_deadline_kills_and_reaps_worker_and_child(self):
        worker = self.worker("hang", child=True)
        child = psutil.Process(int((self.path / "child.pid").read_text()))
        with self.assertRaises(TimeoutError):
            worker.request("turn", "s", {}, timeout=0.1)
        worker.close()
        self.assertIsNotNone(worker.process.poll())
        self.assertFalse(child.is_running())

    def test_duplicate_provider_ids_fail(self):
        tape = [{"actions": [{"provider": "tool", "payload": {}},
                             {"provider": "tool", "payload": {}}],
                 "result": {"status": "completed", "content": "ok"}}]
        worker = self.worker("duplicate", tape)
        with self.assertRaisesRegex(ProtocolError, "duplicate"):
            worker.request("turn", "s", {}, provider=lambda *args: {"ok": True})

    def test_deadline_also_bounds_a_worker_that_stops_reading_stdin(self):
        import threading
        worker = self.worker("no_read")
        # Emergency guard prevents a broken transport from hanging the test suite.
        guard = threading.Timer(2, worker.process.kill)
        guard.start()
        try:
            with self.assertRaises(TimeoutError):
                worker.request("turn", "s", {"content": "x" * 1000000}, timeout=0.1)
        finally:
            guard.cancel()
            guard.join()

    def test_provider_requests_can_complete_out_of_order(self):
        import threading
        arrived = threading.Barrier(2)
        released = threading.Event()
        tape = [{"actions": [{"parallel": [{"provider": "tool", "payload": {"n": 1}},
                                            {"provider": "tool", "payload": {"n": 2}}]}],
                 "result": {"status": "completed", "content": "ok"}}]
        order = []
        def provider(kind, payload, session, remaining):
            arrived.wait(timeout=2)
            if payload["n"] == 1:
                self.assertTrue(released.wait(timeout=2))
            else:
                order.append(2)
                released.set()
            if payload["n"] == 1:
                order.append(1)
            return {"ok": True}
        worker = self.worker(tape=tape)
        self.assertEqual(worker.request("turn", "s", {}, provider=provider)["status"], "completed")
        self.assertEqual(order, [2, 1])
