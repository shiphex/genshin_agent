# 全量24题无检索／RAG对照

本页案例为关键原句与诊断摘要，完整回答、实际上下文及封存记录见[云盘资料说明](../../data_access.md)。所有条件与种子均有摘要对应。

实验 ID：model_comparison；运行 ID：r001；历史 ID：full_validation_20261010_105700。模型 unsloth/Qwen3.5-4B-GGUF:UD-Q6_K_XL。冻结语料22,822片段；词面检索Top5；温度0、seed42、关闭思考、1536-token上限。服务未显式记录的历史采样默认值不补填。

以下数量依据保存的 experiment_summary.json 与 run_manifest.json；逐题说明依据 preliminary_review.json。原始文件及哈希见 [发布清单](../../manifest.json)。**语义初审待用户逐题验收**，用户认为错误极其多，尚无逐题确认或总体正确率。

| 验证层 | 已保存结果 | 边界 |
|---|---|---|
| 检索覆盖 | 旧题6/9找齐标注证据组，平均83.3%；新题0/10，平均20% | 参考不是穷尽集合，n04/n09/n10有替代来源；空组不计成功 |
| 调用完成 | 正式48次：47 stop、1 length；报错0、非标准结束0 | q06 baseline截断；24份RAG均stop，不表示正确 |
| 引用格式与ID | 24份RAG中19份有约定格式；q01/n06/n12含不存在ID | 格式、ID合法与内容支持互不替代 |
| 答案语义 | 初审确认多处身份、主语、因果与时间误读，另有语料机制漏项 | 不把初审核心支持数变成用户验收通过率 |

一题双组连接检查另计2次。q06以3072-token上限重试另计2次，baseline仍length，RAG stop但仍有语义／引用错误。合计52次，不用重试替代第一次答案；这些补充原件在云盘包。用户题目尚未收到，未运行用户批次。

无检索组多处自行补写剧情和身份；RAG组在部分旧题有所改善，但遗漏跨来源证据、引用拼接、把角色陈述提升为事实仍突出。n06/n12完整可答性未确认。q11有怪物数值机制进入语料，q12有玩法指令漏项，不能统一归因于模型记忆。详见案例中的两组初审。

## 全部案例

旧题：[q01](cases/q01.md) · [q02](cases/q02.md) · [q03](cases/q03.md) · [q04](cases/q04.md) · [q05](cases/q05.md) · [q06](cases/q06.md) · [q07](cases/q07.md) · [q08](cases/q08.md) · [q09](cases/q09.md) · [q10](cases/q10.md) · [q11](cases/q11.md) · [q12](cases/q12.md)

新题：[n01](cases/n01.md) · [n02](cases/n02.md) · [n03](cases/n03.md) · [n04](cases/n04.md) · [n05](cases/n05.md) · [n06](cases/n06.md) · [n07](cases/n07.md) · [n08](cases/n08.md) · [n09](cases/n09.md) · [n10](cases/n10.md) · [n11](cases/n11.md) · [n12](cases/n12.md)

[下一步：六题受控诊断](../../generation_diagnosis/r001/summary.md) · [审阅任务](../../README.md) · [资料包](../../data_access.md)
