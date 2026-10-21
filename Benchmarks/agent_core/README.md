---
kind: reference
description: "运行确定性Core正确性探针、固定开销工作负载及有限回放。"
---
# Agent Core Benchmark

## 摘要

15个确定性用例观察候选core的协议行为。模型和工具使用脚本化替身；adapter负责接口转换，候选自行决定循环、记忆与恢复。性能另行执行，不把正确性与速度合成总分。

## 目录

- [执行](#执行)
- [用例与开销](#用例与开销)
- [维护边界](#维护边界)
- [Dev Note](#dev-note)

## 执行

先按[根开发说明](../../docs/development.md#python环境)准备环境，在仓库根运行。接入配置及失败语义见[公共协议](../support/protocol.md)。有限回放不是agent或参考候选，仅验证CLI；下列显式目录须不存在：

```powershell
uv --cache-dir .cache/uv run --locked --group benchmark --offline --no-python-downloads --python 3.11 python -B -m Benchmarks.agent_core.make_replay --output Benchmarks/outputs/agent_core/inputs/demo
uv --cache-dir .cache/uv run --locked --group benchmark --offline --no-python-downloads --python 3.11 python -B -m Benchmarks core --adapters Benchmarks/outputs/agent_core/inputs/demo/adapters.json --output Benchmarks/outputs/agent_core/core/demo
uv --cache-dir .cache/uv run --locked --group benchmark --offline --no-python-downloads --python 3.11 python -B -m Benchmarks perf --adapters Benchmarks/outputs/agent_core/inputs/demo/adapters.json --rounds 2 --batch 3 --warmup 1 --output Benchmarks/outputs/agent_core/perf/demo
```

`core --case c01`可重复指定筛选。`perf`默认 `--rounds 7 --batch 100 --warmup 2`；`--measure timing`测主要延迟，另跑`--measure memory`采样内存。`--timeout`默认每轮10秒。省略`--output`使用用途下的新时间戳目录。

```powershell
uv --cache-dir .cache/uv run --locked --group benchmark --offline --no-python-downloads --python 3.11 python -B -m Benchmarks report --run Benchmarks/outputs/agent_core/core/demo --run Benchmarks/outputs/agent_core/perf/demo
```

报告写到`outputs/reports/`新目录，并列不表示不同配置可直接比较。全部离线测试见[分类索引](../README.md)；只运行本类可用 `unittest discover -s Benchmarks/agent_core/tests -t . -v`。

## 用例与开销

用例矩阵、模拟上下文和策略判定见[评测定义](evaluation.md)，共享资源测量范围见[测量说明](../support/measurement.md)。

每轮新worker，启动单列；预热后正式采样，按轮交替候选顺序。固定负载包含reset、模型—工具—模型、broker、oracle及JSONL写入。`transport_replay`是走相同协议的有限磁带，单列原始值与配对差值；相减不代表纯内核耗时。断言失败不参与性能聚合。

## 维护边界

`cases.py`维护用例与oracle，`runner.py`执行正确性和开销测量，`tapes.py`仅构建有限回放。协议传输与记录复用support；不依赖剧情分类，不改RAG实现和基线。

## Dev Note

无。
