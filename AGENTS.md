# 开发指引

## 项目目标

设计能够以主角／派蒙身份参与原神剧情分析、解读和讨论的 agent。RAG 是为其提供可追溯证据的模块，不是项目的全部目标。

## 开始与结束工作

- 开始工作先阅读根目录 `context.md`；涉及 RAG 时再读 `rag/context.md` 的当前区与 `rag/README.md` 的相关章节，历史按需回查，以实际文件和验证结果为准。
- 按[开发流程](docs/development.md)完成分析、实施、验证和知识更新；根 context 仅在阶段或入口变化时更新，模块 context 维护当前问题、最近验证和反馈，不复制完整实验日志。
- 明确区分已确认约束、实测事实、用户反馈和候选设计。不把暂时倾向或 MVP 技术选择升级成永久要求，不把未经逐题验收的反馈写成全部通过。

## 按任务阅读

- 改变模块关系、依赖或数据流前读[架构](docs/architecture.md)；RAG 接口和命令由模块 README 维护，具体实验只读相应定义和结果。
- 创建或同步文档时读[文档规范](docs/AGENTS.md)、[术语](docs/terminology.md)和 [doc skill](.agents/skills/doc/SKILL.md)；精简文字按需用 [prose-standard](.agents/skills/prose-standard/SKILL.md)。
- 设计 skill 或上下文加载时用 [agent-experience](.agents/skills/agent-experience/SKILL.md)。编写／修订开发题用 [genshin-dev-questions](.agents/skills/genshin-dev-questions/SKILL.md)，独立核验题目事实与证据用 [genshin-question-review](.agents/skills/genshin-question-review/SKILL.md)；不将编题自评或模型作答评分混为独立核验。
- 小改动不要求读取全部历史、创建 Agent Note 或重跑模型实验。重要决策按 [Notes 入口](.agents/notes/README.md)记录；文档完成前检查预算、链接、事实依据和受影响导航。
- 性能实验／回退判断用 [speed-up-perf](.agents/skills/speed-up-perf/SKILL.md)；CI、资源型测试或偶发失败用 [ci-test-reliability](.agents/skills/ci-test-reliability/SKILL.md)；推送／交付前用 [pre-push-checks](.agents/skills/pre-push-checks/SKILL.md)选择必要验证，不要求所有任务加载三者。

## 已确认的工作约定

- Python 数据处理和实验脚本必须通过 uv 管理、运行。按当前任务需要选择实现，不无故引入框架、依赖或存储系统；具体技术选择和运行命令见对应模块文档。
- 保持原始爬虫数据完整。读取 `data/raw/`，将派生数据和报告写到原始目录之外；迁移或清理文件前确认目标范围并保护已有结果。
- 剧情语料排除游戏数值强度、技能倍率、培养、配队和攻略，保留人物、武器与圣遗物的故事、设定及剧情中的力量描述。不能仅因出现“攻击”“战斗”“力量”就删除文本。
- 原文、Wiki 整理／推测和模型生成内容要能区分。保留出处；不凭模型记忆补全缺失剧情、角色身份或分支，不把人物说法与传说自动当成确定事实。
- 检索指标、API 完成状态、引用 ID 合法性和语义正确性分别验证、报告，不能相互替代。
- RAG 专属实现、配置、测试、文档和派生数据放在 `rag/`。共享原始数据、项目总览和公共缓存保留在项目层。
- Git 保留项目开发文档、skill、项目级文档检查，以及 RAG 脚本、测试和明确列出的当前题库／Smoke输入。`rag/` 默认忽略新增内容；原始快照、语料、模型回答、审计／覆盖报告、哈希清单和缓存仅保留本地，不强制加入提交；清理须按用户明确范围并先核对保留资料。新增需跟踪的模块或输入时同步更新 `.gitignore`，提交前检查暂存清单。
- 从 Git 获取项目后，需要另行提供冻结快照并按 RAG README 生成语料。历史模型回答和人工复核不能靠重建语料恢复；需要独立备份，不能把 Git 当作数据备份。
- 当前窗口不修改 `get_genshin_wiki` 爬虫项目代码；冻结快照恢复任务通过 `rag/docs/recovery/crawler_handoff.md` 交给爬虫项目的独立 AI 会话，本项目接入新版数据另行安排。
- 配置和上下文不保存访问令牌或 API 密钥；鉴权值通过环境变量读取。
- 当前基线由 `rag/catalog.json` 和 `rag/docs/data.md` 维护：data只常驻corpus、review20、smoke；新生成写入outputs下独立用途／编号，不能自动覆盖或提升基线。题库更新同步版本及指纹。搬移保留原件字节；实际执行源码与当前实现分开。
- 用户已明确淘汰旧14题原型、样本、旧实验、审阅ZIP、Git bundle和整理归档，不再维护旧目录或兼容映射。后续唯一回答、核验与反馈仍不得按临时文件自动删除；旧档案保留规则不要求重新创建本次已淘汰资料。

## 核验与发布约定

- 20题核验与三题模型Smoke分别维护，第三方初审、检索覆盖、API完成、引用检查和用户语义验收不能相互替代。以冻结原文核对，不将未经逐题确认的结果登记为用户通过。
- Hugging Face只导出当前剧情语料及其审计附件；数据卡明确加载文件，保留来源和许可声明。题库、回答、原始快照和核验原件不随语料发布。
- 导出使用新目录，验证白名单、配置、行数及哈希。只有实际上传并验证访问后才登记available；不编造地址或把旧revision当新格式已发布。
- Git候选文件检查鉴权内容和忽略规则。实际提交、推送和上传按任务授权执行。
