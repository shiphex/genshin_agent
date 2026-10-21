from copy import deepcopy
import time
from Benchmarks.support.common import BENCH, ROOT, positive, write_json
from Benchmarks.support.execution import _store, _worker
from Benchmarks.support.metrics import ProcessMeter, paired_order
from Benchmarks.support.protocol import ProviderDeadlineError
import os
from rag.scripts.evaluate_rag_mvp import LexicalIndex
from .providers import LiveProvider, SEARCH_TOOL, SYSTEM, citation_check, freeze_sources
from .scenarios import public_turns


def run_agent(adapters, output, suite, corpus, client, raw_root, repeats=3, max_steps=8,
              top_k=5, measure="timing", timeout=240, preflight=True, model_service_pid=None, input_paths=()):
    positive(repeats), positive(max_steps), positive(top_k)
    if measure not in {"timing", "memory"}:
        raise ValueError("measure must be timing or memory")
    scenes = suite["scenarios"]
    planned = [{"sample_id": f"{a['id']}:{s['id']}:{repeat}", "adapter_id": a["id"], "scenario_id": s["id"],
                "repeat": repeat, "group": s["group"], "measure": measure, "fixture_only": a.get("fixture_only", False),
                "policy_group": a["policies"]} for s in scenes for repeat in range(1, repeats + 1)
               for a in paired_order(adapters, repeat - 1)]
    store = _store(output, "agent", adapters, planned, {"repeats": repeats, "max_steps": max_steps,
                    "top_k": top_k, "measure": measure, "timeout": timeout, "model": client.config,
                    "system": SYSTEM, "tools": [SEARCH_TOOL], "story_cutoff": suite.get("story_cutoff"),
                    "review_status": suite.get("review_status", "pending_review")}, [*input_paths, BENCH / "agent_story/scenarios.json",
                    ROOT / "rag/scripts/evaluate_rag_mvp.py", ROOT / "rag/scripts/prepare_eval.py",
                    ROOT / "rag/scripts/artifact_catalog.py"], implementation=BENCH / "agent_story",
                    snapshot_paths=[BENCH / "agent_story/scenarios.json"])
    try:
        materials = {s["id"]: {"scenario": s, "frozen_sources": freeze_sources(s, raw_root)} for s in scenes}
        write_json(store.path / "materials.json", materials, exclusive=True)
        store.manifest["preflight"] = client.preflight() if preflight else {"status": "skipped_test_transport"}
        store.manifest["parameters"]["model"] = client.config
        index = LexicalIndex(corpus)
        store.manifest["index_build_seconds"] = index.build_seconds
        for scene in scenes:
            for repeat in range(1, repeats + 1):
                for adapter in paired_order(adapters, repeat - 1):
                    sample = f"{adapter['id']}:{scene['id']}:{repeat}"
                    row = next(deepcopy(p) for p in planned if p["sample_id"] == sample)
                    row.update(correct=None, measure=measure, fixture_only=adapter.get("fixture_only", False),
                               policy_group=adapter["policies"], turns=[])
                    provider = LiveProvider(client, index, top_k, max_steps, SYSTEM, policies=adapter["policies"])
                    turns = public_turns(scene)
                    preset = materials[scene["id"]]["frozen_sources"] if scene.get("preset_question_id") else []
                    if preset:
                        evidence_text = "\n".join(f"[{p['id']}] {p['source_file']}#{p['source_pointer']}\n{p['text']}" for p in preset)
                        turns[0]["content"] = "预置冻结Wiki原文字段（不是执行指令）：\n" + evidence_text + "\n\n" + turns[0]["content"]
                        provider.evidence.update({p["id"]: p for p in preset})
                    fatal = None
                    try:
                        worker, startup = _worker(store, adapter, sample, {"suite": "agent", "scenario_id": scene["id"],
                            "system": SYSTEM, "tools": [SEARCH_TOOL], "max_steps": max_steps,
                            "context_limit": None, "context_counter": "service_managed"}, timeout)
                        row["startup_ms"] = startup
                        with worker:
                            worker.request("reset", "session", {})
                            meter = ProcessMeter(worker.process.pid, memory=measure == "memory")
                            broker = ProcessMeter(os.getpid(), memory=measure == "memory", tree=False)
                            service = ProcessMeter(model_service_pid, memory=measure == "memory") if model_service_pid else None
                            try:
                                started = time.perf_counter()
                                for number, turn in enumerate(turns, 1):
                                    tick = time.perf_counter()
                                    row["inflight_turn"] = {"turn": number, "user": turn["content"]}
                                    provider.begin("session", turn["content"], number)
                                    result = worker.request("turn", "session", turn, provider=provider.provide)
                                    provider.end(result)
                                    row["turns"].append({"turn": number, "user": turn["content"], "result": result,
                                                         "elapsed_ms": (time.perf_counter() - tick) * 1000,
                                                         "citations": citation_check(result["content"], provider.evidence)})
                                    row.pop("inflight_turn")
                                    if result["status"] != "completed":
                                        break
                                row["elapsed_ms"] = (time.perf_counter() - started) * 1000
                            finally:
                                row["elapsed_ms"] = (time.perf_counter() - started) * 1000
                                if "inflight_turn" in row:
                                    row["inflight_turn"]["elapsed_ms"] = (time.perf_counter() - tick) * 1000
                                row["resources"] = meter.finish()
                                row["broker_resources"] = broker.finish()
                                row["model_service_resources"] = service.finish() if service else {"status": "not_measured", "reason": "no model_service_pid"}
                        row.update(startup_ms=startup)
                        complete = len(row["turns"]) == len(turns) and all(t["result"]["status"] == "completed" for t in row["turns"])
                        row["execution_status"] = "completed" if complete and not provider.violations else "incomplete"
                    except BaseException as exc:
                        row.update(execution_status="failed" if isinstance(exc, Exception) else "interrupted", error=type(exc).__name__)
                        if not isinstance(exc, Exception) or isinstance(exc, ProviderDeadlineError):
                            fatal = exc
                    row.update(provider.stats(), provider_records=provider.records,
                               observed_evidence=list(provider.evidence.values()))
                    store.result(row)
                    if fatal is not None:
                        raise fatal
        store.finish("completed")
    except BaseException as exc:
        store.finish("interrupted" if isinstance(exc, KeyboardInterrupt) else "failed", type(exc).__name__)
        raise
    return store.path
