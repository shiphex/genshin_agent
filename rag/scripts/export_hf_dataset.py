"""Stage and verify only the current story corpus for Hugging Face; never upload."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

try:
    from . import artifact_catalog
except ImportError:
    import artifact_catalog

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
    for line_number, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Corpus row {line_number} is not JSON") from error
        validate_record(row, line_number)
    return len(lines)


def dataset_card(manifest):
    return f"""---
license: other
language:
- zh
tags:
- rag
- retrieval
- genshin-impact
configs:
- config_name: story
  default: true
  data_files:
  - split: train
    path: data/corpus.jsonl
---

# Genshin Agent RAG corpus

这是为原神剧情讨论与 RAG 检索准备的中文语料，当前发布包含 **{manifest['rows']:,} 条记录**。

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

corpus = load_dataset(
    "shiphex/genshin_agent_RAG",
    name="story",
    split="train",
)
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

Hugging Face 元数据中的 `license: other` 不授予语料文本开放数据许可。原神及 Wiki 来源文本没有通过本仓库获得再许可；相关权利与使用限制仍由相应权利人和来源条款决定。发布者原创的脚本、清单及说明可按 MIT 许可使用，该声明不扩展到语料文本。使用者应自行确认其使用方式符合适用的来源条款和法律要求。

## 完整性校验

`manifest.json` 记录发布版本、基线标识、来源快照、语料行数，以及每个数据文件的字节数和 SHA-256。下载后可先按清单核对文件大小与哈希，再解析 JSON Lines 并确认记录数为 **{manifest['rows']:,}**。`data/corpus.jsonl` 使用 Git LFS 分发。

文件完整性校验只能确认下载内容与该发布清单一致，不代表语义质量、覆盖完整性或逐条事实正确性已经获得验收。
"""


def release_file_paths():
    return {'README.md', '.gitattributes', 'manifest.json', *DATA_FILES.values()}


def build_release(source, output, *, expected_rows=None, input_snapshot='genshin_wiki_data_20260605',
                  release_version='rag-full-20260605-v2', baseline_id='current-001'):
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
    manifest = {'schema_version': 2, 'release_version': release_version, 'baseline_id': baseline_id,
                'input_snapshot': input_snapshot, 'rows': rows,
                'files': {relative: {'bytes': (source / name).stat().st_size,
                                     'sha256': sha256((source / name).read_bytes())}
                          for name, relative in DATA_FILES.items()}}
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
    if (manifest.get('schema_version') != 2 or set(manifest.get('files', {})) != set(DATA_FILES.values())
            or not isinstance(manifest.get('rows'), int) or manifest['rows'] < 1
            or not all(isinstance(manifest.get(k), str) and manifest[k] for k in ('release_version', 'baseline_id', 'input_snapshot'))):
        raise ValueError('Invalid release manifest')
    if expected_rows is not None and manifest['rows'] != expected_rows:
        raise ValueError('Release row count differs from expected baseline')
    validate_corpus(output / 'data/corpus.jsonl', manifest['rows'])
    for relative, info in manifest['files'].items():
        data = (output / relative).read_bytes()
        if len(data) != info.get('bytes') or sha256(data) != info.get('sha256'):
            raise ValueError('Release hash mismatch: ' + relative)
    # Exact generated frontmatter prevents audit/exclusion files entering the Viewer configuration.
    card = (output / 'README.md').read_text(encoding='utf-8')
    if card.split('---', 2)[:2] != dataset_card(manifest).split('---', 2)[:2]:
        raise ValueError('Invalid dataset card configuration')
    if (output / '.gitattributes').read_text(encoding='ascii') != 'data/corpus.jsonl filter=lfs diff=lfs merge=lfs -text\n':
        raise ValueError('Corpus must use Git LFS')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build')
    build.add_argument('--output', type=Path, required=True)
    verify = commands.add_parser('verify')
    verify.add_argument('release', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'build':
            doc = artifact_catalog.load_catalog(ROOT)
            artifact_catalog.check_catalog(ROOT)
            artifact_catalog.assert_writable_output(ROOT, args.output)
            if not args.output.resolve().is_relative_to(ROOT / 'rag/data/outputs/hf'):
                raise ValueError('HF output must be under rag/data/outputs/hf')
            result = build_release(artifact_catalog.dataset_path(ROOT, 'full_corpus').parent, args.output,
                                   expected_rows=doc['datasets']['full_corpus']['rows'], input_snapshot=doc['source_snapshot'],
                                   release_version=doc['hf']['release_version'], baseline_id=doc['baseline_id'])
        else:
            result = verify_release(args.release)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'HF export failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
