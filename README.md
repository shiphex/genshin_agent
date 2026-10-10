# 原神剧情分析与解读 Agent

项目目标是设计能够以主角／派蒙身份参与剧情讨论、分析和解读的 Agent。当前已完成本地快照的全量剧情 MVP RAG，最终角色 Agent、对话界面和玩家进度分析尚未实现。

## 开发入口

- [开发指引](AGENTS.md)：项目长期约束和上下文读取要求。
- [项目上下文](context.md)：当前阶段、模块导航与待定事项。
- [RAG 模块](rag/README.md)：数据提取、检索、评测的运行方式。
- [RAG 上下文](rag/context.md)：已验证结果、用户反馈和下一轮问题。

RAG 专属代码、实验配置、测试、语料与历史结果统一位于 `rag/`。原始爬虫快照作为共享数据保留在 `data/raw/`；uv 缓存继续共用 `.cache/uv/`。

## Git 与本地数据

Git 保留代码、测试、README、上下文和必要的小型实验输入。`rag/` 使用默认忽略、显式保留的规则；`data/`、`rag/data/`、缓存及新增的 RAG 产物默认不提交。本地现有数据和历史结果仍完整保留。

重新克隆后，先自行提供冻结快照到 `data/raw/genshin_wiki_data_20260605/`，再按 [RAG 运行说明](rag/README.md) 生成样本或全量语料。本文链接的覆盖报告、模型回答等位于被忽略的本地产物中，未提供或生成时不可用；历史模型输出和人工复核需另外备份。

冻结快照恢复的 [爬虫 AI 交接任务](rag/experiments/recovery/crawler_handoff.md) 和回归清单纳入 Git，实际爬虫修复尚未执行；当前窗口不修改爬虫项目代码。

## 当前实验结果

当前全量数据扫描全部5,474个parsed文件，生成22,822个可追溯片段，保留Wiki编纂来源标注、过滤非剧情机制并记录问题。全量纯检索回归中，9道有参考证据的题有6道在Top5找齐，三个跨来源问题仍有缺口；语义质量仍待人工检查。本轮不调用模型。

全量入口见 [RAG运行说明](rag/README.md)，产物与来源抽检见 [全量覆盖报告](rag/data/full/genshin_wiki_data_20260605/coverage.md)，实测及已知问题见 [全量观察](rag/experiments/full/observations.md)。

原30片段、12题和本地Qwen无检索／RAG对照完整保留。此前小样本中9道可答题证据均进入Top5，24次模型调用正常结束；它们不是全库语义质量证明。检索成功和调用成功都不等于答案正确。

完整报告见 [模型对照复核报告](rag/data/mvp/model_comparison/review.md)，具体模型问题见 [实验观察](rag/experiments/mvp/observations.md)。这些生成结果保存在本地，默认不进入版本控制。
