---
kind: workflow
description: "指导分析、设计、实施、验证和文档更新，并维护项目级检查命令。"
---
# 开发流程

## 摘要

从任务范围确定阅读材料，先核对事实与约束，再实施和验证，最后把结果写回对应维护位置。小改动使用短路径；只有重要决策才新增 Agent Note。文档参与整个过程，检查报告区分实际运行、静态核验和未验证事项。

## 目录

- [开始与分析](#开始与分析)
- [设计与实施](#设计与实施)
- [文档同步](#文档同步)
- [Python环境](#python环境)
- [验证](#验证)
- [CI V0](#ci-v0)
- [知识更新与交付](#知识更新与交付)
- [Dev Note](#dev-note)

## 开始与分析

先读根 [AGENTS](../AGENTS.md) 和 [context](../context.md)，检查分支、工作区及已有修改。改变模块组成、数据流或依赖前读[架构](architecture.md)；涉及 RAG 再读模块 README 相关章节和 context 当前区，按问题定位代码、测试或具体实验定义，只读与任务相关的当前资料。

输出应明确：要解决的问题、已知证据、约束、验收方式及不在范围内的内容。区分用户要求、实测事实、反馈和候选方案。发现冲突列出路径与证据，不能靠文字整理改变重要行为。

## 设计与实施

局部修字、链接和机械修改在任务说明中交代改动与检查即可，不要求独立设计文件、Agent Note 或全部实验重跑。改变跨模块职责、对外行为、数据兼容规则或有长期价值的技术取舍时，使用 [Agent Notes](../.agents/notes/README.md) 记录问题、方案、替代选择和验证要求。

按批准的设计约束实施；范围改变时说明影响，不把候选方案写成既成事实。新增行为先写能观察结果或失败路径的测试，再实现；文档、模板和配置不需要为标题或措辞编写镜像测试。必要的安全检查在操作前读取，原始数据与已有实验的保护规则见根 AGENTS。

文档创建与同步调用 [doc](../.agents/skills/doc/SKILL.md)，有精简或含义判断时用 [prose-standard](../.agents/skills/prose-standard/SKILL.md)；修改 skill 或上下文加载方式时用 [agent-experience](../.agents/skills/agent-experience/SKILL.md)。按需读其中参考资料，不必每次加载三个 skill。

## 文档同步

根 AGENTS 列出的接口、配置、格式、默认／失败行为、职责和数据流变化必须分析文档影响：定位[权威位置](AGENTS.md#一项事实一个权威来源)，核对实际代码与行为测试，重新生成可机械推导的内容，更新人工维护的语义、限制和架构，运行对应行为测试及下方 doc-sync。交付报告受影响文档、同步结果和未验证内容。内部修改未改变文档约定时，说明判断即可。不得为通过检查擅改已确认产品行为，或将实现错误写成新规范。

`doc-sync` 即 [doc_sync.py](../scripts/doc_sync.py)，顺序汇总预算、[链接](../scripts/verify_md_links.py)及[CLI 生成新鲜度](../rag/README.md#检索-cli-参考)检查；任一失败非零退出，检查只读，不调用模型、构建语料或联网。

链接源由 `git ls-files --cached --others --exclude-standard` 中存在的 Markdown 自动发现，含新增未忽略文件、Skill 和 Notes。链接目标必须存在且属于该清单或其目录；移动源码后未修入链会失败。外部 URL 不访问；仅未由 Git 提供的 `data/`、`rag/data/` 目标报告 `LOCAL` 豁免，不判断本机是否存在。冻结的 `rag/docs/recovery/crawler_handoff.md` 报告 `FROZEN` 并排除源扫描，指向它的链接仍检查。

V0 支持行内／引用式链接、图片、ATX／Setext 标题、重复标题后缀及显式 `<a id>`；排除代码和注释。HTML 链接、复杂嵌套 Markdown、外链可访问性及源码行号锚点未验证。生成只核对登记 CLI 的解析定义，运行时回退与语义靠测试和审查；独立 type-equiv [暂缓原因](../.agents/notes/implemented/2026-10-19-doc-sync-v0.md)。

## Python环境

根pyproject.toml、uv.lock和.python-version统一管理Python 3.11，环境为根`.venv`、缓存为`.cache/uv`。模块不另建项目／环境；普通检查仅用标准库，psutil属于可选benchmark依赖组。

```powershell
uv --cache-dir .cache/uv sync --locked --no-python-downloads --python 3.11
uv --cache-dir .cache/uv sync --locked --group benchmark --no-python-downloads --python 3.11
```

第一条准备普通环境，第二条安装benchmark依赖；缓存齐备后可加`--offline`。`uv sync`精确同步，可能卸载未选组；`uv run`保留额外依赖，benchmark命令须加`--group benchmark`。运行带`--locked`防止隐式改锁，依赖变更才更新锁文件。模块命令见各README，不用`--project Benchmarks`。

## 验证

以下项目级检查从仓库根目录通过 uv 执行，离线运行要求本机已有 Python 3.11：

```powershell
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B scripts/doc_sync.py
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B scripts/verify_doc_budgets.py --list
uv --cache-dir .cache/uv run --locked --offline --no-python-downloads --python 3.11 python -B -m unittest discover -s tests -v
git diff --check
```

第一条是统一文档门禁，第二条只展示预算余量，不能替代门禁；第三条验证项目检查器，修改检查器时运行。预算约定见[文档规范](AGENTS.md#字数门禁)。

| 改动 | 最小验证 |
| --- | --- |
| 文档、模板 | 对照事实来源、模板和术语，运行 doc-sync 与差异检查 |
| skill | 增加结构检查，并用独立只读场景实际执行其工作步骤；不将显式读取当成自动发现验证 |
| 项目级检查器 | 先验证有效和无效输入，再运行项目级测试与 doc-sync |
| RAG 行为 | 按 [RAG 验证入口](../rag/README.md#数据获取与验证)运行相关测试；按影响选择基线指纹、原文或HF导出检查 |
| 受控发布文档 | 核验修改后来源与 manifest；只刷新当前可维护文档的指纹，不改旧包或实验事实 |

修文档不默认执行会生成新产物、调用模型、上传或推送的命令。静态读到的默认值与实际执行结果分别报告；缺少环境、数据或授权时给出未验证项。对于本地数据链接，分别报告本机存在与新克隆不自带，不能混算成公共入口可用。

### CI V0

[GitHub Actions workflow](../.github/workflows/ci.yml) 在 Pull Request 创建、更新或重新打开，以及 `main` 分支 push 时运行，不按文件路径过滤。Docs 和 Python 两个独立 Job 使用 Ubuntu、Python 3.11 和 uv，权限仅为 `contents: read`，不启用依赖缓存。

Docs 运行上方 doc-sync 与项目级 unittest；Python 依次运行 [RAG unittest](../rag/README.md#数据获取与验证)、联网安装 benchmark 依赖组、[Benchmark 离线测试](../Benchmarks/README.md)。安装命令见上方 Python 环境；空缓存需下载 psutil，不加 `--offline`。安装或测试非零退出使所属 Job 失败，两 Job 独立。`--list` 不作门禁；CI 不运行 `git diff --check`。

这些测试使用临时合成数据和回环 HTTP 假服务，无需 API Key，不调用真实 LLM，也不下载模型或剧情数据。CI 不覆盖真实基线指纹、全量语料构建、检索 Smoke、模型评测及人工语义验收；通过 CI 不代表 GitHub 已配置合并必需检查。

## 知识更新与交付

先更新信息的[权威维护位置](AGENTS.md#一项事实一个权威来源)，再更新受影响导航。模块 context 记录最近检查、问题和反馈，详细实验材料仍由运行产物保存；根 context 只在阶段或入口变化时更新。不积累历史流水账。

Agent Note 只有实现和验证完成才转 implemented；保留尚未覆盖的验证范围，不把程序检查当成人工语义验收。普通页面的 Dev Note 不承担稳定约束。新模块、新文档或新实验输入按既有 Git 边界纳入，提交前查看候选文件和暂存清单；实际提交、推送和上传按任务授权执行。

交付说明列出变更、检查结果、未验证项及剩余问题。Doc Sync V0 到此止步；未来新增检查先明确实际契约及正负例，不预建通用框架或额外 skill。

## Dev Note

无。
