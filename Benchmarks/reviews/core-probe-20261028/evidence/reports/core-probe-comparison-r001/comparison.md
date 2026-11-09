---
kind: reference
description: "汇总两条 Core 技术探针的可复现结果、成本、风险及下一步。"
---
# Core 技术探针对比

## 摘要

2026-10-28，Windows / CPython 3.11.7，基线 `dev/v0.2 @ 1b25d92510dcaa0d4ff6e0216e589f2b3a881bb4`。两候选满足本轮固定历史 Core 用例；自建路线在这个最小负载中的启动、延迟与内存成本较低。真实 Story 未运行，不能比较剧情质量或据此确定生产架构。公共 Benchmark 未改，候选未合并、未推送；本地 Reviewer 无需远端 PR。

## 目录

- [版本与条件](#版本与条件)
- [验证与性能](#验证与性能)
- [适配成本与审阅](#适配成本与审阅)
- [限制与建议](#限制与建议)
- [复现与交接](#复现与交接)

## 版本与条件

| 身份 | core-self | core-sdk |
| --- | --- | --- |
| 分支 | exp/core-self | exp/core-sdk |
| 最终交接 HEAD | `2de247252c064a40029b04bdcb9d4f8760a78f39` | `6e3e72f5f61954f154a077bf84b8bf2015c25033` |
| 实现检查点 | `8e4705f`，最终兼容修正 `2de2472` | `4c059c0`，审阅修复 `c53efa9` |
| 运行实现 | 标准库动态循环 | create_agent + BaseChatModel / ToolNode middleware |
| SDK | 无 | LangChain 1.4.7 / core 1.7.0 / LangGraph 1.2.18 |

共同评估工作区为 `exp/core-compare`，执行时协调检查点 `6f14d8e5cbb636557d9af7b0efcec298708003a8`；最终文档交接 commit 为 `9c372c83e8ba8e23f83357e323aa9f9c7be97f0a`。两个候选 worktree 均从同一基线创建；共同 contract 的工作区字节 SHA-256 为 `c212cbd4b2ab83fa7b1ff1410742427b35a5f01804d529b9946233d02b35e582`。Git blob 为 LF、检出文件为 CRLF，不能直接把两种字节哈希混比；公共实现与基线无 Git 差异，各运行按实际执行字节核验。

两候选均由比较工作区同一解释器直接启动，环境含 psutil 和 39 个 SDK 包，安装不计入启动。共同锁 SHA-256 为 `0b453e917fbbf77941962c3016fed55ab594d7bd60426af498c0a7103c846054`，与 SDK 分支相同。策略均为 serial / recover / context=error / 0 retries；协议 spike-jsonl-v1、口径 fixed-history-v0。详见原 contract、各运行 manifest 和环境清单。

## 验证与性能

| 检查 | core-self | core-sdk（修复后） |
| --- | ---: | ---: |
| 主 Agent 正式 Core Smoke | 9/9 | 9/9 |
| 完整 Core c01–c15 | 15/15 | 15/15 |
| 共同环境候选专项测试 | 5/5 | 6/6（新增一项含 5 个结束状态子例） |
| timing / memory 正式批次 | 各 7/7 | 各 7/7 |
| 真实 Story a01/a06/a12 | 未运行 | 未运行 |

Core 的通过同时要求 execution completed、correct=true、conformance passed；c10/c12 的预期 turn 仍为 step_limit/context_limit。共同环境既有离线测试为 Benchmark 73/73、项目 15/15、RAG 68/68，通过；doc-sync 和差异检查通过。计时和内存运行均另含 transport_replay 7/7，故每阶段完整分母为 21/21。

性能使用 7 轮，每轮新 worker，预热 2 批、每批 100 次，再正式 100 次；主要延迟来自 timing，内存来自独立 memory 阶段。下表为轮次统计的中位数 [最小, 最大]：

| 指标 | core-self | core-sdk | transport_replay（仅参照） |
| --- | ---: | ---: | ---: |
| 启动至 ready，ms，timing | 42.589 [41.377,43.771] | 1263.937 [1253.193,1437.721] | 59.609 [56.544,67.865] |
| 固定负载每次延迟，ms，timing | 19.050 [17.565,22.430] | 21.579 [20.189,23.499] | 18.088 [17.767,19.703] |
| 采样峰值 RSS，MiB，memory | 16.824 [16.809,16.879] | 79.227 [78.828,79.871] | 20.344 [20.066,20.375] |
| 正式 100 次批内 worker CPU 秒，timing | 0.015625 [0,0.0625] | 0.234375 [0.109375,0.453125] | 0.015625 [0,0.0625] |

SDK−self 同轮差值中位 **2.505 ms** [1.069,3.453]，同轮比值中位 **1.133×** [1.048,1.195]；保留全部 7 轮原值。固定负载含 reset、模型—工具—模型、broker、oracle 与 JSONL 写入，不含启动和预热。减去回放不能得到纯 Core 耗时；Windows CPU 端点有量化，采样内存每 10 ms 观察 worker 及可见后代，未测启动过程峰值或 GPU。memory 阶段的延迟不用于主要比较。

**调度限制：** 复用现有 paired_order() 后，真实顺序是 `AB,BA,BA,AB,AB,BA,BA`（A=self，B=SDK），回放始终最后。它不是 contract 中“按轮交替”的严格 AB/BA 解读。此处披露为既有公共调度的残余偏差，不修改规则或挑选样本补齐；本轮没有完成严格交替的验证。不能据 7 轮结果推断显著性、稳定尾延迟或真实模型服务收益。

## 适配成本与审阅

自建生产 Python 202 行、测试 135 行、无新增依赖；SDK 263 行（75+188）、测试 125 行、新增 39 个实际安装包，锁文件约增加 1318 行。行数是可核对投入代理，不是复杂度或质量评分；双方记录的时间窗口口径不同，不比较净开发时间或人类工时。

SDK 的模型／工具编排经独立审阅确由 create_agent 图执行。8 项适配覆盖模型 broker、原始消息往返、会话历史、串行工具桥接、结构化错误、模型步数／上下文预算、完成状态和 tracing。工具默认验证／调用被 broker 桥接替换，不能把此配置表现当作 SDK 默认行为。升级需复核 BaseChatModel、ToolNode middleware 和原始消息保留；自建路线则需自行扩展未来功能。

相对基线的文件清单：双方都有共同准备的 `Benchmarks/{README.md,core-probe-plan.md,experiment-contract.md}`、根 `README.md`、`probes/README.md`、`scripts/doc-budgets.manifest.json`；A 另有 `probes/core_self/{worker.py,adapters.json,README.md,tests/test_bridge.py}`（共 10 文件）；B 另有 `probes/core_sdk/{worker.py,agent.py,adapters.json,README.md,tests/test_bridge.py}`、根 `pyproject.toml` 和 `uv.lock`（共 13 文件）。原始数据、输出和回答未纳入 Git。

独立 Reviewer 复现 SDK 对 length+tool_calls 继续执行并错误 completed 的 P2。原实现 Agent 先写回归观察失败，再最小修复；Reviewer 定向复现确认仅请求一次 model、failed、不执行工具，P2 已解决，未发现修复引入的新问题。公共工具循环与评分规则未变。详细初审、命令、修复前后事实及最终核验见本地独立报告。

评估中还保留一次 SDK 专项测试导入路径错误：从比较工作区直接 discover 时缺少 probes 根路径，`core-sdk-tests.log` 失败；加入候选根到 sys.path 后同一测试集通过，最后 `core-sdk-tests-r003.log` 为 6/6。这是评估命令问题，未通过修改候选掩盖。实现方的缺失 worker、SDK 首次脚本导入等失败原件也保留。

## 限制与建议

配置 `http://127.0.0.1:8000/v1` 的 TCP 不可连接；未启动／下载模型，未执行原生工具预检或真实 Story，真实模型调用 0。语料 SHA 与 catalog 一致，所选三场景 7 条冻结来源可读；这不等于语义充分。API、引用合法性、剧情语义和用户验收均未判定。公共 LiveProvider / normal_messages 对显式 tool_calls:null 的潜在兼容问题仅作风险记录，尚无真实服务触发证据，未让候选删除字段绕过。

下一步先在模型服务可用时，用相同配置对两条路线运行已约定的三场景 Story Smoke，再对冻结证据、criteria 和 forbidden 独立审阅。就当前最小同步 Core 的资源成本，建议把 core-self 作为后续 Story 接入的优先验证路线，同时保留 core-sdk 的可复现分支；当前证据不足以作长期框架淘汰或生产架构结论。严格交替调度若需要另测，应先另行确认公共修正与重测条件。

## 复现与交接

所有路径相对比较工作区 `E:/Workplace/Learn_project/genshin_agent/.cache/worktrees/core-compare`。先核对两候选 HEAD 与上表相符、共同环境锁未变，再按根 uv 约定运行。新执行须换 output 名称，既有目录不可覆盖：

```powershell
$probePython = @('--cache-dir','E:/Workplace/Learn_project/genshin_agent/.cache/uv','run','--locked','--group','benchmark','--group','core-sdk','--offline','--no-python-downloads','--python','3.11','python','-B')
uv @probePython -m Benchmarks core --adapters Benchmarks/outputs/agent_core/inputs/core-probe-r002/combined.json --timeout 10 --output Benchmarks/outputs/agent_core/core/reproduce-NEW
uv @probePython -m Benchmarks perf --adapters Benchmarks/outputs/agent_core/inputs/core-probe-r002/combined.json --rounds 7 --batch 100 --warmup 2 --measure timing --timeout 10 --output Benchmarks/outputs/agent_core/perf/reproduce-timing-NEW
uv @probePython -m Benchmarks perf --adapters Benchmarks/outputs/agent_core/inputs/core-probe-r002/combined.json --rounds 7 --batch 100 --warmup 2 --measure memory --timeout 10 --output Benchmarks/outputs/agent_core/perf/reproduce-memory-NEW
```

Smoke 在 core 命令重复加 `--case c01 --case c02 --case c03 --case c06 --case c08 --case c10 --case c12 --case c13 --case c14`，分别用单候选输入。完整实际命令、专项测试修正方式和测试数量见各候选 README 及本地日志。原题与 RAG 输入未改，不运行全量 Story。

- `Benchmarks/outputs/agent_core/core/core-probe-full-r001`：首次双方 15/15，含修复前 SDK，保留作历史；最终 SDK 使用 `core-sdk-full-r002`，不得混成同一版本。
- `Benchmarks/outputs/agent_core/core/core-self-smoke-r001`、`core-sdk-smoke-r002`：最终 Smoke。
- `Benchmarks/outputs/agent_core/perf/core-probe-{timing,memory}-r001`：正式 7 轮、逐次耗时、trace、manifest、源码副本。
- `Benchmarks/outputs/reports/core-probe-evaluation-r001/`：测试日志、environment.json、story-readiness.json、analysis.json 及汇总脚本；脚本按既有 distribution 汇总，不重定义 oracle。
- 本目录 `report.md`／`summary.json`：原生组合报告，明确保留旧 SDK 运行；最终结论采用修复后版本。
- 两个本地 PR 描述保存在 `Benchmarks/outputs/reports/core-probe-progress-r001/`，相同 Current progress / Verification / Next 结构，供 Reviewer 直接本地读取。
- 两候选 README、Git commit 与比较工作区执行清单提供中断恢复；Git 不保存这些本地运行产物，需独立保留。没有新增长期架构决策，因此未建 Agent Note。
