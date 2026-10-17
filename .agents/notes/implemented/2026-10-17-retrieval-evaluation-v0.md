# Agent Note: 检索评测V0与评测工作流适配

Status: implemented

## 问题

110题JSON开发集与现有三题JSONL模型runner的输入及标注不同。直接套用证据组指标会把来源字段位置误当语义覆盖，且无法稳定比较后续检索方案。用户要求复用现有索引、catalog与编号，完成真实离线评测，并明确要求适配三个上游Skill。

## 决策

采用独立薄入口，复用 LexicalIndex 和 artifact_catalog；题库不转换落盘，协议由[题库说明](../../../rag/eval/README.md#检索评测协议-v0)维护，命令由[模块说明](../../../rag/README.md#110题检索评测)维护，结果仍使用现有retrieval输出编号。r001表示第1次运行，失败编号也不复用；用户选择保留现有路径。

只计算精确来源位置Hit／Coverage，未映射位置保留分母，语义覆盖与最终答案正确性未评测。保存输入、源码、实际参数、环境、逐题结果及终态产物哈希；加载或封存期间输入改变时拒绝完成。错误／中断保留已完成题目，部分汇总不构成完整评测。

三个项目Skill分别承担性能实验、资源型测试可靠性、交付前检查选择。根AGENTS只维护按需入口；开发流程、模块命令和数据保护继续在原位置维护。Skill不扩大推送、上传或改写历史授权。

## 上游依据与适配

查阅并下载固定commit `687f282e8625c6b8d11ff58211a90524be2e4317` 的三个入口：[性能](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/.agents/skills/dsh-speed-up-perf/SKILL.md)、[可靠性](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/.agents/skills/dsh-ci-test-reliability/SKILL.md)、[提交前检查](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/.agents/skills/dsh-pre-push-checks/SKILL.md)，另读可靠性的ci-flake-diagnosis参考。

采用[benchmarks规则](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/benchmarks/AGENTS.md)的固定场景、生产入口、明确计时边界与负例验证；研究support/scaling-report.ts的原始JSONL与汇总分离、machine-profiles.ts的测量环境记录，舍弃机器估算与校准。采用[Snapshot配置](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/vitest.snapshot.config.ts)中重放／更新预期分离的原则：离线合成场景验证行为，正式运行不覆写旧结果；没有移植Snapshot录制系统。

保留控制变量、重复采样、状态同步、独立资源及按差异选择检查。删除上游专有命令、路径、hooks、stacks、UI、机器参数和性能阈值，不新增插件、重复检查框架或全量CI性能门禁。Copyright (c) 2026 DeepSeek；改编内容遵循[MIT许可证](../../skills/doc/LICENSE.deepseek)。上游原件仅作本地忽略区的适配参考。

## 考虑过的替代方案

将JSON转换为旧证据组并接入模型runner：来源缺少必需组与字符范围，容易夸大可计算指标；保留旧三题行为，新增独立适配入口。

新增rag-eval Skill或通用benchmark框架：现有文档与catalog已能承载接口和记录，没有必要；仅适配用户指定的三个工作流Skill。

缩短输出路径或新增A/B命令：用户选择保留现有路径，本轮只保存可对齐结果及对比说明，避免扩大产物迁移和接口范围。

## 验证与影响

2026-10-17新增13项离线测试，核心入口缺失及加载期间输入变化的回归均观察到失败后通过；完整64项RAG及4项项目测试通过。指标覆盖精确匹配、去重、无标注、未映射来源、宏／微分母与负例降分；运行覆盖零API调用、一次建索引、实际查询、基线与覆盖保护、源码封存、失败和中断。

本地r002以当前0.5版110题、22,822片段、Top5完成，来源位置Hit为95/110，Coverage宏平均73.77%、微平均307/445；3条标注未进入语料。逐题结果独立重算，全部输入／源码／产物哈希核对，14份current-003指纹不变。r001保存增加输入变化保护前的执行源码；r002与其排序和指标一致，旧结果未重写。两次耗时不是经控制的性能A/B证据。

三个Skill均做结构检查和独立只读应用，与适配前相同场景对照；基线已能作出主要正确判断，不宣称错误率或成本改善。性能场景澄清负例与发现路径；可靠性场景区分Windows未复现与Linux通过；交付场景区分用户假设和真实工作区。仅证明显式读取后的应用，客户端自动发现尚未验证。未调用真实模型、推送、上传或改变用户语义验收。
