"""Stage and verify only the current story corpus for Hugging Face; never upload."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

try:
    from . import artifact_catalog
    from . import corpus_schema
except ImportError:
    import artifact_catalog
    import corpus_schema

ROOT = Path(__file__).resolve().parents[2]
DATA_FILES = {
    'corpus.jsonl': 'data/corpus.jsonl',
    'audit.json': 'metadata/audit.json',
    'exclusions.jsonl': 'metadata/exclusions.jsonl',
    'coverage.md': 'metadata/coverage.md',
}
REQUIRED_RECORD_FIELDS = {
    'id', 'title', 'type', 'parent_id', 'text', 'source_file',
    'source_pointer', 'source_spans', 'source_kind',
}
SOURCE_KINDS = {'wiki_excerpt', 'wiki_compilation'}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid JSON: " + str(path)) from error


def validate_record(row, line_number):
    if isinstance(row, dict) and corpus_schema.version(row) == 2:
        corpus_schema.validate_record(row)
        return
    if not isinstance(row, dict) or not REQUIRED_RECORD_FIELDS <= row.keys():
        raise ValueError(f"Corpus row {line_number} is missing required fields")
    for field in REQUIRED_RECORD_FIELDS - {"source_pointer", "source_spans"}:
        if not isinstance(row[field], str) or not row[field]:
            raise ValueError(f"Corpus row {line_number} has invalid {field}")
    if row["source_kind"] not in SOURCE_KINDS:
        raise ValueError(f"Corpus row {line_number} has invalid source_kind")
    pointers, spans = row["source_pointer"], row["source_spans"]
    if not isinstance(pointers, list) or not pointers or not all(isinstance(item, str) and item.startswith("/") for item in pointers):
        raise ValueError(f"Corpus row {line_number} has invalid source_pointer")
    if not isinstance(spans, list) or len(spans) != len(pointers):
        raise ValueError(f"Corpus row {line_number} has invalid source_spans")
    for span in spans:
        if (not isinstance(span, dict) or set(span) != {"start", "end"}
                or not isinstance(span["start"], int) or not isinstance(span["end"], int)
                or span["start"] < 0 or span["end"] < span["start"]):
            raise ValueError(f"Corpus row {line_number} has invalid source span")


def validate_corpus(path, expected_rows=None):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("Cannot read corpus: " + str(path)) from error
    if expected_rows is not None and len(lines) != expected_rows:
        raise ValueError(f"Corpus row count {len(lines)} does not match expected {expected_rows}")
    ids, versions, snapshots = set(), set(), set()
    for line_number, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Corpus row {line_number} is not JSON") from error
        validate_record(row, line_number)
        if row['id'] in ids:
            raise ValueError('Duplicate corpus ID')
        ids.add(row['id'])
        versions.add(corpus_schema.version(row))
        snapshot = corpus_schema.source_info(row).get('snapshot')
        if snapshot:
            snapshots.add(snapshot)
    if len(versions) > 1 or len(snapshots) > 1:
        raise ValueError('Mixed corpus schemas or snapshots')
    return len(lines)


def dataset_card(manifest):
    card = f"""---
license: other
pretty_name: 原神剧情 RAG 语料库｜Genshin Impact Story Corpus
language:
- zh
task_categories:
- text-retrieval
tags:
- rag
- retrieval
- genshin-impact
- nlp
- text-generation
- conversational
- roleplay
- multi-turn
- chinese-corpus
configs:
- config_name: story
  default: true
  data_files:
  - split: train
    path: data/corpus.jsonl
---

# 原神剧情 RAG 语料库｜Genshin Impact Story Corpus

这是从冻结的原神 Wiki 快照派生的中文剧情语料（Genshin Impact story/lore corpus），面向剧情检索与 Agent/RAG 的证据回查，当前发布包含 **{manifest['rows']:,} 条结构化记录**。对话保留逐句说话者与正文；`text-generation` 和 `roleplay` 表示可结合检索使用的下游场景，`multi-turn` 指剧情中的多轮对话。本数据集不提供助手对话或监督微调（SFT）的指令与标准回答。

