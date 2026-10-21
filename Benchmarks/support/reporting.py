from collections import defaultdict
from html import escape
from pathlib import Path
from .common import read_json, read_rows, summarize, distribution, write_json


def _cell(value):
    return escape(str(value)).replace("|", "&#124;").replace("\n", "<br>").replace("\r", "")


def _adaptation_details(label, declaration):
    lines = ["", f"### {_cell(label)}：人工声明", "", f"目标：{_cell(declaration['target'])}", "",
             "| 职责 | 责任方 |", "| --- | --- |"]
    lines += [f"| {area} | {_cell(owner)} |" for area, owner in declaration["ownership"].items()]
    if declaration["changes"]:
        lines += ["", "| 范围 | 默认行为 | 适配行为 | 原因 |", "| --- | --- | --- | --- |"]
        lines += ["| " + " | ".join(_cell(change[key]) for key in
                  ("area", "default_behavior", "adapted_behavior", "reason")) + " |"
                  for change in declaration["changes"]]
    else:
        lines += ["", "声明没有修改默认行为。"]
    if "effort_notes" in declaration:
        lines += ["", "投入与维护说明：" + _cell(declaration["effort_notes"])]
    return lines


def make_report(runs, output, enrichers):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    reports, table = [], ["# Spike benchmark 报告", "", "API、执行、引用与语义分别判断；user_acceptance 均未评。",
        "", "V0 协议符合性仅评价候选及适配器是否满足规定行为，不能直接用于排列 SDK 架构优劣。",
        "fixed-history-v0 的剧情结果来自固定历史配置，尚未评估 SDK 自主摘要或裁剪历史的表现。", "",
        "| Run | Suite | 评测口径 | Completed / Total | V0 协议符合性（通过／失败／未判定 / 总数） | 未记录 | Elapsed median ms |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |"]
    adaptations = ["", "## 候选适配记录", "", "适配成本为人工声明，未经框架事实核验；未记录不表示零改动或低成本。",
                   "", "| Run | 候选 | 阶段 | 回放 | 适配记录 |", "| --- | --- | --- | --- | --- |"]
    declarations = []
    for run in map(Path, runs):
        manifest, rows = read_json(run / "manifest.json"), read_rows(run / "results.jsonl")
        report = {"run": str(run), "suite": manifest["suite"], "status": manifest["status"],
                  "evaluation_profile": manifest.get("evaluation_profile"), **summarize(rows)}
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
        identities = {a["id"]: a for a in manifest.get("adapters", [])}
        for group in report["groups"]:
            declaration = identities.get(group["adapter_id"], {}).get("adaptation")
            group["adaptation"] = ({"status": "declared", "declaration": declaration}
                                   if declaration is not None else {"status": "not_recorded"})
            adaptations.append("| " + " | ".join(_cell(value) for value in (manifest["run_id"], group["adapter_id"],
                group["measure"], "是" if group["fixture_only"] else "否", "人工声明" if declaration is not None else "未记录")) + " |")
            if declaration is not None:
                declarations += _adaptation_details(f"{manifest['run_id']} / {group['adapter_id']} / {group['measure']}", declaration)
        if manifest["suite"] in enrichers:
            enrichers[manifest["suite"]](report, run, rows)
        reports.append(report)
        median = report["elapsed_ms"]["median"]
        conformance = report["conformance"]
        profile = report["evaluation_profile"] or "历史口径未声明"
        verdicts = f"{conformance['passed']}／{conformance['failed']}／{conformance['not_evaluated']} / {conformance['total']}"
        if conformance["not_recorded"] == conformance["total"]:
            verdicts = "未记录"
        table.append(f"| {_cell(manifest['run_id'])} | {_cell(manifest['suite'])} | {_cell(profile)} | {report['completed']}/{report['total']} | {verdicts} | {conformance['not_recorded']} | {median} |")
    table += adaptations + declarations
    table += ["", "## 分项数据", "", "完整分组、配对轮次和 AI／人工独立计分见 summary.json；所有逐次数据在原运行目录。",
              "旧 correct／incorrect／unjudged 统计保留在 JSON；缺失符合性字段不从旧正确性推断，不并入新口径的通过或失败数。",
              "", "性能包含候选、适配器及既有 broker、oracle、JSONL 测量范围，不能解释为 SDK 默认实现的独立成本。",
              "", "回放基准只估计公共协议与测量成本。差值不是纯内核耗时；内存为采样峰值。",
              "", "默认三次真实场景运行不能证明稳定尾延迟或统计显著性；没有综合总分或自动性能门禁。", ""]
    write_json(output / "summary.json", {"runs": reports}, exclusive=True)
    (output / "report.md").write_text("\n".join(table), encoding="utf-8")
    return output
