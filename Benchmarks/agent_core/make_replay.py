"""Create an offline CLI demo. Its finite tape is NOT an agent benchmark score."""
import argparse
from pathlib import Path
from Benchmarks.support.common import ROOT, output_path, write_json
from Benchmarks.agent_core.cases import CASES
from Benchmarks.agent_core.tapes import core_tape


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = output_path("inputs", args.output, category="agent_core")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    policy = {"tool_error": "recover", "context": "truncate", "tool_execution": "serial", "max_tool_retries": 0}
    tape = output / "tape.json"
    write_json(tape, {c["id"]: core_tape(c, policy) * (300 if c["id"] == "c15" else 1) for c in CASES}, exclusive=True)
    fixture = ROOT / "Benchmarks/support/replay_worker.py"
    write_json(output / "adapters.json", {"schema_version": 1, "adapters": [{"id": "finite_replay", "fixture_only": True,
        "command": ["{python}", "-B", str(fixture), "--tape", str(tape)], "policies": policy,
        "identity": {"revision": "finite-test-tape-v1", "files": [str(fixture), str(tape)]}}]}, exclusive=True)
    print(output / "adapters.json")


if __name__ == "__main__":
    main()