| 属性 | 值 |
| --- | --- |
| 发布格式 | `{manifest['release_version']}` |
| 基线 | `{manifest['baseline_id']}` |
| 来源快照 | `{manifest['input_snapshot']}` |
| 主数据文件 | `data/corpus.jsonl`（JSON Lines，UTF-8） |

## 加载数据

数据集提供 `story` 配置。其 `train` split **只读取** `data/corpus.jsonl`；`train` 是加载器的分区名称，不表示这些记录是模型训练样本。审计、排除记录和覆盖说明不进入该 split。

```python
from datasets import load_dataset

corpus = load_dataset("shiphex/genshin_agent_RAG", name="story", split="train")
print(len(corpus))
print(corpus[0])
```

## 数据内容与字段

每行是一条剧情相关的语料片段。记录保留片段文本及其来源定位信息，便于检索后回查原材料。

| 字段 | 含义 |
| --- | --- |
| `id` | 语料记录的稳定标识 |
| `title` | 来源条目的标题或路径标签 |
| `type` | 来源内容的分类 |
| `parent_id` | 解析记录对应的来源条目标识 |
| `text` | 用于检索的中文片段文本 |
| `source_file` | 冻结快照内的来源文件相对路径 |
| `source_pointer` | RFC 6901 JSON Pointer 路径数组，用于定位来源 JSON 中的字段 |
| `source_spans` | 与 `source_pointer` 顺序对应的字符范围；起点包含、终点不包含，按解码后的原字段文本计数，字符位置从零开始 |
| `source_kind` | 来源性质：`wiki_excerpt`（Wiki 摘录）或 `wiki_compilation`（Wiki 编纂） |

Wiki 摘录与 Wiki 编纂都不能自动视作官方确认事实。引用人物说法、传说、推测及存在争议的内容时，应保留来源语气和不确定限定；检索结果适合作为回查线索，不单独构成事实核验结论。

## 发布文件

| 路径 | 用途 | 是否载入 `story/train` |
| --- | --- | --- |
| `data/corpus.jsonl` | 完整剧情检索语料 | 是 |
| `metadata/audit.json` | 纳入语料的审计信息 | 否 |
| `metadata/exclusions.jsonl` | 排除项记录 | 否 |
| `metadata/coverage.md` | 覆盖范围与限制说明 | 否 |
| `manifest.json` | 发布身份、行数、大小与文件 SHA-256 | 否 |
| `README.md` | 数据集卡与加载配置 | 否 |

## 来源与回查

语料由冻结 Wiki 快照 `{manifest['input_snapshot']}` 派生。`source_file` 和 `source_pointer` 是该快照内部的路径，不是可直接访问的网页 URL。本发布不包含原始快照；若要按记录精确回查，需要另行取得相同版本的快照。来源文件路径、快照版本与记录 ID 应一并保留，避免把片段脱离上下文使用。

本数据集面向剧情文本检索与证据回查，不包含游戏数值、养成、配队或攻略类语料作为目标内容，也不是带有题目、标准答案或训练标签的基准集。本发布不包含题库、模型回答、人工复核材料、模型权重或缓存。

## 许可与使用边界

