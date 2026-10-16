---
kind: overview
description: "提供剧情 agent 项目、RAG 模块、审阅材料和开发文档的阅读入口。"
---
# 原神剧情分析与解读 agent

## 摘要

项目面向以主角／派蒙身份参与剧情分析和讨论的 agent（智能体）。当前实现集中在冻结 Wiki 剧情的 RAG（检索增强生成）与评测工具，角色对话、界面、玩家进度分析和防剧透尚未实现。模型回答仍存在严重错误，技术完成不代表语义或用户验收通过。

## 目录

- [使用与审阅入口](#使用与审阅入口)
- [开发入口](#开发入口)
- [数据与限制](#数据与限制)
- [Dev Note](#dev-note)

## 使用与审阅入口

- [RAG 使用说明](rag/README.md)：语料、检索、模型实验和模块检查命令。
- [公开审阅入口](rag/reports/README.md)：关键错误原句、必要原文、初审与外部分析任务。
- [24 题双组摘要](rag/reports/model_comparison/r001/summary.md)与[六题受控诊断](rag/reports/generation_diagnosis/r001/summary.md)：分别查看历史对照及其子集的全部条件／种子。
- [数据获取与发布状态](rag/reports/data_access.md)：Hugging Face 语料、审阅资料包与恢复说明。未上传项目仍按该页状态阅读。

## 开发入口

先读 [AGENTS](AGENTS.md) 和[项目上下文](context.md)，再按任务选择材料：

| 入口 | 用途 |
| --- | --- |
| [架构](docs/architecture.md) | 当前模块、依赖与数据流 |
| [开发流程](docs/development.md) | 分析、设计、实施、验证与知识更新 |
| [文档规范](docs/AGENTS.md) | 事实维护位置、模板与字数门禁 |
| [术语约定](docs/terminology.md) | 中文说明及必要英文的统一写法 |
| [Agent Notes](.agents/notes/README.md) | 重要决策、取舍与验证依据 |

## 数据与限制

原始快照、语料、完整回答与复核材料由本地或独立发布物保存，Git 不能代替备份。新克隆重建和按 Pointer 回查需另行取得同一冻结快照，见[模块说明](rag/README.md)。用户对历史模型回答的总体反馈不能当作逐题评分，当前问题见[模块上下文](rag/context.md)。

[爬虫恢复交接](rag/docs/recovery/crawler_handoff.md)属于独立爬虫项目任务，本项目不在此次工作中修改爬虫或接入新版数据。

## Dev Note

无。
