---
kind: reference
description: "运行独立a06故障诊断，核对检索、实际模型上下文及受控历史。"
---
# a06 Diagnostic Probe

## 摘要

假设驱动诊断，顺序O→B→A→C；不修复a06，不比较SDK。续跑只从fa31e46导入`QwenClient`及其配置依赖，其余公共组件、原Core和冻结输入不改。复用`LiveProvider`和完整`LexicalIndex`，增加实验控制与记录。原问题和标准见[Story](../../Benchmarks/agent_story/README.md)，历史身份见[评审入口](../../Benchmarks/reviews/core-probe-20261028/README.md)。AI审阅不等于用户验收。

## 目录

- [条件与判定](#条件与判定)
- [准备与命令](#准备与命令)
- [证据与审阅](#证据与审阅)
- [实现与验证](#实现与验证)

## 条件与判定

| 条件 | 干预与限制 |
| --- | --- |
| O | 关键身份全部一致才复用历史a06第1样本，另两次为佐证；否则原样重跑。历史HTTP payload由原轨迹和执行源码重建，明确标注，不能当原始HTTP捕获。 |
| B | 无模型；每轮比较原问、实际查询及固定oracle-assisted查询。原查询不存在时记不适用。Top5完整保存。 |
| A/C1 | 只在首轮首请求指定`search_story`，之后恢复自主调用。首答有证据且正确时，原会话后两轮才属于C1；不重置。 |
| C2 | A首答不成功或存疑时构造正确历史，只真实执行第2/3轮；不计端到端成绩。 |

本实验[API配置](api.json)保留temperature0、seed42、max_tokens1536、关闭思考，只增加`tool_choice_mode=required_single_tool_prefill`，不套用生成档位。指定调用转为唯一工具加required，临时追加assistant内容`<tool_call>`及换行，设`continue_final_message=content`、`add_generation_prompt=false`；前缀不进入正常历史。Top5、每轮8次模型请求、240秒轮次期限、serial/recover/error/0保持。配置`top_k`不是采样参数；实际payload另含`reasoning_format=deepseek`。O/A使用相同客户端与服务，历史O不跨修复复用；A改变生成起点并跳过该步自由正文，不是旧A的相同请求。

C2优先使用首轮oracle实际Top5，经独立于位置指标的语义审阅确认并列出`supporting_ids`；首答只回答女士，引用实际选中的证据，Wiki编纂明确限定。只有无充分结果才直接选完整正确语料片段。构造的tool消息不是一次真实工具执行。完整片段自然含后问信息，不裁剪。

每条件先一次；出现明确差异或不稳定时，相关A/C条件补足总计三次。B不重复。A技术不兼容不重复冒充对照。首轮一直正确而只有C1失败时，不自动增跑C2。

旧r001因对象`tool_choice`类型告警使A无效；r002已发送required，但允许前置正文直至耗尽预算。r003显式接入已发布的前缀模式，记录线上payload、原始响应及服务日志，未完成指定调用即停止，不改系统提示、放宽预算或另换策略；`length`不能单独证明服务忽略参数。校验器检查强制前缀与续写参数，并拒绝其泄漏到普通请求。

## 准备与命令

从本实验worktree根运行，使用项目Python3.11及现有benchmark依赖；不安装SDK组。语料、原始快照、模型和私有路径不随Git提供。服务由用户部署；CLI不自动启动或下载。

```powershell
$project = 'E:/Workplace/Learn_project/genshin_agent'
$u = @('--cache-dir',"$project/.cache/uv",'run','--locked','--group','benchmark','--offline','--no-python-downloads','--python','3.11','python','-B')
$out = 'Benchmarks/outputs/agent_story/a06_diagnosis/rNEW'
$history = "$project/.cache/worktrees/core-compare/Benchmarks/outputs/agent_story/agent/core-probe-live-r001"
uv @u -m probes.a06_diagnosis inspect --historical-run $history --config probes/a06_diagnosis/api.json --corpus "$project/rag/data/corpus/corpus.jsonl" --raw-root "$project/data/raw/genshin_wiki_data_20260605" --server-log .cache/a06-service-rNEW/stderr.log --output "$out/environment"
uv @u -m probes.a06_diagnosis o --environment "$out/environment" --historical-run $history --output "$out/O-r001"
uv @u -m probes.a06_diagnosis b --environment "$out/environment" --baseline "$out/O-r001" --output "$out/B-r001"
uv @u -m probes.a06_diagnosis a --environment "$out/environment" --output "$out/A-r001"
```

`inspect`核对权重、二进制、模型ID、进程身份和实际命令；启动配置来自同一主项目，公共配置内容与启动源码绑定fa31e46，私有配置哈希仍绑定历史。JSON按内容比较以容许检出换行差异，保留实际字节哈希。历史复用另要求客户端和配置完全一致；服务未就绪、启动未核实或身份改变均拒绝模型阶段。失败目录保留，每个命令须检查退出码。

B后人工填`B-r001/assessment.json`：`queries.<query_id>`含`semantic_sufficiency`（sufficient/insufficient/uncertain）、`supporting_ids`及证据理由。A另填`first_turn.supported_correct`（true/false/null）；null必须说明不确定或技术失败。两者独立于原始记录。满足条件后：

```powershell
uv @u -m probes.a06_diagnosis c2 --environment "$out/environment" --retrieval "$out/B-r001" --a-run "$out/A-r001" --output "$out/C2-r001"
uv @u -m probes.a06_diagnosis verify --run-root $out --output "$out/verification-rNEW"
uv @u -m probes.a06_diagnosis report --run-root $out --output "$out/report-rNEW"
```

报告读取根输出下的`diagnosis.json`，包含`hypotheses`中H1–H4各自`verdict/reason`、`next_component`、`limitations`；未提供时全部未知，不自动评分。关键重复按需改用r002/r003，服务请求始终串行。

## 证据与审阅

每阶段manifest绑定实际源码和输入；sources保存执行源码，hashes封存原始产物。api记录送往原transport的完整JSON及原始响应，trace保留Core/provider协议；不记录headers、环境变量值或异常敏感正文。语义assessment单独保存，报告绑定其哈希。

B分别报告必要证据组Recall@5和全部标注覆盖、排名、未映射项及语义充分性。位置漏召回不能排除替代证据。`freeze_sources`只提取内容，说话者必须从冻结字段的同级`说话者`核对，并确认实际payload片段含其标记。

工具返回→后续payload逐项比较完整包装与文本，不只比较ID。C2注入另行标记。API payload证明客户端发送，不能独自证明服务未裁剪；服务日志及token信息不足时不强判H4。正确首答后的指代漂移只支持H3方向，H3/H4可并存。单次差异不是因果证明。

一个实现Agent和一个只读Reviewer核对变量隔离、答案泄漏、上下文、证据、判定与结论。原始结果不追加公共评分，不自动发布、提交、推送或清理。

## 实现与验证

`controls.py`观测并控制一次请求；`runner.py`复用原worker/provider；`history_worker.py`只在reset后的首次turn装载一次历史；`environment.py`与`stages.py`负责身份和阶段操作；`evidence.py`复用来源映射并检查传递。

```powershell
uv @u -m unittest discover -s probes/a06_diagnosis/tests -v
uv @u -m unittest discover -s probes/core_self/tests -v
uv @u -m unittest discover -s Benchmarks -t . -v
uv @u scripts/doc_sync.py
git diff --check
```

测试用临时数据和假transport，不依赖真实服务。当前结果与限制见[Benchmark context](../../Benchmarks/context.md)，完整输出沿用[产物规则](../../Benchmarks/README.md)，不纳入Git。
