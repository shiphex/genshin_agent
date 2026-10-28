# Core 探针独立审阅

状态：2026-10-28 初审；SDK 修复及正式 perf／Story 结果待补。只读候选与公共框架，唯一写入为本报告。依据为批准的 contract，不增加验收阈值。

**发现（按严重级别）**

1. **P2／core-sdk：带工具调用的截断回复未终止，适配声明与实现不一致。** `probes/core_sdk/agent.py:104` 只在没有 tool_calls 时检查 finish_reason。因此 length 加一个合法工具调用会进入 ToolNode、执行工具、再请求模型，随后可能返回 completed。共同环境实测调用序列为 `model, tool, model`，结果为 `completed/done`。`probes/core_sdk/README.md:30` 的“finish_reason=length 返回 failed”及 adapters.json 的 completion 描述没有限定此例外。公共 QwenClient（`Benchmarks/agent_story/providers.py:105` 起）接受这种结构，故不是无法到达的内部输入。影响是截断生成的工具决策可能被执行，该轮未按声明失败；这不推翻 c01–c15 的已有通过。建议保留原始 assistant 后，在交给 SDK 调度之前检查：有工具须 finish_reason=tool_calls；无工具须 stop 且正文为字符串。补 length+tool_calls 回归。Reviewer 未改候选，已退回原实现方。
2. **公共层条件性风险／不归责候选：显式 tool_calls:null 可阻塞 Story。** `Benchmarks/agent_story/providers.py:110` 接受 null 并视为无工具，但 `:242` 用 `.get("tool_calls", [])` 直接遍历 null；`Benchmarks/support/contracts.py:58` 同样如此。两候选保留原始 null 符合固定历史要求。目前为静态确认的公共边界，尚无真实服务触发证据，不能登记两候选 Story 失败，也不应让候选删除字段绕过。实际触发应单列公共阻塞。

剩余静态审阅未发现需要整批退回实现方的其他缺陷；不将未覆盖的生产能力当作本探针缺陷。

**范围与共同条件**

基线 `1b25d92510dcaa0d4ff6e0216e589f2b3a881bb4`；A 为 `2de247252c064a40029b04bdcb9d4f8760a78f39`；B Python 实现为 `4c059c0e310a627be2cd259404ecaa0a2676a994`，交接 HEAD 为 `6d3a9d55ddba8773a0a4b8aec2cd592aa0ff8716`。B 两版本差异仅 README 和 adapters identity。

已读变更清单、两个 diff 包和 log、实际 worker/agent/tests/adapters/README、协议与 Core 定义、已安装 SDK 的图路由和 ToolNode 源码。未读实现聊天历史，未调用真实模型、未派生 Agent。

比较工作区与两候选当前 contract SHA256 均为 `c212cbd4b2ab83fa7b1ff1410742427b35a5f01804d529b9946233d02b35e582`。双方相对基线的公共 Core/Story/support 与 rag diff 为空；新增探针及导航/预算文档，B 另加依赖组和锁文件。旧 diff 中执行清单属于历史准备提交，唯一比较约束采用批准 contract。

environment.json 记录 CPython 3.11.7、Windows、40 个安装包：psutil 为原 benchmark 包，39 个为 SDK 引入。共同锁与 SDK 锁 SHA256 均为 `0b453e917fbbf77941962c3016fed55ab594d7bd60426af498c0a7103c846054`。核心版本为 langchain 1.4.7、langchain-core 1.7.0、langgraph 1.2.18。此项核对实际环境和锁，并非只采信声明。

**Spec compliance 结论**

固定 Core 范围：初审版本双方通过正式 Smoke 与完整 Core；已独立重新计数比较工作区 results.jsonl。更广的声明边界：A 本轮未发现须修复项；B 有 P2，不应描述为全部声明行为已核验。

| 正式运行（Benchmarks/outputs/agent_core/core/） | A | B | 口径 |
| --- | ---: | ---: | --- |
| core-self-smoke-r001／core-sdk-smoke-r001 | 9/9 | 9/9 | completed、correct=true、conformance=passed 同时满足 |
| core-probe-full-r001 | 15/15 | 15/15 | 同上；固定 c01–c15，不含 P2 新边界 |
| 候选专项日志 | 5/5 | 5/5 | 主 Agent 实测，Reviewer 读日志；独立分母 |

