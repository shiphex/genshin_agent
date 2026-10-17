---
name: genshin-dev-questions
description: Use when continuing to add or revise the story development questions in this repository's rag/eval/questions.json (继续补开发题、修订开发集). Excludes model evaluation runs and crawler changes.
---

# 剧情开发题编写

仅处理 `rag/eval/questions.json` 的开发题。`AGENTS.md`、`rag/eval/README.md` 和当前题库是项目事实来源；本 Skill 编排流程，不规定固定批次、日期、快照或题号。模型评测及爬虫修改另行处理。

## 准备

1. 从仓库根目录读取 `context.md`、适用的 `AGENTS.md`、`rag/context.md` 当前区，以及 `rag/README.md`、`rag/eval/README.md` 和当前 JSON 的相关部分；历史按需回查。检查 Git 状态，保留已有工作与暂存状态。
2. 从当前任务和文件确定本批题号、版本、类型与难度、题数、冻结快照、用户复核状态及输出路径。编辑前保存现有题目对象及顺序作为比较基线；有未提交修改时不能单靠 `HEAD` 作为基线。长期配额与当前题数分开记录。
3. 读取指定快照中的实际原文字段，确认拟用材料含有支持命题的非空文本。若指定任务的对白等字段为空，寻找同一故事阶段或相邻任务中确实可用的原文，核对出处并在交付说明中交代变更；找不到足够依据就缩小或改写命题，不凭记忆补全。

## 起草与原文复核

- 独立题目可分组交给子代理起草；可用且用户未另作指定时，选 `gpt-6-luna`、`low` reasoning。请子代理只读原文，返回候选 `question/answer/keywords/criteria/sources` 与所据原文字段；主代理负责全部最终核对和编辑。批次与分组规模由任务决定。
- 沿用当前开发集每题八字段及字段含义。`sources` 只写相对于冻结快照的 POSIX `file` 路径和精确 RFC 6901 `pointer`，不要手写 `text`。跨故事题分别列出各侧必要证据；多条来源可以共同支撑结论，不要求任一条单独覆盖全题。
- 主代理逐题核对原字段、说话者、故事阶段、答案的每个断言和每项 `criteria`。区分角色判断、初步假说、日志推测、传说、史书编纂立场与确定叙述。连续证据若分别修正不同假说，逐个写清「哪条证据支持或质疑哪个假说」，不得合并成一个确定机制或跨材料互证。核对题型、难度和与既有题的考点重叠。
- 保持原有题目对象及顺序、既有用户复核状态和无关头信息。只按本批任务更新必要元数据，不把主代理原文核对登记为用户逐题通过。

## 准备副本与验收

1. 编辑后逐字段比较基线题目与当前题目，检查新增 ID 唯一、题型和难度符合任务，且没有重复考点。
2. 按 `rag/eval/README.md` 的当前命令，经 uv 运行 `rag/scripts/prepare_eval.py`；默认在 `rag/data/outputs/prepared/rNNN/` 分配新副本，不修改基线清单。显式 `--output` 须遵循[现行产物规则](../../../rag/docs/data.md)，位于outputs/prepared下，且输出父目录尚不存在。不得覆盖旧结果或输入。检查全部出处均解析为非空原文，副本text与快照字段逐字一致；按用户明确的基线更新范围同步题库版本和catalog指纹。
3. 经 uv 运行现有 `rag/tests`，检查 Git 候选文件及暂存清单。生成副本和原始快照留在本地忽略目录；只同步受影响的开发说明与 `rag/context.md` 当前区，根 `context.md` 仅在阶段或入口变化时更新，不碰无关实验。
4. 交付时分开报告程序校验、主代理逐题原文核对和用户逐题验收。只有收到用户的实际逐题确认，才能把相应题目记为用户通过。
