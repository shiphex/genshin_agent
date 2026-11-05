---
kind: reference
description: "定义结构化语料V2、精简模型证据、候选出处迁移和本地HF加载。"
---
# 结构化语料与证据

## 摘要

V2保留chunk内逐句关系、实体上下文及来源；构建和出处迁移只产生独立候选，不切换[catalog](../catalog.json)默认基线。当前实测与未决项见[context](../context.md)，取舍见[决策记录](../../.agents/notes/proposed/2026-11-05-structured-rag-corpus.md)。

## 目录

- [记录与来源](#记录与来源)
- [构建和迁移](#构建和迁移)
- [模型证据](#模型证据)
- [HF加载](#hf加载)
- [Dev Note](#dev-note)

## 记录与来源

JSONL每行一个chunk。完整校验由[corpus_schema.py](../scripts/corpus_schema.py)维护；[导出模块](../scripts/export_hf_dataset.py)的feature_definition同时生成HF类型和数据卡。

| 字段 | 含义 |
| --- | --- |
| schema_version、id、title | 版本2；s2前缀ID绑定快照、文件哈希、知识类型和有序来源范围；标题保留展示路径 |
| knowledge_type | dialogue；character_profile；character_story（含冒险笔记及剧情权能）；character_voice；entity_lore（物件、装备、生物设定）；book_text；quest_description；wiki_compilation |
| metadata | source_family、entity的type/name、source_version，以及context的chapter/act/task_step/path/related_quests；只用上游明确值 |
| source | snapshot、file、file_sha256、kind；Wiki摘录／编纂不自动成为官方事实 |
| content | turns和sections两个对象列表，不适用为空数组 |
| text | 从结构生成的检索正文，索引仍读取title+text |

turn包含kind、source_type、speaker、text、row_pointer、pointer、span、options、quality_flags。kind区分speech/narration/choice/unknown；缺失speaker为null，上游空字符串仍为空。旁白正文中的名字不自动变成说话者。choice整组保留，text/pointer/span为null，每个options成员单独保存text/pointer/span；分支未知。

section保存field、heading_path、text、pointer和span，区分角色章节、装备部件、物件字段、书卷描述及正文。span按解码后原字段计算零基半开区间。默认800字符目标，在完整对象间切块；单条超长对话或选项组允许超限。

未知对话类型保留unknown并标记；非法字段、未支持家族和过滤项进入审计。旧格式只读兼容，不从旧展示文本补造turn。过滤与原页验证沿用现行规则，全量扫描不等同全部剧情完整。

## 构建和迁移

以下从根目录经uv执行，环境见[开发说明](../../docs/development.md#python环境)。

```powershell
uv run --locked --python 3.11 python -B rag/scripts/migrate_sources.py --old-archive E:/Workplace/Learn_project/genshin_wiki_data/genshin_wiki_data_20260605.zip
uv run --locked --python 3.11 python -B rag/scripts/prepare_rag_mvp.py --source-review rag/data/outputs/prepared/r004/source_issues.json
```

旧ZIP只读，不恢复旧raw目录；兼容其未标UTF-8文件名。迁移按原文、角色、类型与流程匹配，显示变化仅用于比对，实际写入新版原字段。输出110题0.6候选、原batches结构的20题候选、逐项报告及异常清单；不改正式题目、答案、criteria或历史核验。

有未决时退出1，登记completed_with_errors/candidate_incomplete。未决source保留旧Pointer并带migration_status=unresolved及original_snapshot；检索禁止将它匹配到新位置，保留分母；原文准备拒绝读取。20题迁移身份与版本由同目录manifest登记。

构建默认原料取catalog.raw_input；--raw-root可覆盖。--source-review校验快照、文件哈希和位置，保留原字段并加入待修提示，清单指纹随输入封存。普通冒号前缀仅标possible_speaker_in_text。实际输入哈希及执行源码记录在独立corpus输出中。

## 模型证据

search_story仍接收query，保留ok/result/evidence和原失败外层。统一to_model_evidence供provider和独立make_messages使用；新证据返回ID、标题、知识类型、上下文、结构化正文及定位，保留质量提示，省去重复text、score、文件哈希及部分审计字段。完整命中留在本地；引用合法性不替代语义支持。

两版来源访问器供报告和覆盖计算复用。已知题库／语料快照不一致时拒绝执行；冻结Benchmark场景仍绑定旧题库及快照，不与新原料直接组合。

## HF加载

```powershell
uv run --locked --python 3.11 python -B rag/scripts/export_hf_dataset.py build --source-run rag/data/outputs/corpus/r002 --output rag/data/outputs/hf/structured-new
uv sync --locked --group hf --group benchmark --python 3.11
```

候选导出校验completed构建及四个附件哈希；默认仍取catalog基线。包内manifest版本3、corpus_schema_version=2，候选baseline_id=null，origin_baseline_id只标原基线。story/train仅加载剧情语料；题库、迁移报告和原料不导出，不自动上传。

```python
import json
from pathlib import Path
from datasets import load_dataset
from rag.scripts.export_hf_dataset import hf_features

hf = json.loads(Path("rag/catalog.json").read_text(encoding="utf-8"))["hf"]
ds = load_dataset(hf["repository"], name="story", split="train", revision=hf["published_revision"])
explicit = load_dataset("json", data_files="rag/data/outputs/corpus/r002/corpus.jsonl",
                        split="train", features=hf_features())
```

数据卡声明嵌套类型；Features使用List(struct)，保持对象列表。跳过数据卡且不传features的裸JSON自动推断可能把首批全空列表推断为null，后续遇到字符串失败，不作为可靠入口。HF版本与本地默认基线独立；旧字段和ID的调用方需适配V2，复现旧结果固定catalog.hf.previous_revision。实际远端加载、Viewer与发布状态分别登记，来源与许可声明继续保留。

## Dev Note

无。
