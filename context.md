---
kind: context
description: "记录项目当前阶段、模块入口及后续工作边界。"
---
# 项目上下文

## 摘要

更新：2026-10-17。项目目标是以主角／派蒙身份参与剧情讨论的agent；当前集中于RAG。用户选择将当前语料、110题、20题核验和三题Smoke设为新基线，旧实验与过程资料不再维护。角色对话、界面、玩家进度和防剧透尚未实现。

## 目录

- [当前入口](#当前入口)
- [状态与边界](#状态与边界)

## 当前入口

- [RAG说明](rag/README.md)、[模块context](rag/context.md)：操作、当前问题和最近验证。
- [catalog](rag/catalog.json)、[基线规则](rag/docs/data.md)：当前资源、来源与新输出。
- [110题与20题核验](rag/eval/README.md)、[三题Smoke](rag/eval/smoke/README.md)：用途和独立验收状态。
- [架构](docs/architecture.md)、[开发流程](docs/development.md)、[文档规范](docs/AGENTS.md)、[术语](docs/terminology.md)与[Agent Notes](.agents/notes/README.md)：按任务阅读。

## 状态与边界

原始快照仍在项目层；RAG本地data保持忽略，不能靠Git恢复。三题Smoke保持原入口，110题已有[离线检索评测](rag/README.md#110题检索评测)，只计算来源定位代理指标，尚未接通模型评测。题库、事实核验和模型初审均未因此获得用户逐题验收。
