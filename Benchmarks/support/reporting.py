from collections import defaultdict
from pathlib import Path
from .common import read_json, read_rows, summarize, distribution, write_json


def make_report(runs, output, enrichers):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    reports, table = [], ["# Spike benchmark 报告", "", "API、执行、引用与语义分别判断；user_acceptance 均未评。", "",
                          "| Run | Suite | Completed / Total | Core correct | Unjudged | Elapsed median ms |",
                          "| --- | --- | ---: | ---: | ---: | ---: |"]
    for run in map(Path, runs):
        manifest, rows = read_json(run / "manifest.json"), read_rows(run / "results.jsonl")
        report = {"run": str(run), "suite": manifest["suite"], "status": manifest["status"], **summarize(rows)}
        groups = defaultdict(list)
        for row in rows:
            groups[(row["adapter_id"], row.get("measure", "correctness"))].append(row)
        report["groups"] = [{"adapter_id": adapter, "measure": measure, **summarize(samples),
            "fixture_only": all(s.get("fixture_only", False) for s in samples),
            "startup_ms": distribution([s.get("startup_ms") for s in samples]),
            "per_iteration_ms": distribution([s.get("per_iteration_ms") for s in samples if s.get("correct") is True]),
            "sampled_peak_rss_bytes": distribution([s.get("resources", {}).get("sampled_peak_rss_bytes") for s in samples
                                                    if s.get("measure") == "memory"]),
            "cpu_seconds": distribution([s.get("resources", {}).get("cpu_seconds") for s in samples])}
            for (adapter, measure), samples in groups.items()]
        if manifest["suite"] in enrichers:
            enrichers[manifest["suite"]](report, run, rows)
        reports.append(report)
        median = report["elapsed_ms"]["median"]
        table.append(f"| {manifest['run_id']} | {manifest['suite']} | {report['completed']}/{report['total']} | {report['correct']} | {report['unjudged']} | {median} |")
    table += ["", "## 分项数据", "", "完整分组、配对轮次和 AI／人工独立计分见 summary.json；所有逐次数据在原运行目录。",
              "", "回放基准只估计公共协议与测量成本。差值不是纯内核耗时；内存为采样峰值。",
              "", "默认三次真实场景运行不能证明稳定尾延迟或统计显著性；没有综合总分或自动性能门禁。", ""]
    write_json(output / "summary.json", {"runs": reports}, exclusive=True)
    (output / "report.md").write_text("\n".join(table), encoding="utf-8")
    return output
