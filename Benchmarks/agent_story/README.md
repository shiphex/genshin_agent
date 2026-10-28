---
kind: reference
description: "运行冻结剧情多轮场景、Qwen原生工具预检和pi评分导入。"
---
# Agent Story Benchmark

## 摘要

16个固定剧情场景在V0固定历史配置下评估证据使用、会话延续与未知边界。通过公共JSONL协议接入候选，统一Qwen、提示词与既有LexicalIndex。符合性与剧情语义分列，比较须结合[适配声明](../support/protocol.md#启动配置)。没有候选实现，不因框架测试通过登记剧情语义通过。

## 目录

- [真实执行](#真实执行)
- [pi与人工评审](#pi与人工评审)
- [材料与限制](#材料与限制)
- [Dev Note](#dev-note)

## 真实执行

按[根开发说明](../../docs/development.md#python环境)准备环境，接入格式见[公共协议](../support/protocol.md)。需要独立取得本地语料、冻结快照及已部署Qwen服务；脚本不启动服务、不下载权重。以下命令会真实请求模型，本次整理未执行：

```powershell
uv --cache-dir .cache/uv run --locked --group benchmark --offline --no-python-downloads --python 3.11 python -B -m Benchmarks preflight --config rag/config/local_api.json
uv --cache-dir .cache/uv run --locked --group benchmark --offline --no-python-downloads --python 3.11 python -B -m Benchmarks agent --adapters Benchmarks/outputs/agent_story/inputs/candidates.json --config rag/config/local_api.json
```

`candidates.json`由用户按协议准备。`agent`仍登记本次原生function call预检；不支持时明确失败，不改成文本模拟。默认16场景，每场景完整重复3次，每次新worker／干净会话；每轮最多8次模型请求、检索Top5、240秒期限。可重复`--scenario a06`筛选，或用`--repeats`、`--max-steps`、`--top-k`、`--timeout`调整。

所有候选共用[本地模型配置](../../rag/docs/local_model.md)，支持私有覆盖和 `--profile simple|standard|deep`；默认使用配置选中的档位。旧平面配置的 temperature／seed 默认0／42且关闭思考；`model=null`仅接受服务恰好公开一个模型。鉴权从环境变量读取，拒绝未知字段；启动路径不进入客户端配置。HTTP超时仍受剩余任务期限限制，deep 如需更长任务时间应显式设置 `agent --timeout 600`，不自动延长原240秒默认值。

默认语料从只读catalog定位并校验指纹，`--corpus`／`--raw-root`可指定自定义材料并记录真实身份。`--model-service-pid`可单列本机服务资源；未提供记未测。`--measure memory`另跑完整场景，不能与timing混合比较。共享测量范围见[说明](../support/measurement.md)。

## pi与人工评审

脚本不启动pi、不管理第三方API。将导出的package.json与模板交给已配置pi，填评分后导入。以下目录／评分须先生成，显式输出目录须不存在：

```powershell
uv --cache-dir .cache/uv run --locked --group benchmark --offline --no-python-downloads --python 3.11 python -B -m Benchmarks review export --run Benchmarks/outputs/agent_story/agent/my-run --output Benchmarks/outputs/agent_story/review/my-package
uv --cache-dir .cache/uv run --locked --group benchmark --offline --no-python-downloads --python 3.11 python -B -m Benchmarks review import --package Benchmarks/outputs/agent_story/review/my-package --input Benchmarks/outputs/agent_story/review/scored.json --kind ai
uv --cache-dir .cache/uv run --locked --group benchmark --offline --no-python-downloads --python 3.11 python -B -m Benchmarks report --run Benchmarks/outputs/agent_story/agent/my-run
```

`--kind human`另行追加复核，保留AI初评。导入核对运行、材料、逐项判断、理由和证据定位；未评、存疑、失败与争议分别展示，不代表用户验收。迁移前历史运行只读，不能追加评分。完整格式见[评测与评审](evaluation.md#评审与报告)。

## 材料与限制

[scenarios.json](scenarios.json)绑定原题ID和哈希，按[评测定义](evaluation.md)解析冻结原文；不复制另一份完整题库。参考答案和criteria仅供评审，a04明确预置的证据除外。原题待审状态保留，未知限定于冻结快照。

本类维护输入、模型／检索provider、评审及所属测试；依赖support，不依赖Core oracle。RAG实现只读复用，RAG eval仍在原目录。全套离线测试见[索引](../README.md)；本类可运行 `unittest discover -s Benchmarks/agent_story/tests -t . -v`，仅使用合成语料、有限磁带与回环假HTTP。

## Dev Note

无。
