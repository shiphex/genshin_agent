---
kind: reference
description: "补入真实 Story Smoke、匿名 AI 初评及引用格式审计的 Core 探针对比。"
---
# Core 技术探针对比：真实 Story 补测

## 摘要

2026-10-28，按用户补充授权，从 dev/v0.2 的配置启动本地模型；两条候选的 Story 执行与协议均 9/9 通过，匿名 AI 初评均 6/9。三场景各有 6 份完全相同的逐轮回答序列，当前没有观察到 Core 路线造成的剧情质量差异。多轮人物延续 a06 是共同失败点。本报告新增真实模型证据；原 r001 的“当时未运行”记录原位保留，不覆盖历史。

## 目录

- [代码与模型条件](#代码与模型条件)
- [结果](#结果)
- [语义与引用问题](#语义与引用问题)
- [结论与后续](#结论与后续)
- [复现与资料](#复现与资料)

## 代码与模型条件

| 项目 | 实际身份／条件 |
| --- | --- |
| 原共同基线 | dev/v0.2 @ 1b25d92510dcaa0d4ff6e0216e589f2b3a881bb4 |
| core-self | 2de247252c064a40029b04bdcb9d4f8760a78f39 |
| core-sdk | 6e3e72f5f61954f154a077bf84b8bf2015c25033；修复源码 c53efa9 |
| 本轮 Benchmark 执行版本 | exp/core-compare @ 9c372c83e8ba8e23f83357e323aa9f9c7be97f0a |
| 补测文档交接 commit | exp/core-compare @ 9892c1d7e5e624c56a1e4329a8d3b063e5d15560 |
| 启动配置与脚本来源 | dev/v0.2 @ 18153d2；公共 local_api.json + Git 忽略的 local_api.local.json |
| 模型 | genshin-qwen35-4b，Qwen3.5-4B-Q4_K_M.gguf，2,740,937,888 字节 |
| 模型 SHA-256 | 00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4 |
| 服务 | llama.cpp 9837 / b3fed31b9；localhost:8000；16K 上下文、单槽位、全 GPU、256/128 batch、F16 KV |
| 共同客户端 | temperature=0、seed=42、max_tokens=1536、enable_thinking=false、API timeout=180 秒 |
| Story 条件 | a01/a06/a12，各 3 次，每次新 worker；max_steps=8、Top5、每轮期限240秒、timing |
| 语料与输入 | catalog 全量22,822片段和原冻结快照只读复用；题库／场景不变 |

新版配置的默认 standard 档含思考与不同采样参数；本轮只复用其服务启动配置，客户端继续使用已确认 contract 的原固定参数，写入独立 api.json，避免旧版 Benchmark 不支持新嵌套字段。这里没有验证 standard/deep 思考质量、显存目标或游戏帧时间。启动模型已由用户本轮显式授权，未改冻结 contract 或合并新版公共客户端。

## 结果

| 检查 | core-self | core-sdk |
| --- | ---: | ---: |
| Core Smoke／完整 Core（沿用 r001） | 9/9、15/15 | 9/9、15/15 |
| 本轮 Story 场景执行／协议符合性 | 9/9、9/9 | 9/9、9/9 |
| 完成对话轮数 | 18/18 | 18/18 |
| 正常完成模型 API 调用 | 27/27 | 27/27 |
| 工具调用 | 9 | 9 |
| API失败／截断／usage缺失 | 0／0／0 | 0／0／0 |
| 冻结标准下 AI 语义初评 | 6/9 | 6/9 |
| a01／a06／a12 初评 | 3/3、0/3、3/3 | 3/3、0/3、3/3 |
| 人工／用户语义验收 | 未进行 | 未进行 |

共 54 次场景内模型请求，另有独立预检和 runner 内置预检各1次，合计 **56 次真实模型调用**。18 样本共96个必需评分项，AI 初评60 pass、36 fail、0 uncertain；CLI 导入已核对完整标准、冻结运行身份和证据定位。引用检查、API及语义分别报告，不从执行完成推断剧情正确。原生 summary 的通用 correct/unjudged 字段不承担 Story 语义结论，读取 groups[].semantic.ai。

下表为完整场景耗时，排除 worker 启动／清理，含模型、检索和对话内各轮；中位数 [最小,最大]，单位秒，每格仅3次：

| 场景 | core-self | core-sdk |
| --- | ---: | ---: |
| a01 单事实检索，1轮 | 8.004 [7.999,8.253] | 7.983 [7.976,8.353] |
| a06 人物指代延续，3轮 | 31.249 [31.181,31.265] | 31.296 [31.249,31.348] |
| a12 不确定身份等同，2轮 | 9.955 [9.916,12.450] | 9.888 [9.885,9.894] |

两路每路 usage 均为 prompt 68,781、completion 8,895、total 77,676 tokens。单服务缓存未清除；每场景实际次序 A,B,B,A,B,A（重复号1/2/3），非严格交替。模型负载及缓存主导这些延迟，3次重复不能判断显著性或推出 SDK 更快。

原固定 Core 性能未重跑，也未与真实模型延迟混算：主要负载延迟中位19.050／21.579 ms，启动42.589／1263.937 ms，独立 memory 采样峰值16.824／79.227 MiB；源码202／263行，新增包0／39。完整7轮范围、真实调度偏差和源码审阅仍见 r001。

## 语义与引用问题

独立 Reviewer 只读取匿名包与冻结材料，没有读取候选映射；随后由主 Agent 导入 AI 评分，不作为用户验收。

- **a06 共同失败：** 模型否认女士夺走神之心，追问将人物漂移为“芙宁娜＝女士”，末轮错误套用林尼相关材料并臆推效忠公子。6份回答的6项标准全部失败，表现为事实、指代及证据归属问题。协议完整保存了历史；没有通过修改 Core 或提示词修饰结果。
- **a01 通过冻结项仍有风险：** 回答覆盖七星整体秘书和首届七星时期；检索文本提供其年代说法的依据，但原题材料与额外检索材料之间有年代张力，不能据此认定所有额外历史表述均已核实。
- **a12 通过冻结项仍有风险：** 两轮保留“或许”并拒绝确定身份等式；首轮仍有超出材料的过度解读。通过本轮标准不表示额外陈述全部正确。

**引用格式单列：** 公共 checker 只识别裸 [ID]，全部36轮 has_citations=false，unknown_ids为空不能当作引用通过。实际每路18轮中9轮使用 [片段ID: ID]，出现18个ID；只读补充审计确认这些ID全部属于对应轮已见证据，其余9轮未提供这种ID。补充审计只确认成员关系，不修正公共 checker、不确认语义支持，也不改变冻结评分。a06 正说明“ID来自已见材料”仍可出现主体与断言错配。

先前公开的 tool_calls:null 公共层潜在边界本轮未触发，不能登记为已修复。

## 结论与后续

两路都可接通既有真实模型和 RAG，多轮 a06 的问题及整体回答完全相同；本次证据不支持用 Core 选型解释剧情差异。当前最小负载下，自建的资源与依赖成本仍较低，保留其优先验证建议；下一轮质量工作应先聚焦实际错误的查询、角色指代、证据归属和引用格式。新 standard/deep 思考档位若要比较，应另设相同条件，不能拿本轮关闭思考结果宣称已验证新档位。

候选源码和公共评测框架均未改，主 dev/v0.2 工作区未改；不合并、不推送。模型端口验证后保持运行，服务PID与启动记录在 lifecycle.json；这不证明长期可用或显存满足游戏共存目标。

## 复现与资料

从 dev/v0.2 根目录显式启动（已有服务运行时不重复启动）：

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B rag/scripts/serve_local_model.py
```

比较工作区沿用共同 SDK 环境。实际 Story 命令如下；复现须改用新的 output 运行号：

```powershell
uv --cache-dir E:/Workplace/Learn_project/genshin_agent/.cache/uv run --locked --group benchmark --group core-sdk --offline --no-python-downloads --python 3.11 python -B -m Benchmarks agent --adapters Benchmarks/outputs/agent_story/inputs/core-probe-live-r001/adapters.json --config Benchmarks/outputs/agent_story/inputs/core-probe-live-r001/api.json --corpus E:/Workplace/Learn_project/genshin_agent/rag/data/corpus/corpus.jsonl --raw-root E:/Workplace/Learn_project/genshin_agent/data/raw/genshin_wiki_data_20260605 --scenario a01 --scenario a06 --scenario a12 --repeats 3 --max-steps 8 --top-k 5 --timeout 240 --measure timing --model-service-pid 36700 --output Benchmarks/outputs/agent_story/agent/REPLACE_WITH_NEW_RUN
```

PID必须替换为当时真实服务PID；未提供则单列未测。所有下列路径相对比较工作区：

- 本目录 report.md / summary.json：原生组合报告，含 AI 初评；本目录 independent-story-review.md：独立语义审阅副本。
- Benchmarks/outputs/agent_story/agent/core-probe-live-r001：18样本、trace、完整响应、冻结材料、源码副本及追加 AI 评审。
- Benchmarks/outputs/agent_story/review/core-probe-live-r001：权威匿名包、完整评分、只读精简视图和摘要。视图不取代原包，全部96项按冻结标准评审。
- Benchmarks/outputs/reports/core-probe-live-r001：环境启动／二进制指纹、生命周期、场景统计、引用格式补充审计及脚本。启动日志含本机路径，仅本地保存。
- Benchmarks/outputs/reports/core-probe-comparison-r001：保留此前 Core/perf 与“当时 Story 未运行”的历史结果。
- 共同执行清单与两份本地 Draft PR 描述维护恢复状态；本地运行产物忽略 Git，需独立保留。
