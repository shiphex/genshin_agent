# 项目上下文

更新：2026-10-14。本文件是项目导航；开发约定见 [AGENTS.md](AGENTS.md)。

项目目标是以主角／派蒙身份参与原神剧情分析、解读与讨论的 Agent。当前集中于 RAG 实验、错误诊断与评测资产维护；角色 Agent、界面、玩家进度分析和防剧透尚未实现。

## 当前入口

- [RAG 使用说明](rag/README.md)与[模块上下文](rag/context.md)：实现、运行方式、验证结果和未解决问题。
- [资料统一索引](rag/catalog.json)与[管理规则](rag/docs/artifacts.md)：稳定用途名称、题库版本、独立运行／复核编号，以及历史ID映射。日期只作为元数据或旧封存坐标。
- 本地 `rag/data/readme.md` 说明数据目录的用途、八类结构和保留边界；随整个数据目录忽略，新克隆参考[本地产物管理](rag/docs/data.md)。
- [开发题库](rag/eval/questions_dev.json)：0.5 版、110 题；原定 100 道核心题和 10 道跨故事题的配额已填满。原文准备使用 `rag/scripts/prepare_eval.py`，尚未接通评测 runner 或自动评分；全部题目仍待用户逐题验收。
- [保留的 v2 题库](rag/eval/questions.json)：2.0.1-pilot、14 题，作为未来 benchmark 资产，暂停扩展；独立模型复核和程序校验不等于用户验收。[题库说明](rag/eval/README.md)。
- [开发题随机抽样](rag/eval/reviews/dev_sample/r001/selected_questions.json)与[第三方复核摘要](rag/eval/reviews/dev_sample/r001/result_by_deepseek_summary.md)：20 题核验材料；摘要已记录四组初审，完整第三方结果仅本地保存，仍待用户确认。
- [公开审阅入口](rag/reports/README.md)：24 题模型对照及其中六题的受控诊断；API 完成、引用合法性、检索覆盖和语义正确性分别报告。
- [数据获取与发布状态](rag/reports/data_access.md)：已登记的语料发布版本和审阅包状态；实际 GitHub 推送和云盘上传由用户操作。
- [历史记录](rag/docs/history/development_20261013.md)与[本地归档说明](rag/docs/archives.md)：旧开发阶段、过程资料的位置与恢复方法。

## 当前工作边界

冻结快照为 `data/raw/genshin_wiki_data_20260605/`；当前派生语料为 22,822 片段。原文、Wiki 整理／推测和模型生成内容须可区分，保留来源。当前词面索引、无数据库／Embedding 是 MVP 选择，不是永久要求。

用户认为前轮模型错误“极其多”，属于总体反馈；不能登记为逐题评分。当前仍有检索遗漏、主体／时序误读、错引和机制文本漏项。候选下一步为短原句抽取及限定保持、实体／多来源检索、更强模型或运行时对照，尚未实施。

本窗口不修改爬虫代码；恢复任务通过[交接说明](rag/docs/recovery/crawler_handoff.md)交给爬虫项目独立会话，新版数据接入另行安排。

2026-10-13 按用户批准方案完成本地资料整理：重复解压副本与缓存清除，旧题库制作／迁移／发布检查过程已核验归档；正式语料、题库、模型结果、第三方复核、已有发布 ZIP 和历史 Git bundle 保持原路径。详细保护哈希、归档清单和验收记录只保留本地；Git 继续忽略这些资料。

随后按用户确认将必要资料继续保留 Git 并按用途归位：共享配置在 `rag/config/`，开发历史和恢复交接在 `rag/docs/`，开发题复核在 `rag/eval/reviews/`，摘录输入在 `rag/reports/inputs/`。[实验索引](rag/experiments/README.md)与[文档索引](rag/docs/README.md)为新增导航；第三方原始复核JSON仍仅本地保存。数据语义与历史发布包不变。

用户随后批准统一身份管理：新增catalog及标准库辅助脚本，实验输入按用途命名，题库复核与报告按用途／rNNN组织；两个执行入口分配新编号和独立本地目录，拒绝已有输出。原始快照、旧运行结果和ZIP保持原样，日期旧ID通过catalog映射；执行、发布和用户验收状态分开维护。本轮只运行纯检索验证，没有调用真实模型。

随后批准本地产物管理：`rag/data/` 按八类归位，[规则与入口](rag/docs/data.md)由catalog管理。语料、准备副本、运行、复核、发布、基线与任务归档分开；封存正文及ZIP不重写，旧地址通过索引读取。生成入口采用新版本／编号，完成才切换当前指针；完整第三方原件移入data，Git只保留输入和摘要。

2026-10-14 按用户要求运行 RAG 纯检索 Smoke Test：全量语料前 3 题均成功返回 Top5，结果登记为本地 `full_retrieval/r005`；未调用模型，语义状态仍待人工复核。详见 [RAG 模块上下文](rag/context.md)。

同日使用本地 `Qwen3.5-4B-Q4_K_M.gguf`、llama.cpp b9837 和 RTX 4060 Vulkan 后端完成完整链路 Smoke Test，登记为 `model_comparison/r002`：q01–q03 的六次正式调用均正常结束，三题预期证据组全部覆盖。Codex 对冻结原文初审发现无检索回答错误，以及 RAG 扩写主体错置、错引和引用格式问题；技术通过不表示语义或用户验收通过。结果与复核依据仅本地保存，入口见 [RAG 模块上下文](rag/context.md)。

随后按用户要求将本次已确认的 Smoke 方案整理保存为[方案 v1](rag/experiments/model_comparison/smoke_qwen35_q4_v1.md)，保留原方案正文并关联执行清单、参数、输入哈希及本地核验材料；明确为运行后保存，不冒充执行前封存。
