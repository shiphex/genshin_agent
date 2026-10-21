"""Finite tape player for transport tests, NOT an agent or a candidate."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def send(kind, identity, session, **payload):
    print(json.dumps({"type": kind, "request_id": identity, "session_id": session, **payload}), flush=True)


def read():
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return json.loads(line)


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--tape", type=Path)
    parser.add_argument("--mode", default="normal")
    parser.add_argument("--child-pid", type=Path)
    args = parser.parse_args()
    tapes = json.loads(args.tape.read_text(encoding="utf-8")) if args.tape else []
    turns = iter(tapes if isinstance(tapes, list) else [])
    serial = 0
    for line in sys.stdin:
        request = json.loads(line)
        kind, identity, session = (request[k] for k in ("type", "request_id", "session_id"))
        if kind == "init":
            if isinstance(tapes, dict):
                turns = iter(tapes[request["scenario_id"]])
            if args.child_pid:
                child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
                args.child_pid.write_text(str(child.pid))
            send("ready", identity, session, protocol_version=1)
            if args.mode == "no_read":
                import threading
                threading.Event().wait()
        elif kind == "reset":
            send("reset_done", identity, session)
        elif kind == "shutdown":
            send("closed", identity, session)
            return
        elif kind == "turn":
            if args.mode == "crash":
                os._exit(7)
            if args.mode == "hang":
                sys.stdin.read()
                return
            if args.mode == "invalid":
                print("{invalid", flush=True)
                continue
            turn = next(turns)
            for action in turn.get("actions", []):
                calls = action.get("parallel", [action])
                pending = set()
                for call in calls:
                    serial += 1
                    call_id = "duplicate" if args.mode == "duplicate" else f"p{serial}"
                    pending.add(call_id)
                    send("provider_call", call_id, session, parent_id=identity,
                         provider=call["provider"], payload=call["payload"])
                for _ in calls:
                    reply = read()
                    if reply["request_id"] not in pending:
                        raise ValueError("unmatched provider response")
            result_session = "wrong" if args.mode == "wrong_session" else session
            send("turn_result", identity, result_session, **turn["result"])


if __name__ == "__main__":
    main()