公共离线 73 Benchmark + 15 项目 + 68 RAG 日志位于 `Benchmarks/outputs/reports/core-probe-evaluation-r001/`。Reviewer 未重复运行。B 初次 `core-sdk-tests.log` 因比较工作区缺少候选 import path 失败；修正命令后的 `core-sdk-tests-r002.log` 为 5/5 OK。属评估命令错误，不算候选缺陷；原日志保留。

关键代码核验：

- A 按 max_steps 循环实际模型请求；B 在 BrokerModel._generate 检查模型请求数。图 recursion_limit 仅为更宽的保险。两者每次模型请求前统计完整 content 的 Unicode 字符，service_managed/null limit 不增加本地字符限制。
- A 保存原生 chat 字典；B 在 AIMessage.additional_kwargs._spike_raw 保存原始 assistant，发给 broker 时恢复。没有 SDK 消息 ID、raw_response 或传输信封混入历史；工具只保留 ok/result 或 ok/error，非法非对象 result 转 invalid_result。B 另保留原始参数字符串与工具 ID，实际 broker 参数没有被 SDK coercion 改写。
- B 在 agent.py:166 创建 create_agent，turn 只 graph.invoke，没有另一套模型循环。安装的 factory.py:1991 起按 AIMessage.tool_calls 生成 Send("tools")；ToolNode wrap_tool_call 处理每个调用并返回 ToolMessage，图随后回到模型。真实 SDK 编排成立。
- B max_concurrency=1 配合 ToolNode config executor 串行调度。middleware 不调用注册 handler，所有可解析请求由 broker 判断，未知工具亦然；错误结果由 SDK 图继续发给模型，无工具重试。这些替换均已披露。
- 双方按 session 保存历史，reset 删除目标会话。B 无 checkpointer，current/raw_calls/steps 在 reset/turn 初始化，无持久图会话；正常、预算及显式模型失败路径保留已观察消息。源码没有按 case ID、答案或回放磁带生成输出。

**Code quality 结论与成本**

A 的串行协议控制流短且易审计，模型消息结构校验较明确。B 两文件分工明确，主要适配归属披露充分；但同时维护原始历史和 SDK 消息，完成/错误检查仍需自己实现。P2 表明这些边界需要回归，框架名称不能替代正确性核验。没有发现阻碍共同 Core 测量的实现真实性问题。

| 可核对成本 | A | B |
| --- | ---: | ---: |
| 生产 Python 物理行 | 202 | 261（75+186） |
| 候选测试物理行／测试数 | 135／5 | 100／5 |
| 新增实际安装包 | 0 | 39 |
| 锁文件变化 | 无 | 新增约1318行 |

行数不是复杂度或质量评分。B 的维护点包括 BaseChatModel、ToolNode middleware、消息往返、会话与预算中断；适配声明总体与源码一致，已确认例外为 P2。A 同样需要自行维护未来功能。两者都只支持一次活动 turn、串行工具、进程内完整历史，没有生产持久化、自主摘要或并行任务。

实现方局部时间记录：A 文档提交 08:16:05、显式实现前时钟 08:17:35、验证结束 08:21:38 UTC；B 为 08:14:57–08:23:10 UTC。起止口径不同，不是净开发时间或人类工时，不能据此排快慢。依赖安装不能混入 worker 启动。正式 perf 未齐，尚不作性能结论。

**P2 可执行最小复现**

经主 Agent 确认尚未进入 perf 后运行。workdir 为 `E:/Workplace/Learn_project/genshin_agent/.cache/worktrees/core-compare`。未写脚本、未改候选、未请求真实服务。将以下 Python 代码通过 PowerShell 单引号 here-string 管道输入以下命令即可复现：

```powershell
uv --cache-dir E:/Workplace/Learn_project/genshin_agent/.cache/uv run --no-sync --offline --no-python-downloads --python .venv/Scripts/python.exe python -B -
```

