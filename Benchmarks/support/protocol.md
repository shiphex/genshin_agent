---
kind: reference
description: "定义adapter配置、双向JSONL消息、provider接口和失败语义。"
---
# Spike JSONL协议v1

## 摘要

协议ID为spike-jsonl-v1。benchmark是父进程，候选adapter是worker；候选决定工具循环、历史维护和恢复，父进程提供模型／工具并观察。命令见 [README](../README.md)。

## 目录

- [启动配置](#启动配置)
- [控制消息](#控制消息)
- [provider消息](#provider消息)
- [分类约定](#分类约定)
- [限制与失败](#限制与失败)
- [Dev Note](#dev-note)

## 启动配置

配置包含schema_version=1与非空adapters数组，ID使用ASCII字母、数字、下划线或连字符，不能重复。以下路径须换成实际实现：

```json
{"schema_version":1,"adapters":[{
  "id":"candidate_a",
  "command":["{python}","candidate_adapter.py"],
  "identity":{"revision":"commit-or-build-id","files":["candidate_adapter.py"]},
  "policies":{"tool_execution":"serial","tool_error":"recover","context":"truncate","max_tool_retries":0}
}]}
```

命令与源码路径相对仓库根目录。tool_execution为serial／parallel，tool_error为recover／terminate，context为error／truncate／compress；工具失败按声明可重试0–3次，成功工具不得重复执行。fixture_only=true专供有限回放，不当真实候选。

## 控制消息

传输编码固定UTF-8；Python worker在Windows管道中须明确配置stdin/stdout编码。

每行一个JSON对象，stdout只输出协议，诊断写stderr。每条消息必须有非空字符串type/request_id/session_id。父进程请求ID使用h前缀；worker provider请求ID不得以h开头，进程生命周期内唯一。

| 父进程type | 附加字段 | worker应答 |
| --- | --- | --- |
| init | protocol_version=1、suite、scenario_id、policies、system、tools、max_steps、context_limit、context_counter | ready，同ID，protocol_version=1 |
| reset | 无 | reset_done，同ID；清除指定会话历史及状态 |
| turn | content：用户文本 | turn_result，同ID，status和字符串content |
| shutdown | 无 | closed，同ID，随后退出 |

初始化和关闭使用session_id=control。worker可保存多个独立会话；Core交替执行A/B。每次Agent场景重复从新worker开始，场景内各轮共用session。

turn_result.status为completed、step_limit、context_limit、tool_error或failed。completed的content对应模型最终回答；其他状态可用空字符串。结果后不得再调用provider。一步是一次模型请求，按用户轮次计数；达到max_steps后不得再请求模型。最后一次仍要求工具时可结束为step_limit。工具次数另计。

## provider消息

worker在turn尚未结束时请求模型或工具，parent_id指向当前turn请求ID：

```json
{"type":"provider_call","request_id":"p1","session_id":"A","parent_id":"h3","provider":"model","payload":{"messages":[{"role":"user","content":"问题"}]}}
```

messages使用chat-completions格式。Agent首条system来自init，之后保留本会话用户、模型和工具历史；Core的system为空，不追加system消息。短场景校验历史，不测试真实长上下文摘要质量。父进程固定模型、工具定义与生成参数，不使用adapter的生成覆盖。

父进程返回同request_id/session_id：

```json
{"type":"provider_result","request_id":"p1","session_id":"A","ok":true,"result":{"message":{"role":"assistant","content":null,"tool_calls":[{"id":"t9","type":"function","function":{"name":"search_story","arguments":"{\"query\":\"甘雨\"}"}}]},"finish_reason":"tool_calls","usage":null}}
```

真实返回还含raw_response供审计；worker只把result.message加入历史。usage缺失为null。不能把审计包装或参考答案混入模型历史。

工具请求使用模型工具ID，不是provider请求ID：

```json
{"type":"provider_call","request_id":"p2","session_id":"A","parent_id":"h3","provider":"tool","payload":{"call_id":"t9","name":"search_story","arguments":{"query":"甘雨"}}}
```

Agent只提供search_story，参数是非空字符串query；Top-K由runner固定。成功结果为 `{"ok":true,"result":{"evidence":[...]}}`，证据保留片段ID、原文与来源；错误为 `{"ok":false,"error":{"code":"..."}}`。unknown_tool／invalid_arguments为可观察错误，model_error另记录异常类型，不自动重试网络。

历史追加role=tool、tool_call_id=t9，content是**工具结果包装对象**（ok/result或ok/error）的JSON字符串，不包含type/request_id/session_id传输字段。多工具结果顺序可变，ID与内容须对应。最多8个provider请求同时在途，父进程允许乱序返回。

## 分类约定

Core模拟工具及上下文见[Core定义](../agent_core/evaluation.md#策略与上下文)；剧情场景、证据与评审见[Story定义](../agent_story/evaluation.md)。

## 限制与失败

provider等待受请求期限限制，超时后只留50ms清理宽限。忽略期限的自定义provider若仍在后台运行，整次运行失败并停止后续样本，避免污染比较；迟到结果不再入队。真实HTTP操作在独立辅助进程中执行，绝对期限到达后终止并等待该进程，不依赖可被慢流量重置的socket超时。

每行最多4,194,304字符，读写队列有界。非法JSON、ID／会话不匹配、重复provider ID、provider未完成就返回结果、进程崩溃或超时均使样本失败。期限覆盖worker停止读取stdin的情况。

worker派生进程须留在可观测进程树，不能脱离运行生命周期。父进程在消息边界记录后代，退出时回收已观测后代并等待；极短且已脱离父进程的后代无法保证发现。外部模型服务不属worker，不会被关闭。

协议不提供沙箱或外部副作用隔离；启动的是用户选择的候选命令。评测脚本本身不包含候选实现。

## Dev Note

无。
