---
kind: reference
description: "提供当前 RAG 基线、语料检索、题库准备和 Hugging Face 导出的使用说明。"
---
# 原神剧情 RAG

## 摘要

本模块为主角／派蒙剧情讨论 agent 提供可追溯证据。当前采用冻结 Wiki 剧情语料、词面检索和本地模型对照；Python 实现只用标准库，通过根项目uv运行，环境见[开发说明](../docs/development.md#python环境)。当前基线身份、路径和哈希由 [catalog](catalog.json)维护，问题与最近验证见[模块上下文](context.md)。

## 目录

- [当前入口](#当前入口)
- [语料与检索](#语料与检索)
- [问题集与 Smoke](#问题集与-smoke)
- [本地模型](#本地模型)
- [110题检索评测](#110题检索评测)
- [检索 CLI 参考](#检索-cli-参考)
- [Hugging Face 导出](#hugging-face-导出)
- [数据获取与验证](#数据获取与验证)
- [Dev Note](#dev-note)

## 当前入口

| 位置 | 用途 |
| --- | --- |
| `scripts/`、`tests/` | 语料、检索评测与导出脚本及行为测试 |
| `config/local_api.json` | 公共 API、生成档位与 llama.cpp 参数；本机值用忽略的 .local.json |
| [eval](eval/README.md) | 110题开发集与20题独立事实核验 |
| [smoke](eval/smoke/README.md) | 三题 Q4 模型完整链路验证 |
| [数据管理](docs/data.md) | 基线、独立输出、保留与更新规则 |
| [开发文档](docs/README.md) | 当前规则与爬虫恢复交接 |

`data/` 仅保留 corpus、review20、smoke 三组原件；说明留在上述文档中。旧实验、题库原型、审阅包和兼容映射已按用户决定淘汰，不再是恢复入口。

## 语料与检索

原始快照在共享 `data/raw/genshin_wiki_data_20260605/`；当前全量语料在 `rag/data/corpus/`，22,822条片段，附审计、排除记录和覆盖说明。来源包含原文件、RFC 6901 Pointer、解码后字符串的零基半开字符范围 `[start,end)` 和来源性质。`wiki_excerpt` 与 `wiki_compilation` 分别表示 Wiki 摘录和编纂，均不自动等于官方事实；保留人物说法、传说、未知分支与不确定性。

构建默认扫描全量；`--all` 保留为兼容参数。新构建写入独立输出，不自动替换基线：

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B rag/scripts/prepare_rag_mvp.py
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B rag/scripts/evaluate_rag_mvp.py --retrieval-only
```

第二条先核对默认语料／三题输入的基线指纹，再检索，不访问模型服务。词面检索使用中文相邻双字／英文词的 IDF 加权重合，内存倒排索引每轮构建一次，默认 Top5；分数不是语义置信度。`--dataset full` 继续有效，sample 模式已移除。可通过 `--corpus`、`--questions` 指定其他语料及 JSONL 输入。

```python
from rag.scripts.artifact_catalog import PROJECT, dataset_path
from rag.scripts.evaluate_rag_mvp import LexicalIndex, load_jsonl
index = LexicalIndex(load_jsonl(dataset_path(PROJECT, "full_corpus")))
hits = index.search("钟离如何看待契约与公平？", top_k=5)
```

过滤排除数值强度、技能倍率、培养、配队与攻略，保留剧情力量描述。已知漏项与语义问题见 context。

## 问题集与 Smoke

[110题](eval/questions.json)是唯一正式开发题库，0.5版；[20题输入](eval/review20.json)及其本地完整结果用于核验题目事实，不是模型作答记录。原文准备命令：

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B rag/scripts/prepare_eval.py
```

该工具读取冻结原文、输出带 `sources[].text` 的副本，不评分、不调用模型。JSON题库尚未接通 JSONL 模型 runner。准备副本按需生成，不是基线的重复常驻文件。

[三题 Smoke](eval/smoke/README.md)保留六份完整回答、实际检索上下文、结构化初审与必要依据。再次运行模型对照的命令是 `evaluate_rag_mvp.py`（不加 `--retrieval-only`）；它会真实访问配置的本地服务并产生新输出，不会重现历史回答。脚本不启动服务或下载权重，鉴权从环境变量读取。

## 本地模型

llama.cpp 显式启动、私有路径覆盖和 simple／standard／deep 调用档位见[本地模型配置](docs/local_model.md)。RAG 与 Benchmark 共用读取器；评测不自动启动服务，旧平面配置仍可读取且默认关闭思考。当前公共配置默认 standard，尚未实测显存、延迟或游戏影响。

## 110题检索评测

标准化入口直接读取原 JSON 开发集，复用词面索引，每轮构建一次，不读取模型配置或访问 API：

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B rag/scripts/evaluate_retrieval.py
```

解析参数及默认值见下方生成表；运行时未指定题库／语料时从 catalog 取得，接受同格式 JSON／JSONL，Top-K 必须为正整数。输出默认分配 `data/outputs/retrieval/r001/`；r001 是第1次检索运行，随后 r002、r003，失败编号也保留。指定输出只接受同一用途下尚不存在的目录。

每轮保存 results.jsonl、summary.json、report.md，以及输入哈希、实际参数和执行源码副本。简报包含指标、覆盖分布、题型／难度分组及耗时表格。默认输入须通过 catalog 指纹／元数据校验；自定义语料记录实际身份，快照未知时不继承基线声明。失败或中断保留已写结果并非零退出，不覆盖当前基线。

指标协议、空标注与分母、A/B 对齐见[题库说明](eval/README.md#检索评测协议-v0)，产物和状态见[数据管理](docs/data.md#新输出与更新)。来源位置命中不代表论据完整覆盖或答案正确；单次逐题计时不作为性能门槛。

### 检索 CLI 参考

下表由[生成器](scripts/gen_retrieval_cli.py)从[evaluate_retrieval.py](scripts/evaluate_retrieval.py)的直接 `argparse` 定义提取，源码是唯一参数依据。验证参数名、解析类型、字面默认值和 help；`None` 是解析结果，运行时 catalog 回退、目录分配、正整数限制及失败语义由上文人工维护和行为测试核对。内建 `--help` 未列入表；不根据 help 文案推断运行时默认值。

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B rag/scripts/gen_retrieval_cli.py
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B rag/scripts/gen_retrieval_cli.py --check
```

生成只替换标记间内容；检查不写文件，过期或标记缺失／重复／反向均失败。仅支持试点的直接定义和字面默认值；出现动态表达式、分组、choices／action 等未支持定义时失败，需审查并显式扩展提取器，不静默漏项。

<!-- BEGIN GENERATED: retrieval-cli -->

| 参数 | 解析类型 | 解析默认值 | 源码 help |
| --- | --- | --- | --- |
| `--questions` | `Path` | `None` | JSON development set; defaults to catalog story_dev |
| `--corpus` | `Path` | `None` | JSONL corpus; defaults to catalog full_corpus |
| `--top-k` | `int` | `5` | — |
| `--output-dir` | `Path` | `None` | new retrieval output directory; allocated automatically by default |

<!-- END GENERATED: retrieval-cli -->

## Hugging Face 导出

只发布剧情语料；导出工具读取当前 catalog，明确配置 `story/train` 仅加载 `data/corpus.jsonl`。审计、排除和覆盖资料放入 metadata 附件；不上传题库、回答或原始快照。新输出路径必须尚不存在：

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B rag/scripts/export_hf_dataset.py build --output rag/data/outputs/hf/release-v2
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B rag/scripts/export_hf_dataset.py verify rag/data/outputs/hf/release-v2
```

发布格式版本为 `rag-full-20260605-v2`，沿用相同语料内容；`train` 是加载分区名，数据卡保留来源与 `license: other` 声明。工具验证白名单、JSONL字段、动态行数和哈希，不上传。配置参考 [Hugging Face 官方文档](https://huggingface.co/docs/hub/datasets-manual-configuration)。

## 数据获取与验证

公开数据入口见[catalog](catalog.json)的 `hf`：`publication_url` 指向已登记的固定版本，`published_revision`、`merged_pull_request` 与 `publication_status` 分别记录 revision、合并 PR 和发布状态；旧布局由 `previous_revision` 定位。`story/train` 只加载剧情语料，审计附件独立存放。

新克隆不含本地 `data/`，须另行提供当前基线原件。重建语料不能恢复模型回答或第三方核验，公开语料也不包含原始快照。

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B rag/scripts/artifact_catalog.py
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B -m unittest discover -s rag/tests -v
```

catalog 检查核对本地基线字节及题库元数据；缺少原件会失败。检索覆盖、API完成、引用合法性、语义支持与用户验收分别判断；程序通过不代表用户逐题通过。离线命令需要已有 Python 3.11。

## Dev Note

无。
