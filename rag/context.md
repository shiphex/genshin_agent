---
kind: context
description: "记录 RAG 当前问题与验证边界，保留既有历史上下文原文。"
---
# RAG 开发上下文

## 摘要

更新：2026-10-16。当前操作入口见 [README](README.md)，资料定位由 [catalog](catalog.json)维护。下面的历史保留区完整保留此前正文；新工作只更新当前状态，不追加过程流水账。

## 目录

- [当前状态与遗留问题](#当前状态与遗留问题)
- [历史保留区](#历史保留区)

## 当前状态与遗留问题

当前仍聚焦检索遗漏、生成忠实性和独立语义复核；程序验证不替代用户逐题验收。文档体系现将模块命令、当前问题、实验执行和历史分别维护，详见[文档规范](../docs/AGENTS.md)。

已核对的遗留冲突：开发题 skill 的“准备副本与验收”仍指定 rag/data/eval_dev/，而 prepare_eval.py 调用 artifact_catalog.reserve_prepared，后者的 output_namespace 只允许 prepared 或新 tmp 任务。原 skill 本轮未修改；下次开发题任务须先对照[现行产物规则](docs/data.md)。

本轮既有 101 项 RAG 测试、catalog 与精确摘录检查通过；文档及 skill 核验见[Agent Note](../.agents/notes/implemented/2026-10-16-ai-native-documentation.md#验证)。未生成 RAG 产物或改变用户验收状态。

## 历史保留区

以下为截至 2026-10-14 的既有正文，按原阶段理解测试数量、状态与时间词。本轮不重新判定其历史实验或用户验收。

更新：2026-10-14。本文件记录当前实现、事实、用户反馈和未解决问题。运行命令见 [README](README.md)，旧阶段详记见[开发历史](docs/history/development_20261013.md)。

## 当前实现与入口

资料身份以[catalog](catalog.json)为准，命名、版本、运行和保留规则见[管理说明](docs/artifacts.md)。实验定义用稳定用途名称；当前题库复核与报告用独立rNNN编号。原始快照和封存结果日期是历史坐标，不改写。

- 当前冻结快照：项目共享 `data/raw/genshin_wiki_data_20260605/`；当前语料：`data/corpora/story_full/v1/`，22,822 个片段。历史构建扫描 5,474 个 parsed 文件，正文约 596 万字符。474 份仅原网页资料只审计，不凭模型猜测补写。
- `scripts/prepare_rag_mvp.py` 是语料准备入口，`scripts/full_corpus.py` 实现全量提取、过滤、切块和审计。语料有文件／Pointer／字符范围及来源性质，可回查冻结原字段。
- `scripts/evaluate_rag_mvp.py` 实现词面 IDF 检索和无检索／RAG 模型对照；内存倒排索引每轮构建一次，默认 full、Top5。当前没有向量检索、数据库、图谱或应用框架；这些是 MVP 选择。
- `scripts/diagnose_rag_generation.py` 是证据与采样配置诊断入口；正式评测默认行为独立保留。
- `scripts/prepare_eval.py` 为开发集读取原文，`scripts/prepare_eval_cases.py` 保留 v2 材料／复核／出处覆盖流程。两者不调用模型或评分。
- `scripts/export_review_bundle.py`、`scripts/export_hf_dataset.py` 负责本地导出与校验，不上传。公开审阅入口在 [reports](reports/README.md)。

原文范围是解码后字符串的零基半开区间 `[start,end)`，不是文件字节偏移。对白保留说话者和不确定分支；人物说法、传说、Wiki 编纂与模型生成不得相互替代。剧情力量描述保留，机制数值／攻略排除规则仍有已知漏项。

## 当前题库与复核

[开发集](eval/questions_dev.json)版本 0.5、110 题，配额为 100 道核心题和 10 道跨故事题；每题维护八字段，445 条出处来自冻结原字段。当前[最终原文副本](data/prepared/story_dev/v0.5/r001/questions.json)保留。来源一致性属于前轮程序与原文核对结果；全部题目仍待用户逐题确认，未接通 JSONL runner 或自动评分。

[v2 题库](eval/questions.json)版本 2.0.1-pilot、14 题，暂停扩展。前轮验证 71 处来源锚点在忽略空白的口径下全部 complete；出处覆盖不是检索召回、可答性或答案评分。独立模型复核、程序校验和用户验收分别记录，用户状态仍 not_reviewed。[历史复核表](data/reviews/benchmark_source/r001/review.md)保留 2.0.0 的旧覆盖口径。

[随机抽样输入](eval/reviews/dev_sample/r001/selected_questions.json)保留从开发集抽出的20题和顺序；[第三方摘要](eval/reviews/dev_sample/r001/result_by_deepseek_summary.md)记录四组初审。完整原件现在位于 `data/reviews/dev_sample/r001/result_by_deepseek.json`，字节不变，继续忽略；摘要和输入留Git。86/86指针一致和20题初判正确属于第三方报告，不是本轮重新语义核验或用户通过。

## 历史模型实验与已知问题

正式记录按索引搬移，内嵌旧路径和字节保持不变；逐题初审尚待用户验收：

- 24 题对照位于 `data/runs/model_comparison/r001/`。48 次正式调用为 47 stop、1 length；连接检查和截断重试另计。旧题 Top5 找齐 6/9、新题 0/10；参考不穷尽等价来源，不能解释为答案正确率。
- 六题受控诊断位于 `data/runs/generation_diagnosis/r001/`。六题是前轮子集，48 次均 stop；人工原文改善部分要点，主体、时序和比例等错误仍在，采样校准没有稳定修复。
- 30 片段历史样本保留在 `data/corpora/story_sample/v1/`，两轮模型结果位于 `data/runs/sample_model_comparison/r001/` 与 `r002/`。旧测试数量、样本检索指标和“未调用模型”等措辞只适用于各自阶段。

已确认问题包括真／影／人偶身份混淆、世界树事件时序混合、人物说法被事实化、错引与不合规引用；机制／操作文本仍有漏项。检索覆盖、API 结束、引用成员资格与语义支持必须分别验证。

用户认为前轮错误“极其多”，属于总体反馈，不替代逐题评分。独立用户题目尚未收到。未证明量化／运行时故障或 4B 的永久能力上限。候选改进为短原句抽取与主体／时间／不确定性保持、实体／多来源检索、更强模型或运行时对照，尚未实施。

## 数据、发布和恢复边界

原始快照、正式语料、模型回答、人工复核与哈希资料只保留本地，Git 不承担备份。当前公开语料版本与审阅包状态见[数据获取](reports/data_access.md)；该页保留已验证的历史发布事实，实际上传另行操作。

v1／v2／v3 审阅 ZIP、旁置清单及 `data/archive/git_history/r001/precompact-cc17b40.bundle` 保留。六个重复解压验证目录和旧 bundle 的恢复检查仓库已清除，按新目录恢复；包内源码 commit 不随当前文档整理改写。

爬虫恢复任务见[交接说明](docs/recovery/crawler_handoff.md)。本窗口不修改爬虫代码，不接入新数据；新版恢复导出和验收完成后另行安排。

## 本地资料整理（2026-10-13）

用户批准清除重复副本、归档历史过程并精简文档。旧标注预览、v2 制作、覆盖迁移、开发题过程、发布检查共 396 个文件已分别存入五个 ZIP；整理前五份文档另存备份 ZIP。归档保留原项目相对路径、逐文件大小和 SHA-256，并已在新目录实际解压读取验证。[归档索引与恢复说明](docs/archives.md)。

移除六个发布展开副本前，重新核验 ZIP 和 35,196 个展开文件的内容一致性；历史 bundle 的哈希、独立 bare 克隆、fsck、对象与引用覆盖均通过。正式语料、题库、实现、模型结果和第三方复核共 11,616 个保护文件的工作前后哈希一致；本地验收结果位于 `data/archive/housekeeping/r001/verification.json`。

上述清理验收：88 项既有测试通过，30 个公开案例／96 份回答的精确摘录校验通过；文档链接和 UTF-8 编码检查通过。完整结果见本地 `data/archive/housekeeping/r001/checks.json`。该轮没有修改正式实现或实验输入、调用真实模型或重建语料。

## 目录归位（2026-10-13）

用户确认必要资料继续进入 Git，并按用途归位；没有独立用途的内容可删除。12个文件归入共享 `config/`、开发 `docs/`、`eval/reviews/dev_sample/r001/` 和 `reports/inputs/`。旧MVP实现／观察、全量观察仍有历史信息价值，保留 Git；只删除搬移后的空目录。

`experiments/` 保留四类实验的复现输入与执行说明，[实验索引](experiments/README.md)说明默认输入与历史状态；开发记录见[文档索引](docs/README.md)。30个报告案例和两份概要保持原路径及原字节，摘录输入移至 `reports/inputs/excerpts_v3.json`。共享配置的两个CLI默认路径和源码打包白名单已同步调整，报告清单随路径和入口文档更新。

完整第三方复核JSON已随抽样资料搬到 `eval/reviews/dev_sample/r001/`，原字节保留且继续忽略；题库与用户待验收状态不变。已有 ZIP、归档和原始模型封存记录不重写，本轮不生成新发布包。工作前快照、搬移映射、保护哈希及本轮验收保存在本地 `data/archive/housekeeping/r002/`，不提交。

本轮验收：11,603个保护文件按搬移映射核对哈希一致；88项既有测试、243个本地文档链接、30个案例／96份精确摘录校验通过。新配置路径的一题纯检索CLI读取通过，模型调用为0；发布清单的16项来源哈希、案例矩阵、包版本和待验收状态保持一致，仅更新路径与入口文档哈希。Git规则允许必要新路径，完整第三方输出及本地工作记录继续忽略。临时检索输出已在保留验收摘要后清除，未提交或推送。

## 资料标识与运行管理

用户批准用途名称＋独立编号＋统一索引。`catalog.json` 登记题库版本、四类实验定义、已知历史运行、复核批次及旧ID映射；`scripts/artifact_catalog.py` 提供定位、目录与编号预留、输入指纹、状态登记和索引检查。冻结定义可复跑，retired定义不分配新运行。

`evaluate_rag_mvp.py` 与 `diagnose_rag_generation.py` 默认将新执行登记到 `data/runs/<实验ID>/rNNN/`；显式输出也须是 `rag/data/` 下的新目录。并发分配有锁，已有目录和失败／中断编号不复用；执行完成不升级用户验收或发布状态。运行清单保存实际输入／配置／源码SHA、Gitcommit及source_dirty标记，不复制鉴权值。诊断模型结果在新运行的 `model/` 子目录。

现有复核改为 `eval/reviews/dev_sample/r001/`，报告改为 `reports/model_comparison/r001/`、`reports/generation_diagnosis/r001/`；旧日期ID仍用于冻结摘录和请求矩阵验证，导出通过catalog解析报告位置。发布副本manifest的schema升级为3并分别记录用途ID、运行ID和legacy_id；已有包的版本、源码commit及内容不变，旧包恢复继续兼容原布局。

本轮新增8项行为测试覆盖并发、目录防覆盖、失败／中断占号、鉴权内容隔离、旧ID歧义／越界和历史包布局兼容，先失败再通过；与既有88项合计96项回归通过。实际默认CLI纯检索验证登记为 `full_retrieval/r002`，只运行q01、模型调用0，不代表全题集效果或语义验收。本轮工作前备份、映射及保护哈希只保存在 `data/archive/housekeeping/r003/`，没有提交或推送。

## 本地产物管理

本地目录入口为 `data/readme.md`，说明八类结构、典型资料、索引定位及保留／恢复边界；该文件随整个data目录忽略，Git中的规则仍见[管理说明](docs/data.md)。本次仅补充目录说明，核对UTF-8编码与README本地链接，不生成或改动数据产物。

用户批准data按corpora、prepared、runs、reviews、releases、baselines、archive、tmp管理。[管理说明](docs/data.md)。语料和检索分开，样本模型两轮单独登记sample_model_comparison/r001、r002，首次API结束原因未知的限定保留；benchmark_source/r001表继续使用2.0.0旧覆盖口径。

catalog扩展固定语料版本、prepared、发布包、基线、归档和旧路径映射。默认读取当前索引位置，历史报告及Hugging Face旧发布绑定全量v1；未知／改动的封存输入不被静默接受，必要时按原哈希读取已有ZIP中的执行输入。

新语料构建自动分配vN，新原文准备按输入版本分配rNNN；成功才切换对应入口，失败保留编号和当前版本。显式输出限对应类别或新tmp任务，已有产物及嵌套写入拒绝。输入问答和text之外的头信息保持透传，不新增语义评分。

42个过程文件归入audit.zip并实际解压核验，实际执行work.py和runner_executed.py留在运行组；全部原件用旧／新坐标及归档成员核对，封存JSON、包和bundle字节不变。旧三轮整理过程收拢housekeeping/r001～r003，当前任务关闭后归入r004。

实际生成验证为story_dev/v0.5/r002（110题／445处出处）和full_retrieval/r003（一题纯检索，模型调用0），均登记清单；未重建用户语料、调用真实模型或改变待验收状态。目录、旧输入、生成覆盖／当前指针与历史包兼容的测试，以及最终保护核验结果保存在本地housekeeping/r004中。

最终验收：101项测试、264个本地链接、96份精确摘录通过；11,590个原始／历史文件按新位置或audit成员核对字节一致。42个过程文件实际归档恢复核验通过，30个案例文件不变，19个原发布文件哈希一致。新准备副本与导入副本内容完全一致；最终纯检索验证为full_retrieval/r004（仅q01、模型调用0），清单中2份实际源码副本与执行指纹一致，已测试拒绝覆盖。旧v3重点包恢复及5项封存执行输入哈希核验通过，临时解压树和旧空目录已清除。

前序验收记录：11,587个原始／历史／输入保护文件按映射核对哈希一致；256个本地文档链接通过，30个案例正文逐行一致（仅导航链接改变），96份精确回答摘录通过。实际拒绝覆盖 `full_retrieval/r002`，其文件与catalog均未改变。85个现有Git候选与源码打包白名单一致，补齐已跟踪的eval资产及开发题技能说明；完整第三方原件和新运行结果继续忽略。旧v3重点ZIP在新目录实际解压与复核通过，原ZIP哈希／源码commit不变，临时展开目录已清除。

用户随后明确要求提交并推送当前修改。提交前重新运行101项测试和公开审阅校验（30个案例／96份精确摘录），均通过；本地产物及data/readme.md继续忽略。

## 纯检索 Smoke Test（2026-10-14）

按用户要求通过 `uv` 运行 `evaluate_rag_mvp.py --dataset full --retrieval-only --limit 3`。运行登记为本地 `data/runs/full_retrieval/r005/`：读取全量语料前 3 题（q01–q03），每题返回 Top5；生成 `results.jsonl`、`summary.json`、`review.md` 和 `run_manifest.json`。索引构建 1.657 秒，检索合计 0.031 秒；3/3 题找到全部预期证据组（平均覆盖 1.0）。模型调用为 0，模型答案字段为空；语义质量仍为 `pending_human_review`，不代表答案正确性。

## Qwen3.5-4B Q4 完整链路 Smoke Test（2026-10-14）

用户批准沿用旧 q01–q03、现有语料／检索／提示词完成六次正式模型调用与逐题初审，不接入开发题库、不作 Q4／Q6 受控比较。通过 uv 执行现有 `evaluate_rag_mvp.py --dataset full --limit 3`，登记为本地 `model_comparison/r002`；[初审报告](data/runs/model_comparison/r002/smoke_review.md)、[结构化初审](data/runs/model_comparison/r002/semantic_review.json)和[验证结果](data/runs/model_comparison/r002/verification.json)仅本地保存。

运行完成后，按用户要求另存[已确认方案 v1](experiments/model_comparison/smoke_qwen35_q4_v1.md)，保留方案正文并将实际执行与核验入口单列，附输入／模型哈希和已知记录限制；该文档可随 Git 保存，后续修订另建版本，不改写本次运行清单或产物哈希。

实测运行环境为 llama.cpp b9837（b3fed31b9）、RTX 4060 / Vulkan0、单槽位、8192 上下文、关闭思考及上下文移位，纯文本不加载 mmproj。GGUF 位于用户提供的 D 盘目录下冻结下载快照，SHA-256 为 `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`；完整路径、启动参数、日志、预检请求／响应及实际辅助脚本保存在运行组的 `runtime_evidence/`。GPU 使用由设备列表、显式启动参数、进程及显存／利用率观测佐证；默认日志没有逐层分配明细。

模型身份、健康检查和独立短回答预检通过，预检调用另计 1 次。六份正式提示词经服务模板／分词接口核对；三题 RAG 输入分别为 2559、2615、2616 tokens，与正式 usage 一致，加上 1536 输出预算后均有至少 4040 tokens 余量。沿用 Top5、温度 0、seed 42、超时 180 秒，未调整参数或重跑。六次正式调用均有正文且 `finish_reason=stop`，错误／截断／其他未完成均为 0；单次耗时 3.453～19.625 秒，三题预期证据组全部覆盖，平均覆盖 1.0。

Codex 对冻结原文的初审发现：三题无检索答案均含错误；q01 RAG 核心命名关系有依据，但神之心扩写主体错置、额外关联缺少支持且未保留 Wiki 编纂性质限定；q02 RAG 答对领取者与交易双方，但加入无本次输入支持的英文别名，并将对话114的领取台词错引为从对话119开始的相邻片段；q03 RAG 保留书中记载并答对命名过程，但使用 `[片段 ID: ...]` 格式，现有审计未识别引用，也未逐项标注。q01／q02 的引用 ID 均合法，不能据此判断引文归属或语义支持；本次六份回答未观察到数值强度、培养、配队或攻略泄漏。精确错误原句、冻结字段／Pointer／字符范围和原文件哈希另存复核侧文件，不改写 runner 原始输出。

技术核验包括 155 处返回片段来源范围、五份执行输入指纹及两份实际执行源码副本；11,614 个已有原始／语料／历史运行／代码输入文件逐个 SHA-256 一致，原 Git 暂存索引及 catalog 旧条目未变。仅新增本轮 catalog 条目，配置和评测代码未修改；本轮服务进程身份核对后已停止，8000 端口关闭。正式回答保留正文、usage 和结束状态，未完整抓取六次原始 HTTP 响应；重建请求明确标为 expected，不冒充抓包。初审与用户验收分开，语义仍为 `pending_human_review`，catalog 用户状态保持 `not_reviewed`，不外推为整体模型能力或 Q4 相对 Q6 的结论；未提交或推送。
