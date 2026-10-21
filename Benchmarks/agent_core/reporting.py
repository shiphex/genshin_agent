"""Performance comparisons for the Core workload."""


def enrich_report(report, run, rows):
    baseline = {r["round"]: r for r in rows if r.get("is_baseline") and r.get("correct") is True}
    report["paired_rounds"] = [{"sample_id": r["sample_id"], "round": r["round"],
        "raw_ms": r["per_iteration_ms"], "baseline_ms": baseline[r["round"]]["per_iteration_ms"],
        "difference_ms": r["per_iteration_ms"] - baseline[r["round"]]["per_iteration_ms"],
        "ratio": r["per_iteration_ms"] / baseline[r["round"]]["per_iteration_ms"]}
        for r in rows if not r.get("is_baseline") and r.get("correct") is True and r["round"] in baseline]
