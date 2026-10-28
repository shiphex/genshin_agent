"""Describe existing benchmark rows; never execute candidates or change verdicts."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from Benchmarks.support.common import distribution, read_json, read_rows

root = Path(__file__).resolve().parents[1] / "evidence"
output = Path(sys.argv[1])
output.mkdir(parents=True, exist_ok=True)
analysis = {}
for phase in ("timing", "memory"):
    run = root / "agent_core/perf" / f"core-probe-{phase}-r001"
    rows = read_rows(run / "results.jsonl")
    assert len(rows) == 21
    assert all(r["execution_status"] == "completed" and r["correct"] is True
               and r["conformance_status"] == "passed" for r in rows)
    groups = {}
    for adapter in ("core_self", "core_sdk", "transport_replay"):
        samples = [r for r in rows if r["adapter_id"] == adapter]
        assert len(samples) == 7
        groups[adapter] = {
            "per_iteration_ms": distribution([r["per_iteration_ms"] for r in samples]),
            "startup_ms": distribution([r["startup_ms"] for r in samples]),
            "cpu_seconds": distribution([r["resources"].get("cpu_seconds") for r in samples]),
            "sampled_peak_rss_mib": distribution([
                r["resources"]["sampled_peak_rss_bytes"] / 1048576 for r in samples
                if r["resources"].get("sampled_peak_rss_bytes") is not None]),
            "rounds": samples,
        }
    pairs = []
    for number in range(1, 8):
        pair = {r["adapter_id"]: r for r in rows if r["round"] == number}
        first = pair["core_self"]["per_iteration_ms"]
        second = pair["core_sdk"]["per_iteration_ms"]
        pairs.append({"round": number, "self_ms": first, "sdk_ms": second,
                      "difference_ms": second - first, "ratio": second / first})
    analysis[phase] = {
        "groups": groups, "paired_sdk_vs_self": pairs,
        "paired_difference_ms": distribution([r["difference_ms"] for r in pairs]),
        "paired_ratio": distribution([r["ratio"] for r in pairs]),
        "parameters": read_json(run / "manifest.json")["parameters"],
    }
with (output / "analysis.json").open("x", encoding="utf-8") as handle:
    json.dump(analysis, handle, ensure_ascii=False, indent=2)
print(json.dumps({p: {k: {m: v for m, v in g.items() if m != "rounds"}
                     for k, g in data["groups"].items()} for p, data in analysis.items()}, indent=2))
print(json.dumps({p: {k: v for k, v in data.items() if k.startswith("paired_")}
                  for p, data in analysis.items()}, indent=2))
