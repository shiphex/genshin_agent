---
kind: reference
description: "提供 RAG 语料、检索、模型实验和模块检查的使用说明。"
---
# 原神剧情 RAG

## 摘要

本模块为主角／派蒙剧情讨论 Agent 提供可追溯证据。当前实现为冻结 Wiki 剧情提取、词面检索、本地模型对照与离线题库维护；Python 使用标准库并通过 uv 运行。

本页维护模块接口、命令与使用限制；当前问题、反馈和最近验证见[模块上下文](context.md)，总体关系见[架构](../docs/architecture.md)。开发前阅读模块上下文。旧阶段详记见[开发历史](docs/history/development_20261013.md)，本地旧过程资料见[归档说明](docs/archives.md)。

## 目录

- [目录与入口](#目录与入口)
- [当前题库](#当前题库)
- [语料与检索](#语料与检索)
- [模型实验与审阅](#模型实验与审阅)
- [发布与本地归档](#发布与本地归档)
- [验证](#验证)
- [Dev Note](#dev-note)

## 目录与入口

| 目录 | 内容 |
| --- | --- |
| `catalog.json` | 题库、实验、运行、复核与报告的统一索引 |
| `scripts/` | 正式 Python 实现 |
| `tests/` | 模块行为测试 |
| `eval/` | 当前开发题库、保留的 v2 题库与字段说明 |
| `config/` | 共享本地模型连接配置 |
| `docs/` | 开发历史、观察、归档恢复和爬虫交接 |
| `experiments/` | 复现实验的输入、采样参数和执行说明 |
| `reports/` | 批准公开的摘要、逐题关键摘录与发布清单 |
| `data/` | 本地语料、模型结果、原文副本、发布包、归档和临时工作文件 |

`data/` 按corpora、prepared、runs、reviews、releases、baselines、archive和tmp管理，位置由catalog定位；封存记录保留原字节及旧坐标。[本地产物管理](docs/data.md)。

## 当前题库

[questions_dev.json](eval/questions_dev.json)为工程迭代入口：0.5 版、110 题，仅维护 `id/type/difficulty/question/answer/keywords/criteria/sources`。原文位置指向冻结快照，`text` 由脚本读取后加入本地副本。当前保留的[最终原文副本](data/prepared/story_dev/v0.5/r001/questions.json)只供本地查看。

在项目根目录运行，输出替换为新的路径：

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/prepare_eval.py
```

[questions.json](eval/questions.json)保留为未来 benchmark 资产：2.0.1-pilot、14 题，暂停扩展。[14 题历史复核表](data/reviews/benchmark_source/r001/review.md)继续可直接阅读；覆盖统计属于 2.0.0 的旧口径。v2 离线工具为 `prepare_eval_cases.py`，字段及命令见[题库说明](eval/README.md)。

两套 JSON 题库尚未接通读取 JSONL 的 `evaluate_rag_mvp.py`；关键词命中不等于语义正确。全部题目仍待用户逐题验收；第三方复核和程序校验单独记录。

## 语料与检索

原始快照位于项目共享的 `data/raw/genshin_wiki_data_20260605/`。新克隆须另行提供该快照，才能构建语料或按原文位置回查。当前[全量语料](data/corpora/story_full/v1/corpus.jsonl)有 22,822 个片段；处理状态和边界见[覆盖说明](data/corpora/story_full/v1/coverage.md)、[审计](data/corpora/story_full/v1/audit.json)及[排除记录](data/corpora/story_full/v1/exclusions.jsonl)。

构建使用新输出目录；评测由索引分配独立运行编号，保留已存在的语料和人工复核：

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/prepare_rag_mvp.py --all
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/evaluate_rag_mvp.py --dataset full --retrieval-only
```

第二条默认读取保留的当前全量语料；如需测试新构建的语料，显式传入 `--corpus`。`--dataset full` 是评测默认值，缺少全量语料时报错；`--dataset sample` 明确选择历史 30 片段样本。`--retrieval-only` 不访问模型服务。

每次评测登记新运行，默认写入 `data/runs/<实验ID>/rNNN/`；显式输出也拒绝已有目录。日期记录在清单中，旧完整结果通过索引定位。身份、版本、状态与保留规则见[资料管理说明](docs/artifacts.md)。

`prepare_rag_mvp.py` 是准备入口，`full_corpus.py` 实现全量提取。保留人物、武器、圣遗物及其他剧情字段；排除培养、技能数值和攻略，不因出现“力量”“战斗”而删除故事。未解析结构和不能分离的混合文本记录到排除资料中，不用模型补原文。

来源记录包括原文件、RFC 6901 Pointer 和解码后字符串的零基半开字符范围 `[start,end)`。`wiki_excerpt` 与 `wiki_compilation` 区分 Wiki 摘录和编纂，均不自动代表官方确认事实。人物观点、传说和不确定性应保持原限定。

检索使用中文相邻双字／英文词的 IDF 加权重合和一次构建的内存倒排索引。默认 Top5；分数用于排序，不代表语义置信度。可复用接口：

```python
from rag.scripts.evaluate_rag_mvp import LexicalIndex, load_jsonl

from rag.scripts.artifact_catalog import dataset_path, PROJECT
index = LexicalIndex(load_jsonl(dataset_path(PROJECT, "full_corpus")))
hits = index.search("钟离如何看待契约与公平？", top_k=5)
```

## 模型实验与审阅

共享配置在 `config/local_api.json`，连接用户部署的本地 chat-completions 服务；鉴权值从环境变量读取。脚本不启动服务或下载模型。实验输入和状态见[实验索引](experiments/README.md)，开发记录见[文档索引](docs/README.md)。

- [24 题模型对照](experiments/model_comparison/README.md)：无检索／RAG 正式对照，完整记录在 `data/runs/model_comparison/r001/`。
- [六题受控诊断](experiments/generation_diagnosis/README.md)：检索／人工证据与采样配置对照，入口为 `diagnose_rag_generation.py`，完整记录在 `data/runs/generation_diagnosis/r001/`。
- [公开审阅入口](reports/README.md)：实验概要、关键回答原句、必要原文和初审；完整上下文不能由摘录替代。

`baseline` 为无检索条件，`rag` 为检索条件。检索覆盖、API 完成、引用格式／ID／支持关系和语义正确性分别核验；`ok` 或 `finish_reason=stop` 不代表答案正确。重跑产生新结果，不能恢复历史回答或人工反馈。

## 发布与本地归档

语料发布文件与审阅 ZIP 的版本、哈希和状态见[数据获取](reports/data_access.md)。现有 v1／v2／v3 ZIP 和历史 Git bundle 保留；重复的 `verified_restore_*` 展开目录已清除，需要时恢复到新目录。

生成新的 Hugging Face staging；工具只导出固定白名单，不上传：

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/export_hf_dataset.py build --output rag/data/tmp/<新的目录>/hf_dataset
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/export_hf_dataset.py verify rag/data/tmp/<新的目录>/hf_dataset
```

`export_review_bundle.py` 负责公开摘录和独立审阅 ZIP。摘录位置在 `reports/inputs/excerpts_v3.json`，生成后检查精确原句、来源、哈希及全部条件／种子：

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/export_review_bundle.py check-views
```

新包使用新的版本和输出目录；包内源码 commit 与后续链接索引分别记录。恢复方式与发布边界见数据获取说明。现有 ZIP 不覆盖最近题库制作资料，后者独立存于[本地归档](docs/archives.md)。

`rag/` 默认忽略新增文件，只跟踪正式脚本、测试、文档、列出的实验输入和批准的报告副本。整个 `rag/data/`、共享快照与缓存保持本地忽略；新克隆中的本地产物链接可能不可用。清除 `tmp/` 前仍须确认没有唯一模型输出、复核或其他未备份内容。

## 验证

项目根目录运行，无需真实模型：

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python -B -m unittest discover -s rag/tests -v
```

整理前各阶段的测试数量和调用状态保留在开发历史；当前验证结果和未解决问题以模块上下文为准。

## Dev Note

无。
