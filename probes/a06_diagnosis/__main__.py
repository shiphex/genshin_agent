"""Explicit stages only: no automatic service launch, tuning or model repetition."""
import argparse
from pathlib import Path
import sys

from Benchmarks.support.common import ROOT
from rag.scripts.evaluate_rag_mvp import load_jsonl
from .environment import inspect_environment, load_environment
from .runner import run_live
from .stages import original_stage, retrieval_stage, controlled_stage, verify_run, report_run, assert_sealed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="stage", required=True)
    for name in ("inspect", "o", "b", "a", "c2", "verify", "report"):
        command = commands.add_parser(name)
        command.add_argument("--output", required=True, type=Path)
        if name == "inspect":
            for flag in ("historical-run", "config", "corpus", "raw-root"):
                command.add_argument("--" + flag, required=True, type=Path)
            command.add_argument("--server-log", type=Path)
        elif name in {"verify", "report"}:
            command.add_argument("--run-root", required=True, type=Path)
        else:
            command.add_argument("--environment", required=True, type=Path)
            if name == "o":
                command.add_argument("--historical-run", required=True, type=Path)
            if name == "b":
                command.add_argument("--baseline", required=True, type=Path)
            if name == "c2":
                command.add_argument("--retrieval", required=True, type=Path)
                command.add_argument("--a-run", required=True, type=Path)
    args = parser.parse_args(argv)
    parent = ROOT / "Benchmarks/outputs/agent_story/a06_diagnosis"
    if args.output.resolve() == parent or not args.output.resolve().is_relative_to(parent):
        parser.error(f"output must be a new directory below {parent}")
    try:
        if args.stage == "inspect":
            result = inspect_environment(args.output, args.historical_run, args.config, args.corpus, args.raw_root, args.server_log)
        elif args.stage == "o":
            result = original_stage(args.output, args.environment, args.historical_run)
        elif args.stage == "b":
            result = retrieval_stage(args.output, args.environment, args.baseline)
        elif args.stage == "a":
            assert_sealed(args.environment)
            env, scene = load_environment(args.environment, require_service=True)
            result = run_live(args.output, scene, load_jsonl(env["corpus"]), env["config"], "A", binding=env)
        elif args.stage == "c2":
            result = controlled_stage(args.output, args.environment, args.retrieval, args.a_run)
        elif args.stage == "verify":
            result, passed = verify_run(args.output, args.run_root)
            print(result)
            return 0 if passed else 1
        else:
            result = report_run(args.output, args.run_root)
        print(result)
        from Benchmarks.support.common import read_json
        return 0 if read_json(Path(result) / "manifest.json")["status"] == "completed" else 1
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        print(f"a06 {args.stage} failed: {type(exc).__name__}; inspect retained stage artifacts.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
