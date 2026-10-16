# Qwen3.5-4B Q4 完整链路 Smoke Test 方案 v1

保存日期：2026-10-14，Asia/Singapore。对应运行：`model_comparison/r002`。

本文件保存本会话中用户明确要求执行的方案。下文“已确认方案”保留该方案正文；“执行记录与核验入口”另列实际产物和限制。本文件在运行完成后按用户要求整理保存，不是执行前封存的文件，也不替代实际执行清单。后续调整另建 v2，保留本版。

## 已确认方案

### 目标与范围

使用本地 GGUF 和现有评测脚本，运行旧版 q01–q03 的 `baseline`／`rag` 对照，共 **6 次正式模型调用**，完成技术验收与逐题初审。

沿用现有语料、检索和提示词；开发题库 110 题的接入及 Q4／Q6 能力比较留待后续。本轮无需修改评测代码或公共接口。

### 启动与预检

- 在用户指定目录递归查找 GGUF，要求唯一匹配 `Qwen3.5-4B-Q4_K_M.gguf`，记录完整路径、文件哈希和 llama.cpp 版本。
- 使用已安装的 `b9837`，明确选择 RTX 4060 的 Vulkan 后端：

```powershell
$smokeModel = Get-ChildItem -LiteralPath 'D:\Models\GGUF\Qwen3.5-4B-Q4_K_M' -Filter 'Qwen3.5-4B-Q4_K_M.gguf' -Recurse
if (@($smokeModel).Count -ne 1) { throw '模型文件必须唯一匹配' }

llama-server.exe -m $smokeModel.FullName `
  --host 127.0.0.1 --port 8000 `
  --device Vulkan0 --split-mode none -ngl all `
  -c 8192 --parallel 1 --jinja --reasoning off `
  --no-mmproj --no-context-shift
```

- 执行时后台隐藏启动，保存日志和进程 ID；通过健康检查、`/v1/models` 与启动日志确认模型身份、GPU 卸载及实际上下文。
- 使用服务模板和分词接口核对三题实际提示词，确保输入加 1536 tokens 输出预算可放入上下文；不裁剪证据来掩盖超限。
- 单独发送一次简短中文回答请求，检查正文非空、正常结束及关闭思考的行为。此调用不计入正式六次。

### 正式执行与结果保存

通过已定位的 uv 运行：

```powershell
& 'C:\Users\ZHmso\.local\bin\uv.exe' --cache-dir .cache/uv run `
  --offline --no-python-downloads --python 3.11 `
  python rag/scripts/evaluate_rag_mvp.py --dataset full --limit 3
```

- 沿用现有配置：Top5、温度 0、seed 42、输出上限 1536、超时 180 秒；`model: null` 从单模型服务识别 ID。
- 由 catalog 分配新的 `model_comparison/rNNN`，保存回答、摘要、复核材料和执行清单；补存服务版本、启动参数、模型身份及预检记录。
- 保留已有暂存修改、历史回答与纯检索结果。任何失败或截断均如实记录，不覆盖首次结果，不自动调整参数重跑。
- 完成后仅停止本轮启动的服务进程。启动失败时保存诊断，不自动升级运行时或更换模型。

### 验收与交付

- **链路验收：**三题各有两组结果，六次调用正文非空、均为 `finish_reason=stop`；错误、截断和其他未完成计数均为零。
- **检索与引用：**分别报告证据组覆盖和引用 ID 合法性；无检索组不要求引用，RAG 引用还需检查是否支持对应断言。
- **逐题初审：**对照冻结原文检查摩拉名称来源、神之心交易双方、归离原命名，并检查书籍记载限定、无依据扩写及数值／攻略泄漏。
- **结论边界：**链路通过与语义初审分开报告，用户验收保持待确认；三题结果不外推为整体模型能力。
- 更新根目录与 RAG 上下文，校验新运行索引及产物一致性。交付简要结果表和本地报告链接；默认不提交或推送。

## 执行记录与核验入口

以下为完成运行后核对的事实，不是新增验收要求。运行数据仅本地保存，新克隆须另行提供备份；此方案文档可随 Git 保存。

