# 数据获取与发布状态

当前发布版本为review-20261010-v3。GitHub和Google Drive真实地址尚未登记，状态 **pending_upload**。GitHub提供精简诊断，完整记录由两种ZIP保留。

| 包 | 内容 | 状态 |
|---|---|---|
| 重点分析包 | 同版本源码／摘要、两轮完整回答和请求、封存记录、必要原字段／说话者及证据记录 | pending_upload |
| 完整复现包 | 同版本资料、完整冻结快照、22,822片段语料、审计／排除记录与历史实验 | pending_upload |

版本、源码commit、文件清单和包哈希见[manifest.json](manifest.json)及包内bundle_manifest.json，随包bundle_index.json／SHA256SUMS.txt校验整个ZIP。包源码固定后，分享链接索引可单独更新，不能把索引commit当作包内源码版本。

## 历史对应

本轮以970c114为边界合并后三次发布提交及精简工作，移除完整报告的可上传历史，保留源码／测试／小型输入。完整旧历史备份为本地忽略的Git bundle，未创建推送备份分支。未执行gc／prune，旧对象仍可能被本机reflog及Codex内部refs/codex引用保留，但不属于待推送分支／标签历史。首次按分支推送，不使用会携带内部引用的mirror推送。

v2两包与其哈希保持原样，源码030acd91bf43950cf054ef429d8a5a5dedd65bcf属于重写前历史；其代码和完整报告在v2 ZIP或本地Git bundle中恢复，不保证这个旧commit在公开GitHub可访问。v1候选包仍不作为交付。请优先上传v3。

## 上传与登记

1. 创建公开GitHub仓库，检查分支／标签及候选文件后配置remote，首次推送清理后的分支，无需强制推送。原数据、ZIP、缓存和Git bundle保持忽略。
2. 从rag/data/publication/review-20261010-v3上传两份ZIP、bundle_index.json及SHA256SUMS.txt到Google Drive。验证解压目录与本地历史备份不上传。
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
