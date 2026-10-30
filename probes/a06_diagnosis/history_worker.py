"""C2-only launcher; inject once after reset, then execute the unmodified Core."""
from copy import deepcopy
import json
from pathlib import Path
import sys

from probes.core_self.worker import Core


class SeededCore(Core):
    def __init__(self, messages):
        super().__init__()
        self.seed, self.seeded = deepcopy(messages), False

    def turn(self, request):
        if not self.seeded:
            expected = [{"role": "system", "content": self.system}] if self.system else []
            if self.seed[:len(expected)] != expected or request["session_id"] in self.histories:
                raise ValueError("invalid controlled history initialization")
            self.histories[request["session_id"]] = deepcopy(self.seed)
            self.seeded = True
        return super().turn(request)


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="strict")
    fixture = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    try:
        SeededCore(fixture["messages"]).run()
    except EOFError:
        return 0
    except Exception as exc:
        print(f"controlled-history: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
