"""Public CLI. Run from the repository root via uv run --locked --group benchmark."""
import argparse
import json
from pathlib import Path
import sys

from .support.common import BENCH, ROOT, output_path, read_json, read_rows


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List offline Core cases and Agent scenarios")
    for name in ("core", "perf", "agent"):
        command = commands.add_parser(name)
        command.add_argument("--adapters", type=Path, required=True)
        command.add_argument("--output", type=Path)
        command.add_argument("--timeout", type=float, default=240 if name == "agent" else 10)
        if name == "core":
            command.add_argument("--case", action="append", dest="cases", help="Repeat to select Core IDs")
        else:
            command.add_argument("--measure", choices=("timing", "memory"), default="timing")
        if name == "perf":
            command.add_argument("--rounds", type=int, default=7)
            command.add_argument("--batch", type=int, default=100)
            command.add_argument("--warmup", type=int, default=2)
        if name == "agent":
            command.add_argument("--config", type=Path, default=ROOT / "rag/config/local_api.json")
            command.add_argument("--profile", help="Explicit generation profile from the model config")
            command.add_argument("--corpus", type=Path)
            command.add_argument("--raw-root", type=Path)
            command.add_argument("--scenario", action="append", dest="scenarios")
            command.add_argument("--repeats", type=int, default=3)
            command.add_argument("--max-steps", type=int, default=8)
            command.add_argument("--top-k", type=int, default=5)
            command.add_argument("--model-service-pid", type=int)
    preflight = commands.add_parser("preflight", help="LIVE Qwen native function-call capability check")
    preflight.add_argument("--config", type=Path, default=ROOT / "rag/config/local_api.json")
    preflight.add_argument("--profile", help="Explicit generation profile from the model config")
    preflight.add_argument("--output", type=Path)
    review = commands.add_parser("review").add_subparsers(dest="review_command", required=True)
    export = review.add_parser("export", help="Offline: give package.json and template to pi")
    export.add_argument("--run", type=Path, required=True)
    export.add_argument("--output", type=Path)
    ingest = review.add_parser("import", help="Offline: validate and append pi/human scoring JSON")
    ingest.add_argument("--package", type=Path, required=True)
    ingest.add_argument("--input", type=Path, required=True)
    ingest.add_argument("--kind", choices=("ai", "human"), required=True)
    report = commands.add_parser("report")
    report.add_argument("--run", action="append", type=Path, required=True)
    report.add_argument("--output", type=Path)
    return root


def local_run(path):
    path = path.resolve()
    if not path.is_relative_to((BENCH / "outputs").resolve()):
        raise ValueError("run or review package must be under Benchmarks/outputs")
    return path


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "list":
            from .agent_core.cases import CASES
            from .agent_story.scenarios import load_scenarios
            suite = load_scenarios(ROOT)
            print(json.dumps({"core_cases": len(CASES), "agent_scenarios": len(suite["scenarios"]),
                              "core": [{"id": c["id"], "title": c["title"]} for c in CASES],
                              "agent": [{"id": s["id"], "title": s["title"], "group": s["group"]} for s in suite["scenarios"]]},
                             ensure_ascii=False, indent=2))
            return 0
        if args.command == "review":
            from .agent_story.review import export_review, import_review
            if args.review_command == "export":
                result = export_review(local_run(args.run), output_path("review", args.output, category="agent_story"))
            else:
                package = local_run(args.package)
                local_run(Path(read_json(package / "binding.json")["run_path"]))
                result = import_review(package, args.input, args.kind)
        elif args.command == "report":
            from .reports import make_report
            result = make_report([local_run(path) for path in args.run], output_path("reports", args.output))
        elif args.command == "preflight":
            from .agent_story.commands import preflight
            result = preflight(args, output_path("preflight", args.output, category="agent_story"))
        else:
            category = "agent_story" if args.command == "agent" else "agent_core"
            output = output_path(args.command, args.output, category=category)
            if args.timeout <= 0:
                raise ValueError("timeout must be positive")
            from .support.execution import load_adapters
            adapters = load_adapters(args.adapters)
            if args.command == "agent":
                from .agent_story.commands import execute
            else:
                from .agent_core.commands import execute
            result = execute(args, adapters, output)
            print(str(result))
            rows = read_rows(result / "results.jsonl")
            return int(any(r["execution_status"] != "completed" or r.get("correct") is False for r in rows))
        print(str(result))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Benchmark failed ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
