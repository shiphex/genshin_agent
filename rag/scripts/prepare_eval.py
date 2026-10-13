"""Read dev questions and write a local copy with source text filled in."""

import argparse
import json
import hashlib
from pathlib import Path, PurePosixPath
import re
import sys

try:
    from . import artifact_catalog
except ImportError:
    import artifact_catalog

PROJECT = Path(__file__).resolve().parents[2]


def resolve_pointer(value, pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
        raise ValueError("invalid RFC 6901 Pointer")
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise ValueError("invalid array index")
            value = value[int(token)]
        elif isinstance(value, dict):
            value = value[token]
        else:
            raise ValueError("Pointer traverses a non-container value")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Pointer must resolve to nonempty text")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=PROJECT / "rag/eval/questions_dev.json")
    parser.add_argument("--raw-root", type=Path, default=PROJECT / "data/raw/genshin_wiki_data_20260605")
    parser.add_argument("--output", type=Path, help="file in a new local directory; default allocates a prepared copy")
    args = parser.parse_args(argv)
    generation = None
    try:
        source_input, raw_root = args.input.resolve(), args.raw_root.resolve()
        output = args.output.resolve() if args.output is not None else None
        if output is not None and (output == source_input or output.is_relative_to(raw_root)
                or output.is_relative_to(PROJECT / "data/raw")
                or not output.is_relative_to(PROJECT / "rag/data") or output == PROJECT / "rag/data"):
            raise ValueError("output must be a separate local file inside rag/data, outside raw data")
        if output is not None and output.exists():
            raise ValueError("output already exists; choose a new file")
        document = json.loads(source_input.read_text(encoding="utf-8-sig"))
        cache = {}
        count = 0
        for question in document["questions"]:
            for source in question["sources"]:
                name, pointer = source["file"], source["pointer"]
                try:
                    if "text" in source:
                        raise ValueError("remove manually maintained text from the input")
                    parts = PurePosixPath(name).parts
                    if not parts or parts[0] != "parsed" or ".." in parts or "\\" in name or ":" in name:
                        raise ValueError("file must be a relative POSIX path inside parsed")
                    path = (raw_root / name).resolve()
                    if not path.is_relative_to(raw_root / "parsed") or not path.is_file():
                        raise ValueError("source file is missing or outside parsed")
                    if path not in cache:
                        cache[path] = json.loads(path.read_text(encoding="utf-8-sig"))
                    source["text"] = resolve_pointer(cache[path], pointer)
                    count += 1
                except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
                    raise ValueError(f"{question['id']}: {name}#{pointer}: {exc}") from exc
        # Read all sources before creating an output; exclusive mode also prevents overwrites.
        encoded = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        datasets = artifact_catalog.load_catalog(PROJECT)['datasets']
        identifiers = [key for key, row in datasets.items() if (PROJECT / row['path']).resolve() == source_input]
        if len(identifiers) != 1:
            raise ValueError('register the input dataset in catalog before preparing')
        generation, output = artifact_catalog.reserve_prepared(PROJECT, identifiers[0], document['version'], output)
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
        metadata = {'input_sha256': hashlib.sha256(source_input.read_bytes()).hexdigest(),
                    'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                    'source_snapshot': raw_root.name, 'source_files': {p.relative_to(raw_root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in cache},
                    'sources': count, 'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        (output.parent / 'prepared_manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        artifact_catalog.finish_prepared(PROJECT, generation, 'completed', metadata)
        print(f"Prepared {len(document['questions'])} questions / {count} sources: {output}")
        return 0
    except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
        if generation and artifact_catalog.load_catalog(PROJECT)['prepared'][generation]['status'] == 'building':
            artifact_catalog.finish_prepared(PROJECT, generation, 'failed')
        print(f"Preparation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
