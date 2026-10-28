---
kind: architecture
description: "说明项目当前模块、证据数据流和扩展位置。"
---
# 当前架构

## 摘要

项目面向以主角／派蒙身份参与剧情讨论的 agent（智能体）。当前实现集中于 RAG（检索增强生成）及离线评测工具，角色对话与应用界面尚未实现。本文解释模块关系，使用方式由模块 README 维护，当前问题与验证由模块 context 维护。

## 目录

- [模块组成](#模块组成)
- [证据与执行数据流](#证据与执行数据流)
- [边界与扩展](#边界与扩展)
- [相关入口](#相关入口)
- [Dev Note](#dev-note)

## 模块组成

| 部分 | 职责与依赖 |
| --- | --- |
| 项目层 | 项目导航、共同开发约束、统一uv配置与根环境、共享原始快照及公共缓存 |
| [RAG 模块](../rag/README.md) | 从冻结 Wiki 快照提取剧情，提供带出处的检索证据及模型对照工具 |
| [题库](../rag/eval/README.md) | 维护110题与20题事实核验；原文准备与模型评测分开 |
| [基线索引](../rag/docs/data.md) | 固定当前资源与指纹，新运行写入独立输出 |
| [Smoke](../rag/eval/smoke/README.md) | 三题模型链路、完整结果与初审依据 |
| [Benchmarks](../Benchmarks/README.md) | 按被测任务分类；agent_core测确定性行为与开销，agent_story用Qwen与既有词面检索测多轮任务 |
| [Core探针](../probes/README.md) | 自建循环与create_agent候选，仅经JSONL broker获取模型和工具结果；依赖与适配成本单列 |

RAG 通过配置连接用户已部署的 chat-completions 服务，不负责下载模型或启动服务。外部爬虫属于独立项目，恢复任务通过既有交接说明传递。

## 证据与执行数据流

共享冻结快照 → 剧情提取、过滤与切块 → 本地带来源语料 → 词面检索 → 证据和问题组成模型输入 → 回答与调用记录 → 独立语义核验。

语料准备入口是 [prepare_rag_mvp.py](../rag/scripts/prepare_rag_mvp.py)，全量提取由 [full_corpus.py](../rag/scripts/full_corpus.py) 负责；三题检索和模型对照由 [evaluate_rag_mvp.py](../rag/scripts/evaluate_rag_mvp.py) 负责。新增 [evaluate_retrieval.py](../rag/scripts/evaluate_retrieval.py) 直接适配110题 JSON，复用前者的 LexicalIndex 和既有 catalog／运行编号，只计算来源定位代理指标。题库原文准备另由 [prepare_eval.py](../rag/scripts/prepare_eval.py) 执行，JSON 题库仍未接通模型生成评测。

[catalog](../rag/catalog.json) 定位当前基线资源、路径和哈希；[产物管理](../rag/docs/data.md)规定独立生成与基线更新。正式运行的 manifest（元数据清单）记录实际输入、执行参数及源码指纹。公开概要和重新运行均不能恢复历史回答或人工反馈。

## 边界与扩展

Benchmarks只编排场景、统一provider、收集轨迹和评分，不实现agent core。分类自持用例、runner和判定；support供所有分类共享协议、记录和测量，不导入分类实现，薄入口组合报告。候选adapter内保留工具循环、历史和恢复决策；RAG实现与catalog只读复用。新运行写入Benchmarks/outputs/分类/用途/运行号，跨分类报告写outputs/reports；旧输出原位只读，RAG eval暂留rag。本分支按用户批准白名单发布[评审副本](../Benchmarks/reviews/core-probe-20261028/README.md)，已执行范围及未验证事项由其维护，不代表生产Core选型。

当前词面检索和脚本组合是 MVP 选择。以后引入向量检索、数据库、角色 agent 或界面时，先说明新增职责、依赖和兼容影响，再更新本页；不把未实施方案画成现有组件。

原文、Wiki 编纂和模型生成内容的区别贯穿证据流；具体来源字段、过滤行为和命令仍以 RAG README 为维护入口。API 完成、检索覆盖、引用合法性与语义正确性各有验证依据，不由流程完成自动推导。

## 相关入口

- [项目阶段](../context.md)：当前关注点。
- [开发流程](development.md)：如何分析、设计、实施和更新知识。
- [RAG context](../rag/context.md)：当前问题与最近验证。
- [文档规范](AGENTS.md)：信息归属和维护要求。

## Dev Note

无。
