# 数据获取与发布状态

当前有两类独立发布物：Hugging Face 数据集用于全量派生 RAG 语料；`review-20261010-v3` 审阅资料包用于完整实验记录。GitHub提供精简诊断。两份审阅 ZIP 的外部地址尚未登记，状态仍为 **pending_upload**。

## Hugging Face 派生语料

目标仓库为 <https://huggingface.co/datasets/shiphex/genshin_agent_RAG>，首版为 `rag-full-20260605-v1`。它只包含 `rag/data/corpora/story_full/v1/` 的以下派生文件：

| 文件 | 字节数 | SHA-256 |
|---|---:|---|
| `corpus.jsonl` | 33,087,738 | `1fafb904a22126b1fa757d1f6a2c119f1fa10f5637d5d75bcccfb9425c6efed3` |
| `audit.json` | 1,073,603 | `7aec9fc7e7ec6d12c625d75e20168b33e6e18d38dc2e54d178866e6732d75a58` |
| `exclusions.jsonl` | 438,694 | `39079f6248bf8ed8fe227eb52c4b4906793740b1b35c3bb43145967c5228c269` |
| `coverage.md` | 58,645 | `1dd52c27ccd5db96165b5a588a28e7f67f969478ee4335f63300c086c3bf3aa6` |

语料为22,822条可回查片段；远端 `manifest.json` 记录同一版本、输入快照标识、行数、文件大小和哈希。Dataset Card 使用 `license: other`：原神及 Wiki 文本没有通过本仓库获得再许可，MIT 仅适用于发布者原创的脚本、清单与说明。发布不含原始快照、模型回答、审阅 ZIP、Git bundle、缓存或其他 `rag/data/` 内容；必须另行提供同一冻结快照才能重建或按 Pointer 回查。

本地 staging 已用 `rag/scripts/export_hf_dataset.py` 生成并校验，文件白名单、JSONL字段、行数和哈希均通过。远端状态为 **available**，revision 为 `592d198a9cde390005323a9f849c0d3981fb5a33`。已从该公开 revision 以未登录 HTTP 下载全部七个发布文件到新目录，并重算 manifest 哈希、解析 JSONL、确认22,822条记录和LFS对象可访问；验证时间为2026-10-10。

| 包 | 内容 | 状态 |
|---|---|---|
| 重点分析包 | 同版本源码／摘要、两轮完整回答和请求、封存记录、必要原字段／说话者及证据记录 | pending_upload |
| 完整复现包 | 同版本资料、完整冻结快照、22,822片段语料、审计／排除记录与历史实验 | pending_upload |

版本、源码commit、文件清单和包哈希见[manifest.json](manifest.json)及包内bundle_manifest.json，随包bundle_index.json／SHA256SUMS.txt校验整个ZIP。包源码固定后，分享链接索引可单独更新，不能把索引commit当作包内源码版本。

## 历史对应

本轮以970c114为边界合并后三次发布提交及精简工作，移除完整报告的可上传历史，保留源码／测试／小型输入。完整旧历史备份为本地忽略的Git bundle，未创建推送备份分支。未执行gc／prune，旧对象仍可能被本机reflog及Codex内部refs/codex引用保留，但不属于待推送分支／标签历史。首次按分支推送，不使用会携带内部引用的mirror推送。

v2两包与其哈希保持原样，源码030acd91bf43950cf054ef429d8a5a5dedd65bcf属于重写前历史；其代码和完整报告在v2 ZIP或本地Git bundle中恢复，不保证这个旧commit在公开GitHub可访问。v1候选包仍不作为交付。请优先上传v3。

## 审阅资料包上传与登记

1. 创建公开GitHub仓库，检查分支／标签及候选文件后配置remote，首次推送清理后的分支，无需强制推送。原数据、ZIP、缓存和Git bundle保持忽略。
2. 从rag/data/publication/review-20261010-v3上传两份ZIP、bundle_index.json及SHA256SUMS.txt到Google Drive。验证解压目录与本地历史备份不上传。Hugging Face 语料发布不包含这些文件。
3. 设置“持链接者可查看”，允许下载，见[Google Drive共享说明](https://support.google.com/drive/answer/7166529?hl=en)。用未登录窗口下载并核对哈希；通过后才标available。
4. 登记真实GitHub URL、两包链接和未登录测试时间，更新此页及manifest；未提供地址继续pending_upload。目标模型无法直接读取ZIP时，下载附加或分批提供资料。

## 校验与恢复

准备uv和Python3.11；下面的离线命令需要已有解释器。

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/export_review_bundle.py verify <下载的ZIP> --extract-to <尚不存在的目录>
```

先验证路径、清单、大小与SHA-256，再解压。禁止越界、符号链接、Windows路径别名和重复文件。ZIP保持项目相对结构；历史绝对路径原样保留，恢复时按相对后缀定位，不执行旧绝对命令。

重点包的publication/selected_source_fields.jsonl保存原字段与说话者，selected_evidence_records.jsonl保存必要语料记录，可校验摘要；两轮results.jsonl和诊断trials／requests保留完整上下文及回答。完整包可直接读取冻结语料，历史模型结果无需重建。当前源码与历史runner_executed.py分别标记；模型权重、运行服务、缓存和个人配置另备。

下次发布更新脚本VERSION和白名单，固定新的源码commit、生成新输出目录，保留旧资料包。

## 已验证的v3本地交付

包内源码commit：569175ff73fb3ef9a9f206a9308b627240e44a06。新源码提交已合并旧三次发布工作，之后索引更新独立记录。

| ZIP文件 | 字节数 | SHA-256 |
|---|---:|---|
| review-20261010-v3-focused.zip | 2879846 | d428ec5d0af81eaf80f314895d2ff9e2c679c94cebf2200e396eea116fd64d5b |
| review-20261010-v3-full.zip | 48218582 | f7a19c5102bc92ce6ec0ff131cd71e15d33bf639db817e9b3c27be25a831bd7c |

两包各覆盖30页／96份回答，摘要与原件定位校验通过；完整包读取22,822个片段。60项测试通过，原数据和v2包哈希未变。

本地历史备份：rag/data/archive/git_history/r001/precompact-cc17b40.bundle，旁置.sha256校验值；bundle verify和独立裸仓库恢复已通过。恢复时可在新目录git clone该bundle，不要推送恢复出的旧历史。
