---
kind: index
description: "导航面向所有Benchmark分类的共享协议、产物和测量基础。"
---
# Benchmark共享组件

`support/`供当前和未来的所有Benchmark分类复用。只有两个以上实际分类需要相同行为时才提取；专用工具和场景留在所有者旁。共享代码不导入分类实现，分类汇总由根入口组合。

| 入口 | 职责 |
| --- | --- |
| [协议](protocol.md) | 双向JSONL、adapter声明、传输期限和清理；`protocol.py`／`contracts.py` |
| [测量](measurement.md) | 采样范围、usage缺失和追溯边界；`metrics.py` |
| `common.py`／`execution.py` | 根路径、exclusive新运行、指纹、源码副本和worker初始化 |
| `reporting.py` | 公共分母与报告写入；所属分类通过回调补充指标 |
| `replay_worker.py`／`testing.py` | 有限协议磁带及隔离测试辅助，供多个分类验证框架 |

Python配置和锁文件只在项目根维护。公共测试运行方式见[总入口](../README.md)，本目录可用 `unittest discover -s Benchmarks/support/tests -t . -v`。资源限制是运行条件；当前不提供内存上限执行器。
