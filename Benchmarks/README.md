---
kind: index
description: "按被测任务导航各类benchmark、共享组件与统一执行入口。"
---
# Benchmarks

本目录按被测任务分类。统一入口 `python -m Benchmarks` 只解析、分派和组合报告；各分类维护自己的场景、判定、命令与测试。当前是agent core Spike评测框架，没有候选core实现。

| 入口 | 内容 |
| --- | --- |
| [agent_core](agent_core/README.md) | 15个确定性用例、oracle和独立开销测量；`core`／`perf` |
| [agent_story](agent_story/README.md) | 16个剧情场景、Qwen／RAG接入与AI／人工评审；`agent`／`preflight`／`review` |
| [support](support/README.md) | 面向所有分类的共享协议、产物、资源测量和测试辅助 |
| [开发规则](AGENTS.md)、[当前状态](context.md) | 分类边界、结果保护、最近验证与未测范围 |

Python环境统一由[项目开发说明](../docs/development.md#python环境)维护。在仓库根目录运行离线检查：

```powershell
uv --cache-dir .cache/uv run --locked --group benchmark --offline --no-python-downloads --python 3.11 python -B -m unittest discover -s Benchmarks -t . -v
uv --cache-dir .cache/uv run --locked --group benchmark --offline --no-python-downloads --python 3.11 python -B -m Benchmarks list
```

新输出使用 `outputs/<分类>/<用途>/<运行号>/`，跨分类 `report` 写 `outputs/reports/<运行号>/`。显式 `--output` 也须位于对应用途下的新目录；重跑使用新名称。历史输出原位只读，保留旧manifest、源码副本和路径绑定；可读取和生成新报告，不能追加评分。全部输出被Git忽略，须独立备份。

RAG eval目前仍由 [rag](../rag/README.md) 维护，尚未迁移。未来新增分类按实际任务建目录；多类确实共用的能力再提取到support，不预建空目录或通用插件框架。
