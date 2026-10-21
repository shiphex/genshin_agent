"""Bounded JSONL subprocess transport; provider requests may finish out of order."""
import json
from pathlib import Path
import queue
import subprocess
import threading
import time

import psutil


MAX_LINE = 4 * 1024 * 1024
EXPECTED = {"init": "ready", "reset": "reset_done", "turn": "turn_result", "shutdown": "closed"}


class ProtocolError(ValueError):
    pass


class ProviderDeadlineError(TimeoutError):
    """Abort the run: a provider ignored cancellation; do not contaminate later samples."""


class Worker:
    def __init__(self, command, stderr_path, timeout=240, trace=None):
        if not isinstance(command, list) or not command or not all(isinstance(s, str) for s in command):
            raise ValueError("adapter command must be a nonempty argv list")
        self.timeout, self.trace = timeout, trace or (lambda *args: None)
        self.serial, self.seen, self.children = 0, set(), {}
        self.closed = False
        self.events = queue.Queue(maxsize=128)
        self.outgoing = queue.Queue(maxsize=32)
        self.stopped = threading.Event()
        self.stderr = Path(stderr_path).open("x", encoding="utf-8")
        started = time.perf_counter()
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=self.stderr, text=True, encoding="utf-8",
                                            errors="strict", bufsize=1)
        except BaseException:
            self.stderr.close()
            raise
        self.spawn_ms = (time.perf_counter() - started) * 1000
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.writer = threading.Thread(target=self._write, daemon=True)
        self.reader.start()
        self.writer.start()

    def _put(self, item):
        while not self.stopped.is_set():
            try:
                self.events.put(item, timeout=0.05)
                return
            except queue.Full:
                pass

    def _read(self):
        try:
            while not self.stopped.is_set():
                line = self.process.stdout.readline(MAX_LINE + 1)
                if not line:
                    self._put(ProtocolError("worker stdout closed"))
                    return
                if len(line) > MAX_LINE or not line.endswith("\n"):
                    raise ProtocolError("unterminated or oversized JSONL message")
                try:
                    value = json.loads(line)
                except ValueError as exc:
                    raise ProtocolError("invalid JSONL message") from exc
                if not isinstance(value, dict) or any(not isinstance(value.get(k), str) or not value[k]
                                                     for k in ("type", "request_id", "session_id")):
                    raise ProtocolError("message needs type, request_id and session_id")
                self._put(value)
        except (ValueError, OSError) as exc:
            self._put(exc if isinstance(exc, ProtocolError) else ProtocolError("invalid worker stream"))

    def _write(self):
        try:
            while not self.stopped.is_set():
                try:
                    line = self.outgoing.get(timeout=0.05)
                except queue.Empty:
                    continue
                self.process.stdin.write(line)
                self.process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            self._put(ProtocolError("worker stdin closed"))

    def track_children(self):
        try:
            for child in psutil.Process(self.process.pid).children(recursive=True):
                self.children[(child.pid, child.create_time())] = child
        except psutil.NoSuchProcess:
            pass

    def _send(self, message):
        self.trace("send", message)
        line = json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n"
        if len(line) > MAX_LINE:
            raise ProtocolError("outgoing JSONL message exceeds limit")
        try:
            self.outgoing.put_nowait(line)
        except queue.Full as exc:
            raise ProtocolError("worker write queue is full") from exc

    def request(self, kind, session, payload, provider=None, timeout=None):
        if self.closed or kind not in EXPECTED:
            raise ProtocolError("closed worker or unsupported request")
        self.serial += 1
        identity = f"h{self.serial}"
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        request = {**payload, "type": kind, "request_id": identity, "session_id": session}
        self._send(request)
        pending = {}
        cancelled = threading.Event()
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("adapter request deadline exceeded")
                try:
                    message = self.events.get(timeout=remaining)
                except queue.Empty:
                    continue
                if isinstance(message, BaseException):
                    raise message
                if isinstance(message, tuple):
                    pid = message[1]
                    call, sid = pending.pop(pid)
                    call["thread"].join(timeout=0.05)
                    if "exception" in call:
                        raise call["exception"]
                    self._send({"type": "provider_result", "request_id": pid,
                                "session_id": sid, **call["result"]})
                    continue
                self.track_children()
                self.trace("receive", message)
                if message["session_id"] != session:
                    raise ProtocolError("response belongs to another session")
                if message["type"] == "provider_call":
                    pid = message["request_id"]
                    if kind != "turn" or message.get("parent_id") != identity or provider is None:
                        raise ProtocolError("provider request outside its turn")
                    if pid in self.seen or pid.startswith("h"):
                        raise ProtocolError("duplicate or reserved provider request ID")
                    if message.get("provider") not in {"model", "tool"} or not isinstance(message.get("payload"), dict):
                        raise ProtocolError("invalid provider request")
                    if len(pending) >= 8:
                        raise ProtocolError("more than eight outstanding provider requests")
                    self.seen.add(pid)
                    call = {}
                    def execute(call=call, message=message, pid=pid):
                        try:
                            call["result"] = provider(message["provider"], message["payload"], session,
                                                      max(0.001, deadline - time.monotonic()))
                        except BaseException as exc:
                            call["exception"] = exc
                        finally:
                            if not cancelled.is_set():
                                self._put(("provider_ready", pid))
                    call["thread"] = threading.Thread(target=execute, daemon=True)
                    pending[pid] = (call, session)
                    call["thread"].start()
                else:
                    if message["type"] != EXPECTED[kind] or message["request_id"] != identity:
                        raise ProtocolError("unexpected response type or request ID")
                    if pending:
                        raise ProtocolError("turn ended with outstanding providers")
                    if kind == "init" and message.get("protocol_version") != 1:
                        raise ProtocolError("unsupported protocol version")
                    if kind == "turn" and (message.get("status") not in {
                            "completed", "step_limit", "context_limit", "tool_error", "failed"}
                            or not isinstance(message.get("content"), str)):
                        raise ProtocolError("invalid turn result")
                    return message
        except BaseException as exc:
            cancelled.set()
            self._kill()
            cleanup_deadline = time.monotonic() + 0.05
            for call, _ in pending.values():
                call["thread"].join(timeout=max(0, cleanup_deadline - time.monotonic()))
            self.provider_lingering = sum(call["thread"].is_alive() for call, _ in pending.values())
            if self.provider_lingering and isinstance(exc, Exception):
                raise ProviderDeadlineError("provider exceeded bounded cleanup; run must stop") from exc
            raise

    def _kill(self):
        self.track_children()
        children = list(self.children.values())
        for process in reversed(children):
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)
        _, alive = psutil.wait_procs(children, timeout=5)
        if alive:
            raise ProtocolError("worker descendants did not exit")

    def close(self):
        if self.closed:
            return
        try:
            if self.process.poll() is None:
                try:
                    self.request("shutdown", "control", {}, timeout=1)
                    self.process.wait(timeout=1)
                except (ProtocolError, TimeoutError, subprocess.TimeoutExpired):
                    pass
            self._kill()
        finally:
            self.closed = True
            self.stopped.set()
            self.writer.join(timeout=2)
            self.process.stdin.close()
            self.process.stdout.close()
            self.reader.join(timeout=2)
            self.stderr.close()
        if self.reader.is_alive() or self.writer.is_alive():
            raise ProtocolError("worker IO threads did not stop")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
