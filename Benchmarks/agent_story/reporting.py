"""Story semantic and service metrics."""
from .review import semantic_summary


def enrich_report(report, run, rows):
    report["semantic"] = semantic_summary(run, rows)
    for group in report["groups"]:
        selected = [r for r in rows if r["adapter_id"] == group["adapter_id"] and
                    r.get("measure", "correctness") == group["measure"]]
        group["semantic"] = semantic_summary(run, selected)
        for key in ("model_calls", "tool_calls", "model_http_responses", "model_api_completed",
                    "model_truncated", "model_failed", "usage_missing_calls"):
            group[key] = sum(r.get(key, 0) for r in selected)
        group["usage_totals"] = {key: sum(r["usage_totals"][key] for r in selected)
            if selected and all(r.get("usage_totals", {}).get(key) is not None for r in selected) else None
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    report["citation_checks"] = {"turns_with_unknown_ids": sum(bool(t["citations"]["unknown_ids"]) for r in rows for t in r.get("turns", [])),
                                 "semantic_support": "not_evaluated"}
