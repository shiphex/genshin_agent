"""Build and verify the public Hugging Face RAG corpus release.

The script only stages a fixed, derived corpus snapshot.  It never uploads
data and never changes the corpus source or the shared raw snapshot.
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RELEASE_VERSION = "rag-full-20260605-v1"
INPUT_SNAPSHOT = "genshin_wiki_data_20260605"
DATASET_RELATIVE = Path("data/full") / INPUT_SNAPSHOT
try:
    from rag.scripts import artifact_catalog
except ModuleNotFoundError:
    import artifact_catalog
SOURCE = artifact_catalog.dataset_path(ROOT, 'full_corpus', 'v1').parent
CORPUS_ROWS = 22_822
DATA_FILES = ("corpus.jsonl", "audit.json", "exclusions.jsonl", "coverage.md")
REQUIRED_RECORD_FIELDS = {
    "id", "title", "type", "parent_id", "text", "source_file",
    "source_pointer", "source_spans", "source_kind",
}
SOURCE_KINDS = {"wiki_excerpt", "wiki_compilation"}


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


def validate_corpus(path, expected_rows):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("Cannot read corpus: " + str(path)) from error
    if len(lines) != expected_rows:
        raise ValueError(f"Corpus row count {len(lines)} does not match expected {expected_rows}")
    for line_number, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Corpus row {line_number} is not JSON") from error
        validate_record(row, line_number)
    return len(lines)


def dataset_card():
    return """---
license: other
language:
- zh
tags:
- rag
- retrieval
- genshin-impact
---

# Genshin Agent RAG corpus

这是 `genshin_wiki_data_20260605` 冻结 Wiki 快照生成的中文剧情 RAG 派生语料，版本为
`rag-full-20260605-v1`。它包含用于检索的片段、处理审计、排除记录和覆盖说明；不包含原始
快照、模型回答、模型权重、缓存或审阅资料包。

## 内容与追溯

`corpus.jsonl` 有 22,822 个片段。每条记录保留 `source_file`、RFC 6901 JSON Pointer
（`source_pointer`）、解码后原字段的零基半开字符范围（`source_spans`）和来源性质
（`source_kind`），可在提供同一冻结快照时回查。该发布不包含快照，因此路径本身不是可公开
访问的 URL；重建或完整回查需要另行提供相同版本的原始输入。

`wiki_excerpt` 表示 Wiki 摘录，`wiki_compilation` 表示 Wiki 编纂/整理。二者都不等同于
官方确认的游戏事实；人物说法、传说、推测和原文中的不确定性必须保留其性质。

## 许可与使用限制

此数据集中的《原神》文本和 Wiki 来源文本不通过本仓库获得再许可；其权利、来源条款和使用
限制仍由相应权利人及来源决定。`license: other` 表示未对这些文本授予开放数据许可。

发布者原创的导出脚本、清单和说明文档可按 MIT 使用，但该声明不扩展到语料文本。使用者应自行
核实来源条款、适用法律和其具体用途的许可条件。

## 验证

`manifest.json` 记录每个数据文件的大小和 SHA-256。下载后应先核对哈希，再逐行解析
`corpus.jsonl`；该文件通过 Git LFS 分发。
"""


def git_attributes():
    return f"{DATASET_RELATIVE.as_posix()}/corpus.jsonl filter=lfs diff=lfs merge=lfs -text\n"


def release_file_paths(output):
    return {"README.md", ".gitattributes"} | {
        (DATASET_RELATIVE / name).as_posix() for name in (*DATA_FILES, "manifest.json")
    }


def build_release(source, output, *, expected_rows=CORPUS_ROWS, input_snapshot=INPUT_SNAPSHOT):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("Release output must be a new directory")
    if output == source or output.is_relative_to(source):
        raise ValueError("Release output must not overlap the source")
    missing = [name for name in DATA_FILES if not (source / name).is_file()]
    if missing:
        raise ValueError("Missing approved source files: " + ", ".join(missing))
    rows = validate_corpus(source / "corpus.jsonl", expected_rows)
    files = {
        name: {"bytes": (source / name).stat().st_size, "sha256": sha256((source / name).read_bytes())}
        for name in DATA_FILES
    }
    manifest = {
        "schema_version": 1,
        "release_version": RELEASE_VERSION,
        "input_snapshot": input_snapshot,
        "source_root": f"rag/data/full/{input_snapshot}",
        "rows": rows,
        "files": files,
    }
    target = output / DATASET_RELATIVE
    target.mkdir(parents=True)
    for name in DATA_FILES:
        shutil.copyfile(source / name, target / name)
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "README.md").write_text(dataset_card(), encoding="utf-8")
    (output / ".gitattributes").write_text(git_attributes(), encoding="ascii")
    return verify_release(output, expected_rows=expected_rows)


def verify_release(output, *, expected_rows=CORPUS_ROWS):
    output = Path(output).resolve()
    if not output.is_dir():
        raise ValueError("Release directory is missing")
    actual_files = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
    if actual_files != release_file_paths(output):
        raise ValueError("Release contains unapproved or missing files")
    target = output / DATASET_RELATIVE
    manifest = read_json(target / "manifest.json")
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or manifest.get("release_version") != RELEASE_VERSION
            or manifest.get("rows") != expected_rows
            or not isinstance(manifest.get("files"), dict)):
        raise ValueError("Invalid release manifest")
    rows = validate_corpus(target / "corpus.jsonl", expected_rows)
    for name in DATA_FILES:
        details = manifest["files"].get(name)
        path = target / name
        if (not isinstance(details, dict) or details.get("bytes") != path.stat().st_size
                or details.get("sha256") != sha256(path.read_bytes())):
            raise ValueError("Release hash mismatch: " + name)
    if "license: other" not in (output / "README.md").read_text(encoding="utf-8"):
        raise ValueError("Dataset card must use the selected license policy")
    if "filter=lfs" not in (output / ".gitattributes").read_text(encoding="ascii"):
        raise ValueError("Corpus must use Git LFS")
    if rows != manifest["rows"]:
        raise ValueError("Release row count mismatch")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    build = subcommands.add_parser("build")
    build.add_argument("--output", type=Path, required=True)
    verify = subcommands.add_parser("verify")
    verify.add_argument("release", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        result = build_release(SOURCE, args.output)
    else:
        result = verify_release(args.release)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