| 核验对象 | 本次依据 |
| --- | --- |
| 运行身份、输入与实际源码 | [run_manifest.json](../../data/runs/model_comparison/r002/run_manifest.json)：`model_comparison/r002`，源码 commit `0bf881628d99f1c66ed82f51628540ff9b22602b`，`source_dirty=true`；两份实际执行源码位于同组 `executed_source/` |
| 模型身份 | [runtime_identity.json](../../data/runs/model_comparison/r002/runtime_evidence/runtime_identity.json)：完整 GGUF 路径、大小和 SHA-256；[server_version.json](../../data/runs/model_comparison/r002/runtime_evidence/server_version.json)：b9837（b3fed31b9） |
| 服务生命周期 | [server_process.json](../../data/runs/model_comparison/r002/runtime_evidence/server_process.json)：实际启动参数与 PID；[server_shutdown.json](../../data/runs/model_comparison/r002/runtime_evidence/server_shutdown.json)：仅停止本轮进程 |
| 预检与上下文 | [preflight_summary.json](../../data/runs/model_comparison/r002/runtime_evidence/preflight_summary.json)：独立预检 1 次；RAG 输入 2559／2615／2616 tokens，实际 8192 上下文、1 槽位 |
| 六次正式结果 | [results.jsonl](../../data/runs/model_comparison/r002/results.jsonl)及[summary.json](../../data/runs/model_comparison/r002/summary.json)：六次均 stop、错误／截断／其他未完成均为 0；三题预期证据组全部覆盖 |
| 初审与冻结依据 | [smoke_review.md](../../data/runs/model_comparison/r002/smoke_review.md)、[semantic_review.json](../../data/runs/model_comparison/r002/semantic_review.json)、[frozen_review_sources.json](../../data/runs/model_comparison/r002/frozen_review_sources.json)：错误原句、原字段、Pointer、字符范围和原文件哈希 |
| 产物完整性 | [verification.json](../../data/runs/model_comparison/r002/verification.json)及[smoke_artifact_hashes.json](../../data/runs/model_comparison/r002/smoke_artifact_hashes.json)：155 处来源范围、11,614 个已有文件保护核验及 68 份产物指纹；哈希清单不含自身 |

本次 GGUF SHA-256：`00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`。

固定执行输入的 SHA-256 以下列原运行清单为准：

| 输入 | SHA-256 |
| --- | --- |
| [全量语料](../../data/corpora/story_full/v1/corpus.jsonl) | `1fafb904a22126b1fa757d1f6a2c119f1fa10f5637d5d75bcccfb9425c6efed3` |
| [旧题 JSONL](../full_retrieval/questions.jsonl) | `669cdee767006906246a595f31476a2219d98dee3db2c1c06c8eed2edc618988` |
| [共享配置](../../config/local_api.json) | `42930815410d85bb2ad2d597332ab0ba8044feb97c507cc780a4267ed87d3787` |

实际调用由保留在 `runtime_evidence/work.py` 的辅助程序在 uv 提供的 Python 3.11 环境中启动 runner，内部 argv 增加 `-B`；实际命令见 [formal_command.json](../../data/runs/model_comparison/r002/runtime_evidence/formal_command.json)。六份 `*_expected_formal_request.json` 是重建请求，已核对消息与正式 prompt token 数一致，不是 HTTP 抓包。

核验限制：默认服务日志没有逐层 GPU 分配明细，GPU 使用由 Vulkan0 参数、设备列表、PID、显存和利用率观测佐证；六次正式原始 HTTP 响应未完整抓取，runner 保存正文、usage 和结束状态。技术链路通过，但初审仍发现回答错误、错引与引用格式问题；语义状态保持 `pending_human_review`，catalog 用户状态为 `not_reviewed`。

后续复跑从项目根目录执行，保留本版方案及本次运行，分配新的 `rNNN`；先核对输入哈希与服务设备编号。模型、运行时、输入或参数变更应明确记录，不能将新输出替换成本次结果。
