---
kind: reference
description: "记录 LangChain Core 探针的依赖、适配、验证与恢复命令。"
---
# LangChain Core 探针

## 摘要

在 exp/core-sdk 独立工作区实现 [contract](../../Benchmarks/experiment-contract.md) 规定的 create_agent 候选。实现验证已通过，正式统一比较与 Story Smoke 由主 Agent 执行；本探针不决定生产 Core 选型。

## 目录

- [执行与边界](#执行与边界)
- [SDK 适配与成本](#sdk-适配与成本)
- [Current progress](#current-progress)
- [Verification](#verification)
- [Next](#next)
- [Dev Note](#dev-note)

## 执行与边界

所有命令从本 worktree 根执行；Python 3.11，根 uv 项目，公共缓存为 `E:/Workplace/Learn_project/genshin_agent/.cache/uv`。已执行 `uv --cache-dir E:/Workplace/Learn_project/genshin_agent/.cache/uv add --group core-sdk langchain==1.4.7`，根 uv.lock 锁定传递依赖；实际 langchain-core 1.7.0、langgraph 1.2.18、pydantic 2.14.1，共安装 39 个 SDK 包（另有 benchmark 的 psutil）。worker 不直接调用真实模型或工具，只有父进程 broker 提供结果。公共 Benchmark、RAG 和题库只读。

离线同步使用 `uv --cache-dir E:/Workplace/Learn_project/genshin_agent/.cache/uv sync --locked --group benchmark --group core-sdk --offline --no-python-downloads --python 3.11`；新环境须先去掉 offline 联网安装。统一评估应直接用准备好的 Python 启动 `probes/core_sdk/worker.py`，不把 uv 安装计入启动。配置为 [adapters.json](adapters.json)，最终评估应将源码绝对路径和实际实现 commit 绑定到 identity；源码字节另有 manifest 哈希。

## SDK 适配与成本

实际路径为 JSONL → 自定义 BaseChatModel → create_agent 编译图 → ToolNode middleware → JSONL 工具 broker；图驱动 model/tool/model，不另建循环。SDK 消息保存于独立会话历史，适配器保留原始 assistant（包括 null content 和工具参数字符串）；发给模型时不带 SDK ID、审计包装或私有 metadata。Story system 只在新会话首条加入，service_managed/null limit 不做本地字符限制。

适配声明权威位置为 adapters.json：loop=candidate、history=shared、recovery=adapter。max_concurrency=1 限制图及 ToolNode；middleware 绕过默认工具验证／调用与错误文本，让父 broker 执行并返回结构化包装，非法结果转 invalid_result，不重试；模型请求前检查步数与 Core Unicode 内容预算。有工具调用时仅接受 finish_reason=tool_calls；无工具调用时仅接受 stop 且 content 为字符串。其他结束保留原始回复、返回 failed，不执行其中工具；关闭 SDK 模型缓存和继承的 LangSmith tracing。模型与工具仍按 create_agent 默认图路由推进。接口依据为官方 [create_agent](https://reference.langchain.com/python/langchain/agents/factory/create_agent) 和 [wrap_tool_call](https://reference.langchain.com/python/langchain/agents/middleware/types/AgentMiddleware/wrap_tool_call)，并已对照安装源码验证。

生产源码为 worker.py 75 行、agent.py 188 行，合计 263 物理行；候选特有测试 125 行、6 项（新增结束状态回归含 5 个子例）。依赖组新增 39 个实际安装包，传递版本与平台条件完整见根锁文件。记录的 UTC 检查点：2026-10-28 08:14:57 建立 README，08:23:10 确认初次交付 full-002 运行结束；这是包含初次实现和验证的本地观测窗口，不换算人类工时，也不涵盖之前的约束阅读或后续 Review 修复。

仅支持同步的一次活动 turn、serial/recover/error/0，无生产持久化、重试或长历史摘要。升级 SDK 必须重查消息转换、middleware 调用和串行调度。显式 tool_calls:null 会被原样保留；公共 normal_messages/LiveProvider 对该形式可能发生 TypeError，当前合成用例没有此形式，未据此修改公共层或声称真实服务已验证。公共架构没有改动：这是 probes 下既有候选 adapter 边界的实验实现。

## Current progress

- Completed：约束与协议阅读、缺失实现负例、SDK 锁定、真实 create_agent 桥接、Core Smoke 9/9、完整 Core 15/15、初次 Benchmarks 73/73、项目测试 15/15。依赖／负例检查点为 994a036，初次 Python 实现为 4c059c0；Review 修复轮 1 已补回归并确认旧实现失败，修复后候选测试 6/6、完整 Core 15/15、文档门禁和差异检查通过。修复源码 commit 为 c53efa9a034979087ab97fbbeea6db1b262cf76b，adapters identity 已绑定。
- In progress：无；等待 Reviewer 复核与主 Agent 重测。
- Blocked：无。

## Verification

以下均为实现验证，不混入主 Agent 正式比较：

| 证据 | 实测结果 |
| --- | --- |
| sdk-dev-missing-worker-001 | c01 failed/ProtocolError，stderr 确认 worker.py 不存在；负例临时 identity 指向本 README 以记录进程失败 |
| sdk-dev-smoke-001 | 9/9 启动失败，根因是直接脚本的包导入路径；已修正，原件保留 |
| sdk-dev-smoke-002 | 9/9 completed、correct=true、conformance=passed |
| sdk-dev-full-001、sdk-dev-full-002 | 均为 15/15 completed、correct=true、conformance=passed；c10/c12 turn 状态为 step_limit/context_limit |
| 候选桥接测试 | 先观察缺失模块失败，后 5/5 通过；新增 Story 与截断历史用例各先观察对应失败 |
| Benchmarks / 项目测试 | 73/73、15/15，均退出 0 |
| sdk-dev-review1-full-001 | Review 修复后 15/15 completed、correct=true、conformance=passed，退出 0 |

Review 修复轮 1：独立 Reviewer 发现带合法 tool_calls 的 length 回复绕过结束检查，导致 model→tool→model 并错误 completed。新增回归先观察此失败，还覆盖 content_filter、缺失结束原因、工具调用配 stop，以及无工具调用的 stop/null content。最小修复在原始 assistant 入历史后校验上述结束组合；异常回复只请求一次 model，不执行工具且完整保留历史。修复后 6/6 候选测试通过。公共框架、contract 和依赖锁没有修改，本轮按影响范围不重跑已通过的公共测试。

上述运行目录都在本地 `Benchmarks/outputs/agent_core/core/`，被 Git 忽略，须单独保留。可复现命令如下；重复执行须换新 output：

```powershell
uv --cache-dir E:/Workplace/Learn_project/genshin_agent/.cache/uv run --locked --group benchmark --group core-sdk --offline --no-python-downloads --python 3.11 python -B -m Benchmarks core --adapters probes/core_sdk/adapters.json --output Benchmarks/outputs/agent_core/core/sdk-dev-review1-full-001
uv --cache-dir E:/Workplace/Learn_project/genshin_agent/.cache/uv run --locked --group benchmark --group core-sdk --offline --no-python-downloads --python 3.11 python -B -m unittest discover -s probes/core_sdk/tests -v
uv --cache-dir E:/Workplace/Learn_project/genshin_agent/.cache/uv run --locked --group benchmark --group core-sdk --offline --no-python-downloads --python 3.11 python -B -m unittest discover -s Benchmarks -t . -v
uv --cache-dir E:/Workplace/Learn_project/genshin_agent/.cache/uv run --locked --group benchmark --group core-sdk --offline --no-python-downloads --python 3.11 python -B -m unittest discover -s tests -v
```

文档门禁沿用[开发流程](../../docs/development.md#验证)的 doc_sync.py 和 git diff --check。正式 perf、真实 Story/API、剧情语义与用户验收尚未由本 Agent 运行，不能由合成通过推断。

本 Agent 启动的安装、测试和 Core 命令均已结束，所有返回的执行 session 已确认退出。收尾用 psutil 排除检查命令自身完整祖先树后，未发现本 worktree 的 Python／uv／worker 后台进程，读取失败数为 0；Windows CIM 查询权限不足，未据该失败推断清理完成。主 Agent 可开始正式评测，无本 Agent 背景负载。

## Next

恢复先核对 worktree/exp/core-sdk、根 context、contract、本 README 和 git status/log；contract SHA256 应为 c212cbd4b2ab83fa7b1ff1410742427b35a5f01804d529b9946233d02b35e582。修复提交后由 Reviewer 复核结束状态回归；主 Agent 在 exp/core-compare 绑定最新源码 commit、复用根锁文件和同一 Python，重跑 SDK 正式 Smoke／Core 及统一 perf，继续按既有计划处理 Story；本分支不推送、不合并。禁止修改公共 oracle 适配候选。

## Dev Note

无。
