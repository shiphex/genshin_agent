---
kind: reference
description: "提供 Core 技术探针的最小评审材料、来源、复算命令与未发布范围。"
---
# Core 技术探针评审入口

## 摘要

这是 `review/core-probe` 的评审快照，基线为 `1b25d92`，不代表生产 Core 选型。两套最终候选、统一依赖和精选证据在同一分支；不合并原实验分支。原始输出保留本地。本次只有本目录白名单内的回答、评分和报告作为用户批准的发布例外，其他 outputs 继续忽略。

## 目录

- [阅读顺序与来源](#阅读顺序与来源)
- [材料与限制](#材料与限制)
- [离线核验与复算](#离线核验与复算)
- [重新运行](#重新运行)
- [Dev Note](#dev-note)

## 阅读顺序与来源

1. 读[已确认实验约定](../../experiment-contract.md)、[Core 定义](../../agent_core/evaluation.md)和[公共协议](../../support/protocol.md)。
2. 比较[自建候选](../../../probes/core_self/README.md)与[SDK 候选](../../../probes/core_sdk/README.md)的源码、专项测试和适配声明。候选文件按原字节保留，README 的进度属于实现阶段，不代表当前统一评估状态。
3. 读[Core／性能历史报告](evidence/reports/core-probe-comparison-r001/comparison.md)及[真实 Story 补测报告](evidence/reports/core-probe-comparison-r002/comparison.md)。r001 当时未跑 Story，r002 补充真实结果；原报告的本机路径和历史“不推送”说明原样保留，不能作为本分支的当前操作指令。
4. 独立审阅 Story 时先只读[完整18样本匿名包](evidence/agent_story/review/core-probe-live-r001/package.json)，自行按冻结标准判断，再查看[既有 AI 评分](evidence/agent_story/review/core-probe-live-r001/scored.json)、[候选映射](evidence/agent_story/review/core-probe-live-r001/binding.json)和[独立语义审阅](evidence/reports/core-probe-comparison-r002/independent-story-review.md)。
5. 对照[Core 独立审阅与修复复核](evidence/reports/core-probe-comparison-r002/independent-core-review.md)、[来源及文件哈希](provenance.json)和[决策 Note](../../../.agents/notes/implemented/2026-10-28-core-probe-review-publication.md)。

| 来源 | 身份 |
| --- | --- |
| 共同基线 | `1b25d92510dcaa0d4ff6e0216e589f2b3a881bb4` |
| 自建最终源码 | `2de247252c064a40029b04bdcb9d4f8760a78f39` |
| SDK 最终交接 | `6e3e72f5f61954f154a077bf84b8bf2015c25033`，源码修复 `c53efa9` |
| 对比文档交接 | `9892c1d7e5e624c56a1e4329a8d3b063e5d15560` |

这些原 commit 是来源标记，原实验分支不推送，不能保证远端能直接检出它们。`provenance.json` 同时登记原 Git blob 与实际执行文件的 SHA-256；LF／CRLF 可能不同。源码及冻结 JSON 按实际字节发布并关闭自动换行转换。六份历史 PowerShell 日志原为 UTF-16LE，发布副本转 UTF-8 供 GitHub 阅读，解码文本不变，原字节哈希及转换单列登记；原终端行尾空格保留，只有这些历史日志豁免行尾空格检查，源码和文档不豁免。此 manifest 证明一致性，不独立证明作者或实验真实性。

## 材料与限制

`evidence/` 保持原 outputs 的相对目录结构，便于定位原报告引用。Core 包含自建最终 Smoke、SDK 修复后 Smoke、首次完整运行和 SDK 修复后完整运行的 manifest／results。首次完整运行中的 SDK 是旧版本，只用于历史核对；最终 SDK 结论使用 `core-sdk-full-r002`。性能两阶段各保留21条结果，即两个候选加回放参照各7轮，以及逐次耗时和运行元数据。

Story 保留原 manifest、results、summary、materials，以及完整匿名包、映射、评分和补充引用审计。原 summary 的通用 correct/unjudged 不承担语义判定。两路场景执行／协议各9/9，AI 初评各6/9，a06 各0/3；没有用户语义验收。引用格式检查、ID成员关系与语义支持分别看待。冻结原文和检索摘录保留其出处，Wiki 整理、人物说法及模型生成内容不能自动当作官方事实；完整数据的来源与许可见[RAG说明](../../../rag/README.md)。本评审材料不属于 HF 语料导出。

不发布两份性能 trace、重复 sources、独立 Story trace、完整语料／快照、权重／服务二进制、私有配置、服务日志和开发失败目录。匿名包已保留每样本 Story trace；单独 trace 的原哈希登记在 provenance，公开字节不足以重算原 run_identity，不能把它说成完整原始运行备份。原 binding 保留本机 run_path，仅用于来源核对；不要对它运行现有 CLI import。第三方可独立重新评分，原评分和原运行不追加修改。

性能实际顺序为 AB,BA,BA,AB,AB,BA,BA，回放始终最后，未完成严格逐轮交替；只能作本机描述性比较。真实 Story 关闭思考，未验证新版 standard/deep。54次场景内调用有原结果，额外2次预检只保留历史报告声明，未发布完整预检原件。本次整理不调用模型、不重测性能、不恢复缺失数据。未上传的原始记录继续独立保留。

## 离线核验与复算

以下 PowerShell 命令从仓库根运行。首次同步需要网络；缓存齐全后可加 `--offline`。Python 3.11，所有命令由 uv 管理：

```powershell
uv --cache-dir .cache/uv sync --locked --group benchmark --group core-sdk --no-python-downloads --python 3.11
$reviewRoot = 'Benchmarks/reviews/core-probe-20261028'
$reviewUv = @('--cache-dir','.cache/uv','run','--locked','--group','benchmark','--group','core-sdk','--offline','--no-python-downloads','--python','3.11','python','-B')
uv @reviewUv "$reviewRoot/scripts/verify_publication.py"
uv @reviewUv -m unittest discover -s probes/core_self/tests -v
uv @reviewUv -m unittest discover -s probes/core_sdk/tests -v
uv @reviewUv -m unittest discover -s Benchmarks -t . -v
uv @reviewUv scripts/doc_sync.py
```

核验器检查发布白名单与哈希、最终版本分母、包／评分绑定、完整标准与证据定位、匿名包和原结果一致性，并重算性能。不会重新判断自然语言语义。统计／审计脚本是实际执行脚本的可移植副本，只改变路径和输出位置；Story 脚本不再哈希未发布的独立 trace。下面 `$reviewRecalc` 每次换新目录，已有结果不覆盖：

```powershell
$reviewRecalc = '.cache/core-review-recalc-NEW'
uv @reviewUv "$reviewRoot/scripts/analyze_results.py" $reviewRecalc
uv @reviewUv "$reviewRoot/scripts/analyze_story.py" $reviewRecalc
uv @reviewUv "$reviewRoot/scripts/audit_citation_format.py" $reviewRecalc
```

## 重新运行

可移植配置为 [adapters.json](inputs/adapters.json) 和实际客户端参数 [story-api.json](inputs/story-api.json)，仅有环境变量名字段，无鉴权值。原实现与评测框架不修改。每次显式输出目录必须新建；Core 可离线运行：

```powershell
uv @reviewUv -m Benchmarks core --adapters "$reviewRoot/inputs/adapters.json" --timeout 10 --output Benchmarks/outputs/agent_core/core/review-NEW
```

性能按原参数分别运行，避免与测试或其他负载并行；此命令沿用原调度偏差，不保证更正顺序：

```powershell
uv @reviewUv -m Benchmarks perf --adapters "$reviewRoot/inputs/adapters.json" --rounds 7 --batch 100 --warmup 2 --measure timing --timeout 10 --output Benchmarks/outputs/agent_core/perf/review-timing-NEW
uv @reviewUv -m Benchmarks perf --adapters "$reviewRoot/inputs/adapters.json" --rounds 7 --batch 100 --warmup 2 --measure memory --timeout 10 --output Benchmarks/outputs/agent_core/perf/review-memory-NEW
```

真实 Story 另需取得 catalog 对应全量语料、原冻结快照并部署同指纹模型。评审包中的摘录不能冒充全量检索输入，基线也不含后续 `18153d2` 的服务启动脚本。模型身份与启动参数见[模型记录](evidence/reports/core-probe-live-r001/model-identity.json)，不要执行历史报告里不存在于本分支的启动命令。准备服务和数据后，下列命令会实际请求模型；本次发布未执行：

```powershell
uv @reviewUv -m Benchmarks agent --adapters "$reviewRoot/inputs/adapters.json" --config "$reviewRoot/inputs/story-api.json" --corpus rag/data/corpus/corpus.jsonl --raw-root data/raw/genshin_wiki_data_20260605 --scenario a01 --scenario a06 --scenario a12 --repeats 3 --max-steps 8 --top-k 5 --timeout 240 --measure timing --output Benchmarks/outputs/agent_story/agent/review-NEW
```

未提供 `--model-service-pid` 时服务资源单列未测，不能沿用旧PID。新运行结果写忽略的 outputs，不写回证据目录。发布检查结果见 [verification.json](verification.json)。

## Dev Note

无。
