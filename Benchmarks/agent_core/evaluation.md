---
kind: reference
description: "定义15个Core用例、模拟上下文、错误恢复和性能工作负载。"
---
# Core评测定义

## 摘要

确定性oracle观察历史、调用ID、终止状态及后续行为。测试替身不实现agent决策；真实表现须由候选接入后另行测量。

## 目录

- [用例矩阵](#用例矩阵)
- [策略与上下文](#策略与上下文)
- [开销采样](#开销采样)
- [Dev Note](#dev-note)

## 用例矩阵

| Core ID | 内容 |
| --- | --- |
| c01 | 模型直接完成 |
| c02–c05 | 单工具、多工具非位置ID、未知工具、非法参数 |
| c06–c08 | 超时、执行异常、非法结果 |
| c09–c10 | 多步正常完成、最大模型请求数 |
| c11–c12 | 模拟上下文恰好到限、超限 |
| c13–c14 | A/B交替隔离、reset清除历史 |
| c15 | 固定模型—工具—模型开销负载 |

oracle核对模型历史、实际工具调用与结果ID、终止状态和后续行为，不能伪造工具结果。策略见 [协议](../support/protocol.md)。这些探针不是全部agent能力认证。


## 策略与上下文

echo参数为 `{"text":"..."}`，正常result为 `{"text":"..."}`。timeout／tool_exception以结构化错误注入，不依赖墙钟等待。非法结果用 `{"ok":true,"result":"not-an-object"}` 注入，候选须识别invalid_result；恢复时传给模型的error只包含对应code。

未知工具与非法参数可本地拒绝，也可请求工具入口获错。recover将对应结构化错误送回模型继续完成；terminate返回tool_error，不能只改标签而继续调用。

模拟context_limit统计所有消息content的Unicode字符数，不含工具参数，也不是tokenizer。c11恰好100，c12超过100且末尾含KEEP：error不请求模型；truncate保留末尾100字符；compress在预算内保留KEEP。这只检查预算和必要标记，不证明摘要语义无损。

## 开销采样

correctness与perf分开。perf每轮新worker，记录启动至ready耗时，再预热2批、每批100次，正式100次，默认7轮。一次负载含reset、工具交互、broker、oracle和轨迹写入；逐次耗时与整批均值分别保存。候选按轮交替顺序，多候选轮换起始者。

transport_replay使用同协议、同负载的有限磁带，每轮单列；保留原始值、同轮差值和比值。进程、序列化和检查成本不能靠相减完全分离。断言失败的样本不用于性能汇总或配对，不按幸运样本选最快方案。

共享范围、CPU／RSS采样与比较限制见[测量说明](../support/measurement.md)。命令由[分类README](README.md)维护。

## Dev Note

无。
