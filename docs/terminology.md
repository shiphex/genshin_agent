---
kind: reference
description: "统一中文文档和 skill 中实际使用的技术术语写法。"
---
# 术语约定

## 摘要

中文说明保留必要英文术语。本文只规定写法，领域行为仍由相应文档维护；不复制上游特有的运行时概念。

## 目录

- [写法](#写法)
- [使用规则](#使用规则)
- [Dev Note](#dev-note)

## 写法

| 术语 | 首次出现时可用的说明 | 后续写法／维护入口 |
| --- | --- | --- |
| agent | agent（智能体） | agent；[架构](architecture.md) |
| skill | skill（技能） | skill；根 AGENTS 的任务阅读路由 |
| Agent Note | 无需改译文档类型 | Agent Note；[记录约定](../.agents/notes/README.md) |
| Dev Note | Dev Note（开发备注） | Dev Note；[文档规范](AGENTS.md) |
| RAG | RAG（检索增强生成） | RAG；[模块说明](../rag/README.md) |
| manifest | manifest（元数据清单） | manifest；[资料管理](../rag/docs/artifacts.md) |
| API／CLI／JSONL | 必要时解释 CLI 为命令行界面 | 保留缩写 |
| context | 普通说明写“上下文” | 路径及代码保留 context |
| Table of Contents | 页内目录 | 章节导航，区别于文件夹索引 |
| Pointer | RFC 6901 Pointer | 保留 Pointer；[来源说明](../rag/README.md#语料与检索) |

## 使用规则

按单页阅读需要提供首现解释，标题、代码、路径和 Agent Note 固定头部无需括注。已在组合词中解释的术语不重复括注。普通中文词不为追求英文而换词，标识的大小写与状态值保持原样。

本表参考上游[术语表](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/glossary.zh.md)与[统一译法](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/i18n/terminology.md)，只采用项目需要的部分，不建立翻译配对或独立领域词汇副本。

## Dev Note

无。
