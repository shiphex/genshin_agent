# 上游来源与适配

查阅日期：2026-10-16。来源为 DeepSeek Harness 的 master 页面；本次未能从网页访问结果可靠确认同一源码 commit，因此这些链接是查阅入口，不声称是固定 commit 的完整源码快照。

## 已阅读的机制

- [根 AGENTS](https://github.com/deepseek-ai/deepseek-harness/blob/master/AGENTS.md)、[文档规范](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/AGENTS.md)、architecture 与 development：长期约束、架构、使用说明和开发流程分工。
- [dsh-doc](https://github.com/deepseek-ai/deepseek-harness/blob/master/.agents/skills/dsh-doc/SKILL.md)：分类、就近归位、事实核验及文档审查。阅读其 structure-hierarchy、review、style、metadata-links-i18n 参考资料和 package-group／package-reference／package-library 模板；模板只复用职责与验证方法。
- [dsh-prose-standard](https://github.com/deepseek-ai/deepseek-harness/blob/master/.agents/skills/dsh-prose-standard/SKILL.md)及 examples：保留完整含义，避免以删字替代审查。
- [agent-experience 实际正文](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/preset/agent-preset/skills/agent-experience/SKILL.md)：上游 .agents/skills 入口为符号链接；采用按需加载、清楚的发现路径和有界结果。
- [Agent Notes](https://github.com/deepseek-ai/deepseek-harness/blob/master/.agents/notes/README.md)：重要决策才记录，状态对应内容；历史不能充当当前行为。
- [术语规则](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/i18n/terminology.md)与 [glossary](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/glossary.zh.md)：必要英文与中文解释分开处理，不导入不存在的领域模型。
- [字数检查](https://github.com/deepseek-ai/deepseek-harness/blob/master/scripts/verify-doc-budgets.ts)、预算 manifest、verify-md-links、verify-agent-note-format、verify-skill-invocation-metadata 与 package.json：显式预算、有效／无效输入、链接锚点、状态格式和发现策略的验证职责。

## 适配差异

| 上游机制 | 本项目处理与原因 |
| --- | --- |
| 三个独立 skill | 保持职责拆分，名称改为 doc、prose-standard、agent-experience；描述和步骤中文化 |
| 文档分类及模板 | 七种本地类型；删除插件安装、生成 API、Cordis、TypeScript SDK 形式，不虚构对应能力 |
| 双语配对与网站投影 | 删除；项目只维护中文说明，不引入译文或网站 |
| 按空白分词预算 | 改为汉字与 ASCII 连续词混合计数；Python 标准库实现，适用于当前中文资料 |
| 完整文档门禁 | 本轮只新增字数自动门禁和测试；链接、模板、术语及 Notes 格式实际审查，不冒充已有自动体系 |
| Notes 分类、归档及门禁 | 暂缓，只保留按需创建的三个状态，避免无实际需求的子树与工具 |
| 全量原仓库操作核验 | 定向检查本项目真实命令，区分静态与实测；不因核验而调用模型或生成未授权数据 |

仓库原有历史正文、冻结包和结果不移植成新体系的当前规范。只读审查与写任务分开；小改动不强制增加记录或全量实验。模板、skill 和 Python 检查器包含对上游机制的改编，必要许可保存在 [LICENSE.deepseek](../LICENSE.deepseek)。

## 已知限制

上游 website-sync 参考页此次未能取得，网站机制仅根据 dsh-doc 对投影和发布边界的说明核对，未复现；本项目不采用该机制。未运行上游 Node/pnpm 检查，也未声称本地实现与其全部门禁等价。
