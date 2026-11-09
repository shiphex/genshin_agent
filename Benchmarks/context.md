---
kind: context
description: "记录结构化RAG探针的当前验证、诊断与验收边界。"
---
# Benchmark当前状态

## 摘要

更新：2026-11-09。exp/rag-structured-validation组合结构化RAG与core-self探针，入口见[验证说明](../probes/structured_rag_validation/README.md)。独立worktree保留两个原分支；当前语料、正式题库和默认基线未切换。公共框架仍按[索引](README.md)与[协议](support/protocol.md)维护。

## 当前状态与边界

本地r001显式使用corpus/r002、prepared/r004与261106 raw。A06自主O首两轮未检索；三次A强制调用成功但完整首答仍有无依据扩写，均未获C1资格。三次C2在人工正确首答和oracle证据下，后两问正确并保留温迪说法；真实首轮和三轮整体标准保留存疑，不算端到端。

固定证据对照：首问两种表示均有无据姓名及来源限定问题，整样本各0/3；第三问两组均正确归属，整样本各3/3。不能据有限固定seed重复宣称一般优劣。a07/a10/a11各三次均有语义失败；局部正确项、查询不足、证据误读和用户假说升级分别记录。旧A06 r003/report-r002仅作历史参照，不宣称同条件提升或4B永久能力上限。

## 最近验证

68次真实API响应全部正常结束，实际工具调用10次；六组成对payload仅预定工具content变化。最终审计10条实际query，独立审阅9充分、1不足；初始用户身份追问另有缺口。充分性不代替模型正确使用证据。

完整输出在本地Benchmarks/outputs/agent_story/structured_rag_validation/r001，模型执行源码0ec0c09与报告修正源码分开封存。完整性核验无发现，当前基线14份指纹不变，本次服务已停止。三个独立AI审阅任务分别评A06/查询、回归和呈现，原件未覆盖；用户语义验收未进行。29项新模块离线测试通过，其余最小验证与文档检查按[开发流程](../docs/development.md#验证)交付；不登记远端CI、Linux、SDK比较或性能验收。