Hugging Face 元数据中的 `license: other` 不授予语料文本开放数据许可。原神及 Wiki 来源文本没有通过本仓库获得再许可；相关权利与使用限制仍由相应权利人和来源条款决定。本项目原创的 RAG 脚本和 schema 说明按 [MIT 许可及适用范围](https://github.com/shiphex/genshin_agent/blob/feat/rag-structured-corpus/rag/LICENSE-MIT.txt)提供；该许可不扩展到语料文本或第三方材料。使用者应自行确认其使用方式符合适用的来源条款和法律要求。

The text data belongs to HoYoVerse/Wiki community. The structure, schema, and scripts are under MIT License. This MIT license applies only to original project contributions and does not license the story text or third-party material.

## 完整性校验

`manifest.json` 记录发布版本、基线标识、来源快照、语料行数，以及每个数据文件的字节数和 SHA-256。下载后可先按清单核对文件大小与哈希，再解析 JSON Lines 并确认记录数为 **{manifest['rows']:,}**。`data/corpus.jsonl` 使用 Git LFS 分发。

文件完整性校验只能确认下载内容与该发布清单一致，不代表语义质量、覆盖完整性或逐条事实正确性已经获得验收。
"""
    if manifest.get('corpus_schema_version') == 2:
        card = card.replace('license: other\n', 'license: other\ndataset_info: ' + json.dumps(
            {'config_name': 'story', 'features': card_features()}, ensure_ascii=False, separators=(',', ':')) + '\n', 1)
        start = card.index('| `id` |')
        end = card.index('\n\nWiki 摘录', start)
        card = card[:start] + '''| `schema_version` | 语料格式版本2；与发布包manifest版本分别管理 |
| `id`、`title` | 绑定快照与来源范围的片段ID、标题 |
| `knowledge_type` | 对话、人物资料／故事／语音、实体设定、书籍、任务描述或Wiki编纂 |
| `metadata` | source_family、entity、source_version及context；缺失标量为null，不适用列表为空 |
| `source` | snapshot、file、file_sha256、kind；来源性质不等于事实核验结论 |
| `content.turns` | 按原序的对象列表；kind、source_type、speaker、text、row_pointer、pointer、span、options、quality_flags |
| `content.sections` | field、heading_path、text、pointer及span；保留章节、部件或分卷关系 |
| `text` | 自动生成的检索文本；模型证据不会与结构化正文重复发送 |
''' + card[end:]
        card = card.replace('`source_file` 和 `source_pointer`', '`source.file` 和正文的 `pointer`')
        card = card.replace('| 基线 | `None` |', '| 身份 | 独立候选，尚未提升基线 |')
        card = card.replace('## 发布文件', '''## 读取对话与章节

```python
row = next(row for row in corpus if row["content"]["turns"])
chapter = row["metadata"]["context"]["chapter"]
act = row["metadata"]["context"]["act"]
turns = row["content"]["turns"]
print(chapter, act)
for turn in turns:
    print(turn["speaker"], turn["text"])
```

`turns` 可能为空；旁白、玩家选项和未知说话者须按 `kind`、`options` 与 `quality_flags` 判断。`text` 由逐句内容或段落生成，章节、幕次和任务步骤另存于 `metadata.context` 与 `title`，不直接写入 `text`。

## 发布文件''', 1)
        card += '''
## 嵌套类型与质量限制

`turns`、`sections`、`options`保持对象列表。选项组不代表已知分支；choice的text、pointer、span为null，正文与定位在options内。
普通正文的span使用解码后原字段的零基半开字符范围。speaker为空或类型为narration时，不从正文推断角色归属。
quality_flags包含上游待修或疑似异常；结构完整与原文可定位不表示角色归属及语义已经通过。

数据卡内声明完整features，默认按发布目录或Hub的story配置加载时使用这些类型。
本地直接读取JSONL时须传项目导出模块的`hf_features()`；它以`Features`和`List(struct)`定义全部字段。
跳过数据卡且不传features的自动推断可能把首批全空字段推断为null，不能用作本格式的可靠加载入口。
本地导出不代表已经上传；发布状态以公开数据集页面及项目 catalog 的实际核验记录为准。
'''
    return card


def feature_definition():
    """One stdlib type definition drives both the data card and optional HF Features."""
    string = 'string'
    span = {'start': 'int64', 'end': 'int64'}
    unit = {'text': string, 'pointer': string, 'span': span}
    def array(item):
        return {'_list': item}
    return {
        'schema_version': 'int64', 'id': string, 'title': string, 'knowledge_type': string,
        'metadata': {'source_family': string, 'entity': {'type': string, 'name': string},
                     'source_version': string, 'context': {'chapter': string, 'act': string, 'task_step': string,
                                                         'path': array(string), 'related_quests': array(string)}},
        'source': {'snapshot': string, 'file': string, 'file_sha256': string, 'kind': string},
        'content': {'turns': array({'kind': string, 'source_type': string, 'speaker': string,
                                  'row_pointer': string, **unit, 'options': array(unit), 'quality_flags': array(string)}),
                    'sections': array({'field': string, 'heading_path': array(string), **unit})},
        'text': string}


def card_features(definition=None):
    definition = feature_definition() if definition is None else definition
    fields = []
    for name, value in definition.items():
        if isinstance(value, str):
            field = {'dtype': value}
        elif '_list' in value:
            item = value['_list']
            field = {'list': item if isinstance(item, str) else card_features(item)}
        else:
            field = {'struct': card_features(value)}
        fields.append({'name': name, **field})
    return fields


def hf_features():
    """Optional integration dependency; never imported by ordinary corpus tooling."""
    from datasets import Features, List, Value
    def convert(value):
        if isinstance(value, str):
            return Value(value)
        if '_list' in value:
            return List(convert(value['_list']))
        return {k: convert(v) for k, v in value.items()}
    return Features(convert(feature_definition()))


def source_run_details(source):
    source = Path(source)
    manifest = read_json(source / 'run_manifest.json')
    if manifest.get('purpose') != 'corpus' or manifest.get('execution_status') != 'completed':
        raise ValueError('Source must be a completed corpus build')
    meta = manifest.get('metadata', {})
    for name in DATA_FILES:
        path = source / name
        if not path.is_file() or path.is_symlink() or sha256(path.read_bytes()) != meta.get('artifact_sha256', {}).get(name):
            raise ValueError('Source build artifact hash mismatch: ' + name)
    if not isinstance(meta.get('chunks'), int) or not meta.get('source_snapshot'):
        raise ValueError('Source build lacks candidate identity')
    return manifest


def release_file_paths():
    return {'README.md', '.gitattributes', 'manifest.json', *DATA_FILES.values()}


def build_release(source, output, *, expected_rows=None, input_snapshot='genshin_wiki_data_20260605',
                  release_version='rag-full-20260605-v2', baseline_id='current-001', source_run_id=None, origin_baseline_id=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('Release output must be a new directory')
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Release output must not overlap the source')
    if any(not (source / name).is_file() or (source / name).is_symlink() for name in DATA_FILES):
        raise ValueError('Missing or unsafe approved source file')
    rows = validate_corpus(source / 'corpus.jsonl', expected_rows)
    if not rows:
        raise ValueError('Corpus must not be empty')
    first = json.loads((source / 'corpus.jsonl').read_text(encoding='utf-8').splitlines()[0])
    corpus_version = corpus_schema.version(first)
    if corpus_version == 2:
        corpus_schema.assert_snapshot_match([first], input_snapshot)
    manifest = {'schema_version': 2, 'release_version': release_version, 'baseline_id': baseline_id,
                'input_snapshot': input_snapshot, 'rows': rows,
                'files': {relative: {'bytes': (source / name).stat().st_size,
                                     'sha256': sha256((source / name).read_bytes())}
                          for name, relative in DATA_FILES.items()}}
    if corpus_version == 2:
        manifest.update(schema_version=3, corpus_schema_version=2, source_run_id=source_run_id,
                        origin_baseline_id=origin_baseline_id, publication_status='not_published')
    output.mkdir(parents=True, exist_ok=False)
    for name, relative in DATA_FILES.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'README.md').write_text(dataset_card(manifest), encoding='utf-8')
    (output / '.gitattributes').write_text('data/corpus.jsonl filter=lfs diff=lfs merge=lfs -text\n', encoding='ascii')
    return verify_release(output, expected_rows=expected_rows)


def verify_release(output, *, expected_rows=None):
    output = Path(output).resolve()
    if not output.is_dir():
        raise ValueError('Release directory is missing')
    if any(p.is_symlink() for p in output.rglob('*')):
        raise ValueError('Release must not contain symlinks')
    actual = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
    if actual != release_file_paths():
        raise ValueError('Release contains unapproved or missing files')
    manifest = read_json(output / 'manifest.json')
    if (manifest.get('schema_version') not in (2, 3) or set(manifest.get('files', {})) != set(DATA_FILES.values())
            or not isinstance(manifest.get('rows'), int) or manifest['rows'] < 1
            or not all(isinstance(manifest.get(k), str) and manifest[k] for k in ('release_version', 'input_snapshot'))
            or (manifest.get('schema_version') == 2 and not manifest.get('baseline_id'))):
        raise ValueError('Invalid release manifest')
    if expected_rows is not None and manifest['rows'] != expected_rows:
        raise ValueError('Release row count differs from expected baseline')
    validate_corpus(output / 'data/corpus.jsonl', manifest['rows'])
    first = json.loads((output / 'data/corpus.jsonl').read_text(encoding='utf-8').splitlines()[0])
    if manifest['schema_version'] == 3:
        if manifest.get('corpus_schema_version') != 2 or corpus_schema.version(first) != 2:
            raise ValueError('Release/corpus schema mismatch')
        corpus_schema.assert_snapshot_match([first], manifest['input_snapshot'])
    for relative, info in manifest['files'].items():
        data = (output / relative).read_bytes()
        if len(data) != info.get('bytes') or sha256(data) != info.get('sha256'):
            raise ValueError('Release hash mismatch: ' + relative)
    # Keep the loading contract exact while allowing historical card metadata.
    card = (output / 'README.md').read_text(encoding='utf-8')
    parts = card.split('---', 2)
    expected_parts = dataset_card(manifest).split('---', 2)
    if len(parts) != 3 or parts[0].strip() or parts[1].count('\nconfigs:\n') != 1:
        raise ValueError('Invalid dataset card configuration')
    header, expected_header = parts[1], expected_parts[1]
    license_lines = [line for line in header.splitlines() if line.startswith('license:')]
    feature_lines = [line for line in header.splitlines() if line.startswith('dataset_info:')]
    expected_features = [line for line in expected_header.splitlines() if line.startswith('dataset_info:')]
    if (license_lines != ['license: other'] or feature_lines != expected_features
            or header.split('\nconfigs:\n', 1)[1] != expected_header.split('\nconfigs:\n', 1)[1]):
        raise ValueError('Invalid dataset card configuration')
    if (output / '.gitattributes').read_text(encoding='ascii') != 'data/corpus.jsonl filter=lfs diff=lfs merge=lfs -text\n':
        raise ValueError('Corpus must use Git LFS')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build')
    build.add_argument('--output', type=Path, required=True)
    build.add_argument('--source-run', type=Path, help='completed candidate corpus run; default remains catalog baseline')
    verify = commands.add_parser('verify')
    verify.add_argument('release', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'build':
            doc = artifact_catalog.load_catalog(ROOT)
            if args.source_run is None:
                artifact_catalog.check_catalog(ROOT)
            artifact_catalog.assert_writable_output(ROOT, args.output)
            if not args.output.resolve().is_relative_to(ROOT / 'rag/data/outputs/hf'):
                raise ValueError('HF output must be under rag/data/outputs/hf')
            if args.source_run is None:
                result = build_release(artifact_catalog.dataset_path(ROOT, 'full_corpus').parent, args.output,
                                       expected_rows=doc['datasets']['full_corpus']['rows'], input_snapshot=doc['source_snapshot'],
                                       release_version=doc['hf']['release_version'], baseline_id=doc['baseline_id'])
            else:
                run = source_run_details(args.source_run)
                meta = run['metadata']
                result = build_release(args.source_run, args.output, expected_rows=meta['chunks'],
                                       input_snapshot=meta['source_snapshot'], release_version='rag-structured-' + meta['source_snapshot'] + '-v1',
                                       baseline_id=None, source_run_id='corpus/' + args.source_run.name,
                                       origin_baseline_id=run['baseline_id'])
        else:
            result = verify_release(args.release)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'HF export failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
