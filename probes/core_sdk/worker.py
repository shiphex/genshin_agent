"""Direct Python entry point for the spike-jsonl-v1 candidate worker."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from probes.core_sdk.agent import CoreAgent


class Worker:
    def __init__(self):
        self.sequence = 0
        self.agent = None
        self.active = None

    @staticmethod
    def send(message):
        print(json.dumps(message, ensure_ascii=False, separators=(",", ":"), allow_nan=False), flush=True)

    @staticmethod
    def read():
        line = sys.stdin.readline(4194305)
        if not line or len(line) > 4194304:
            raise ValueError("closed input or oversized message")
        message = json.loads(line)
        if not isinstance(message, dict) or any(not isinstance(message.get(key), str) or not message[key]
                                                for key in ("type", "request_id", "session_id")):
            raise ValueError("invalid message envelope")
        return message

    def broker(self, provider, payload):
        self.sequence += 1
        identity = f"p{self.sequence}"
        self.send({"type": "provider_call", "request_id": identity, "session_id": self.active["session_id"],
                   "parent_id": self.active["request_id"], "provider": provider, "payload": payload})
        response = self.read()
        if response["type"] != "provider_result" or response["request_id"] != identity or response["session_id"] != self.active["session_id"]:
            raise ValueError("provider response mismatch")
        return response

    def run(self):
        while True:
            message = self.read()
            kind, session = message["type"], message["session_id"]
            result = {"request_id": message["request_id"], "session_id": session}
            if kind == "init":
                if self.agent is not None or message.get("protocol_version") != 1:
                    raise ValueError("invalid initialization")
                self.agent = CoreAgent(message, self.broker)
                result.update(type="ready", protocol_version=1)
            elif kind == "shutdown":
                self.send({**result, "type": "closed"})
                return
            elif self.agent is None:
                raise ValueError("worker is not initialized")
            elif kind == "reset":
                self.agent.reset(session)
                result["type"] = "reset_done"
            elif kind == "turn":
                self.active = message
                result.update(type="turn_result", **self.agent.turn(session, message["content"]))
                self.active = None
            else:
                raise ValueError("unsupported control message")
            self.send(result)


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="strict")
    try:
        Worker().run()
    except Exception as exc:
        print(f"worker failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
