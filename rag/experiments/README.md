# 实验输入与执行说明

本目录只保留复现实验所需的小型输入、参数和执行说明。完整请求、模型回答、检索结果和审计位于本地 `rag/data/`；正式题库和原文准备流程见[题库说明](../eval/README.md)。

实验用途名称固定，具体执行用 `rNNN` 编号；输入、旧ID、结果及报告关联由[catalog](../catalog.json)维护。[身份、版本与状态规则](../docs/artifacts.md)。表中的本地产物路径是历史运行，新执行使用 `data/runs/<实验ID>/rNNN/`。

| 实验 | 输入 | 对应产物与状态 |
| --- | --- | --- |
| 历史样本 | [mvp/selection.json](sample_retrieval/selection.json)、[mvp/questions.jsonl](sample_retrieval/questions.jsonl) | 30片段／12题，`data/corpora/story_sample/v1/`；仍是显式 sample 模式的默认输入 |
| 全量检索回归 | [full/questions.jsonl](full_retrieval/questions.jsonl) | q01–q12 的全量出处标注，`data/runs/full_retrieval/r001/`；是 full 模式默认输入 |
| 24题模型对照 | [执行说明](model_comparison/README.md)、[新增12题](model_comparison/questions.jsonl) | 旧 q01–q12 加新 n01–n12，`data/runs/model_comparison/r001/`；初审待用户验收 |
| Q4 完整链路 Smoke | [已确认方案 v1](model_comparison/smoke_qwen35_q4_v1.md) | 旧 q01–q03，`model_comparison/r002`；六次正式调用完成，初审发现问题，仍待用户验收；方案为运行后整理保存 |
| 六题受控诊断 | [执行说明](generation_diagnosis/README.md)、[cases.jsonl](generation_diagnosis/cases.jsonl)、[采样参数](generation_diagnosis/generation_profiles.json) | 前轮六题子集，`data/runs/generation_diagnosis/r001/`；全部条件／种子保留 |

MVP 与全量的12题题号相同，但证据标注针对不同语料，不能当成重复文件删除。六题诊断也不能替代24题对照。

其他入口已经按用途归位：

- 共享模型连接配置：[config/local_api.json](../config/local_api.json)。只读取环境变量鉴权，配置不保存密钥。
- 运行和当前状态：[RAG README](../README.md)、[模块上下文](../context.md)。
- 实现、观察和开发历史：[开发文档](../docs/README.md)。
- 开发题抽样与第三方复核：[题库复核资料](../eval/reviews/dev_sample/r001/selected_questions.json)和[摘要](../eval/reviews/dev_sample/r001/result_by_deepseek_summary.md)。完整第三方JSON在同目录，仅本地保存。
- 冻结快照恢复交接：[恢复任务](../docs/recovery/crawler_handoff.md)。本窗口不修改爬虫代码。
- 公开审阅和摘录生成：[报告入口](../reports/README.md)、[摘录位置清单](../reports/inputs/excerpts_v3.json)。

复跑选择新的输出目录。历史参考、程序验证、API完成和用户语义验收分别记录，不把任何一项当成其他项通过的证明。
