"""Build a traceable full lore corpus in a new output; never replace the baseline."""
import argparse
import json
from pathlib import Path
import re
import sys

try:
    from . import artifact_catalog
except ImportError:
    import artifact_catalog

PROJECT = Path(__file__).resolve().parents[2]

GAMEPLAY = re.compile(
    r"(?:攻击力|防御力|生命值|暴击率|暴击伤害|元素充能效率|伤害加成|护盾强效|治疗加成|伤害)"
    r"[^。！？\n]{0,30}(?:\d+(?:\.\d+)?\s*[%％]|百分之)"
    r"|(?:基础攻击力|暴击率|暴击伤害|元素精通)\s*[:：]?\s*\d"
    r"|技能倍率|毕业面板|配队推荐|推荐配队|强度评级|推荐圣遗物|\bDPS\b",
    re.IGNORECASE,
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def resolve_pointer(value, pointer):
    """Resolve an RFC 6901 JSON Pointer without evaluating source text."""
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("JSON Pointer must start with /")
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', type=Path, help='defaults to catalog raw_input')
    parser.add_argument('--source-review', type=Path, help='snapshot-bound source_issues.json from source migration')
    parser.add_argument('--all', action='store_true', help='compatibility flag; full extraction is the default')
    parser.add_argument('--max-chars', type=int, default=800)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args(argv)
    output = None
    try:
        if args.raw_root is None:
            args.raw_root = PROJECT / artifact_catalog.load_catalog(PROJECT)['raw_input']['path']
        if args.max_chars < 1:
            raise ValueError('max-chars must be positive')
        if args.output_dir is not None and args.output_dir.resolve().is_relative_to(args.raw_root.resolve()):
            raise ValueError('output must be outside the raw snapshot')
        if __package__:
            from . import full_corpus
        else:
            import full_corpus
        output = artifact_catalog.reserve_output(PROJECT, 'corpus', args.output_dir)
        review = {}
        if args.source_review:
            document = read_json(args.source_review)
            if document.get('schema_version') != 1 or document.get('source_snapshot') != args.raw_root.name:
                raise ValueError('source review snapshot/schema mismatch')
            for issue in document['issues']:
                source_path = (args.raw_root / issue['file']).resolve()
                if not source_path.is_relative_to((args.raw_root / 'parsed').resolve()):
                    raise ValueError('review source outside parsed')
                import hashlib
                if hashlib.sha256(source_path.read_bytes()).hexdigest() != issue['source_sha256']:
                    raise ValueError('review source hash mismatch')
                resolve_pointer(read_json(source_path), issue['row_pointer'])
                review.setdefault(issue['file'], {})[issue['row_pointer']] = issue['flags']
        inputs = sorted(p for folder in ('parsed', 'pages', 'category_members') for p in (args.raw_root / folder).rglob('*.json'))
        if args.source_review:
            inputs.append(args.source_review)
        inputs += [Path(__file__), Path(full_corpus.__file__), Path(full_corpus.schema.__file__), Path(artifact_catalog.__file__)]
        artifact_catalog.seal_inputs(PROJECT, output, inputs,
                                     {'raw_root': str(args.raw_root.resolve()), 'max_chars': args.max_chars, 'corpus_schema_version': 2})
        records, issues, audit = full_corpus.build_full(args.raw_root, args.max_chars, review)
        if not records:
            raise ValueError('no usable full-corpus records; inspect the source snapshot')
        full_corpus.write_full(output, records, issues, audit)
        import hashlib
        metadata = {'source_snapshot': args.raw_root.name, 'corpus_schema_version': 2, 'chunks': len(records),
                    'files_scanned': audit['files_scanned'], 'quality_flags': audit['quality_flags'],
                    'artifact_sha256': {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                                       for name in ('corpus.jsonl', 'audit.json', 'exclusions.jsonl', 'coverage.md')}}
        artifact_catalog.finish_output(PROJECT, output, 'completed', metadata)
        print(json.dumps(dict(metadata, output_dir=str(output))))
        return 0
    except KeyboardInterrupt:
        if output:
            artifact_catalog.finish_output(PROJECT, output, 'interrupted')
        return 130
    except (OSError, ValueError, KeyError, TypeError) as error:
        if output:
            artifact_catalog.finish_output(PROJECT, output, 'failed')
        print(f'Preparation failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
