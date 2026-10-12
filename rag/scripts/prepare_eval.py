"""Read dev questions and write a local copy with source text filled in."""

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys

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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        source_input, raw_root, output = args.input.resolve(), args.raw_root.resolve(), args.output.resolve()
        if (output == source_input or output.is_relative_to(raw_root)
                or output.is_relative_to(PROJECT / "data/raw")
                or not output.is_relative_to(PROJECT / "rag/data") or output == PROJECT / "rag/data"):
            raise ValueError("output must be a separate local file inside rag/data, outside raw data")
        if output.exists():
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
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
        print(f"Prepared {len(document['questions'])} questions / {count} sources: {output}")
        return 0
    except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
        print(f"Preparation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
