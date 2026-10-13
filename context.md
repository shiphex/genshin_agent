# 项目上下文

更新：2026-10-13。此文件为开发导航，不是剧情事实来源。

项目目标为主角／派蒙身份的原神剧情分析讨论Agent。当前处于RAG全量实验、错误诊断和审阅发布准备阶段；角色Agent、界面、玩家进度分析和防剧透尚未实现。约定见 [AGENTS.md](AGENTS.md)。

## 当前阶段与入口

- [MVP开发问题集](rag/eval/questions_dev.json)：当前0.5，共110题，原定100道核心题和10道跨故事题的类型／难度配额已填满。本批新增gq2-090～100，继续选取天理、龙族、天使及历史相关的独立考点；旧99题对象与相对顺序保留。八字段与2026-06-05冻结快照不变，[原文准备脚本](rag/scripts/prepare_eval.py)生成的副本仅本地保留。全部110题仍待用户逐题复核；未接通评测运行或自动评分；[说明](rag/eval/README.md)。
- [开发题随机抽样](rag/experiments/dev_question_sample_20261013/selected_questions.md)：从0.5版110题中不放回抽取20题，按每批5题保存题号、题目和原参考答案，供复制给第三方核验；抽样不代表答案已通过复核。
- [剧情评测集v2](rag/eval/questions.json)：2.0.1-pilot原样保留为未来benchmark资产，暂停完善和110题扩展。首批14题已完成独立模型复核与程序校验，仍待用户逐题确认；历史数据与报告保持完整。
- [公开审阅入口](rag/reports/README.md)：24题双组及六题全部条件／种子的精简诊断，只放关键原句、必要原文和初审；完整记录在云盘包；六题为前轮子集。
- [24题结果](rag/reports/full_validation_20261010_105700/summary.md)：48次正式调用中47stop、1length；旧题Top5找齐6/9、新题0/10，参考不穷尽，不能代表答案正确率。
- [六题诊断](rag/reports/generation_diagnosis_20261010_145424/summary.md)：48次stop；人工原文改善部分答案，仍有身份、主体、比例和时序误读，校准参数未稳定修复。未证明量化／运行时故障或4B永久能力上限。
- [RAG说明](rag/README.md)和[模块上下文](rag/context.md)：具体实现、原文验证、历史与未解决问题。当前冻结语料22,822片段，未切换数据、重建语料或修改检索。
- [Hugging Face RAG语料集](https://huggingface.co/datasets/shiphex/genshin_agent_RAG)：`rag-full-20260605-v1` 的四个派生语料文件已公开；许可、哈希、revision与匿名下载校验见[数据获取](rag/reports/data_access.md)。
- [数据与发布步骤](rag/reports/data_access.md)：重点分析包和完整复现包由uv标准库脚本生成，同一bundle_id／源码commit。审阅包的GitHub／Drive地址仍待登记、pending_upload；包源码版本与后续链接索引分别记录。

用户认为前轮错误“极其多”，这是总体反馈，不等于逐题验收。全部初审仍待用户确认；独立用户题目尚未收到。

2026-10-12 MVP开发集Git收尾：用户已授权将开发集、唯一读写脚本及相关说明提交并推送至当前 `feat/story-eval-v2-pilot` 分支。收尾重新核对14题／63条来源及原v2不变，88项既有测试通过；实际提交与远端状态以Git记录为准。

2026-10-12 Git收尾：用户明确授权将当前评测集v2试点改动创建新分支、提交并推送；分支名为 `feat/story-eval-v2-pilot`。本轮重新运行84项测试及14题／71处出处校验通过，用户逐题验收仍待完成。此次授权不涉及云盘上传。

2026-10-12 覆盖摘要收尾：用户随后授权提交并推送2.0.1-pilot精简改动，沿用 `feat/story-eval-v2-pilot` 分支；重新验证88项测试及14题／71处出处通过。具体提交与远端状态以Git记录为准，完整本地诊断及备份继续忽略。

## Hugging Face 语料发布（2026-10-10）

用户批准先发布当前全量派生 RAG 语料，不发布 `rag/data/` 整体、原始快照、模型回答、审阅 ZIP、Git bundle或缓存。新增 `rag/scripts/export_hf_dataset.py` 只从 `rag/data/full/genshin_wiki_data_20260605/` 导出四个批准文件、manifest、Dataset Card和LFS规则；它不上传、不会修改源数据。实际 staging 已验证22,822条记录和全部哈希，64项 RAG 测试通过。

Dataset Card 标为 `license: other`，不将原神或 Wiki 文本宣称为 MIT；MIT 仅适用于发布者原创的脚本、清单和说明。目标数据集已 **available**：远端 revision 为 `592d198a9cde390005323a9f849c0d3981fb5a33`，已从该公开 revision 进行未登录 HTTP 下载并重算哈希、解析 JSONL、确认22,822条记录与LFS对象可访问。完整审阅包的 Google Drive 策略不变，继续独立于语料集。

## 工作边界

原快照、语料和历史实验保持完整。Git继续忽略大数据，只批准rag/reports中的可追溯发布副本作为例外；历史输出需独立资料包备份。发布检查原回答、哈希、薄Git链接与ZIP恢复，不调用模型。

爬虫修复通过 [交接任务](rag/experiments/recovery/crawler_handoff.md) 交给独立会话；本项目未改其代码，新版接入另行安排。

候选下一步为短原句抽取及主体／时间／不确定性保持，然后做更强模型或运行时对照、实体／多来源检索。角色口吻与可展开出处是后续设计倾向；当前词面索引、无数据库／Embedding是MVP选择，不是永久要求。

v2资料包已完成恢复验证，保留其原始源码哈希和ZIP，不重写。本轮在970c114后合并发布历史，生成对应新源码的v3包；旧完整报告由本地Git bundle与v2包保留，旧提交不要求在公开仓库可访问。初步精简验证覆盖30页、96份回答，原数据不变。交付与状态见[数据获取](rag/reports/data_access.md)。

本轮已验证：以970c114为边界的发布源码合并提交为569175ff73fb3ef9a9f206a9308b627240e44a06；旧完整报告／清单33个blob不再被根仓库分支或标签引用，内部Codex引用和reflog保留未gc。30页110953字节，96份回答均有精确摘录，60项测试通过；11,536个保护文件及21个源码／输入blob未变。v3两包和新Git克隆校验通过，完整包可读22,822片段。最终分享仍pending_upload，版本及哈希见[数据获取](rag/reports/data_access.md)。
