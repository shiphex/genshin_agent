"""Controlled evidence x sampling experiment, separate from normal RAG evaluation."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from http.client import HTTPException
import json
from pathlib import Path
import sys
import time
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit

try:
    from . import evaluate_rag_mvp as evaluate
    from . import full_corpus
except ImportError:
    import evaluate_rag_mvp as evaluate
    import full_corpus

RAG_ROOT = Path(__file__).resolve().parents[1]
PROJECT = RAG_ROOT.parent
DEFAULT_CORPUS = RAG_ROOT / "data/full/genshin_wiki_data_20260605/corpus.jsonl"
EXPERIMENT = RAG_ROOT / "experiments/generation_diagnosis"


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_trials(corpus, cases, profiles):
    """Freeze contexts once; only the sampling profile varies within each context."""
    cases = evaluate.map_source_evidence(cases, corpus)
    evaluate.validate_inputs(corpus, cases)
    if set(profiles) != {"current", "calibrated"}:
        raise ValueError("expected current and calibrated profiles")
    by_id = {row["id"]: row for row in corpus}
    index = evaluate.LexicalIndex(corpus)
    trials = []
    for case in cases:
        identities = list(dict.fromkeys(case["curated_ids"]))
        if not identities or any(i not in by_id for i in identities):
            raise ValueError(f"invalid curated IDs for {case['id']}")
        curated = [by_id[i] for i in identities]
        coverage = evaluate.evidence_coverage(case["expected_evidence"], curated)
        if coverage is None or not coverage["all_covered"]:
            raise ValueError(f"curated context lacks a reference group for {case['id']}")
        contexts = {"R": index.search(case["question"], top_k=5), "C": curated}
        messages = {k: evaluate.make_messages(case["question"], rows) for k, rows in contexts.items()}
        matrix = [("R0", "current", 42), ("C0", "current", 42)]
        matrix += [(condition, "calibrated", seed) for seed in (42, 43, 44) for condition in ("R1", "C1")]
        for condition, profile, seed in matrix:
            context = contexts[condition[0]]
            trials.append({"question_id": case["id"], "question": case["question"],
                           "condition": condition, "profile": profile, "seed": seed,
                           "generation": {**profiles[profile], "seed": seed},
                           "messages": messages[condition[0]], "evidence": context,
                           "evidence_ids": [r["id"] for r in context],
                           "evidence_coverage": evaluate.evidence_coverage(case["expected_evidence"], context)})
    return trials


def validate_sources(corpus, cases, raw_root, selected_ids=()):
    by_id = {row["id"]: row for row in corpus}
    raw_root = Path(raw_root).resolve()
    documents = {}
    def document(name):
        path = (raw_root / name).resolve()
        if not path.is_relative_to(raw_root):
            raise ValueError("source file escapes raw snapshot")
        if name not in documents:
            documents[name] = json.loads(path.read_text(encoding="utf-8-sig"))
        return documents[name]
    def resolve(doc, pointer):
        for key in pointer.lstrip("/").split("/"):
            key = key.replace("~1", "/").replace("~0", "~")
            doc = doc[int(key)] if isinstance(doc, list) else doc[key]
        return doc
    anchors = 0
    curated_ids = set()
    for case in cases:
        for group in case["expected_source_evidence"]:
            for anchor in group:
                text = resolve(document(anchor["source_file"]), anchor["source_pointer"])
                if text[anchor["start"]:anchor["end"]] != anchor["quote"]:
                    raise ValueError(f"reference quote differs from raw field: {case['id']}")
                anchors += 1
        curated_ids.update(case["curated_ids"])
    for identity in sorted(curated_ids | set(selected_ids)):
        row = by_id[identity]
        if identity in curated_ids and row.get("source_kind") != "wiki_excerpt":
            raise ValueError("curated context must use direct excerpts")
        pointers, spans = row["source_pointer"], row["source_spans"]
        if not pointers or len(pointers) != len(spans):
            raise ValueError("invalid evidence source locations")
        for pointer, span in zip(pointers, spans):
            text = resolve(document(row["source_file"]), pointer)
            if not isinstance(text, str) or not 0 <= span["start"] < span["end"] <= len(text):
                raise ValueError("invalid evidence raw character range")
        if full_corpus.reconstruct_record(document(row["source_file"]), row) != row["text"]:
            raise ValueError(f"evidence text differs from reconstructed raw fields: {identity}")
    return {"reference_anchors_checked": anchors,
            "source_files": {name: fingerprint(raw_root / name) for name in documents}}


def write_review(output, trials, results):
    lines = ["# 证据与采样参数受控诊断：原始回答", "",
             "R为当前Top5检索证据，C为人工选定直接原文；0为当前参数，1为校准参数。",
             "采样配置整体变化；不单独归因于温度。ok仅表示调用正常结束，语义与引用需回查。", ""]
    by_question = list(dict.fromkeys(t["question_id"] for t in trials))
    for identity in by_question:
        own = [t for t in trials if t["question_id"] == identity]
        lines += [f"## {identity} · {own[0]['question']}", ""]
        for source in ("R", "C"):
            context = next(t["evidence"] for t in own if t["condition"][0] == source)
            lines += [f"### {source} · 输入证据", ""]
            for row in context:
                lines += [f"#### [{row['id']}] {row['title']}", "",
                          "来源性质：`" + row.get("source_kind", "unknown") + "`；出处：`" + row.get("source_file", "") + "`；Pointer：`" + str(row.get("source_pointer", [])) + "`。", "",
                          row["text"], ""]
        for result in (r for r in results if r["question_id"] == identity):
            answer = result["answer"]
            lines += [f"### {result['condition']} · seed {result['seed']} · {answer['status']}", "",
                      "请求参数：`" + json.dumps(result["generation"], ensure_ascii=False) + "`", "",
                      answer.get("text", "调用失败：" + answer.get("error", "unknown")), ""]
        lines += ["初步来源复核与用户验收另行记录，不自动判断事实正确。", ""]
    (output / "review.md").write_text("\n".join(lines), encoding="utf-8")


def run_trials(trials, config, output, input_manifest=None, chat_fn=None):
    """Save each completed call immediately; never overwrite an existing run."""
    output = Path(output).resolve()
    evaluate.validate_output_dir(output, protect_sample=True)
    output.mkdir(parents=True, exist_ok=False)
    chat_fn = chat_fn or evaluate.chat
    write_json(output / "sealed_inputs.json", {"sealed_at_utc": datetime.now(timezone.utc).isoformat(),
                                              "trials": len(trials), "input_manifest": input_manifest or {}})
    write_json(output / "trials.json", trials)
    results = []
    with (output / "requests.jsonl").open("x", encoding="utf-8") as requests, (output / "results.jsonl").open("x", encoding="utf-8") as answers:
        for number, trial in enumerate(trials, 1):
            print(f"[{number}/{len(trials)}] {trial['question_id']} {trial['condition']} seed={trial['seed']}", file=sys.stderr, flush=True)
            request = {"model": config["model"], "messages": trial["messages"], "stream": False,
                       "temperature": 0, "seed": 42, "max_tokens": config.get("max_tokens", 768),
                       "chat_template_kwargs": {"enable_thinking": False}, **trial["generation"]}
            requests.write(json.dumps({"call_number": number, "question_id": trial["question_id"],
                                       "condition": trial["condition"], "seed": trial["seed"], "payload": request}, ensure_ascii=False) + "\n")
            requests.flush()
            started = time.monotonic()
            try:
                answer = chat_fn(config, trial["messages"], generation=trial["generation"])
                answer["citation_audit"] = evaluate.citation_audit(answer["text"], trial["evidence"])
            except (HTTPException, URLError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                answer = {"status": "error", "error": type(exc).__name__}
            answer["elapsed_seconds"] = round(time.monotonic() - started, 3)
            result = {k: v for k, v in trial.items() if k not in ("messages", "evidence")}
            result["answer"] = answer
            answers.write(json.dumps(result, ensure_ascii=False) + "\n")
            answers.flush()
            results.append(result)
    summary = {"completed_at_utc": datetime.now(timezone.utc).isoformat(), "model": config["model"],
               "max_tokens": config.get("max_tokens", 768), "enable_thinking": False,
               "questions": len({t["question_id"] for t in trials}), "calls": len(results),
               "call_statuses": dict(Counter(r["answer"]["status"] for r in results)),
               "condition_calls": dict(Counter(r["condition"] for r in results)),
               "semantic_evaluation": "pending_source_review", "user_acceptance": "pending",
               "model_call_seconds": round(sum(r["answer"]["elapsed_seconds"] for r in results), 3)}
    write_json(output / "summary.json", summary)
    write_review(output, trials, results)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=EXPERIMENT / "cases.jsonl")
    parser.add_argument("--profiles", type=Path, default=EXPERIMENT / "generation_profiles.json")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--raw-root", type=Path, default=PROJECT / "data/raw/genshin_wiki_data_20260605")
    parser.add_argument("--config", type=Path, default=RAG_ROOT / "experiments/mvp/local_api.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        evaluate.validate_output_dir(args.output_dir, raw_root=args.raw_root,
                                     input_paths=(args.cases, args.profiles, args.corpus, args.config), protect_sample=True)
        if args.output_dir.exists():
            raise FileExistsError("diagnosis output directory already exists")
        corpus, cases = evaluate.load_jsonl(args.corpus), evaluate.load_jsonl(args.cases)
        profiles = json.loads(args.profiles.read_text(encoding="utf-8-sig"))
        config = json.loads(args.config.read_text(encoding="utf-8-sig"))
        trials = prepare_trials(corpus, cases, profiles)
        sources = validate_sources(corpus, cases, args.raw_root,
                                   selected_ids={i for trial in trials for i in trial["evidence_ids"]})
        models = evaluate.api_request(config, "models")["data"]
        model = config.get("model")
        if not model:
            if len(models) != 1:
                raise ValueError("set an explicit model ID")
            model = models[0]["id"]
        if model not in {m["id"] for m in models}:
            raise ValueError("configured model is not served")
        config["model"] = model
        if config.get("max_tokens") != 1536:
            raise ValueError("controlled diagnosis requires max_tokens=1536")
        url = urlsplit(config["base_url"])
        service = {**config, "base_url": urlunsplit((url.scheme, url.netloc, "", "", ""))}
        props = evaluate.api_request(service, "props")
        template = evaluate.api_request(service, "apply-template", {
            "messages": [{"role": "user", "content": "template probe"}], "add_generation_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
        if not template.endswith("<think>\n\n</think>\n\n"):
            raise ValueError("non-thinking template probe differs from expected Qwen template")
        manifest = {"files": {str(p.resolve()): fingerprint(p) for p in (args.cases, args.profiles, args.corpus, args.config)},
                    "config": {k:config.get(k) for k in ("base_url", "model", "max_tokens", "timeout")},
                    "profiles": profiles, "sources": sources,
                    "runtime": {"build_info": props.get("build_info"), "default_generation_settings": props.get("default_generation_settings"),
                                "chat_template": props.get("chat_template"), "nonthinking_probe_tail": template[-160:]},
                    "question_checks": {case["id"]:case.get("checks", []) for case in cases},
                    "answer_reference_sent_to_model": False,
                    "evaluation_script_sha256": fingerprint(Path(evaluate.__file__)), "runner_sha256": fingerprint(Path(__file__))}
        summary = run_trials(trials, config, args.output_dir, input_manifest=manifest)
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if summary["call_statuses"].get("ok", 0) == len(trials) else 1
    except (HTTPException, URLError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        print(f"Diagnosis failed ({type(exc).__name__}); inspect inputs, service and saved results.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
