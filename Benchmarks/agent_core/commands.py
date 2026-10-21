"""Dispatch Core cases and the fixed performance workload."""
from .cases import CASES
from .runner import run_core, run_perf


def execute(args, adapters, output):
    if args.command == "perf":
        return run_perf(adapters, output, args.rounds, args.batch, args.warmup, args.measure, args.timeout)
    cases = CASES
    if args.cases:
        if set(args.cases) - {case["id"] for case in cases}:
            raise ValueError("unknown selected ID")
        cases = [case for case in cases if case["id"] in args.cases]
    return run_core(adapters, output, cases, args.timeout)
