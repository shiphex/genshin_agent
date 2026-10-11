# 原神剧情 RAG：全量 MVP 与历史样本

## 固定剧情评测集 v2 小试

[eval/questions.json](eval/questions.json)已按用户批准的原文优先流程重建为14题 `2.0.0-pilot`：问题、参考答案、要点和证据同时设计。全部已完成独立轻量模型原文复核和程序校验，仍待用户逐题确认；确认后再扩展到核心100题与额外10题跨故事题。旧100题逐字备份在本地实验目录，旧12题历史实验输入及报告保持原样。

字段、配额、限制和离线命令见[题库说明](eval/README.md)，本地[14题复核表](data/eval_rebuild/20261011_pilot_v2/review.md)便于查看问题、答案与核验要点。新入口 `scripts/prepare_eval_cases.py` 负责材料导出、封存复核输入、标注核验、出处范围覆盖和备份安装，不接入旧检索runner。新JSON容器和schema不能直接传给仍读取JSONL的 `evaluate_rag_mvp.py`；语义检索Judge另行实施。本轮84项测试通过。

## 公开审阅与发布资料

[公开审阅入口](reports/README.md)提供24题双组摘要及六题全部条件／种子的关键摘录；新克隆可读错误原句、必要原文和初审，完整上下文／回答仍属于独立审阅资料包。当前全量派生语料发布到[Hugging Face 数据集](https://huggingface.co/datasets/shiphex/genshin_agent_RAG)；版本、哈希、下载校验和审阅包状态见[数据获取](reports/data_access.md)与[发布清单](reports/manifest.json)。

原数据和历史实验继续忽略；只有批准的rag/reports副本进入Git。Hugging Face 只含 `rag-full-20260605-v1` 的四个派生语料文件与清单，不含原始快照、模型回答、审阅 ZIP 或缓存。本文后续data/链接是历史本地产物，取得完整包后可用，不作为公开阅读的必要入口。前期“未调用模型”属于构建历史；当前已运行两轮对照，错误仍未修复，逐题验收待完成。

从项目根目录生成新的 Hugging Face staging（目录必须不存在），再进行本地校验；脚本只使用标准库，不上传或修改源语料：

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/export_hf_dataset.py build --output <新的staging目录>
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/export_hf_dataset.py verify <staging目录>
```

staging 固定包含 `README.md`、`.gitattributes` 与 `data/full/genshin_wiki_data_20260605/` 下的 `corpus.jsonl`、`audit.json`、`exclusions.jsonl`、`coverage.md`、`manifest.json`。Dataset Card 采用 `license: other`：原神及 Wiki 文本不在本仓库获得再许可；只有发布者原创脚本、清单和说明可按 MIT 使用。下载后先校验 manifest；相同冻结快照仍需由使用者另行提供，才能重建或按来源坐标回查。

先维护概要、分析任务及人工选择的excerpts.json（原回答／原字段的零基半开字符位置与哈希），再从项目根运行：

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/export_review_bundle.py views
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/export_review_bundle.py check-views
```

检查测试、薄Git链接和候选文件后，固定本地源码commit，保持工作树干净，生成新的本地输出目录：

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/export_review_bundle.py bundles --output rag/data/publication/review-20261010-v3
```

脚本只使用标准库，无模型／网络调用，不重建语料。两份ZIP使用同一源码commit和bundle_id，保留历史执行runner与当前修正代码；包内bundle_manifest.json记录每个文件的路径、大小、SHA-256，旁置清单、bundle_index.json和SHA256SUMS.txt。批准的数据目录与文件类型形成明确打包清单，排除缓存、环境文件、个人配置和模型权重。

生成时验证整个ZIP并在新目录解压，完整包读取冻结语料与原文坐标，重点包校验publication/selected_source_fields.jsonl的原字段／说话者。旧封存绝对路径原样保留，恢复按项目相对路径定位。完整包不用重建即可复核历史；重点包含两轮完整回答、请求、必要原字段及证据记录，但不含完整快照／语料。v2包及其源码哈希保留为历史，不因Git重写而修改。uv、Python3.11、模型权重及服务另行准备；离线uv命令需要已有解释器。

后续仅登记链接的索引版本可以不同于包内source_commit。实际推送／上传由用户操作，未经未登录下载检查保持pending_upload。校验／解压命令见[数据说明](reports/data_access.md)。


当前数据集为本地快照的全量剧情 MVP，历史 30 片段样本完整保留。两条离线脚本入口与一个全量提取辅助模块均只使用 Python 标准库，通过 uv 运行；没有 Python 应用框架、第三方依赖、数据库、Embedding 或知识图谱。

本次实际运行的结果和具体错误示例见 [实验观察](experiments/mvp/observations.md)。检索成功、模型正常结束与事实正确分别记录。

后续开发请先读 [模块上下文](context.md)。原始爬虫快照位于项目共享的 `data/raw/`；RAG 专属脚本、配置、测试和结果均位于本模块。

2026-10-10已运行本地Qwen4B全量24题模型对照，见[实验说明](experiments/full_validation_20261010/README.md)与[双组回答、出处及逐题初审](data/full_validation/20261010_105700/report.md)。48次正式调用中47次正常结束、1次无检索截断；已发现检索遗漏、身份混淆、错引及机制语料漏项。模型完成状态与用户事实验收分开记录；用户新题尚未收到。后文“本轮未运行模型”等描述属于全量构建阶段，最新验证以此入口和模块上下文为准。

当前已准备 [冻结快照剧情恢复交接任务](experiments/recovery/crawler_handoff.md) 和 [19 页回归清单](experiments/recovery/regression_cases.json)，供爬虫项目的独立 AI 会话实施。用户明确要求本窗口不修改爬虫代码；新解析和恢复导出尚未实现，当前 RAG 数据集未切换。

## 版本控制与恢复运行

最新完成六题四组、48次“证据 × 参数”受控诊断，见[执行说明](experiments/generation_diagnosis/README.md)与[诊断报告及全部回答](data/generation_diagnosis/20261010_145424/report.md)。48次均正常结束；人工原文改善部分要点，但主体／时序等错误仍在，校准参数未稳定修复。默认评测不变，新增独立诊断入口；语义初审仍待用户验收。

`rag/` 默认不跟踪新增内容，显式保留 `scripts/*.py`、`tests/*.py`、README／上下文、实验说明 Markdown，以及 `.gitignore` 中列出的选择清单、题目、无密钥模型配置和恢复回归清单。新增需要版本控制的目录或实验输入时应同步调整忽略规则。

整个 `rag/data/` 只保留本地，包括样本／全量语料、模型原始回答、检索结果、审计／覆盖报告及恢复哈希基线；共享快照、uv 与 Python 缓存同样不提交。忽略不会删除文件。这些本地产物的文档链接在新克隆中可能不可用。

新工作区先提供 `data/raw/genshin_wiki_data_20260605/`，再运行下文的准备和纯检索命令。语料可从同一输入／配置重建，历史模型输出和人工检查需另行备份，重跑评测会产生新结果。不要为提交报告而强制添加大型文件，也不要重跑覆盖已有复核。

## 当前全量数据与运行

已扫描 5,474 个 parsed JSON，生成 22,822 个可回查片段，正文约 596 万字符，JSONL 约 33 MB。3,809 份文件入库、1,496 份部分入库、167 份排除、2 份用作索引元数据；每份文件有独立处理状态。474 份未解析原网页只审计，不恢复 WikiText 或用模型猜测补写。

- [corpus.jsonl](data/full/genshin_wiki_data_20260605/corpus.jsonl)：当前检索语料。
- [coverage.md](data/full/genshin_wiki_data_20260605/coverage.md)：各类覆盖、抽检原文、问题和未解析页面。
- [audit.json](data/full/genshin_wiki_data_20260605/audit.json)：文件逐项状态及统计。
- [exclusions.jsonl](data/full/genshin_wiki_data_20260605/exclusions.jsonl)：2,702 项文件、字段、段落或流程组问题，不是 2,702 个坏文件。
- [纯检索回归报告](data/full/genshin_wiki_data_20260605/retrieval/review.md)：12 题的检索候选与参考证据。
- [全量阶段观察](experiments/full/observations.md)：验证结果及当前局限。

在项目根目录运行：

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/prepare_rag_mvp.py --all
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/evaluate_rag_mvp.py --dataset full --retrieval-only
```

准备的 `--all` 与 `--selection` 互斥。`--raw-root` 可选择其他具有 parsed/pages 的本地快照，`--output-dir` 指定派生目录，`--max-chars` 设置全量目标长度（默认800字符）。全量模式禁止写入共享原始目录、任何可识别的原始快照或历史样本目录。

评测默认 `--dataset full`，必须有全量语料，缺失即报错，不静默回退到 sample。`--dataset sample` 明确选择历史样本；仍支持显式 `--corpus`、`--questions`、`--config`、`--output-dir` 和 `--limit`。纯检索不访问任何模型服务；不加 `--retrieval-only` 才会沿用本地API进行回答对照，本轮没有运行该步骤。

全量模式对任务、角色、书籍、武器、圣遗物、道具、材料、任务道具、怪物、生物、秘境、名片、食物以及编年史／北陆图书馆逐类提取。角色冒险笔记和已确认的神之眼、神之心、月之轮、古龙大权等故事也保留；前端重复／损坏展示区记录但不直接入库。任务索引与分类名单用于审计，分类中未匹配标题可能是系列或模板，不等于缺失任务。

全量片段沿用七字段，并增加 `source_kind` 与 `source_spans`。`source_spans` 与 Pointer 列表一一对应，使用**解码后原字段字符串**的零基半开字符范围 `[start,end)`，不是原文件字节偏移。对白Pointer定位内容或选项字符串，说话者通过同一原行复现。ID由文件、Pointer和范围生成，可在相同输入／配置下稳定重建。

原文只做明确的展示清理：HTML注释、换行、实体、简单Wiki链接及已知展示标签。未知模板、残缺标记、错误说话者／流程标签隔离；CSS页面样式不进入正文。长文按段落、句子和必要的字符位置切分，无重叠；对白只在完整条目间按连续流程分组。目标800字符，单条超长对白或不可拆的显示标记可超过目标，不截断原话。

字段白名单之外还有保守的机制规则，识别百分比属性、元素单位、护甲修复、冷却／无敌帧及明确的怪物机制描述。混合字段若能按自然段分离，保留故事段、隔离机制段并记录范围；不可分的对白或段落整体隔离。规则不等于全库语义审计，剩余资料仍需要人工检查。

`wiki_compilation` 标记编年史和北陆图书馆，`wiki_excerpt` 标记其他Wiki摘录。两者都不自动等同于官方确认事实。检索、报告和模型上下文显示来源性质；原文的“也许”“很可能”不由脚本消除。

检索保持原词面IDF加权匹配，`LexicalIndex` 在每轮评测开始时构建一次内存倒排索引，复用所有查询。开发中可复用该接口：

```python
from rag.scripts.evaluate_rag_mvp import LexicalIndex, load_jsonl

index = LexicalIndex(load_jsonl("rag/data/full/genshin_wiki_data_20260605/corpus.jsonl"))
hits = index.search("钟离如何看待契约与公平？", top_k=5)
```

12 题回归使用 [全量标注草稿](experiments/full/questions.jsonl) 中的原文文件、Pointer和字符锚点映射新ID。当前9道有参考证据的题，6道在Top5找齐全部必要证据，平均证据组覆盖83.3%；3道跨来源题有缺失。q10旧样本资料不足不再被当作全库无答案，q11/q12仅检查过滤策略、未运行模型拒答或自动语义评分。题目、证据粒度和候选规模已变化，不能把本次数字与旧小样本直接视为同一量表。

## 历史 30 片段样本的运行

在仓库根目录执行。需要已安装的 Python 3.11 或更新版本和 uv；缓存、输出留在工作区。以下命令使用已安装的 Python 3.11，离线运行，不下载解释器或依赖。

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/prepare_rag_mvp.py
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/evaluate_rag_mvp.py --dataset sample --retrieval-only
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/evaluate_rag_mvp.py --dataset sample --output-dir rag/data/mvp/model_comparison
```

第三条命令运行 12 题 × 无检索 / RAG，共 24 次本地模型调用。可先加 `--limit 1` 检查服务连接。准备脚本支持 `--raw-root`、`--selection` 和 `--output-dir`；评测脚本支持 `--corpus`、`--questions`、`--config` 和 `--output-dir`，都可用 `--help` 查看。

模型配置在 `rag/experiments/mvp/local_api.json`，默认连接 `http://127.0.0.1:8000/v1`。`model: null` 会从 `/models` 获取唯一模型 ID；如果服务有多个模型，请填写确切 ID。当前使用用户部署的 Qwen3.5-4B GGUF，聊天请求关闭思考输出。`timeout` 是每次 HTTP 请求的秒数，`max_tokens` 控制输出长度。需要服务鉴权时，设置 `api_key_env` 为环境变量名称，并在环境中提供值；配置和结果不保存密钥。服务应已启动；脚本不会启动 Docker、下载模型或修改推理服务。

`0.0.0.0` 是服务监听地址，客户端使用 `127.0.0.1`。服务连接受沙箱限制时，需要让该次本地连接在允许访问服务的环境中运行。`--retrieval-only` 完全不访问模型服务。

## 数据选择与过滤

`rag/experiments/mvp/selection.json` 显式列出 l01–l30 的原文件和 RFC 6901 JSON Pointer。对应专题为“钟离、契约与璃月历史”，覆盖角色、任务、书籍、武器和圣遗物。片段是原字段或同一流程中的连续对话，不包含模型摘要。`source_pointer` 使用列表，允许一个片段引用多个原字段或连续对话条目。JSON Pointer 中的 `/`、`~` 按 `~1`、`~0` 转义。

准备脚本按内容类型执行字段白名单：

| 类别 | 可提取字段 |
| --- | --- |
| 武器 | 名称、介绍、故事 |
| 圣遗物 | 套装名；部件的名称、描述、故事 |
| 角色 | 身份、人物介绍、角色故事、语音、神之眼/神之心故事 |
| 任务 | 标题、章节、流程、描述、对话与选项 |
| 书籍 | 书名、卷名、正文 |

命之座、元素属性、武器类型、数值属性、技能效果、精炼、突破材料、奖励和攻略字段不能通过选择清单进入语料。神之心等 `权能` 故事会保留。角色击败魔物、仙人施展力量等剧情叙述也保留，不能按“攻击”“战斗”“力量”删文。

对白保留原说话者；空说话者和 `？？？` 不由模型补全。选项标为“玩家选项；分支关系未知”，旁白单独标注。拒绝跨任务流程或不连续的对白选择，避免跨场景拼接。

模板、Widget、重定向、同名错任务页、空字段、缺失原页面、未处理的 Wiki 标记和疑似混合强度文本进入 `exclusions.jsonl`。数值/攻略识别只是保守的窄规则，不是完整的语义分类器；仍需人工检查保留字段。确认混合且不能分离的选项可在清单中添加 `exclude_reason`，它会被排除并保留原因。需要截取其他段落时先修改选择并检查 JSON Pointer，不靠 LLM 改写原文。

原始数据不变。输出在 `rag/data/mvp/`，由 `/rag/data/` 忽略规则保护；脚本、选择清单和评测题可纳入版本控制。准备脚本禁止将输出写到原始快照内部。

## 如何读实验结果

`baseline` 是无检索对照组，`rag` 是检索后实验组。`ok` 只表示模型调用正常结束，不表示事实正确。`rag · ok` 后的正文是实验回答，当前还没有最终角色 Agent 的聊天界面。“自然角色回答＋可展开出处”仅为当前候选方向，不是固定产品规则。

样本准备阶段产生 `corpus.jsonl`（仅七个约定字段）和 `exclusions.jsonl`，全量另增加范围、来源性质及审计文件。检索评测产生：

- `results.jsonl`：问题、期望证据、实际 Top 5 原文、检索分数、两组模型回答、耗时和引用 ID 检查。
- `summary.json`：有答案题的证据组覆盖、模型调用成功/失败数。尚未完成的模型或语义评估不会被计作通过。
- `review.md`：原文、出处、参考判断、模型回答及人工检查清单。

问题清单有 4 道事实题、3 道跨来源题、2 道模糊题、1 道资料不足题、2 道强度题。参考判断是根据所选原文人工方式整理的**待用户复核草稿**，不冒充已经获得人工专家验收的金标准。

`expected_evidence` 是证据组列表：每组内为可替代片段，跨来源问题需要覆盖所有组。空列表表示样本不支持作答，检索 Recall 不计分，也不把“找到一个相关片段”当成能回答。模型只收到问题和检索原文，不收到参考答案或证据标注。

检索算法是中文相邻双字与英文词的 IDF 加权重合，分数仅用于排序，没有概率或语义置信度含义。无匹配项返回空列表；不以无关片段凑满五条。它不是 BM25 或语义检索。先检查找不到证据的实际原因，再决定是否升级。

两个回答条件共享系统策略：无检索条件允许已有知识；RAG 条件只使用提供的资料。数据集中的角色观点、书籍传说和未公开筹码不能自动转为事实。引用 ID 存在只证明格式和上下文成员资格，**不证明原文支持结论**；这部分以及无依据断言、强度答案仍需人工检查。RAG 输出强度数值时，还要区分是否来自模型记忆，不能直接断言语料漏进了数值。

重跑会覆盖指定输出目录里的同名文件。保留或另选 `--output-dir`，避免覆盖已完成的人工复核。默认纯检索与模型对照使用不同的输出目录。准备与评测都会拒绝向原始快照写入。

模型 API 失败会保留其他成功的回答并以非零退出码结束；错误响应体和密钥不写入结果。每次响应保存 `finish_reason`、token 使用量及耗时。`length` 表示输出被截断，保留文本但标为 `truncated`，不计入成功调用；非标准结束原因标为 `incomplete`。两者也会产生非零退出码。检查这些状态后再进行语义评估，必要时调整 `max_tokens` 并只重跑相关题目。

引用检查只识别约定的 `[l01]` 格式；例如模型写成 `[片段 ID: l01]` 会记为没有合规引用，仍可在人工报告中看到原始回答。人工检查标记目前按题目保存；在备注中分别记录 baseline / RAG 的判断，避免把无检索时的数值答案混成 RAG 的语料泄漏。

## 检查代码

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python -m unittest discover -s rag/tests -v
```

测试使用临时原始数据和本地 HTTP 测试服务，覆盖字段排除、剧情力量保留、混合文本隔离、来源检查、对白连续性、检索、跨来源覆盖、提示词与 API 接口；不需要真实模型。

这轮不处理防剧透。玩家进度、扩大语料、模型辅助清洗与图谱建设留给下一轮，按实测瓶颈选择。
