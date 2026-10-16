# 本地过程资料归档

本页指向 `rag/data/` 的链接仅本地可用，不随 Git 提供。获取与恢复见[数据获取说明](../reports/data_access.md)；这些归档包不属于 Hugging Face 语料发布范围，须独立取得。

2026-10-13 按用户批准的整理方案执行。正式语料、题库、模型结果、最新第三方复核和已有发布 ZIP 保持原路径；旧过程文件以 ZIP 保留原项目相对路径。整理前的完整文档文字另有本地备份，开发历史见[历史记录](history/development_20261013.md)。

本地归档根目录为 `rag/data/archive/housekeeping/r001/`，整个目录继续由 `.gitignore` 忽略。新克隆不会自动包含这些包，须独立备份或另行取得。`archive_index.json` 记录 ZIP 大小、SHA-256、原文件数量和恢复验证状态；`SHA256SUMS.txt` 用于校验 ZIP，各包内 `archive_manifest.json` 记录逐文件路径、大小和哈希。

## eval-annotations

[eval-annotations.zip](../data/archive/housekeeping/r001/eval-annotations.zip)保存原 `rag/data/eval_annotations/` 下的 28 个文件：旧标注预览、旧工具、原文字段副本、语料副本和过程记录。已移除展开目录。

## eval-rebuild

[eval-rebuild.zip](../data/archive/housekeeping/r001/eval-rebuild.zip)保存原 `rag/data/eval_rebuild/` 下的 72 个过程文件：旧100题、生成轮次、独立复核、原文材料、封存输入、保护哈希和一次性修订脚本。[14题历史复核表](../data/reviews/benchmark_source/r001/review.md)保留原位置，按 2.0.0 的旧覆盖口径阅读。

## eval-coverage

[eval-coverage.zip](../data/archive/housekeeping/r001/eval-coverage.zip)保存原 `rag/data/eval_coverage_compact/` 的 11 个文件：2.0.1 覆盖摘要迁移备份、候选题库、验证、保护哈希及脚本。已移除展开目录。

## eval-dev

[eval-dev.zip](../data/archive/housekeeping/r001/eval-dev.zip)保存原 `rag/data/eval_dev/` 的 28 个历史文件，包括各版本草稿、原文准备副本、基线和一次性脚本。[0.5版最终原文副本](../data/prepared/story_dev/v0.5/r001/questions.json)保留原位置；正式题库仍为 `rag/eval/questions_dev.json`。新生成副本继续选择新路径。

## publication-checks

[publication-checks.zip](../data/archive/housekeeping/r001/publication-checks.zip)保存原 `rag/data/publication_checks/` 及 `rag/data/` 根目录三份发布辅助脚本，共 257 个文件：精简报告检查、薄Git工作副本、工作前文档、哈希和一次性检查工具。已移除展开资料。

## documentation-before

[documentation-before.zip](../data/archive/housekeeping/r001/documentation-before.zip)保存整理前 `context.md`、`rag/context.md`、`rag/README.md`、`rag/eval/README.md` 和 `.gitignore` 的原字节。

## 恢复

1. 用 `Get-FileHash -Algorithm SHA256 -LiteralPath <ZIP>` 核对 `SHA256SUMS.txt`／`archive_index.json`。
2. 在项目内选择一个不存在的新目录，例如 `rag/data/tmp/restore-<新的任务>`，不覆盖当前题库、原始快照或正式结果。
3. 从项目根目录通过 uv 解压所需包：

   ```powershell
   uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python -m zipfile -e rag/data/archive/housekeeping/r001/eval-rebuild.zip rag/data/tmp/restore-<新的任务>
   ```

4. 按包内 `archive_manifest.json` 核对每项文件大小与 SHA-256。包内路径从项目根开始；例如旧题库恢复到 `<新目录>/rag/data/eval_rebuild/20261011_pilot_v2/questions_v1_original.json`。

包内资料是历史输入、输出和当时的代码。阅读与核验使用新恢复目录；旧绝对路径和历史脚本不自动执行，也不回填当前正式题库。

## 已清除的重复副本

`rag/data/releases/review/v1/`、v2、v3 下的六个 `verified_restore_focused/full` 目录合计 35,196 个文件、515,709,932 字节，与对应 ZIP 全部一致后移除。ZIP、清单、校验值和包内源码版本不变。需要恢复发布资料时使用[发布恢复命令](../reports/data_access.md#校验与恢复)。

`rag/data/archive/git_history/r001/restore_check.git/` 在原 Git bundle 哈希、独立 bare 克隆、fsck 及对象／引用覆盖核验通过后移除；`.bundle` 和 `.sha256` 保留。空标注目录和 Python 字节码缓存一并清除。

本次归档过程、删除清单、保护基线、验收与辅助脚本均只在本地归档根目录保存。已有发布包不包含最近题库过程资料，不能替代这批归档。
