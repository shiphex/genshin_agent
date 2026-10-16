---
kind: reference
description: "维护资料身份、编号、版本、状态及其验证规则。"
---
# 资料标识、版本与运行管理

## 摘要

[catalog.json](../catalog.json)是题库、实验、运行、复核和报告的统一索引。日期只记录来源快照或事件时间，不作为当前目录的实验身份。

## 目录

- [命名与职责](#命名与职责)
- [索引内容](#索引内容)
- [新运行](#新运行)
- [复核与状态](#复核与状态)
- [历史兼容与保留](#历史兼容与保留)
- [检查](#检查)
- [Dev Note](#dev-note)

## 命名与职责

| 对象 | 名称与位置 | 管理方式 |
| --- | --- | --- |
| 题库 | `eval/questions_dev.json`、`eval/questions.json` | 路径稳定，版本在文件和索引中记录 |
| 实验定义 | `experiments/<用途名称>/` | 输入与参数通过索引登记；Git记录修订 |
| 实验运行 | `<实验ID>/r001`、`r002` | 每次执行独立编号，失败或中断也保留 |
| 复核批次 | `eval/reviews/<用途名称>/r001/` | 对应题库版本与固定抽样输入，独立记录外部初审和用户验收 |
| 发布报告 | `reports/<实验ID>/<运行ID>/` | 关联某次运行，保留逐题关键摘录和概要 |
| 新完整结果 | `data/runs/<实验ID>/<运行ID>/` | 本地保存原始结果、输入指纹与运行清单 |

用途名称使用小写英文和下划线，例如 `model_comparison`；题数、模型、日期写入说明或元数据。`rNNN` 是唯一编号，不表达正确性或按日期排序；历史导入编号不要求与事件时间先后相同。

## 索引内容

- `datasets`：题库版本、当前语料及固定版本、prepared_current；本地语料可在新克隆中缺失，另行恢复。样本模型两轮已独立登记为sample_model_comparison。
- `experiments`：用途、定义状态、可复现输入。`active` 表示当前使用，`frozen` 表示保留既有输入与协议、仍可复跑，`retired` 不再接受新运行。
- `runs`：实验／运行ID、实际清单、报告位置和时间；artifacts是当前位置，legacy_artifacts记录旧封存坐标，legacy_id记录原实验ID。
- `reviews`：题库及版本、固定输入、摘要、完整本地复核位置、来源时间与独立状态。原始模型复核继续忽略。

索引只负责身份与定位，详细请求、上下文、参数、哈希和结束原因仍由实际运行清单及结果文件保存。旧运行的 `recorded_at` 逐项引用已有记录；缺失的创建时间保留 null，不从目录日期推测。

## 新运行

两个评测入口通过 `scripts/artifact_catalog.py` 分配编号。目录和索引更新有独占锁，目录存在或已有编号时不会覆盖；未登记但已存在的结果目录同样跳过。进程异常退出留下的锁不自动删除，应先确认没有其他执行进程。

纯检索示例，从项目根目录运行：

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/evaluate_rag_mvp.py --dataset full --retrieval-only
```

默认分配full_retrieval的下一个空闲编号。全量／样本无检索与RAG对照分别登记为model_comparison／sample_model_comparison，证据 × 参数诊断为generation_diagnosis。显式输出须在runs或新的tmp任务目录，同样登记编号并拒绝已有目录；诊断结果位于运行的model子目录。[语料、prepared和其他本地产物](data.md)。

每个新运行保存 `run_manifest.json`：输入、配置和执行源码的大小／SHA-256，实际选项、Git源码commit及工作区是否有未提交改动。`source_dirty=true` 时不能把commit当作完整执行版本，须结合文件指纹和相应代码备份定位。清单不复制配置内容或鉴权值。

`running` 结束后转为 `completed`、`completed_with_errors`、`failed` 或 `interrupted`。非法输入或服务失败不会覆写旧运行；已有输出拒绝发生在编号登记前。进程被强制终止时可能保留 `running` 和已存在目录，需要按实际日志人工核对，不自动登记完成。

## 复核与状态

当前没有自动复核runner。新复核先固定题库版本和抽样内容，在 `reviews` 登记下一个空闲编号，再保存摘要与独立原件；不能复用已有批次或把新题库版本套到旧输入上。程序索引检查核对材料路径，剧情语义仍单独复核。

三种状态分别记录：

- 执行状态只表示运行进度／完成情况，截断和不完整API结果记入 `completed_with_errors`。
- `review_status` 为 `not_reviewed`、`in_review`、`accepted` 或 `needs_revision`；accepted须对应用户明确验收，自动程序不会升级。
- `publication_status` 为 `not_published`、`pending_upload` 或 `available`；available须有实际分享／下载验证。

外部模型声称完成的复核用 `execution_status=completed_as_reported`，与用户验收分开。检索、API结束、引用合法性和语义正确性也不能相互替代。

## 历史兼容与保留

原始快照仍在共享原目录；模型结果、封存记录、归档和ZIP已按类型搬移，原字节及内嵌旧路径保持不变。legacy_paths解析旧坐标，archived_files定位audit.zip内成员。旧日期实验ID仍用于原矩阵核验，恢复旧发布包沿用原目录；当前报告清单schema为3，原包版本不变。

必要定义、题库、索引、复现输入和批准的报告进入Git；完整结果、原始复核、哈希基线、ZIP和临时文件继续忽略。新增复核或发布目录时同步更新 `.gitignore` 的明确白名单。

已结束的过程文件可核验归档；唯一模型回答、用户反馈和复核不得当临时文件删除。重跑生成新结果，不能恢复历史原件。[归档恢复](archives.md)。

## 检查

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/artifact_catalog.py
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/export_review_bundle.py check-views
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python -B -m unittest discover -s rag/tests -v
```

索引检查不把本地旧结果缺失当成语义失败；重建语料和取得历史回答仍是独立的数据恢复步骤。

## Dev Note

无。