```python
import sys
sys.path.insert(0, r'E:/Workplace/Learn_project/genshin_agent/.cache/worktrees/core-sdk')
from probes.core_sdk.agent import CoreAgent
from copy import deepcopy
calls=[]
config={'system':'','tools':[{'type':'function','function':{'name':'echo','description':'Echo','parameters':{'type':'object','properties':{'text':{'type':'string'}},'required':['text']}}}],'max_steps':3,'context_limit':10000,'context_counter':'unicode_content_codepoints_v1','policies':{'tool_execution':'serial','tool_error':'recover','context':'error','max_tool_retries':0}}
def broker(kind,payload):
    calls.append((kind,deepcopy(payload)))
    if len(calls)==1:
        return {'ok':True,'result':{'message':{'role':'assistant','content':None,'tool_calls':[{'id':'t1','type':'function','function':{'name':'echo','arguments':'{"text":"partial-call"}'}}]},'finish_reason':'length'}}
    if kind=='tool': return {'ok':True,'result':{'text':'partial-call'}}
    return {'ok':True,'result':{'message':{'role':'assistant','content':'done'},'finish_reason':'stop'}}
agent=CoreAgent(config,broker)
print({'result':agent.turn('A','test'),'provider_sequence':[kind for kind,_ in calls]})
```

原始 stdout：`{'result': {'status': 'completed', 'content': 'done'}, 'provider_sequence': ['model', 'tool', 'model']}`。退出0，工具报告墙钟2.4386663秒。耗时仅说明最小复现规模，不是性能样本。

**待补与限制**

待 B 修复差异和回归、正式 perf、有条件 Story Smoke。Core 固定历史通过率只能证明既定协议行为，不能推导 SDK 一般架构优劣；合成通过不能推导剧情语义。Story 必须分开报告执行/API/引用/criteria/forbidden 与冻结证据支持，不能登记为用户验收。服务或数据不可用记未运行，不用合成替代。无推送、合并或生产选型结论。

**修复轮 1 定向复核：P2 ADDRESSED**

复核 B 最终 HEAD `6e3e72f5f61954f154a077bf84b8bf2015c25033`，Python 修复 commit `c53efa9a034979087ab97fbbeea6db1b262cf76b`。范围仅 `core-sdk-fix-r001.diff`，不扩展未改代码；上述初审发现及旧结果保留为修复前事实。状态更新：P2 已修复，等待最终统一 Core/perf 证据。Story readiness 由主 Agent 检查，服务不可连的正式证据待其结果材料，Reviewer 未执行真实 Story。

`agent.py:104–107` 在原始 assistant 加入 current 后，要求有工具调用时 finish_reason=tool_calls，无调用时 finish_reason=stop 且 content 为字符串；否则抛 TurnStop("failed")，不会把该回复交给图调度工具。现有 turn 异常路径保存 current，保留原始回复。新增测试覆盖 length/content_filter/stop/None + tools，以及 stop/null content 五个子例，同时断言只调用 model、返回 failed、原始历史保留。README 与 adaptation 的 completion 声明已相应同步。

Reviewer 在同一 workdir、同一共同 uv 环境重新执行本报告上面的原始复现代码和命令（没有修改输入），实际 stdout：
`{'result': {'status': 'failed', 'content': ''}, 'provider_sequence': ['model']}`。
退出码 0，工具墙钟 2.494436 秒；仅作定向复现，不计入 perf。主 Agent 独立专项日志 `Benchmarks/outputs/reports/core-probe-evaluation-r001/core-sdk-tests-r003.log` 另为 6/6 OK；Reviewer 读日志，没有重复整套测试。实现方 README 记录先红后绿及实现阶段 full 15/15，不能替代主 Agent 新正式运行。

定向结论：**ADDRESSED**；修复 diff 未发现新引入问题。最终 B 源码为 263 物理行，测试 125 行／6 项；初审成本表的 261／100／5 为修复前数值。其余初审限制不变。此后不再运行测试，等待正式 perf 数据。

**最终数据复核与结论（2026-10-28）**

