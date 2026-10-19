# 文档规范

本规范适用于项目现行文档和项目级 skill；根 [AGENTS](../AGENTS.md) 维护长期开发约束。文档工作使用 [doc](../.agents/skills/doc/SKILL.md)，文字判断使用 [prose-standard](../.agents/skills/prose-standard/SKILL.md)，不将检查清单代替事实核验。

## 一项事实一个权威来源

每项事实只在负责它的位置维护，其他位置链接引用。

| 维护位置 | 负责什么 | 不放什么 |
| --- | --- | --- |
| 根 AGENTS | 长期约束、必读路由；链接具体规则的维护位置 | 详细操作步骤（→ development、模块 README）、实例、已链接规则的完整副本 |
| 根 context | 项目阶段、模块入口；用一句导航指向模块 | 模块内部问题与验证详情（→ 模块 context）、完整运行记录（→ 对应结果） |
| architecture | 当前模块关系、总体数据流 | 模块内部接口与命令（→ 模块 README）、决策原因与取舍（→ Agent Note） |
| development | 开发步骤、项目级检查命令 | 模块命令的完整副本（→ 模块 README）、实验流水账（→ 对应结果） |
| terminology | 术语写法；链接领域含义的已有定义 | 领域行为定义（→ 架构、模块 README） |
| 模块 README | 接口、模块命令、使用限制；以代码和测试核验实际行为 | 总体模块关系（→ architecture）、当前问题与最近验证（→ 模块 context）、决策过程（→ Agent Note） |
| 模块 context | 当前问题、反馈、最近验证 | 完整运行记录（→ 对应结果）、稳定接口与命令的副本（→ 模块 README） |
| 题库 JSON | 题库内容与版本；与 catalog 引用通过已有检查核对一致性 | 资源定位清单（→ catalog）、模型回答与核验结果（→ 对应输出） |
| catalog | 资源身份与定位、题库引用 | 题库正文与版本的副本（→ 题库 JSON）、使用协议（→ 当前使用说明）、执行事实（→ 输出清单） |
| Agent Note | 重要决策原因与取舍 | 当前架构、接口和行为定义的副本（→ 架构、模块 README 及实现） |
| 对应定义、结果、manifest、历史记录 | 实验、发布、历史事实；明确版本和历史范围 | 不以新结果覆盖旧事实，不将历史结论当作当前行为说明（→ 当前架构、模块 README） |

权威位置是维护责任，不是掩盖冲突的优先级。实现与文档或已批准约束不一致时，先给出文件位置、实测／静态证据和影响，再决定修正文档还是另行设计行为变更。不得静默把当前代码当作新的用户要求。

## 分类与模板

人读现行文档使用 YAML frontmatter：`kind` 选模板，`description` 用一句中文说明可查阅的内容。下表是类型与模板的唯一映射；模板在 [doc/templates](../.agents/skills/doc/templates/)。

| kind | 模板 | 使用位置 |
| --- | --- | --- |
| overview | [overview.md](../.agents/skills/doc/templates/overview.md) | 根 README |
| architecture | [architecture.md](../.agents/skills/doc/templates/architecture.md) | 当前总体架构 |
| workflow | [workflow.md](../.agents/skills/doc/templates/workflow.md) | 开发步骤 |
| reference | [reference.md](../.agents/skills/doc/templates/reference.md) | 模块、专题和术语参考 |
| index | [index.md](../.agents/skills/doc/templates/index.md) | 文件夹 README 索引 |
| context | [context.md](../.agents/skills/doc/templates/context.md) | 阶段和交接状态 |
| Agent Note | [agent-note.md](../.agents/skills/doc/templates/agent-note.md) | 按状态记录重要决策，头部格式独立 |

常规文档有摘要和页内目录（Table of Contents），由浅入深组织正文。AGENTS、skill 指令、Agent Note 和极短索引豁免；极短索引指仅有用途介绍、直接入口表和相关入口的索引，无需再索引自身。文件夹索引只介绍直接文档的职责，不复述正文。不为套模板添加空洞内容；普通 reference 的主体章节按主题命名，模板规定的信息职责须覆盖。

当前文档描述当前行为；上下文保留当前问题和验证边界。已有历史段落可原文留在标识清楚的保留区，不继续追加过程日志。冻结实验说明、发布事实、案例、归档恢复与 history 不在本轮模板整改范围；不会因其格式或长度重写原文。

## 写作与审查

报告用Markdown表格列出数值，按需用Callout突出提示或结论；保留单位、分母、未计分／未完成状态及指标限制，数据图表依据对应结果绘制。

项目文档、报告和示例说明按需配图。SVG采用深色背景、浅色文字，保证标签和读数清晰；图种、尺寸与布局按内容选择。

使用[术语表](terminology.md)。一段一个主题，按物理行保存完整段落，代码块和表格保持格式。精简前核对主体、条件、时序、否定、例外、失败行为和不确定性；不能为省字删除必要含义。命令、字段、默认行为先对照实现；执行过的检查和静态阅读分别标识，缺环境或会产生未授权输出的操作不能假装已运行。

Dev Note 是非权威工作备注，不能维护稳定约束或第二份任务队列。普通现行页面需要备注时放在最后，没有内容写“无”；短索引和 context 可省略，context 已承担交接职责。稳定结论归回维护位置，重要取舍进入 Agent Note。skill 编排操作，不拥有产品行为定义；审查任务不因加载 skill 获得写权限。

## 字数门禁

[预算 manifest](../scripts/doc-budgets.manifest.json) 是逐文件上限的唯一来源，[检查器](../scripts/verify_doc_budgets.py) 实现计数。常用、兼容汉字及 U+20000–U+2FA1F 内汉字逐字计数；连续 ASCII 字母、数字、下划线计一单位，其他字符不计。按原始 Markdown 统计，包含元数据、标题、代码、表格、链接文本和目标。`RAG模块` 计 3，`Python 3.11` 计 3；这不是模型 token 数。

正常检查遇到超限、缺失文件、重复条目、非法预算或越界路径均失败。`--list` 只豁免超限退出码，配置错误仍失败。命令由[开发流程](development.md#验证)维护。先归位错放内容，再精简重复；必要时说明理由调整上限，不自动扩容，不把上限当删字目标。通常保留约 5% 余量；RAG context 只保留当前问题和最近验证。新增现行文档、skill 或模板时同步预算清单；历史证据和许可证不为预算整改。
