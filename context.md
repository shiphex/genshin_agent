---
kind: context
description: "记录项目当前阶段、模块入口及下一会话的工作边界。"
---
# 项目上下文

## 摘要

更新：2026-10-16。项目目标是以主角／派蒙身份参与剧情讨论的 agent；当前集中于 RAG 实验、错误诊断与评测资产维护。角色对话、界面、玩家进度和防剧透尚未实现。长期约束见 [AGENTS](AGENTS.md)。

## 目录

- [当前入口](#当前入口)
- [状态与未解决问题](#状态与未解决问题)

## 当前入口

- [架构](docs/architecture.md)、[开发流程](docs/development.md)、[文档规范](docs/AGENTS.md)与[术语](docs/terminology.md)：按任务加载的中文文档体系。
- [RAG README](rag/README.md)与[模块 context](rag/context.md)：模块命令、当前问题与最近验证。
- [catalog](rag/catalog.json)、[资料规则](rag/docs/artifacts.md)和[数据管理](rag/docs/data.md)：资源、版本和本地产物定位。
- [题库说明](rag/eval/README.md)、[实验索引](rag/experiments/README.md)、[审阅入口](rag/reports/README.md)：输入、历史执行与复核分别维护。
- [Agent Notes](.agents/notes/README.md)、[RAG 文档索引](rag/docs/README.md)：重要决策和原有历史／恢复入口。

## 状态与未解决问题

文档体系采用职责分层、三个独立 skill、分类模板和中文字数门禁；实现与验证入口见[首条 Agent Note](.agents/notes/implemented/2026-10-16-ai-native-documentation.md)。RAG 的语义问题及待用户验收状态未因本轮文档调整改变。

历史模型回答、题库复核、数据整理和 Smoke Test 记录保留在模块 context 及其链接位置，不在项目导航重复。旧开发题 skill 的输出路径冲突见模块当前问题；未在本轮修订该 skill。