最终候选身份：A `2de247252c064a40029b04bdcb9d4f8760a78f39`；B `6e3e72f5f61954f154a077bf84b8bf2015c25033`，Python 修复仍为 `c53efa9a034979087ab97fbbeea6db1b262cf76b`。P2 保持 ADDRESSED。下面是最终结论，上文初审“待补”段落仅保留当时状态。

**新增公共测量发现：严格逐轮交替未实现。** timing 与 memory 原始行顺序均为 AB、BA、BA、AB、AB、BA、BA，transport_replay 每轮最后。原因是未修改的 `Benchmarks/support/metrics.py:7–10` 同时轮转和反转，`agent_core/runner.py:103` 复用该排序后再追加回放。实际双方均有先执行轮次，但不符合 contract 按轮交替的严格字面要求。属公共测量偏差，不是候选缺陷；不能声称全部执行条件无偏差。数据可作注明此限制的本机描述性 A/B 比较，残余顺序效应未被完全排除；不能给出统计显著性或一般架构优劣结论。本次不改框架、不重跑候选。

独立核验方式：通过共同 uv 环境运行仅使用 pathlib/json/hashlib/statistics/subprocess 的只读 stdin 脚本，从两份 results.jsonl 重算中位数、最小/最大值和同轮差值/比值；不调用候选，不使用分析脚本的聚合函数。命令前缀与原最小复现相同：`uv --cache-dir E:/Workplace/Learn_project/genshin_agent/.cache/uv run --no-sync --offline --no-python-downloads --python .venv/Scripts/python.exe python -B -`，workdir 为比较工作区。最终核验退出 0；读取官方 report.md/summary.json 和 analyze_results.py/analysis.json 交叉核对。

每阶段 21 个计划 sample_id 与 21 个唯一原始行完全对应；两候选与回放各7轮，全部 execution completed、correct=true、conformance passed。全部每批100次、每轮预热200次（2批）、timeout=10秒；每阶段每候选正式700次、预热1400次，但统计实验单位仍为7轮，不能把700次当独立重复。有效批21/21，排除失败批0；无丢分母或只挑最快样本。每行 per_iteration_ms 等于 elapsed_ms/100。分析脚本先断言全通过再聚合，在当前全通过数据上没有失败污染；未来含失败数据须显式过滤，不能照搬为通用处理器。

两阶段 manifests 的31项 provenance 哈希、候选声明与环境一致；每项当前文件及 sources 冻结副本的 SHA256 均匹配 manifest。双方 command 指向同一共同解释器，未把 uv 安装计入 worker 启动。环境为 CPython3.11.7、Windows、psutil7.2.2、16逻辑CPU；SDK包及锁与初审核验一致。公共执行源码与基线 Git 内容一致；工作区使用CRLF而Git blob使用LF，因此基线比较规范化换行，不能把Git blob原始字节哈希说成与Windows执行文件相同。实际执行文件与两阶段冻结副本按原始字节核对一致。首次直接将Git LF blob与工作区CRLF比较的审计断言失败已按此原因澄清，不是候选或评测失败。

主要候选源码 SHA256：

| 文件 | SHA256 |
| --- | --- |
| A worker.py | 8a44e5fcee9fe75fa531cae10aab24baa8872da1b7e8d7c0703514087a6ba865 |
| B worker.py | fe46c17ded22ea55037bf128158f55931c0f0726a2b0a2e1dcc49ac21132982f |
| B agent.py | 0257c43793cccc7b7785235e81249c1ca897dd0dc75f8e156d83ae08a2fd81fc |

最终 correctness 重新从 raw rows 计数：A smoke-r001 为9/9，A在full-r001为15/15；B修复后smoke-r002为9/9、core-sdk-full-r002为15/15，均同时满足 completed/correct/passed。旧 full-r001 的B15/15是修复前历史，未混为最终B证据。最终专项日志A5/5、B6/6。

**性能原始轮次与重算结果**

主要延迟只取 `Benchmarks/outputs/agent_core/perf/core-probe-timing-r001/results.jsonl`。每格为该轮100次批总耗时除100，单位ms；差值与比值严格同轮配对，非“两个中位数相减/相除”。

