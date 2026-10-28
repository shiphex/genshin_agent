---
kind: overview
description: "提供剧情agent项目、当前RAG基线及开发文档入口。"
---
# 原神剧情分析与解读 agent

## 摘要

项目面向以主角／派蒙身份参与剧情分析和讨论的agent。当前实现为冻结Wiki剧情的RAG与离线评测工具，角色对话、界面、玩家进度和防剧透尚未实现。模型回答仍有语义问题，技术完成不代表用户验收。

## 目录

- [使用入口](#使用入口)
- [开发入口](#开发入口)
- [数据与限制](#数据与限制)
- [Dev Note](#dev-note)

## 使用入口

- [RAG说明](rag/README.md)：语料、检索、本地模型与Hugging Face导出。
- [问题集](rag/eval/README.md)：110题及20题独立事实核验。
- [三题Smoke](rag/eval/smoke/README.md)：模型链路结果、依据与已知问题。
- [当前数据规则](rag/docs/data.md)：基线与独立生成内容。
- [Core 技术探针评审](Benchmarks/reviews/core-probe-20261028/README.md)：双候选源码、精选证据与复算入口。
- [Benchmarks分类索引](Benchmarks/README.md)：按agent_core／agent_story分类评测，support供未来各类复用。

## 开发入口

先读[AGENTS](AGENTS.md)和[context](context.md)，再按任务阅读[架构](docs/architecture.md)、[开发流程](docs/development.md)、[文档规范](docs/AGENTS.md)、[术语](docs/terminology.md)和[Agent Notes](.agents/notes/README.md)。

## 数据与限制

当前基线由[统一清单](rag/catalog.json)维护，旧实验与审阅包已按用户决定淘汰。除本次明确白名单内的Core评审材料外，Git不包含原始快照、语料、模型回答和核验原件；新克隆须独立取得本地数据，获取与验证见RAG说明。重跑不能恢复历史回答。

[爬虫恢复交接](rag/docs/recovery/crawler_handoff.md)属于独立爬虫项目任务，本项目此次不修改爬虫或接入新版数据。

## Dev Note

无。
