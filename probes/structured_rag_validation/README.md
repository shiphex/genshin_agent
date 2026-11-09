---
kind: reference
description: "验证V2证据的A06表现、固定证据呈现及相关多轮场景。"
---
# 结构化 RAG 探针验证

## 摘要

实验组合 RAG `94a46ef` 与 A06 探针 `387067c`，只使用 core-self；不评选 SDK 或提升默认语料。历史 A06 r003/report-r002 只作参照。模型失败保留，执行、检索、API、引用及语义分开；独立 AI 审阅不代表用户验收。

## 目录

- [实验条件](#实验条件)
- [运行与材料](#运行与材料)
- [验证与评审](#验证与评审)
- [Dev Note](#dev-note)

## 实验条件

使用主项目只读 corpus/r002、prepared/r004 的迁移题库与261106 raw；场景 a06/a07/a10/a11 的题面和标准不变。独立场景绑定保存实际题库路径、哈希、模板及冻结材料；`load_scenarios` 可选 `questions_path`，缺省仍读取正式题库。旧位置只通过迁移报告定位到新位置，不直接匹配新版语料。

Qwen3.5-4B Q4、temperature=0、seed=42、1536 token、关闭思考；Top5、每轮8次请求、240秒，串行执行。服务使用[既有启动器](../../rag/docs/local_model.md#启动与调用)及主工作区公共配置和私有覆盖；实验请求不套用 standard 档位。检查原 A06 权重、二进制及实际启动命令，结束仅停止本次拥有的服务。

O自主一次；B无模型，保存原问、实际查询及oracle Top5。A三次，仅首轮首请求指定 search_story，后续恢复自主；首答完整正确且有据时，后两轮才属于C1。失败或存疑样本对应C2：充分性审阅后，以完整证据和仅回答女士的正确首答构造历史，只执行后两轮，不算端到端。技术强制调用失败不通过换策略或增预算重试。完成后追加全部实际查询审计。

呈现对照分别覆盖首问人物与第三问说话者归属。两组共用 `to_model_evidence` 输出；文本组仅将content依次渲染为turn/section编号及“字段名: JSON值”，options用独立编号和结束标记，保留空集合、null、空串及质量提示。其他字段、片段顺序、历史、工具说明和参数相同。每组各三次，顺序交替，tool_choice=none，单次续答，不新增检索或计入端到端。a07/a10/a11各自主运行三次、干净worker。

## 运行与材料

在本实验worktree根使用项目uv环境和benchmark依赖，完整参数见 `python -B -m probes.structured_rag_validation --help`。显式传入共享主项目绝对路径；输出目录必须新建，位于Benchmarks/outputs/agent_story/structured_rag_validation之下。

```powershell
$project = 'E:/Workplace/Learn_project/genshin_agent'
$u = @('--cache-dir',"$project/.cache/uv",'run','--locked','--group','benchmark','--offline','--no-python-downloads','--python','3.11','python','-B')
$run = 'Benchmarks/outputs/agent_story/structured_rag_validation/rNEW'
uv @u -m probes.structured_rag_validation prepare --project $project --run $run
uv @u -m probes.structured_rag_validation start --run $run
uv @u -m probes.structured_rag_validation preflight --run $run
uv @u -m probes.structured_rag_validation live --run $run --condition O
uv @u -m probes.structured_rag_validation retrieval --run $run --name B-r001
```

先审阅B，再运行A并独立评估首答；使用 `assess` 将独立评估导入各阶段的只增版本。评估输入必须声明匹配该阶段hashes.json的 `stage_hashes_sha256` 与reviewer；samples逐项包含criteria的id/verdict/rationale/evidence_refs，B的queries包含充分性、supporting_ids及reason，A另含first_turn.supported_correct（true/false/null）与reason。C2引用具体评估版本及哈希。其余命令为live（A/C2/R）、presentation、retrieval（B-final-r001）、verify、report和stop。每步检查退出码，服务异常时仍保留失败目录并清理本次进程。CLI不会下载模型。stage的hashes及sources封存原件，后续评估不覆盖它们。

## 验证与评审

```powershell
uv @u -m unittest discover -s probes/structured_rag_validation/tests -v
uv @u -m unittest discover -s probes/core_self/tests -v
uv @u -m unittest discover -s Benchmarks -t . -v
uv @u -m unittest discover -s rag/tests -v
uv @u scripts/doc_sync.py
git diff --check
```

独立审阅每个场景的criteria与forbidden，并说明已送达证据是否支持断言；B的位置指标不代替充分性。评估项使用pass/fail/uncertain、理由和可回查定位。C2和呈现对照单列诊断，固定seed的有限重复不支持统计显著性。结果保留实际payload、原始响应、完整hit、来源和日志；计数仅使用API实际usage，缺失不冒充token统计。执行前后核对当前基线14文件，输出及评估不纳入Git。

模型阶段要求当前源码与prepare时一致；verify/report允许使用已核验的执行源码封存，另记当前后处理源码、原执行commit及变化文件。它们仍核对全部输入、场景与封存哈希，不用放宽输入校验来适配新报告。r001模型执行于0ec0c09，后处理修正provider的tool_calls计数；原请求、回答、评分和来源均不改。

## Dev Note

无。