| 轮 | 顺序 | A | B | 回放 | B−A | B/A |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | AB | 19.729599 | 22.234504 | 18.084604 | 2.504905 | 1.126962 |
| 2 | BA | 17.713290 | 21.166161 | 18.087796 | 3.452871 | 1.194931 |
| 3 | BA | 17.565034 | 20.188658 | 17.990022 | 2.623624 | 1.149366 |
| 4 | AB | 22.429661 | 23.499054 | 19.200935 | 1.069393 | 1.047678 |
| 5 | AB | 19.050173 | 21.739582 | 19.253375 | 2.689409 | 1.141175 |
| 6 | BA | 19.580497 | 21.579429 | 19.703163 | 1.998932 | 1.102088 |
| 7 | BA | 18.336297 | 20.774262 | 17.766887 | 2.437965 | 1.132958 |

| 指标，中位数 [最小, 最大] | A | B | 传输回放参照 |
| --- | ---: | ---: | ---: |
| timing批均值 ms/次 | 19.050 [17.565,22.430] | 21.579 [20.189,23.499] | 18.088 [17.767,19.703] |
| timing启动到ready ms | 42.589 [41.377,43.771] | 1263.937 [1253.193,1437.721] | 59.609 [56.544,67.865] |
| memory采样峰值 MiB | 16.824 [16.809,16.879] | 79.227 [78.828,79.871] | 20.344 [20.066,20.375] |

同轮B−A中位数2.504905ms，范围[1.069393,3.452871]；同轮B/A中位数1.132958，范围[1.047678,1.194931]。7/7观察轮B均较慢；“约13.3%”仅描述这7轮配对比值的中位数，不是显著性结论或性能门槛。启动单列，不与预热后每次负载混合。

内存只取独立 `core-probe-memory-r001/results.jsonl`，模式均为periodic_memory，间隔10ms、sampling_errors均0，范围为worker及可观测后代。timing中的endpoints_only“peak”不能作为正式采样峰值；memory阶段延迟也没有混入主延迟表。采样间峰值与短寿命后代可能遗漏，未测GPU。CPU为100次正式批内进程CPU计数差值，粒度与进程发现限制存在，不是纯Core耗时；不得按0读数推断无CPU成本。

此负载包含reset、工具往返、JSONL、broker、oracle与轨迹写入，排除启动及预热。回放仅为传输参照，永不当候选；相减不能分离纯SDK/Core成本。B更高的启动/RSS是当前适配和依赖组合的实测，不是未适配LangChain默认实现的独立开销。最终实现成本为A202行标准库源码、B263行源码与39新增包；行数、一次修复、不同起止的墙钟记录不能换算维护质量总分或人类工时。

**Story与最终判定**

已读取 `Benchmarks/outputs/reports/core-probe-evaluation-r001/story-readiness.json`：catalog_match=true，语料SHA256为 `1fafb904a22126b1fa757d1f6a2c119f1fa10f5637d5d75bcccfb9425c6efed3`，登记a01/a06/a12合计7条冻结来源位置；配置端点127.0.0.1:8000不可连，native_tool_preflight和story_smoke均not_run。该文件记录不可用结果，没有两次检查的独立时间戳；Reviewer只确认材料中可见事实，不扩写为独立复测次数。真实模型调用0；剧情语义、引用正确性、身份断言边界和用户验收均未评。公共null风险仍为未由真实服务触发的限制，不算候选失败。

- **Spec compliance：** 最终双方满足已执行的固定Core验收；B P2已修复并独立复现确认。Story因环境条件不具备而按contract标未运行。perf存在上述公共排序偏差，不能写成整个contract无偏差完成。
- **Code quality：** 初审及修复定向复核范围内无未解决候选缺陷；B真实SDK编排成立，适配声明与修复后源码一致。两者均为探针，不具备生产就绪结论。
- **比较有效性：** 同环境、同锁、同公共源码和负载下的本机描述性比较可复核；数据支持A在本次负载上的较低延迟、启动和RSS。必须附带实际顺序限制，不推出通用SDK架构输赢、剧情质量或生产选型。未合并、未推送、未改候选和公共框架。
