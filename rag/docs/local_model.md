---
kind: reference
description: "配置 llama.cpp 显式启动、本机私有覆盖及三档模型调用预算。"
---
# 本地模型配置

## 摘要

[公共配置](../config/local_api.json)维护 API、生成档位及 llama.cpp 候选参数；本机路径使用 Git 忽略的覆盖文件。评测仅连接服务，启动需要单独执行命令。设计原因和未完成的性能验收见[讨论记录](../../.agents/notes/proposed/2026-10-28-local-model-config.md)。

## 目录

- [本机信息与隐私](#本机信息与隐私)
- [启动与调用](#启动与调用)
- [字段与合并](#字段与合并)
- [限制与验证](#限制与验证)
- [Dev Note](#dev-note)

## 本机信息与隐私

复制 `rag/config/local_api.local.example.json` 为同目录 `local_api.local.json`，填写 `llama_cpp.model_path`（实际 GGUF 文件，不能只写缓存目录）、`executable`（命令名或绝对路径）和 `device`（通过 `llama-server --list-devices` 核对）。公共配置不含个人目录和设备选择；示例中的路径仅为占位。

`rag/config/*.local.json` 已由 Git 忽略；自定义 `name.json` 会读取相邻 `name.local.json`，也须位于该忽略范围或自行补忽略规则。不对已跟踪文件使用 assume-unchanged，不把真实路径填回公共 JSON。Git 忽略不加密文件，也不阻止 `git add -f`；提交前用 `git check-ignore -v -- rag/config/local_api.local.json` 和暂存清单核对。鉴权值只放环境变量，配置仅写 `api_key_env` 名称，未知字段拒绝。

客户端获得的配置剔除启动字段；本机模型路径、可执行文件和设备名不进入模型请求或配置参数清单。运行产物仍按各模块规则本地保存，可能含 API 地址和完整回答；分享前独立检查。真实 llama-server 自身日志可能输出本机路径。

## 启动与调用

在仓库根目录按[统一 uv 环境](../../docs/development.md#python环境)运行：

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B rag/scripts/serve_local_model.py --dry-run
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B rag/scripts/serve_local_model.py
```

第一条校验配置、本地程序与 GGUF 是否存在，只输出隐藏路径和设备值的参数列表，不加载权重。第二条实际以前台进程启动服务，Ctrl+C 停止；不会后台常驻、下载模型或停止已有服务。地址、端口、模型别名从公共 API 配置取得；启动仅接受本地 HTTP `/v1`，文件缺失或参数非法时非零退出。若端口已占用，由 llama-server 报错，不接管占用进程。

服务就绪后，以下命令会真实请求模型并写入新的模型评测输出；不重现旧回答：

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B rag/scripts/evaluate_rag_mvp.py --profile standard
```

`--profile simple|standard|deep` 显式选档，省略时使用 JSON 的 `profile`。Benchmark 的 `agent`、`preflight` 使用相同参数，入口见[说明](../../Benchmarks/agent_story/README.md#真实执行)。未实现自动分档。切换请求档位无需重启；修改上下文、设备、缓存精度等启动参数需要重启。

## 字段与合并

[读取实现](../scripts/local_model_config.py)先递归合并公共 JSON 与可选同名 `.local.json`，再应用选中档位；档位字段覆盖同级根字段，`generation` 逐字段合并。CLI 只覆盖档位选择。根 `base_url/model/api_key_env/top_k/seed` 供各档共用；根 `top_k` 是检索条数，`generation.top_k` 才是采样。`generation` 支持 temperature、seed、top_p、top_k、min_p、presence_penalty、frequency_penalty、repeat_penalty，优先于同名根字段。旧平面配置仍可读取，缺省思考关闭；`model=null` 保留客户端原有单模型发现行为，但启动入口需要明确别名。

公共配置的当前档位如下；输出上限包含思考和正文，超时是每次 API 调用的失败保护，不是速度保证。

RAG 检索使用根 `top_k`；Benchmark 检索仍由其 CLI 的 `--top-k` 控制。

`tool_choice_mode` 允许 `native`（缺省）、`required_single_tool` 和 `required_single_tool_prefill`（当前公共值），不作为采样字段发送。后两种将指定函数转换为唯一目标工具加 required；目标必须唯一。prefill 仅适用于当前 Qwen3.5 工具模板：请求须以 user/tool 消息结束，附加临时 assistant 内容 `<tool_call>\n` 并设置 `continue_final_message=content`、`add_generation_prompt=false`，直接进入工具格式，显式关闭该次思考并将已有思考预算置0。普通请求和字符串策略不转换，后续恢复原工具、消息和档位。指定调用须正常工具结束、名称一致且参数为 JSON 对象，否则失败，不降级或重试。`request` 保存模式、原始指定及实际 payload；前缀不进入正常历史，无工具 RAG 不受影响。

| 档位 | 思考 | thinking_budget_tokens | max_tokens | timeout（秒） |
| --- | --- | --- | --- | --- |
| simple | 关闭 | 0 | 1024 | 30 |
| standard（默认） | 开启 | 1024 | 3072 | 90 |
| deep | 开启 | 8192 | 12288 | 600 |

客户端发送 `chat_template_kwargs.enable_thinking`、`thinking_budget_tokens` 与 `reasoning_format=deepseek`；不以猜测的 `reasoning_budget` 请求字段替代。预算必须为非负整数并小于总生成上限。RAG 只返回最终正文，Benchmark 保留原始响应但正常历史剔除 `reasoning_content`；只有思考、没有正文或原生工具调用不能算可用回答，截断状态仍单独判断。RAG 摘要和执行参数记录实际生成设置，Benchmark 记录剔除启动信息后的有效配置。

`llama_cpp` 的启动字段由[启动实现](../scripts/serve_local_model.py)构造参数：ctx_size、gpu_layers、parallel、batch_size、ubatch_size、flash_attn、cache_type_k、cache_type_v，以及本机 executable、model_path、device。始终使用单设备模式、离线、不加载视觉投影、Jinja、思考自动模式和关闭自动 fit；公共值采用 16K、全 GPU、单槽位、256/128、auto、F16。`--predict` 取各档总生成上限最大值，思考默认值取默认档，请求可覆盖。每槽上下文必须大于所有档位的生成上限；不自动删证据或压缩历史。

## 限制与验证

约 4GB 是显存目标，参数没有实现显存硬上限；权重文件大小不等于显存峰值。16K 中 deep 上限会挤压输入空间；调用者负责使输入、思考与正文总量容纳于上下文。超预算后再评估 Q8 KV、缩短上下文或 CPU 卸载，不能仅凭启动成功认定兼容、游戏流畅或剧情正确。

2026-10-30 精确 a06 重放确认 required 语法已启用，但允许不限长度的前置正文，仍会耗尽1536 token；旧短输入验证不足以保证该输入完成。前缀模式已在相同系统提示、用户问题与生成上限下验证原生调用；它增加输入前缀、跳过强制步骤的思考，不是原 A 的相同请求，须重建 O/A 对照。不保证其他模板、参数 schema、预算精确执行、剧情或性能。预算与解析见[b3fed31b9 源码](https://github.com/ggml-org/llama.cpp/blob/b3fed31b9/tools/server/server-common.cpp)，采样见[Qwen 模型卡](https://huggingface.co/Qwen/Qwen3.5-4B#best-practices)；更换版本或模板须重新验证。

## Dev Note

无。
