"""a06 stage operations and evidence-bound reporting, without model-based scoring."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import shutil

from Benchmarks.agent_story.scenarios import public_turns
from Benchmarks.agent_story.providers import SYSTEM
from Benchmarks.support.common import read_json, read_rows, write_json, file_hash, encoded
from rag.scripts.evaluate_rag_mvp import LexicalIndex, load_jsonl
from .controls import ObservedClient, api_statistics
from .environment import load_environment, REVIEW
from .evidence import source_anchors, map_anchors, coverage, audit_transfers, audit_injected_history
from .runner import HERE, new_store, run_live, seal


def verify_hashes(path):
    path = Path(path)
    expected = read_json(path / "hashes.json")
    return [name for name, sha in expected.items() if not (path / name).is_file() or file_hash(path / name) != sha]


def assert_sealed(path):
    if verify_hashes(path):
        raise ValueError("stage artifacts changed")


def original_stage(output, environment, historical_run):
    assert_sealed(environment)
    env, scene = load_environment(environment, require_service=True)
    if not env["reuse_gate"]["reusable"]:
        return run_live(output, scene, load_jsonl(env["corpus"]), env["config"], "O", binding=env)
    historical_run = Path(historical_run)
    if historical_run.resolve() != Path(env["historical_run"]).resolve():
        raise ValueError("different historical run")
    publication = read_json(REVIEW / "provenance.json")
    if file_hash(historical_run / "trace.jsonl") != publication["original_story_trace_sha256"]:
        raise ValueError("historical trace hash mismatch")
    published = REVIEW / "evidence/agent_story/agent/core-probe-live-r001"
    for name in ("manifest.json", "materials.json", "results.jsonl"):
        if file_hash(historical_run / name) != file_hash(published / name):
            raise ValueError("historical publication binding changed")
    store = new_store(output, "O", {"historical_reuse": True, "reuse_gate": env["reuse_gate"],
        "environment": str(Path(environment).resolve()), "environment_sha256": file_hash(Path(environment) / "environment.json"),
        "context_origin": "reconstructed_from_original_core_trace_and_execution_source"})
    try:
        for name in ("manifest.json", "materials.json", "results.jsonl", "trace.jsonl"):
            shutil.copyfile(historical_run / name, store.path / ("original-" + name))
        rows = read_rows(historical_run / "results.jsonl")
        row = deepcopy(next(r for r in rows if r["sample_id"] == "core_self:a06:1"))
        trace = [e for e in read_rows(historical_run / "trace.jsonl") if e["sample_id"] == row["sample_id"]]
        responses = {e["message"]["request_id"]: e["message"] for e in trace if e["message"]["type"] == "provider_result"}
        current_raw = None
        def emit(event):
            event["context_origin"] = "reconstructed_from_original_core_trace_and_execution_source"
            store.append("api.jsonl", event)
        client = ObservedClient(env["config"], emit, transport=lambda *args: current_raw)
        turn = 0
        for entry in trace:
            store.append("trace.jsonl", entry)
            message = entry["message"]
            if message["type"] == "turn":
                turn += 1; client.begin(turn)
            elif message["type"] == "provider_call" and message["provider"] == "model":
                result = responses[message["request_id"]]
                if not result.get("ok"):
                    raise ValueError("historical model request failed")
                current_raw = result["result"]["raw_response"]
                client.chat(message["payload"]["messages"], env["tools"], 180)
        for item in row["turns"]:
            item["model_requests"] = sum(r["provider"] == "model" and r["turn"] == item["turn"] for r in row["provider_records"])
            item["tool_requests"] = sum(r["provider"] == "tool" and r["turn"] == item["turn"] for r in row["provider_records"])
        row.update(condition="O", historical_reuse=True, historical_repeats=[r["sample_id"] for r in rows
                   if r["scenario_id"] == "a06" and r["adapter_id"] == "core_self"],
                   transfers=audit_transfers(trace, read_rows(store.path / "api.jsonl")))
        store.result(row); store.finish("completed")
    except BaseException as exc:
        store.finish("failed", type(exc).__name__); raise
    finally:
        seal(store.path)
    return store.path


def retrieval_stage(output, environment, baseline):
    assert_sealed(environment); assert_sealed(baseline)
    env, scene = load_environment(environment)
    corpus = load_jsonl(env["corpus"])
    settings = read_json(HERE / "inputs.json")
    anchors = source_anchors(scene, env["raw_root"])
    mapped = map_anchors(anchors, corpus)
    store = new_store(output, "B", {"top_k": 5, "model_calls": 0,
        "environment": str(Path(environment).resolve()), "environment_sha256": file_hash(Path(environment) / "environment.json"),
        "baseline_sha256": file_hash(Path(baseline) / "hashes.json"), "oracle_assisted_diagnostic": True})
    try:
        write_json(store.path / "source-evidence.json", mapped, exclusive=True)
        originals = read_rows(Path(env["historical_run"]) / "results.jsonl")
        current = read_rows(Path(baseline) / "results.jsonl")
        queries = []
        for number, question in enumerate(public_turns(scene), 1):
            queries.append({"query_id": f"t{number}-user", "turn": number, "kind": "user", "query": question["content"]})
            seen = set()
            for row in [*originals, *current]:
                if row.get("scenario_id") != "a06" or row.get("adapter_id", "core_self") != "core_self":
                    continue
                for record in row.get("provider_records", []):
                    if record["provider"] == "model" and record["turn"] == number:
                        for call in record["response"].get("result", {}).get("message", {}).get("tool_calls") or []:
                            query = json.loads(call["function"]["arguments"])["query"]
                            if query not in seen:
                                queries.append({"query_id": f"t{number}-actual-{len(seen)+1}", "turn": number,
                                                "kind": "actual", "query": query}); seen.add(query)
            if not seen:
                queries.append({"query_id": f"t{number}-actual-none", "turn": number, "kind": "actual",
                                "query": None, "reason": "no_original_tool_query"})
            queries.append({"query_id": f"t{number}-oracle", "turn": number, "kind": "oracle",
                            "query": settings["oracle_queries"][number - 1], "oracle_assisted_diagnostic": True})
        write_json(store.path / "queries.json", queries, exclusive=True)
        store.manifest["planned_samples"] = [{"sample_id": q["query_id"], "query_id": q["query_id"]} for q in queries]
        index = LexicalIndex(corpus)
        for query in queries:
            if query["query"] is None:
                store.result({"sample_id": query["query_id"], **query, "execution_status": "not_applicable", "hits": []})
                continue
            hits = index.search(query["query"], 5)
            required = settings["necessary_dialogue_indices"][query["turn"] - 1]
            selected = [a for a in mapped if int(a["source_pointer"].split("/")[-2]) in required]
            store.result({"sample_id": query["query_id"], **query, "execution_status": "completed", "hits": hits,
                          "necessary": coverage(selected, hits), "all_annotated": coverage(mapped, hits)})
        store.manifest["index_build_seconds"] = index.build_seconds
        store.finish("completed")
    except BaseException as exc:
        store.finish("failed", type(exc).__name__); raise
    finally:
        seal(store.path)
    return store.path


def make_fixture(scene, corpus, retrieval_rows, assessment):
    target_id = read_json(HERE / "inputs.json")["known_correct_chunk"]
    target = next(row for row in corpus if row["id"] == target_id)
    oracle = next(r for r in retrieval_rows if r["turn"] == 1 and r["kind"] == "oracle")
    review = assessment.get("queries", {}).get(oracle["query_id"], {})
    approved = review.get("semantic_sufficiency") == "sufficient"
    hit_ids = {h["id"] for h in oracle["hits"]}
    supporting_id = next((i for i in review.get("supporting_ids", [target_id]) if i in hit_ids), None)
    selected = approved and supporting_id is not None
    evidence = deepcopy(oracle["hits"] if selected else [target])
    supporting_id = supporting_id if selected else target_id
    supporting = next(h for h in evidence if h["id"] == supporting_id)
    qualification = "根据所给 Wiki 编纂，" if supporting.get("source_kind") == "wiki_compilation" else ""
    call_id = "controlled-history-c2"
    return {"synthetic_history": True, "selection": "B_actual_top5" if selected else "direct_corpus_selection",
        "query_id": oracle["query_id"], "first_turn_model_requests": 0, "end_to_end_score": "not_applicable",
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": scene["turns"][0]["content"]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function",
                "function": {"name": "search_story", "arguments": encoded({"query": oracle["query"]})}}]},
            {"role": "tool", "tool_call_id": call_id, "content": encoded({"ok": True, "result": {"evidence": evidence}})},
            {"role": "assistant", "content": f"{qualification}夺走温迪神之心的是「女士」。[{supporting_id}]"}]}


def controlled_stage(output, environment, retrieval, a_run):
    for path in (environment, retrieval, a_run):
        assert_sealed(path)
    assessment = read_json(Path(a_run) / "assessment.json")
    if assessment.get("first_turn", {}).get("supported_correct") is True:
        raise ValueError("C2 requires an unsuccessful or uncertain first A turn")
    env, scene = load_environment(environment, require_service=True)
    corpus = load_jsonl(env["corpus"])
    reviewed = read_json(Path(retrieval) / "assessment.json")
    fixture = make_fixture(scene, corpus, read_rows(Path(retrieval) / "results.jsonl"), reviewed)
    binding = {**env, "retrieval_sha256": file_hash(Path(retrieval) / "hashes.json"),
               "retrieval_assessment_sha256": file_hash(Path(retrieval) / "assessment.json"),
               "a_run_sha256": file_hash(Path(a_run) / "hashes.json"),
               "a_assessment_sha256": file_hash(Path(a_run) / "assessment.json")}
    return run_live(output, scene, corpus, env["config"], "C2", fixture=fixture, binding=binding)


def verify_run(output, run_root):
    store = new_store(output, "verification")
    findings = []
    stages = []
    try:
        for path in sorted(Path(run_root).iterdir()):
            if path == store.path or not (path / "hashes.json").is_file():
                continue
            manifest = read_json(path / "manifest.json")
            if manifest["condition"] in {"verification", "report"}:
                continue
            stage_info = {"path": path.name, "status": manifest["status"], "hashes_sha256": file_hash(path / "hashes.json"),
                          "assessment_sha256": file_hash(path / "assessment.json") if (path / "assessment.json").exists() else None}
            findings.extend(f"{path.name}: modified {name}" for name in verify_hashes(path))
            if manifest["condition"] in {"O", "A", "C2"} and (path / "api.jsonl").exists():
                records = read_rows(path / "api.jsonl")
                stage_info["api_statistics"] = api_statistics(records)
                if manifest["condition"] == "C2":
                    delivery = audit_injected_history(read_json(path / "injected-history.json"), records)
                    stage_info["injected_history_delivery"] = delivery
                    if not delivery["exact_match"]:
                        findings.append(f"{path.name}: injected history differs from actual payload")
                for record in records:
                    if record["event"] != "request" or record.get("endpoint") != "chat/completions":
                        continue
                    payload = record["payload"]
                    if payload["messages"][0] != {"role": "system", "content": SYSTEM}:
                        findings.append(f"{path.name}: changed system")
                    if payload.get("chat_template_kwargs") != {"enable_thinking": False}:
                        findings.append(f"{path.name}: changed generation template")
                    if any(set(m) - {"role", "content", "tool_calls", "tool_call_id"} for m in payload["messages"]):
                        findings.append(f"{path.name}: unexpected message fields")
                    forced = "tool_choice" in payload
                    if forced and not (manifest["condition"] == "A" and record["turn"] == 1 and record["request"] == 1):
                        findings.append(f"{path.name}: misplaced force")
                    prefill = forced and manifest["parameters"]["model"].get("tool_choice_mode") == "required_single_tool_prefill"
                    if prefill:
                        if (payload["messages"][-1] != {"role": "assistant", "content": "<tool_call>\n"}
                                or payload.get("continue_final_message") != "content"
                                or payload.get("add_generation_prompt") is not False
                                or payload.get("tool_choice") != "required"):
                            findings.append(f"{path.name}: missing forced tool prefill")
                    elif ("continue_final_message" in payload or "add_generation_prompt" in payload
                          or any(m.get("content") == "<tool_call>\n" for m in payload["messages"])):
                        findings.append(f"{path.name}: tool prefill leaked into ordinary request")
                transfers = audit_transfers(read_rows(path / "trace.jsonl"), records)
                findings.extend(f"{path.name}: tool result not delivered intact {x['call_id']}" for x in transfers if not x["exact_match"])
            stages.append(stage_info)
        write_json(store.path / "verification.json", {"stages": stages, "findings": findings,
            "semantic_verification": "independent_review_required", "user_acceptance": "not_evaluated"}, exclusive=True)
        store.finish("failed" if findings else "completed")
    finally:
        seal(store.path)
    return store.path, not findings


def report_run(output, run_root):
    store = new_store(output, "report")
    try:
        lines = ["# a06 Diagnostic Probe", "", "程序完成、证据覆盖、引用与语义判断分别报告；用户验收未进行。", "",
                 "| 条件 | 执行状态 | 记录模型请求 | 实际新请求 | API响应/正常结束 | 工具请求 |", "| --- | --- | ---: | ---: | --- | ---: |"]
        assessments = {}
        for path in sorted(Path(run_root).iterdir()):
            if path == store.path or not (path / "hashes.json").is_file():
                continue
            manifest = read_json(path / "manifest.json")
            if manifest["condition"] in {"verification", "report"}:
                continue
            assert_sealed(path)
            rows = read_rows(path / "results.jsonl")
            api = api_statistics(read_rows(path / "api.jsonl")) if (path / "api.jsonl").exists() else api_statistics([])
            lines.append(f"| {path.name} | {manifest['status']} | {sum(r.get('model_calls', 0) for r in rows)} | {api['new_model_requests']} | {api['api_http_responses']}/{api['api_completed_responses']} | {sum(r.get('tool_calls', 0) for r in rows)} |")
            assessment = path / "assessment.json"
            if assessment.exists():
                assessments[path.name] = {"sha256": file_hash(assessment), "assessment": read_json(assessment)}
        write_json(store.path / "assessments.json", assessments, exclusive=True)
        lines.extend(["", "模型请求按实际捕获与历史重建分别计数；是否复用历史由 O 的 manifest 记录。API 响应、Provider 接受状态及指定工具是否生效分别核对，不能互相替代。", "",
                      "## B检索覆盖与语义", "", "| 查询 | 必要组Recall@5 | 必要位置排名 | 语义充分性 |", "| --- | --- | --- | --- |"])
        b_path = Path(run_root) / "B-r001"
        if b_path.exists():
            review = read_json(b_path / "assessment.json") if (b_path / "assessment.json").exists() else {}
            for row in read_rows(b_path / "results.jsonl"):
                if row.get("query") is None:
                    lines.append(f"| {row['query_id']} | 不适用 | 原运行无查询 | 不适用 |")
                    continue
                value = row["necessary"]
                ranks = ",".join(str(a["rank"]) if a["rank"] is not None else "—" for a in value["anchors"])
                semantic = review.get("queries", {}).get(row["query_id"], {}).get("semantic_sufficiency", "pending_review")
                lines.append(f"| {row['query_id']} | {value['covered_groups']}/{value['total_groups']} | {ranks} | {semantic} |")
        conclusions_path = Path(run_root) / "diagnosis.json"
        conclusions = read_json(conclusions_path) if conclusions_path.exists() else {
            "hypotheses": {h: {"verdict": "unknown", "reason": "pending semantic review"} for h in ("H1", "H2", "H3", "H4")},
            "next_component": "pending_review", "limitations": ["No semantic conclusions inferred from execution success."]}
        write_json(store.path / "diagnosis.json", conclusions, exclusive=True)
        lines.extend(["", "## 假设判断", "", "| 假设 | 判断 | 依据 |", "| --- | --- | --- |"])
        for h, value in conclusions["hypotheses"].items():
            lines.append(f"| {h} | {value['verdict']} | {value['reason']} |")
        if conclusions.get("observations"):
            lines.extend(["", "## 可复查观察", ""])
            lines.extend("- " + str(item) for item in conclusions["observations"])
        lines.extend(["", "## 下一步", "", str(conclusions["next_component"]), "", "## 限制", ""])
        lines.extend("- " + str(item) for item in conclusions["limitations"])
        if conclusions.get("remaining_evidence"):
            lines.extend(["", "## 尚缺证据", ""])
            lines.extend("- " + str(item) for item in conclusions["remaining_evidence"])
        (store.path / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        store.finish("completed")
    finally:
        seal(store.path)
    return store.path
