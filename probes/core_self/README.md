---
kind: reference
description: "说明自建 Core 探针的接口、命令、验证边界及进度恢复。"
---
# 自建最小 Core 探针

## 摘要

在 exp/core-self 独立实现动态模型／工具循环。唯一行为要求见 [contract](../../Benchmarks/experiment-contract.md)，SHA-256 为 `c212cbd4b2ab83fa7b1ff1410742427b35a5f01804d529b9946233d02b35e582`。原始基线 `1b25d92510dcaa0d4ff6e0216e589f2b3a881bb4`，准备 commit `3a09829`。本页记录实现阶段，不能替代统一正式比较或用户语义验收。

## 目录

- [接口与限制](#接口与限制)
- [命令](#命令)
- [Current progress](#current-progress)
- [Verification](#verification)
- [Next](#next)
- [Dev Note](#dev-note)

## 接口与限制

[worker.py](worker.py) 可直接用 Python 脚本启动，[adapters.json](adapters.json) 只有一个 adapter，源码 identity 为 worker 和配置本身；`revision=core-self-v1` 是构建标识，主 Agent 正式运行时绑定实现 commit 与源码哈希。worker 只导入标准库，只通过父进程 broker 获取模型／工具；不访问真实模型、语料或网络，不依赖 Benchmark 实现。

遵循 [spike-jsonl-v1](../../Benchmarks/support/protocol.md)：UTF-8 stdin/stdout 每行一个对象；实现 init／ready、reset／reset_done、turn／turn_result、shutdown／closed。provider 请求使用进程内单调 p 前缀 ID，以 parent_id 和 session_id 对应当前轮次，串行等待并校验结果 ID。stdout 只写协议，异常诊断写 stderr，非法控制消息退出 1。

固定策略为 serial／recover／error／0，其他策略拒绝初始化。每轮 max_steps 只计算模型请求；每次模型调用前检查全部 content 的 Unicode 字符总数，service_managed 仅接受空上限。保留每会话原生消息与工具 ID；只将 result.message 入历史，工具仅追加 ok/result 或 ok/error 包装。JSON 参数解析失败本地生成 invalid_arguments；工具名称与参数 schema 校验交给 broker。非法工具结果转 invalid_result，错误继续交给模型；不重试工具或模型。最终仅 finish_reason=stop 且 content 为字符串时 completed；截断或模型失败返回 failed。

循环、历史与恢复全由 candidate 实现，adapter 只声明启动命令与 identity；无 SDK 默认行为需改写，adaptation.changes 为空。没有生产持久化、自主摘要、并行工具或多轮并发请求；历史留在进程内直到 reset／退出，失败轮的已观察消息也保留。没有生产级安全隔离；工具副作用由父进程负责。不能将本探针的符合性当作通用 agent 能力。

候选兼容显式 `tool_calls=null`，按无调用处理且原样保留消息。公共层静态边界已报告主 Agent：QwenClient 保留此字段，但 LiveProvider 的 pending 推导与 normal_messages 会直接遍历，可能导致实际 Story 失败；尚未获得真实服务复现，不改框架或绕开比较条件。若触发，保留失败原件并报告。

## 命令

所有命令从本 worktree 根执行；独立 `.venv`，不新增依赖。Python 前缀统一为：

```powershell
uv --cache-dir E:/Workplace/Learn_project/genshin_agent/.cache/uv run --locked --group benchmark --offline --no-python-downloads --python 3.11 python -B
```

在此前缀后执行以下命令；显式输出目录须不存在，每次重跑改用新编号，失败也保留：

```powershell
probes/core_self/worker.py
-m unittest discover -s probes/core_self/tests -v
-m Benchmarks core --adapters probes/core_self/adapters.json --output Benchmarks/outputs/agent_core/core/self-impl-001
scripts/doc_sync.py
```

第一行直接启动 worker 并等待 JSONL init；评估时由父进程管理生命周期。正式 Smoke、Core、perf 与 Story 由主 Agent 统一执行。

## Current progress

- Completed：协议与 oracle 核对；缺失 worker 负例；202 行动态自建循环；5 个桥接测试红转绿；实现阶段 Core c01–c15 共 15/15 通过；导航、预算、完整差异与源码 identity 核对；本地提交交接。
- In progress：无；正式评测与独立审阅由主 Agent 接手。
- Blocked：无。

## Verification

以上 Python 前缀用于全部实测。结果均为本地实现验证，不是正式对比或用户语义验收。

| 命令／输出 | 实测结果 |
| --- | --- |
| `-m Benchmarks core --adapters probes/core_self/adapters.json --case c01 --output Benchmarks/outputs/agent_core/core/self-missing-001` | 1/1 失败，退出 1；stderr 明确 worker.py 不存在，原件保留 |
| `-m unittest discover -s probes/core_self/tests -v`，实现前 | 4/4 错误，worker stdout closed，确认缺失实现 |
| 同一桥接测试命令，实现后 | 初版 4/4 通过；末轮新增 null 回归先失败（1/5，另 4 个通过），修复后最终 5/5 通过，退出 0；覆盖中文／emoji、system、原生 ID、证据、多轮历史、畸形参数、模型错误／截断、工具后上下文增长与 null 字段保留 |
| `-m Benchmarks core --adapters probes/core_self/adapters.json --output Benchmarks/outputs/agent_core/core/self-impl-001` | execution completed、correct true、conformance passed 均 15/15；c10 为 step_limit，c12 为 context_limit；退出 0 |
| 同一 Core 命令，输出改为 `Benchmarks/outputs/agent_core/core/self-impl-002` | null 回归修复后的最终源码，全部 15/15 completed／correct／passed，退出 0 |
| `scripts/doc_sync.py` | 初始与实现文档预算、链接和 CLI 新鲜度通过，退出 0；交接版再次核对 |

资源测试用独立 TemporaryDirectory，复用公共 Worker 的期限与 close，close 等待进程与 IO 线程结束；不派生后台子进程。没有修改依赖、公共 Benchmark、场景、RAG 或题库。未运行性能或真实 Story，Linux 与真实模型尚未验证。

投入记录：文档检查点 commit `2ff94fe` 的时间为 2026-10-28 08:16:05 UTC；首次显式时钟记录为 08:17:35 UTC，位于桥接负例后、worker 实现前。最终代码验证结束记录为 08:21:38 UTC；源码 202 行、测试 135 行、配置 17 行。实现主单元 commit `8e4705f`；末轮 null 修复与最终交接以当前 HEAD 为准。此前会话起始没有独立计时记录，不能据此估算人类工时。

08:21:38 UTC 用 `Get-Process python,pythonw,uv -ErrorAction SilentlyContinue` 未发现进程；所有测试与 Core 命令同步结束，没有后台 worker、测试或安装。CIM 只读枚举因权限拒绝，未提权；公共 Worker.close 另外保证进程与 IO 线程清理。本分支只供本地审阅，无需推送或创建远端 PR。

## Next

新 Agent 先确认当前 worktree／分支，读根 context、contract、本 README、`git status` 和 `git log`。下一步由主 Agent 本地读取当前 HEAD，绑定绝对源码路径与 commit，在共同环境的新目录执行正式 Smoke，不复用实现阶段结果；在其开始性能测量后不要并行启动本路线测试。若评测返回失败，先保留轨迹，在本 worktree 补回归、修复并提交，然后通知主 Agent 重跑受影响检查。

## Dev Note

无。
