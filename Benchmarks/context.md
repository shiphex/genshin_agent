---
kind: context
description: "记录a06诊断现状及Core评审材料的验证边界。"
---
# Benchmark当前状态

## 摘要

更新：2026-10-30。exp/a06-diagnosis从aa57d98增加[独立a06诊断](../probes/a06_diagnosis/README.md)，r003在原worktree导入fa31e46的QwenClient及配置依赖，显式接入工具前缀模式。原Core、LiveProvider逻辑、场景、评分和冻结输入不改；主工作区未改。[评审入口](reviews/core-probe-20261028/README.md)继续维护历史材料。

## 当前状态与边界

本轮只用core-self，重建O/A而不跨修复复用历史。r003新O无检索且首答错误；B与r002逐字节一致。三次A均32 token完成原生search_story并接回真实Top5，核心目标认出女士，但首答仍混同温迪与摩拉克斯、扩写身份和误用证据，不能计C1。H1获部分支持但强制检索不足以解决a06；后两问仍有查询不足因素。

三次C2与r002回答及注入历史一致，完整保留正确首答后仍将已送达女士台词错归温迪，局部支持H4；H3未知。A与C2查询和Top5不同，不把差异仅归正确历史。第八席和canonical效忠原文均未送达，不判为忽略。程序引用格式与语义分列，用户验收未进行。

## 最近验证

26项诊断、73项Benchmark及5项自建测试通过，14份基线指纹、文档及产物传递检查通过。r003共21次真实模型请求，服务已停止。独立AI审阅与用户验收分开记录。完整报告在本地Benchmarks/outputs/agent_story/a06_diagnosis/r003；r001/r002保留只读。输出仍忽略；提交与推送不包含运行产物。
