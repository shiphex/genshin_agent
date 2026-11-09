"""Small a06 orchestrator; original Core, Provider and message checks stay intact."""
from copy import deepcopy
from pathlib import Path
import sys

from Benchmarks.agent_story.providers import LiveProvider, SYSTEM, SEARCH_TOOL, citation_check
from Benchmarks.agent_story.scenarios import public_turns
from Benchmarks.support.common import ROOT, RunStore, provenance, write_json, read_rows, file_hash
from Benchmarks.support.protocol import Worker
from probes.core_self.worker import POLICIES
from .controls import ObservedClient, api_statistics
from .evidence import audit_transfers, audit_injected_history

HERE = Path(__file__).resolve().parent


def new_store(output, condition, parameters=None, paths=()):
    sources = [ROOT / "probes/core_self/worker.py", ROOT / "Benchmarks/agent_story/providers.py",
               ROOT / "Benchmarks/agent_story/http_worker.py", ROOT / "Benchmarks/agent_story/scenarios.py",
               ROOT / "Benchmarks/agent_story/scenarios.json", ROOT / "rag/scripts/evaluate_rag_mvp.py",
               ROOT / "rag/scripts/prepare_eval.py", ROOT / "rag/scripts/artifact_catalog.py",
               ROOT / "rag/eval/questions.json", ROOT / "rag/scripts/local_model_config.py",
               HERE / "inputs.json", *paths]
    identity = provenance(sources, implementation=HERE)
    store = RunStore(output, {"suite": "a06_diagnosis", "condition": condition,
        "planned_samples": [], "parameters": parameters or {}, "provenance": identity,
        "user_acceptance": "not_evaluated", "end_to_end_score": "not_applicable"})
    directory = store.path / "sources"; directory.mkdir()
    for name, sha in identity["files"].items():
        source = Path(name) if Path(name).is_absolute() else ROOT / name
        if source.suffix == ".py" or source.name in {"inputs.json", "scenarios.json", "pyproject.toml", "uv.lock", ".python-version"}:
            (directory / (sha + "-" + source.name)).write_bytes(source.read_bytes())
    return store


def run_live(output, scene, corpus, config, condition, *, fixture=None, transport=None, binding=None):
    if condition == "A" and transport is None:
        log = Path(binding["server_log"]) if binding and binding.get("server_log") else None
        if log is None or not log.is_file():
            raise ValueError("real forced condition requires the corresponding service log")
        with log.open("rb"):
            pass
    store = new_store(output, condition, {"model": config, "max_steps": 8, "top_k": 5,
        "timeout": 240, "system": SYSTEM, "tools": [SEARCH_TOOL], "policies": POLICIES,
        "context_counter": "service_managed", "context_limit": None, "binding": binding})
    client = ObservedClient(config, lambda e: store.append("api.jsonl", e), transport=transport)
    log_path = Path(binding["server_log"]) if binding and binding.get("server_log") else None
    log_start = log_path.stat().st_size if log_path and log_path.exists() else 0
    if log_path is not None:
        def choice_guard():
            with log_path.open("rb") as handle:
                handle.seek(log_start)
                text = handle.read().decode("utf-8", errors="replace")
            accepted = not any("tool_choice" in line and ("Wrong type" in line or "using default" in line)
                               for line in text.splitlines())
            store.append("api.jsonl", {"event": "tool_choice_capability", "turn": 1, "request": 1,
                                      "server_rejected_named_choice": not accepted})
            return accepted
        client.choice_guard = choice_guard
    provider = LiveProvider(client, corpus, 5, 8, SYSTEM, policies=POLICIES)
    command = [sys.executable, "-B", str(ROOT / "probes/core_self/worker.py")]
    if fixture is not None:
        write_json(store.path / "injected-history.json", fixture, exclusive=True)
        command = [sys.executable, "-B", "-m", "probes.a06_diagnosis.history_worker",
                   str((store.path / "injected-history.json").resolve())]
        provider.histories["session"] = deepcopy(fixture["messages"])
        for message in fixture["messages"]:
            if message["role"] == "tool":
                import json
                provider.evidence.update({h["id"]: h for h in json.loads(message["content"])["result"]["evidence"]})
    row = {"sample_id": f"{condition}:a06:1", "condition": condition, "scenario_id": "a06",
           "turns": [], "correct": None, "execution_status": "incomplete"}
    store.manifest["planned_samples"] = [{"sample_id": row["sample_id"], "condition": condition, "scenario_id": "a06"}]
    try:
        def trace(direction, message):
            store.append("trace.jsonl", {"direction": direction, "message": message})
        with Worker(command, store.path / "worker.stderr.txt", timeout=240, trace=trace) as worker:
            store.manifest["worker_command"] = command
            worker.request("init", "control", {"protocol_version": 1, "suite": "agent", "scenario_id": "a06",
                "policies": POLICIES, "system": SYSTEM, "tools": [SEARCH_TOOL], "max_steps": 8,
                "context_limit": None, "context_counter": "service_managed"})
            worker.request("reset", "session", {})
            for number, turn in enumerate(public_turns(scene), 1):
                if fixture is not None and number == 1:
                    continue
                client.begin(number, force_first=condition == "A" and number == 1)
                provider.begin("session", turn["content"], number)
                before_models, before_tools = provider.total_models, provider.tool_requests
                result = worker.request("turn", "session", turn, provider=provider.provide)
                provider.end(result)
                row["turns"].append({"turn": number, "user": turn["content"], "result": result,
                    "model_requests": provider.total_models - before_models,
                    "tool_requests": provider.tool_requests - before_tools,
                    "citations": citation_check(result["content"], provider.evidence)})
                if result["status"] != "completed":
                    break
        expected = 2 if fixture is not None else 3
        if len(row["turns"]) == expected and all(t["result"]["status"] == "completed" for t in row["turns"]) and not provider.violations:
            row["execution_status"] = "completed"
    except BaseException as exc:
        row.update(execution_status="failed" if isinstance(exc, Exception) else "interrupted", error=type(exc).__name__)
        if not isinstance(exc, Exception):
            raise
    finally:
        if log_path and log_path.exists():
            with log_path.open("rb") as handle:
                handle.seek(log_start)
                (store.path / "server-segment.log").write_bytes(handle.read())
        records = read_rows(store.path / "api.jsonl") if (store.path / "api.jsonl").exists() else []
        row.update(provider.stats(), provider_records=provider.records, observed_evidence=list(provider.evidence.values()),
                   force_status=client.force_status, transfers=audit_transfers(read_rows(store.path / "trace.jsonl"), records))
        executed = {t["turn"] for t in row["turns"]}
        row.update(api_statistics(records), unexecuted_turns=[n for n in range(2 if fixture is not None else 1, 4) if n not in executed])
        if fixture is not None:
            row["injected_history_delivery"] = audit_injected_history(fixture, records)
        store.result(row)
        store.finish("completed" if row["execution_status"] == "completed" else "failed", row.get("error"))
        seal(store.path)
    return store.path


def seal(path):
    """Seal immutable stage artifacts; later assessments remain separate files."""
    path = Path(path)
    hashes = {p.relative_to(path).as_posix(): file_hash(p) for p in sorted(path.rglob("*"))
              if p.is_file() and p.name not in {"hashes.json", "assessment.json"}}
    write_json(path / "hashes.json", hashes, exclusive=True)
