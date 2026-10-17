---
kind: reference
description: "说明110题开发集、20题独立事实核验与三题模型链路Smoke。"
---
# 剧情开发题与核验

## 摘要

[questions.json](questions.json)是唯一正式开发题库：0.5版、110题、445条出处。路径改变未修改JSON字节、题目或用户状态；旧14题复杂标注原型已淘汰。[review20.json](review20.json)固定四组各5题，保存核验输入顺序与原文，不是模型作答 Smoke。[smoke/](smoke/README.md)收纳三题模型链路验证的输入和说明，历史结果仍在 `rag/data/smoke/`。

## 目录

- [字段与原文](#字段与原文)
- [20题核验](#20题核验)
- [维护与验证](#维护与验证)
- [检索评测协议 V0](#检索评测协议-v0)
- [Dev Note](#dev-note)

## 字段与原文

每题维护 `id/type/difficulty/question/answer/keywords/criteria/sources`。keywords 只是提示，criteria 是扁平评价要点，命中关键词不等于语义正确。保留100道核心题和10道跨故事题；类型、配额与状态以题库内容为准。

sources 只维护冻结快照中的相对 POSIX file 和 RFC 6901 pointer，不手写 text；多条来源可共同支撑，也不穷尽等价出处。原文、Wiki整理、人物观点和推论须区分；不凭模型记忆补依据。改快照后需重新核对Pointer，不能继承旧来源有效性。

`prepare_eval.py` 先读取全部来源，再写出附加 `sources[].text` 的副本，透传其他字段，不调用模型或评分。默认分配独立 prepared 输出；显式输出须是 `rag/data/outputs/prepared/` 下新目录中的文件，拒绝覆盖及写入原始数据。命令由[模块说明](../README.md#问题集与-smoke)维护。

## 20题核验

完整第三方结果在本地 `rag/data/review20/result.json`；[原摘要与提示词记录](../data/review20/summary.md)与它同目录保存，输入、结果及摘要均由[catalog](../catalog.json)绑定。第三方报告四组20题初判正确、55条criteria无原文矛盾、86/86指针一致；这些是第三方历史结论，本次未重新进行剧情语义核验，也不是用户逐题通过。

原输入按既有顺序保留，没有重新抽样或合并批次。摘要原字节保留，其中旧路径、“第四组”、日期和输出要求属于历史记录，不是当前操作指令，也不证明四组均采用完全相同提示词。其“20题正确”不能替代逐题疑点或用户验收。新核验使用[独立核验skill](../../.agents/skills/genshin-question-review/SKILL.md)，不直接执行历史提示词。

## 维护与验证

全部110题仍待用户逐题确认。题库用于开发评测，不作训练样本；泛化评估另设留出集。当前 JSON 题库尚未接通 JSONL 模型评测入口。

修题先保存题目对象及顺序，再读原文字段、逐项核对，按任务更新版本和catalog指纹。运行原文准备核对445条来源时只生成临时副本；常驻基线不保存第二份110题正文。[开发题 skill](../../.agents/skills/genshin-dev-questions/SKILL.md)。

## 检索评测协议 V0

`retrieval-source-location-v0` 使用原题库顺序、只以 question 查询；入口和参数见[模块说明](../README.md#110题检索评测)。题库保持原字节，不生成第二份常驻题库。results.jsonl 的 source_location 按每题唯一 `(file,pointer)` 精确匹配返回片段的 source_file／source_pointer；一个片段可包含多个 Pointer，重复片段不重复计数。

| 指标 | 定义 |
| --- | --- |
| 来源位置 Hit@K | 命中至少一个标注位置为1，否则0；汇总为计分题均值 |
| 来源位置 Coverage@K | 每题命中位置数／标注位置数；宏平均按计分题等权，微平均按标注位置总数加权 |

未进入语料的位置保留分母，逐题标记 in_corpus=false；不因检索不可达而删除。sources=[] 的题仍检索，指标为 null、不入均值，并计入 unscored_questions。非法结构、重复题号、无效来源路径／Pointer、空语料与非正 Top-K 拒绝执行；不依赖原始快照来做新一轮原文或语义核验。

来源标注不穷尽等价出处，也没有与 criteria 对齐的必需证据组及充分字符范围。字段命中可能只取回长字段的一小块。因此本协议只计算来源定位代理指标；semantic_coverage 和 answer_correctness 均为 not_evaluated，不把 Hit／Coverage 宣称为语义召回率或最终答对率。

未来检索 A/B 固定 protocol_id、schema_version、题库与语料 SHA-256、题号集合及 Top-K，按 question_id 对齐匹配详情和逐题增退，再比较汇总。记录检索实现身份及有意改变的变量；输入或协议不同须先说明差异，不能直接宣称同条件提升。时间、运行编号和绝对路径不参与结果一致性判断；耗时比较须在同等环境重复采样。V0 不新增对比命令或自动性能门槛。

## Dev Note

无。
