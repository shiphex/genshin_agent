---
kind: reference
description: "维护当前基线文件、独立输出和后续更新规则。"
---
# 当前基线与输出管理

## 摘要

[catalog](../catalog.json)的 schema_version=2，当前baseline_id=current-003，保留20题摘要与历史提示词原件，Smoke输入及说明归入eval/smoke；本次迁移未改题目或结果字节，不表示语义或用户验收通过。资源身份、路径、大小及 SHA-256 只有这一份权威登记；不保留旧实验索引、归档映射或重复 manifest。

## 目录

- [基线内容](#基线内容)
- [新输出与更新](#新输出与更新)
- [获取与清理](#获取与清理)
- [Dev Note](#dev-note)

## 基线内容

| 位置 | 内容 |
| --- | --- |
| `data/corpus/` | corpus.jsonl、audit.json、exclusions.jsonl、coverage.md |
| `eval/questions.json` | 110题定义，版本仍为0.5 |
| `eval/review20.json`、`data/review20/result.json` | 固定20题、原文与完整第三方核验原件 |
| `data/review20/summary.md` | 用户提供的第三方摘要与历史提示词记录，保持原字节 |
| `eval/smoke/questions.jsonl` | 历史运行实际处理的前三题，逐行提取 |
| `data/smoke/` | 完整结果、语义初审、冻结原文依据、两个实际执行源码副本 |

`data/` 共11个原件；现行说明在模块 README、eval 与 smoke 文档中维护，第三方历史摘要作为核验记录随结果保留。共享原始快照留在项目层。语料、题库及模型原件迁移时字节不变，管理信息重新登记。Smoke provenance 区分旧12题输入哈希与新三题文件；不声称新文件曾作为当时的输入。旧运行ID仅为原件内的历史身份，不提供路径兼容。

## 新输出与更新

新生成内容统一写入 `data/outputs/<用途>/rNNN/`；用途为 corpus、prepared、retrieval、model、review 或 hf，目录按需创建。已有目录、原始目录、基线及已有运行的嵌套目录拒绝写入；失败／中断编号不复用。普通运行不修改 catalog 或当前入口。

review用于新的题库核验记录，沿用 `artifact_catalog.reserve_output(root, 'review')` 的目录分配、`seal_inputs` 的输入封存和 `finish_output` 的执行登记；当前没有自动核验runner。用户要求落盘时才生成，执行完成仍保持review_status=not_reviewed，不把外部模型初审登记为用户验收。

构建、原文准备和评测的 run_manifest.json 记录执行状态、实际参数、输入文件哈希、Git commit、source_dirty和执行源码副本；配置只记指纹，不复制鉴权。新全量构建的原始目录目前仅记路径与快照名，未保存逐文件输入指纹。原文准备被手动中断时可能留下running状态，需人工核对，编号不复用。HF 导出由包内 manifest.json 维护固定白名单与发布信息，显式指定新目录。

基线更新是独立操作：明确替换集合，在新输出验证通过后再更新 catalog 的基线身份、路径、哈希及题库版本，完成所有引用核对。失败保持当前基线不变；现有工具没有自动提升基线的接口。不默认保留每次可重建副本，也不在生成成功时升级用户验收状态。

## 获取与清理

整个 `data/` 继续忽略；Git 保留正式实现、当前题目输入和文档，不能代替原件备份。新克隆缺本地文件时，catalog 校验明确失败；获取入口见[模块说明](../README.md#数据获取与验证)。

本次用户明确淘汰旧题库原型、实验、发布ZIP、Git bundle和整理归档，不另建完整备份。后续清理仍须明确范围；唯一回答、核验与用户反馈不能按临时文件自动删除。临时 HF 导出和原文副本在核验后可移除；保留需要交付的真实模型输出。

## Dev Note

无。
