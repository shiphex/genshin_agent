# 原神剧情分析与解读 Agent

项目目标是设计能够以主角／派蒙身份参与剧情讨论、分析和解读的Agent。目前实现了本地冻结快照的剧情RAG和评测工具；最终角色Agent、对话界面、玩家进度分析和防剧透尚未实现。

**当前回答存在严重错误。** 本地Qwen3.5-4B的24题无检索／RAG对照已实际运行，用户反馈错误“极其多”。后续六题证据 × 参数诊断发现，补齐原文改善了部分机制说明，但人物身份、主体、时间与比例误读仍存在；校准采样未稳定修复。检索成功和调用正常结束都不表示答案正确，结果仍待用户逐题验收。

## 审阅入口

- [公开报告与外部模型分析任务](rag/reports/README.md)：不需本地数据即可阅读关键错误原句、必要原文和初审；完整回答／上下文在云盘包。
- [24题双组诊断摘要](rag/reports/full_validation_20261010_105700/summary.md)：覆盖48份正式回答，保留调用状态与关键错误原句。
- [六题全部条件／种子](rag/reports/generation_diagnosis_20261010_145424/summary.md)：覆盖48份回答的全部条件与种子；六题为前轮子集。
- [数据获取与上传步骤](rag/reports/data_access.md)、[版本／校验清单](rag/reports/manifest.json)：v3两种资料包本地准备；v2保留为重写前历史，GitHub／Google Drive地址待登记，pending_upload。

当前语料22,822片段，扫描5,474份parsed文件；检索为词面IDF加权Top5。Wiki摘录与编纂分别标注；过滤目标排除数值强度和攻略，但实测仍有机制与玩法漏项。资料来自Wiki冻结快照，不自动等同于官方事实。详见 [RAG运行说明](rag/README.md) 和 [模块上下文](rag/context.md)。

## 开发与离线检查

[AGENTS.md](AGENTS.md)记录工作约定；开始工作先读 [项目上下文](context.md)。Python操作通过uv运行，目前脚本只使用标准库。先安装uv并准备Python3.11；离线命令要求本机已有解释器。

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python -m unittest discover -s rag/tests
```

单元测试无需模型服务或完整快照。提取、检索、模型评测和发布导出命令见 [RAG README](rag/README.md)。

## Git与数据

Git保存源码、测试、开发文档、小型输入和批准报告副本；data/、rag/data/、ZIP、模型权重及缓存不提交。原快照和历史实验不由导出修改。新克隆可直接阅读案例；深度分析下载重点包，完整覆盖／复现下载完整包，见 [数据说明](rag/reports/data_access.md)。没有资料包时可另行提供同一冻结快照再生成语料；历史模型回答与人工复核无法靠重建恢复，Git不能代替备份。

两种包使用同一源码commit，之后登记链接只更新索引，以包内source_commit为准。未自动上传或推送，也未虚构地址。

冻结快照恢复的 [爬虫AI交接任务](rag/experiments/recovery/crawler_handoff.md) 单独保留，本项目未修改爬虫或接入新版数据。事实抽取、更强模型对照和多来源检索是待验证的修复方向，尚未实现。
