---
kind: reference
description: "固定 core-self 与 core-sdk 技术探针的共同条件、验收和失败处理。"
---
# Core 技术探针共同 contract

## 摘要

状态：用户于 2026-10-28 确认。基线为 dev/v0.2 的 `1b25d92510dcaa0d4ff6e0216e589f2b3a881bb4`。本 contract 只约束本次探针，复用现有 Benchmark，不决定生产 Core 选型。

## 目录

- [最低行为](#最低行为)
- [固定条件与测量](#固定条件与测量)
- [允许不同的实现](#允许不同的实现)
- [Smoke、验收与失败](#smoke验收与失败)

## 最低行为

双方实现真实候选 worker，遵守 [spike-jsonl-v1](support/protocol.md) 与 `fixed-history-v0`，支持 init、reset、turn、shutdown、独立会话、原生工具调用及正确 ID 对应。按初始化预算限制模型步数和上下文；完整保留本会话模型与工具历史，工具结果仅含协议规定的包装，诊断只写 stderr。

公共策略固定为 `tool_execution=serial`、`tool_error=recover`、`context=error`、`max_tool_retries=0`。错误须结构化传回模型，非法工具结果识别为 invalid_result；步数耗尽、上下文超限等按既有状态结束。具体断言以 [Core 定义](agent_core/evaluation.md)和现有 oracle 为准，不新增第二套规则。不能按用例 ID、参考答案或有限磁带生成候选输出。

## 固定条件与测量

两分支从同一基线创建。主 Agent 在独立 exp/core-compare 工作区评估，公共 Benchmark 源码、输入及评测规则保持基线字节，使用同一机器、Python 3.11 和含 SDK 依赖的同一评估环境；候选进程直接用该解释器启动，不将 uv 安装计入启动。SDK 及传递依赖在实现时锁定，记录实际版本与锁文件。候选源码、实现 commit、contract 哈希、环境与命令随新运行保存。

完整 Core 使用全部 c01–c15、每轮期限 10 秒。开销复用现有 perf：7 轮、每批 100 次、预热 2 批，候选按轮交替先后；timing 与 memory 分开运行，均为相同负载及期限。使用现有 transport_replay 单列传输参照，绝不作为候选。启动单列，按轮报告原始值、中位数、范围、配对差值与比值；失败批次不进入性能聚合，完整分母和失败轨迹保留，不设性能通过阈值。

Story 使用同一只读 catalog 语料、冻结快照、系统提示和现有词面检索；执行前核对真实输入哈希。沿用 `rag/config/local_api.json` 的同一模型配置，temperature=0、seed=42，每场景 3 次、新 worker，max_steps=8、Top5、timeout=240 秒、timing；记录服务实际模型身份。只读复用主工作区数据，不重建或提升基线，不启动或下载模型。[公共测量](support/measurement.md)和 [Story 定义](agent_story/evaluation.md)继续适用。

## 允许不同的实现

core-self 自建最小循环；core-sdk 必须实际使用 LangChain `create_agent` 承担模型与工具编排，不能仅导入 SDK 后运行另一套自建循环。允许不同的内部状态、消息转换、SDK middleware 和工具桥接；不要求生产持久化、UI 或自主历史策略。

各 Agent 只修改自己的候选 worktree，不改公共 Benchmark、题库、RAG 和 contract。SDK 的循环、历史或恢复默认行为若需关闭、替换或适配，必须在协议 adaptation 中如实声明归属和原因；无法保持共同条件时先报告阻塞。独立审阅声明、代码差异、依赖、实现时间记录和维护限制，不把声明当核验事实。

## Smoke、验收与失败

顺序固定：主 Agent 重跑既有离线测试；双方分别运行 Core Smoke `c01,c02,c03,c06,c08,c10,c12,c13,c14`；双方 Smoke 全通过后，运行完整 Core 与独立 perf。Core 验收须每个计划样本 execution_status=completed、correct=true、conformance_status=passed；这里 c10/c12 的预期 turn 状态仍分别为 step_limit/context_limit。

模型和 RAG 可用且原生工具预检通过后，Story Smoke 固定 `a01,a06,a12`，覆盖事实查询、多轮延续、身份断言边界；本探针不扩展到全部 Story 场景。执行、API、引用合法性与逐项剧情语义独立报告；主 Agent 或独立 Reviewer 对照冻结证据、criteria 和 forbidden 审阅，缺证据记存疑，不能登记为用户验收。服务或数据不可用记未运行及原因，不用合成回答替代。

失败保留新输出及完整分母；评估者不得修改候选掩盖失败。候选问题退回原实现 Agent 修复并提交新 commit，再重跑受影响检查；公共协议阻塞先报告，不改比较条件。未通过 Smoke 的候选不进入后续正式比较；另一候选可保留独立结果，但不宣称完成有效 A/B 对比。最终列出 commit、文件、实测命令、结果、性能、适配成本、风险及建议；不合并、不推送、不改用户已有工作。
