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

中文剧情检索语料，共 {manifest['rows']} 条。发布格式版本：`{manifest['release_version']}`；
原始快照：`{manifest['input_snapshot']}`。`story/train` 只加载 `data/corpus.jsonl`，
train 是加载分区名；用途为剧情检索和回查。metadata 下为审计、排除记录和覆盖说明。

## 来源与限制

记录保留 source_file、RFC 6901 source_pointer、解码后原字段的零基半开字符范围
source_spans 及 source_kind。wiki_excerpt 是 Wiki 摘录，wiki_compilation 是 Wiki
编纂，均不自动等同于官方事实。人物说法、传说和推测须保持原限定。

本发布不包含原始快照、题库、模型回答、复核资料、权重或缓存。路径不是公开原文 URL；
完整回查需要另行提供相同冻结快照。

## 许可

原神及 Wiki 来源文本未通过本仓库获得再许可，权利和使用限制仍由相应权利人及来源决定。
license: other 表示未授予这些文本开放数据许可。发布者原创脚本、清单和说明可按 MIT
使用，此声明不扩展到语料文本。

## 校验

manifest.json 记录发布身份、行数、文件大小与 SHA-256；下载后先核对哈希，再逐行解析。
corpus.jsonl 通过 Git LFS 分发。本次发布不表示已完成语义质量或用户验收。
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
