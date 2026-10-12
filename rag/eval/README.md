# 剧情评测问题集

## 当前 MVP 开发集

[questions_dev.json](questions_dev.json)是当前工程迭代入口，版本 `0.4`，共99题。原49题的对象及顺序保留；本批新增gq2-044～089、107～110，其中40题以天理、法涅斯、降临者、龙族、天使和原神历史为主要考点，另10题覆盖其他剧情。每题只维护 `id/type/difficulty/question/answer/keywords/criteria/sources`。`criteria` 是扁平评价要点；`keywords` 仅为关键实体／术语提示，命中不代表语义正确，同义表达也不要求逐字匹配。

头信息记录实际创建日期、剧情截止、冻结快照、用户待复核状态、用途和证据／审核约定。`target_core_matrix` 原样沿用v2，`target_cross_story` 保留中等5／困难5，`target_total=110` 表示长期参考配额，不是当前题数；本批按剩余缺口的最大余数法分配50题：核心题中fact 14、causal 14、worldbuilding 9、relationship 9，跨故事中等和困难各2题。读写脚本原样保留这些头信息。

`sources` 可有多条，按文件与Pointer去重，各条共同提供参考依据，不代表找到任意一条就足够，也不穷尽其他有效出处。人工只维护冻结快照下的相对POSIX `file` 和RFC 6901 `pointer`，不手写 `text`。默认快照为 `data/raw/genshin_wiki_data_20260605/`；全部现有来源引用完整字符串字段。参考答案保留人物说法、推论和传说的限定，来源来自冻结Wiki，并非自动获得官方事实认证。

唯一辅助脚本只读取问题集和原文，写出补充 `sources[].text` 的本地副本；不调用模型或评测。项目根目录运行：

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/prepare_eval.py --output rag/data/eval_dev/<新的本地目录>/questions_dev_prepared.json
```

仅有 `--input`、`--raw-root`、`--output` 三个参数；前两项默认使用上述开发集和冻结快照。输出必须是 `rag/data/` 下的新文件，不能覆盖输入、原始目录或已有结果，生成副本继续忽略。更换快照必须重新核对题目依据，不能只沿用旧Pointer。未接通旧JSONL评测runner。

人工重点审核疑难题、存在争议的标准，以及后续迭代发现的新错误或回退；不以全量人工确认作为开发使用门槛。本批50题按冻结原文逐题核对，99题均尚未获用户逐题验收。99题共364条出处均解析为非空原文，准备副本的`text`与快照逐字一致；88项既有RAG测试通过。本批本地准备副本位于`rag/data/eval_dev/20261012_batch05_v0_4/questions_dev_prepared_review_complete.json`，早期修订副本和另一批不同主题的本地草稿均保留且未覆盖。上一批gq2-016原拟引用的《为了青色的身影》在冻结快照中没有对白，实际使用相邻主线《在终曲之前》与《温迪的计划》的对白。

## 保留的冻结原文评测集 v2

以下为v2的结构与历史工具说明，保留作未来benchmark资产；当前暂停继续完善与110题扩展。

[questions.json](questions.json)是从冻结原文同时设计问题、参考答案、要点和证据的v2题库。保留版本为 `2.0.1-pilot`，共14题，待用户逐题复核；原规划为110题，当前暂停扩展。旧题核验认可不自动继承，本题库尚未运行检索Judge或被评测模型。

## 结构与配额

| 核心类型 | 简单 | 中等 | 困难 | 合计 |
| --- | ---: | ---: | ---: | ---: |
| fact 事实查询 | 15 | 10 | 5 | 30 |
| causal 故事因果 | 8 | 12 | 10 | 30 |
| worldbuilding 世界观推理 | 2 | 7 | 11 | 20 |
| relationship 人物关系 | 5 | 11 | 4 | 20 |
| 合计 | 30 | 40 | 30 | 100 |

另有 `group=cross_story` 的10题：中等5题、困难5题，仍标注上述主要类型。首批四类型各含简单、中等、困难各一题，另加中等、困难跨故事题各一题。核心完整集有10题前提纠正或不确定性辨析；同一 `story_topic` 最多6题。难度根据证据跨度、推理和叙述辨析判断，冷门名称不等于困难；标签与难度仍需用户复核。

## 标注语义

- `reference_answer` 是合格回答示例，不要求逐字复述，也不是凭模型记忆补全的百科答案。
- `key_points` 用稳定ID记录必须覆盖的事实 (`fact`)、推理 (`inference`) 和限定 (`qualification`)，通过 `evidence_ids` 引用依据。允许有依据的不同表达和论证路径；本阶段没有评分权重。
- `evidence` 固定需要支持的原子语义事实。每项 `sources` 是已核验的一组出处，多段可以共同支撑，不是“找到任意一句就成功”，也不穷尽所有等价来源。
- 来源坐标为冻结快照下的相对POSIX路径、RFC 6901 Pointer和Python Unicode码点的零基半开区间 `[start,end)`；`quote`、文件SHA-256和说话者由程序提取。
- `wiki_excerpt` 表示冻结Wiki摘录，`wiki_compilation` 表示Wiki编纂；它们都不是官方真伪认证。人物判断、传说、未知说话者与分支限制须在命题和答案里保留。
- `annotation_status=source_reviewed` 表示独立模型原文复核和程序校验已完成；`user_review=not_reviewed` 表示尚未获得用户逐题确认，两者不能替代。

## 出处覆盖与未来检索评分

`corpus_anchor_coverage` 检查已标注原文中的实质文字是否保留在指定派生语料中。先回查相关chunk正文与原字段重建一致，再合并相同文件／Pointer的范围，因此相邻或重叠chunk可以共同覆盖一个出处。忽略纯空白缺口（换行、空格、制表符及Unicode空白）；实质文字部分覆盖记为partial，完全未覆盖记为missing。修改chunk ID不改变结果。

此检查不执行检索，不判断替代来源，不验证语义推理。它不是检索召回率、答案正确率或完整可答性；complete只表示所标注出处都保留，partial/missing不表示整个语料无法作答。覆盖字段是可重算的派生观察，不要求未来RAG命中这些原位置。

题库每题只保留 `status`、`covered_anchors`、`total_anchors` 三字段摘要，不嵌入缺口区间、空白标志或方法说明。真实缺失文字的原句、坐标、文件及Pointer写入独立本地 `coverage_report.json`，纯空白不产生记录。2.0.1-pilot的14题／71处出处均为complete，仍不表示语义检索通过。

版本变化：2.0.0-pilot采用严格字符范围口径，将两题的段间换行标为partial；2.0.1-pilot忽略纯空白并精简摘要。问题、参考答案、要点、证据和用户复核状态未变。旧题库与报告保留原样，旧partial不能按新口径解读为剧情缺失。

未来语义检索Judge将使用问题、语义事实和本轮检索文本，另外记录“证据ID→本轮chunk／原句”的支持关系。题库没有必须命中的chunk ID。换原始快照时必须重新验证出处／哈希，不能沿用旧Pointer冒充新证据。

## 离线工具

在项目根目录，通过uv运行，默认读取2026-06-05冻结快照和当前全量语料：

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/prepare_eval_cases.py validate --questions rag/eval/questions.json --mode pilot
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/prepare_eval_cases.py coverage --questions rag/eval/questions.json --output-dir rag/data/eval_coverage_compact/20261012_v2_0_1/new_coverage
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python -m unittest discover -s rag/tests
```

