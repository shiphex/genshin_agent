---
kind: reference
description: "维护本地产物类别、生成边界、保留和恢复规则。"
---
# 本地产物管理

## 摘要

`rag/data/` 是本地产物库，整个目录继续由Git忽略；[catalog](../catalog.json)登记位置、版本、编号、旧坐标和保留方式。[身份与运行规则](artifacts.md)。原始爬虫快照仍位于共享 `data/raw/`，不迁入本目录。

## 目录

- [八类目录](#八类目录)
- [入口与兼容](#入口与兼容)
- [生成与关闭](#生成与关闭)
- [历史资料](#历史资料)
- [Dev Note](#dev-note)

## 八类目录

| 目录 | 内容与保留 |
| --- | --- |
| `corpora/<资源>/vN/` | 派生语料、审计、排除、覆盖与来源清单；已完成版本不覆盖 |
| `prepared/<题库>/v<输入版本>/rNNN/` | 原文准备副本及生成清单；当前入口由datasets.prepared_current指定 |
| `runs/<实验>/rNNN/` | 完整请求、回答、清单、配置和实际执行代码；历史原件长期保留 |
| `reviews/<复核>/rNNN/` | 完整第三方复核与本地历史复核材料；摘要与输入仍在Git中的eval/reviews |
| `releases/<发布物>/vN/` | ZIP、原清单和校验值；原文件名、包内源码commit与字节保持不变 |
| `baselines/<资源>/vN/` | 原快照保护／恢复核验哈希；生成基线不是恢复完成 |
| `archive/<任务>/rNNN/` | 已结束任务的资料包、before.zip、audit.zip和索引；恢复使用新目录 |
| `tmp/<任务>/rNNN/` | 一次性生成、检查、解压工作区；无唯一原件后结束清理 |

运行的请求、结果和保护清单保持成组，不按扩展名跨目录拆散。实际执行的 `work.py`、`runner_executed.py` 留在运行组；辅助整理／检查脚本与闭环任务日志压缩到audit.zip，保留原项目路径和逐文件SHA。

## 入口与兼容

通过 `artifact_catalog.dataset_path()` 读取当前语料，指定版本则读取固定版本。runs指向具体执行，prepared_current指向选定成功副本，不按目录日期排序选latest。失败构建不会替换当前语料或副本。

legacy_paths保存旧地址到新位置的最长前缀映射。resolve_data_path解析旧绝对／相对坐标并拒绝越界；read_data_bytes还可以读取已归档的辅助文件。封存JSON的旧路径、参数、结束状态和哈希不改写。

旧Git输入通过legacy_input_paths定位；若当前输入修订或换行变化，发布工具只接受封存哈希一致的字节，必要时从原ZIP读取。未知或不符的输入拒绝打包，不补猜内容。旧ZIP仍按原布局恢复。历史报告及已有Hugging Face发布绑定全量语料v1，不把当前新版本冒充原输入。

## 生成与关闭

```powershell
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/prepare_rag_mvp.py --all
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/prepare_eval.py
uv --cache-dir .cache/uv run --offline --no-python-downloads --python 3.11 python rag/scripts/evaluate_rag_mvp.py --dataset full --retrieval-only
```

上述命令分别生成新语料版本、新原文副本、新检索运行；本次整理未重建用户语料或调用真实模型。成功构建／准备才切换对应入口。显式输出须位于相应类别或新的tmp任务目录，拒绝已有目录和已完成产物的嵌套写入。题库版本修改须同步catalog；自定义输入先登记资源ID。

完成生成不表示语义或用户验收通过。任务关闭时，可再生成临时文件可以清除，唯一回答、复核、反馈和实际执行程序必须保留。归档前逐文件核对并实际恢复读取，之后才移除展开资料。最终包与索引保持可读，过程脚本、日志集中audit.zip，不反复留下完整解压树。

新运行清单的executed_copy保存实际执行的RAG源码字节，便于工作区未提交或之后修正时回查；配置内容只记哈希，不复制鉴权值。早期纯检索验证仅有指纹时保留该限制，不补写为完整源码快照。

## 历史资料

- 全量／样本语料在corpora/story_full/v1和story_sample/v1；原检索记录分别在runs/full_retrieval/r001、sample_retrieval/r001。
- 24题对照／六题诊断在runs/model_comparison/r001、generation_diagnosis/r001。
- 样本两轮模型回答在runs/sample_model_comparison/r001（旧版未记录结束原因）与r002，不继承successful计数为完整API响应证明。
- 导入开发题副本为prepared/story_dev/v0.5/r001，本轮准备验证为r002，110题／445处来源，仍待用户验收。
- 第三方原件在reviews/dev_sample/r001；benchmark_source/r001的历史表仍按2.0.0旧覆盖口径阅读。
- releases/review/v1是不交付候选，v2历史封存，v3当前待上传；包内容不变。
- Git bundle在archive/git_history/r001，原快照基线在baselines/wiki_snapshot/v1。
- 三轮整理资料在archive/housekeeping/r001～r003，本次数据迁移闭环为r004，仅本地保存。

新克隆须独立提供或恢复本地资料；Git、索引和公开摘要不能代替完整数据备份。

## Dev Note

无。
