from copy import deepcopy
import time
from Benchmarks.support.common import BENCH, ROOT, positive, write_json
from Benchmarks.support.execution import _store, _worker
from Benchmarks.support.metrics import ProcessMeter, paired_order
from Benchmarks.support.protocol import ProtocolError, ProviderDeadlineError
import sys
from .cases import CASES, ECHO_TOOL, CoreOracle


def core_initialization(case):
    return {"suite": "core", "scenario_id": case["id"], "tools": [ECHO_TOOL], "system": "",
            "max_steps": case["max_steps"], "context_limit": case["context_limit"],
            "context_counter": "unicode_content_codepoints_v1"}


def _core_turn(worker, oracle, turn):
    if turn.get("reset"):
        worker.request("reset", turn["session_id"], {})
        oracle.reset(turn["session_id"])
    oracle.begin(turn)
    result = worker.request("turn", turn["session_id"], {"content": turn["content"]}, provider=oracle.provide)
    oracle.end(result)
    return result


def _conformance(oracle, complete=False, error=None):
    # An execution failure alone is not evidence of a contract violation.
    # Worker wraps the original violation if provider cleanup exceeds its bound.
    protocol_error = isinstance(error, ProtocolError) or (
        isinstance(error, ProviderDeadlineError) and isinstance(error.__cause__, ProtocolError))
    if oracle.errors or protocol_error:
        return "failed"
    return "passed" if complete else "not_evaluated"


def run_core(adapters, output, cases=None, timeout=10):
    cases = CASES if cases is None else cases
    planned = [{"sample_id": f"{a['id']}:{c['id']}", "adapter_id": a["id"], "case_id": c["id"],
                "fixture_only": a.get("fixture_only", False), "policy_group": a["policies"],
                "conformance_status": "not_evaluated"}
               for c in cases for a in adapters]
    store = _store(output, "core", adapters, planned, {"timeout": timeout}, implementation=BENCH / "agent_core",
                   evaluation_profile="fixed-history-v0")
    try:
        for case in cases:
            for adapter in adapters:
                sample = f"{adapter['id']}:{case['id']}"
                oracle = CoreOracle(case, adapter["policies"])
                started = time.perf_counter()
                row = {"sample_id": sample, "adapter_id": adapter["id"], "case_id": case["id"],
                       "policy_group": adapter["policies"], "fixture_only": adapter.get("fixture_only", False), "turns": []}
                fatal = None
                try:
                    worker, startup = _worker(store, adapter, sample, core_initialization(case), timeout)
                    row["startup_ms"] = startup
                    with worker:
                        for turn in case["turns"]:
                            row["turns"].append(_core_turn(worker, oracle, turn))
                    row.update(execution_status="completed", **oracle.verdict())
                    row["conformance_status"] = _conformance(oracle, complete=True)
                except BaseException as exc:
                    row.update(execution_status="failed" if isinstance(exc, Exception) else "interrupted", correct=False, error=type(exc).__name__,
                               checks_failed=oracle.errors)
                    row["conformance_status"] = _conformance(oracle, error=exc)
                    if not isinstance(exc, Exception) or isinstance(exc, ProviderDeadlineError):
                        fatal = exc
                row["elapsed_ms"] = (time.perf_counter() - started) * 1000
                store.result(row)
                if fatal is not None:
                    raise fatal
        store.finish("completed")
    except BaseException as exc:
        store.finish("interrupted" if isinstance(exc, KeyboardInterrupt) else "failed", type(exc).__name__)
        raise
    return store.path


def run_perf(adapters, output, rounds=7, batch=100, warmup=2, measure="timing", timeout=10):
    positive(rounds), positive(batch)
    if type(warmup) is not int or warmup < 0 or measure not in {"timing", "memory"}:
        raise ValueError("invalid warmup or measurement phase")
    # The baseline is a finite protocol tape, never an alternate core implementation.
    from .tapes import core_tape
    baseline = {"id": "transport_replay", "policies": {"tool_error": "recover", "context": "truncate",
                "tool_execution": "serial", "max_tool_retries": 0}, "fixture_only": True}
    if any(a["id"] == baseline["id"] for a in adapters):
        raise ValueError("transport_replay is a reserved adapter ID")
    planned = [{"sample_id": f"{a['id']}:r{r + 1}", "adapter_id": a["id"], "round": r + 1,
                "is_baseline": a is baseline, "measure": measure, "fixture_only": a.get("fixture_only", False),
                "policy_group": a["policies"], "conformance_status": "not_evaluated"} for r in range(rounds)
               for a in paired_order(adapters, r) + [baseline]]
    store = _store(output, "perf", adapters, planned, {"rounds": rounds, "batch": batch,
                    "warmup_batches": warmup, "measure": measure, "timeout": timeout,
                    "timed_scope": "reset + turn + broker, oracle and JSONL trace; excludes startup and warmup"},
                    [BENCH / "agent_core/tapes.py", BENCH / "support/replay_worker.py"], implementation=BENCH / "agent_core",
                    evaluation_profile="fixed-history-v0")
    tape_path = store.path / "transport-tape.json"
    write_json(tape_path, core_tape(CASES[-1], baseline["policies"]) * (batch * (warmup + 1)), exclusive=True)
    baseline["command"] = [sys.executable, "-B", str(BENCH / "support/replay_worker.py"), "--tape", str(tape_path)]
    try:
        for r in range(rounds):
            for adapter in paired_order(adapters, r) + [baseline]:
                sample = f"{adapter['id']}:r{r + 1}"
                row = next(deepcopy(p) for p in planned if p["sample_id"] == sample)
                row.update(measure=measure, fixture_only=adapter.get("fixture_only", False),
                           policy_group=adapter["policies"], iterations_ms=[], warmup_completed=0)
                oracle = CoreOracle(CASES[-1], adapter["policies"])
                fatal = None
                try:
                    worker, startup = _worker(store, adapter, sample, core_initialization(CASES[-1]), timeout)
                    row["startup_ms"] = startup
                    with worker:
                        for _ in range(batch * warmup):
                            _core_turn(worker, oracle, CASES[-1]["turns"][0])
                            row["warmup_completed"] += 1
                        meter = ProcessMeter(worker.process.pid, memory=measure == "memory")
                        try:
                            started = time.perf_counter()
                            for iteration in range(batch):
                                tick = time.perf_counter()
                                row["inflight_iteration"] = iteration + 1
                                _core_turn(worker, oracle, CASES[-1]["turns"][0])
                                row["iterations_ms"].append((time.perf_counter() - tick) * 1000)
                                row.pop("inflight_iteration")
                        finally:
                            row["elapsed_ms"] = (time.perf_counter() - started) * 1000
                            row["resources"] = meter.finish()
                    row.update(execution_status="completed", per_iteration_ms=row["elapsed_ms"] / batch, **oracle.verdict())
                    row["conformance_status"] = _conformance(oracle, complete=True)
                except BaseException as exc:
                    row.update(execution_status="failed" if isinstance(exc, Exception) else "interrupted", correct=False,
                               error=type(exc).__name__, checks_failed=oracle.errors)
                    row["conformance_status"] = _conformance(oracle, error=exc)
                    if not isinstance(exc, Exception) or isinstance(exc, ProviderDeadlineError):
                        fatal = exc
                row["completed_iterations"] = len(row["iterations_ms"])
                store.result(row)
                if fatal is not None:
                    raise fatal
        store.finish("completed")
    except BaseException as exc:
        store.finish("interrupted" if isinstance(exc, KeyboardInterrupt) else "failed", type(exc).__name__)
        raise
    return store.path