工具还提供 `materials`、`review-input`、`build`、`install`，分别导出原字段、封存独立复核输入、组装正式出处并接入复核、备份后替换正式题库。build同时生成独立覆盖报告，coverage可对正式题库另生成新报告；报告记录题库与语料SHA-256，仅含实质缺失的详细位置。各入口可用 `--help` 查看。材料选择格式是 `{"materials":[{"id":"S01","source_file":"parsed/...json","source_pointer":"/字段"}]}`，可选start/end；模型只引用编号，不手抄quote或hash。

生成草稿含questions与materials，evidence.sources暂用 `{"material_id":"S01"}`。独立复核封存输入只含当前问题与实际原文；不提供生成者自评。review JSON记录input_sha256、model、reasoning_effort及逐题passed/needs_revision与issues；哈希绑定问答、原文切片与源文件字节。缺题、重复、旧稿复核或critical/important未修问题不能升级为source_reviewed，未知severity也拒绝。

所有导出／备份目录必须是 `rag/data/` 内的新目录，拒绝原始目录及已有目录。`install`仅能替换 `rag/eval/questions.json`，先逐字备份旧文件并校验哈希，再安装经验证的候选文件。该工具不调用模型、不改检索、不上传数据。

## 复核与版本维护

v2原规划为先由用户逐题复核14题，再修订并扩展剩余96题；该扩展目前暂停，不作为MVP开发集的使用门槛。未来恢复benchmark工作时再确认复核安排。模型生成、独立复核与用户反馈分别留档，未逐题确认者不记为用户通过。

旧100题及各轮草稿、完整原文材料、复核原始输出和保护哈希保存在本地 `rag/data/eval_rebuild/20261011_pilot_v2/`，继续忽略；原12题历史实验输入与报告保持原样。本地记录需要独立备份，不能靠Git或重建语料恢复。程序检查不保证全部语义判断正确。

2.0.1覆盖摘要迁移的逐字备份、语义内容不变检查和覆盖报告保存于本地 `rag/data/eval_coverage_compact/20261012_v2_0_1/`。本轮未调用模型重标注。

本题库是公开开发评测集，问题、答案与标注不作为训练样本；最终泛化评测另设留出集。修订必须记录版本与变化，扩展保留已有题号，跨版本比较使用未变题目。
