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
- [验证](#验证)
- [知识更新与交付](#知识更新与交付)
- [Dev Note](#dev-note)

## 开始与分析

先读根 [AGENTS](../AGENTS.md) 和 [context](../context.md)，检查分支、工作区及已有修改。改变模块组成、数据流或依赖前读[架构](architecture.md)；涉及 RAG 再读模块 README 相关章节和 context 当前区，按问题定位代码、测试或具体实验定义，只读与任务相关的当前资料。

输出应明确：要解决的问题、已知证据、约束、验收方式及不在范围内的内容。区分用户要求、实测事实、反馈和候选方案。发现冲突列出路径与证据，不能靠文字整理改变重要行为。

## 设计与实施

局部修字、链接和机械修改在任务说明中交代改动与检查即可，不要求独立设计文件、Agent Note 或全部实验重跑。改变跨模块职责、对外行为、数据兼容规则或有长期价值的技术取舍时，使用 [Agent Notes](../.agents/notes/README.md) 记录问题、方案、替代选择和验证要求。

按批准的设计约束实施；范围改变时说明影响，不把候选方案写成既成事实。新增行为先写能观察结果或失败路径的测试，再实现；文档、模板和配置不需要为标题或措辞编写镜像测试。必要的安全检查在操作前读取，原始数据与已有实验的保护规则见根 AGENTS。

文档创建与同步调用 [doc](../.agents/skills/doc/SKILL.md)，有精简或含义判断时用 [prose-standard](../.agents/skills/prose-standard/SKILL.md)；修改 skill 或上下文加载方式时用 [agent-experience](../.agents/skills/agent-experience/SKILL.md)。按需读其中参考资料，不必每次加载三个 skill。

## 验证

以下项目级检查从仓库根目录通过 uv 执行，离线运行要求本机已有 Python 3.11：

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python -B scripts/verify_doc_budgets.py
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python -B scripts/verify_doc_budgets.py --list
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python -B -m unittest discover -s tests -v
git diff --check
```

第一条是预算门禁，第二条只展示字数和余量，不能替代门禁；第三条验证预算检查器自身，修改检查器时运行。预算清单与计数约定见[文档规范](AGENTS.md#字数门禁)。

| 改动 | 最小验证 |
| --- | --- |
| 文档、模板 | 对照事实来源、模板和术语，检查相对路径／锚点，运行预算与差异检查 |
| skill | 增加结构检查，并用独立只读场景实际执行其工作步骤；不将显式读取当成自动发现验证 |
| 项目级检查器 | 先验证有效和无效输入，再运行项目级测试与预算门禁 |
| RAG 行为 | 按 [RAG 验证入口](../rag/README.md#数据获取与验证)运行相关测试；按影响选择基线指纹、原文或HF导出检查 |
| 受控发布文档 | 核验修改后来源与 manifest；只刷新当前可维护文档的指纹，不改旧包或实验事实 |

修文档不默认执行会生成新产物、调用模型、上传或推送的命令。静态读到的默认值与实际执行结果分别报告；缺少环境、数据或授权时给出未验证项。对于本地数据链接，分别报告本机存在与新克隆不自带，不能混算成公共入口可用。

## 知识更新与交付

先更新信息的[权威维护位置](AGENTS.md#一项事实一个权威来源)，再更新受影响导航。模块 context 记录最近检查、问题和反馈，详细实验材料仍由运行产物保存；根 context 只在阶段或入口变化时更新。不积累历史流水账。

Agent Note 只有实现和验证完成才转 implemented；保留尚未覆盖的验证范围，不把程序检查当成人工语义验收。普通页面的 Dev Note 不承担稳定约束。新模块、新文档或新实验输入按既有 Git 边界纳入，提交前查看候选文件和暂存清单；实际提交、推送和上传按任务授权执行。

交付说明列出变更、检查结果、未验证项及剩余问题。未来可增加链接、模板结构和 Notes 生命周期的自动检查，须先确定维护位置、范围与有效／无效样例，不提前引入空目录、通用框架或额外 skill。

## Dev Note

无。
