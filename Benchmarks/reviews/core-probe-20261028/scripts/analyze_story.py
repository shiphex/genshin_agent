"""Summarize frozen Story execution; semantic verdicts come from independent review."""
import hashlib
import json
import sys
import statistics
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "evidence"
run = root / "agent_story/agent/core-probe-live-r001"
rows = [json.loads(line) for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines()]
assert len(rows) == 18
assert all(r["execution_status"] == "completed" and r["conformance_status"] == "passed" for r in rows)
def dist(values):
    return {"n": len(values), "median": statistics.median(values), "min": min(values), "max": max(values)}
groups = {}
for adapter in ("core_self", "core_sdk"):
    selected = [r for r in rows if r["adapter_id"] == adapter]
    turns = [turn for row in selected for turn in row["turns"]]
    groups[adapter] = {
        "samples": len(selected), "completed": sum(r["execution_status"] == "completed" for r in selected),
        "conformance_passed": sum(r["conformance_status"] == "passed" for r in selected),
        "turns": len(turns), "all_turn_status_completed": all(t["result"]["status"] == "completed" for t in turns),
        "citations": {"turns_with_citations": sum(t["citations"]["has_citations"] for t in turns),
                      "unknown_citation_ids": sorted({c for t in turns for c in t["citations"]["unknown_ids"]})},
        "sample_elapsed_ms": dist([r["elapsed_ms"] for r in selected]),
        "turn_elapsed_ms": dist([t["elapsed_ms"] for t in turns]),
        "scenarios": {s: {"sample_elapsed_ms": dist([r["elapsed_ms"] for r in selected if r["scenario_id"] == s]),
                          "model_calls": sum(r["model_calls"] for r in selected if r["scenario_id"] == s),
                          "tool_calls": sum(r["tool_calls"] for r in selected if r["scenario_id"] == s)}
                      for s in ("a01", "a06", "a12")},
        **{field: sum(r[field] for r in selected) for field in
           ("model_calls", "tool_calls", "model_http_responses", "model_api_completed", "model_truncated", "model_failed", "usage_missing_calls")},
        "usage_totals": {k: sum(r["usage_totals"][k] for r in selected)
                         for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
    }
same = {}
for s in ("a01", "a06", "a12"):
    samples = [r for r in rows if r["scenario_id"] == s]
    normalized = [[{"user": t["user"], "answer": t["result"]["content"],
                    "status": t["result"]["status"], "citations": t["citations"]}
                   for t in r["turns"]] for r in samples]
    unique = {json.dumps(x, sort_keys=True, ensure_ascii=False) for x in normalized}
    same[s] = {"samples": len(samples), "distinct_answer_sequences_with_citations": len(unique)}
summary = {"groups": groups, "same_response_check": same,
           "total_in_run_model_calls": sum(r["model_calls"] for r in rows),
           "additional_successful_preflight_calls": 2,
           "execution_order": [r["adapter_id"] + ":" + r["scenario_id"] + ":" + str(r["repeat"]) for r in rows],
           "run_sha256": {n: hashlib.sha256((run / n).read_bytes()).hexdigest()
                          for n in ("manifest.json", "results.jsonl", "materials.json")}}
output = Path(sys.argv[1])
output.mkdir(parents=True, exist_ok=True)
target = output / "execution-analysis.json"
with target.open("x", encoding="utf-8") as handle:
    json.dump(summary, handle, ensure_ascii=False, indent=2)
print(json.dumps(summary, ensure_ascii=False, indent=2))
