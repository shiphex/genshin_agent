"""Extract manually selected lore fields, leaving the raw snapshot untouched."""

import argparse
import json
import hashlib
from pathlib import Path
import re
import sys

try:
    from . import artifact_catalog
except ImportError:
    import artifact_catalog

RAG_ROOT = Path(__file__).resolve().parents[1]
PROJECT = RAG_ROOT.parent
DEFAULT_ROOT = PROJECT / "data/raw/genshin_wiki_data_20260605"
DEFAULT_SELECTION = artifact_catalog.experiment_input(PROJECT, 'sample_retrieval', 'selection')
DEFAULT_OUTPUT = RAG_ROOT / "data/mvp"

# This is a field allowlist, not a blanket deletion of combat-related words.
ALLOWED = {
    "weapons": r"/(名称|介绍|故事)",
    "artifacts": r"/名称|/(时之沙|死之羽|理之冠|生之花|空之杯)/(名称|描述|故事)",
    "characters": (
        r"/角色/(名称|称号|全名|所属|出身|种族|介绍|性别|昵称~1外号|归属|职业)"
        r"|/角色故事/(角色详细|角色故事[1-5])|/角色语音/[^/]+"
        r"|/权能/(神之眼|神之心)"
    ),
    "books": r"/title|/volumes/\d+/(name|content)",
    "archon-quests": r"/任务标题/中文|/(章节|章节名称|幕|幕名称|描述)|/任务流程/\d+|/对话/\d+",
    "character-quests": r"/(任务名称|所属章|所属幕|所属幕名称|任务描述)|/任务流程/\d+|/对话/\d+",
    "event-quests": r"/(任务名称|所属任务|任务描述)|/任务列表/\d+|/剧情对话/\d+/对话/\d+",
}
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


def render_value(value):
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        raise ValueError("selected field must be text or a dialogue row")
    kind = value.get("类型")
    if kind in ("option", "选项"):
        options = value.get("选项", [value.get("内容", "")])
        if not isinstance(options, list) or not all(isinstance(x, str) for x in options):
            raise ValueError("invalid dialogue options")
        return "\n".join("[玩家选项；分支关系未知] " + x.strip() for x in options if x.strip())
    content = value.get("内容", "")
    if not isinstance(content, str):
        raise ValueError("invalid dialogue content")
    if not content.strip():
        return ""
    if kind in ("narration", "旁白"):
        return "[旁白] " + content.strip()
    speaker = value.get("说话者", "")
    if not isinstance(speaker, str):
        raise ValueError("invalid speaker")
    return (speaker.strip() or "[原文说话者为空]") + "：" + content.strip()


def extract_entry(root, entry):
    """Return (record, None), or (None, an explicit exclusion reason)."""
    root = Path(root).resolve()

    def skip(reason):
        return None, {"id": entry.get("id"), "source_file": entry.get("source_file"),
                      "source_pointer": entry.get("source_pointer"), "reason": reason}

    if entry.get("exclude_reason"):
        return skip(entry["exclude_reason"])
    try:
        source = (root / entry["source_file"]).resolve()
        parsed = root / "parsed"
        if not source.is_relative_to(parsed):
            return skip("source_outside_parsed")
        family = source.relative_to(parsed).parts[0]
        if family not in ALLOWED:
            return skip("unsupported_type")
        value = read_json(source)
        page_path = root / "pages" / source.name
        if not page_path.exists():
            return skip("missing_raw_page")
        pages = read_json(page_path).get("query", {}).get("pages", {})
        if len(pages) != 1:
            return skip("ambiguous_raw_page")
        page = next(iter(pages.values()))
        if page.get("ns") != 0 or "missing" in page:
            return skip("non_content_page")
        raw = page.get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("*", "")
        if re.match(r"\s*#(?:REDIRECT|重定向)", raw, re.IGNORECASE):
            return skip("redirect_page")
        if family.endswith("-quests") and not re.search(r"\{\{\s*任务(?:\s|\||\})", raw):
            return skip("wrong_task_page")
        pointers = entry["source_pointer"]
        if not isinstance(pointers, list) or not pointers:
            return skip("missing_source_pointer")
        if any(not isinstance(p, str) or not re.fullmatch(ALLOWED[family], p) for p in pointers):
            return skip("field_not_allowed")
        values = [resolve_pointer(value, p) for p in pointers]
        dialogue_paths = [p for p in pointers if re.search(r"/对话/\d+$", p)]
        if dialogue_paths:
            if len(dialogue_paths) != len(pointers) or len({p.rsplit("/", 1)[0] for p in pointers}) != 1:
                return skip("discontinuous_dialogue")
            indices = [int(p.rsplit("/", 1)[1]) for p in pointers]
            if indices != list(range(indices[0], indices[0] + len(indices))):
                return skip("discontinuous_dialogue")
            if family != "event-quests":
                stages = {v.get("所属任务流程") for v in values}
                if len(stages) != 1 or not next(iter(stages)):
                    return skip("cross_stage_dialogue")
        texts = [render_value(v) for v in values]
        # An empty selected field is an issue, even if other selected fields contain text.
        if any(not text for text in texts):
            return skip("empty_text")
        text = "\n\n".join(texts)
        if GAMEPLAY.search(text):
            return skip("mixed_gameplay")
        if any(marker in text for marker in ("<!--", "{{", "[[")):
            return skip("unresolved_markup")
        title = value.get("title") or value.get("名称") or value.get("任务名称")
        title = title or value.get("任务标题", {}).get("中文")
        title = title or value.get("角色", {}).get("名称")
        if not isinstance(title, str) or not title.strip():
            return skip("missing_title")
        relative = source.relative_to(root).as_posix()
        labels = "、".join(p.rsplit("/", 1)[-1].replace("~1", "/").replace("~0", "~") for p in pointers)
        if dialogue_paths:
            labels = values[0].get("所属任务流程", "剧情对话")
        return {"id": entry["id"], "title": title + " / " + labels, "type": family,
                "parent_id": relative, "text": text, "source_file": relative,
                "source_pointer": pointers}, None
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        return skip("invalid_or_missing_source")


def prepare(root, manifest):
    entries = manifest["entries"]
    ids = [entry.get("id") for entry in entries]
    if any(not isinstance(x, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", x) for x in ids):
        raise ValueError("selection IDs must be nonempty ASCII identifiers")
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate selection IDs")
    records, issues = [], []
    for entry in entries:
        record, issue = extract_entry(root, entry)
        (issues if issue else records).append(issue if issue else record)
    return records, issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_ROOT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--selection", type=Path, help="explicit sample selection; default is the existing 30 chunks")
    mode.add_argument("--all", action="store_true", help="scan all parsed JSON files in this snapshot")
    parser.add_argument("--max-chars", type=int, default=800, help="full-mode target chunk length")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    dataset = 'full_corpus' if args.all else 'sample_corpus'
    version = None
    try:
        if args.output_dir is not None and args.output_dir.resolve().is_relative_to(args.raw_root.resolve()):
            raise ValueError("output directory must be outside the raw snapshot")
        if __package__:
            from .evaluate_rag_mvp import validate_output_dir
        else:
            from evaluate_rag_mvp import validate_output_dir
        if args.output_dir is not None:
            validate_output_dir(args.output_dir, protect_sample=args.all)
        version, args.output_dir = artifact_catalog.reserve_corpus(PROJECT, dataset, args.output_dir)
        metadata = {'source_snapshot': args.raw_root.name, 'raw_root': str(args.raw_root.resolve()),
                    'max_chars': args.max_chars if args.all else None,
                    'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        if args.all:
            if args.output_dir.resolve().is_relative_to(DEFAULT_OUTPUT.resolve()):
                raise ValueError("full output must not overwrite the historical sample dataset")
            if __package__:
                from .full_corpus import build_full, write_full
            else:
                from full_corpus import build_full, write_full
            records, issues, audit = build_full(args.raw_root, args.max_chars)
            if not records:
                raise ValueError("no usable full-corpus records; inspect the source snapshot")
            write_full(args.output_dir, records, issues, audit)
            metadata.update(chunks=len(records), files_scanned=audit['files_scanned'])
            (args.output_dir / 'corpus_manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            artifact_catalog.finish_corpus(PROJECT, dataset, version, 'completed', metadata)
            print(json.dumps({"files_scanned": audit["files_scanned"], "chunks": len(records),
                              "issues": len(issues), "elapsed_seconds": audit["elapsed_seconds"],
                              "output_dir": str(args.output_dir)}, ensure_ascii=False))
            return 0
        records, issues = prepare(args.raw_root, read_json(args.selection or DEFAULT_SELECTION))
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name, rows in (("corpus.jsonl", records), ("exclusions.jsonl", issues)):
            (args.output_dir / name).write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        metadata.update(chunks=len(records), selection_sha256=hashlib.sha256(Path(args.selection or DEFAULT_SELECTION).read_bytes()).hexdigest())
        (args.output_dir / 'corpus_manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        artifact_catalog.finish_corpus(PROJECT, dataset, version, 'completed' if records else 'failed', metadata)
        print(json.dumps({"chunks": len(records), "excluded": len(issues),
                          "output_dir": str(args.output_dir)}, ensure_ascii=False))
        return 0 if records else 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        if version and artifact_catalog.load_catalog(PROJECT)['datasets'][dataset]['versions'][version]['status'] == 'building':
            artifact_catalog.finish_corpus(PROJECT, dataset, version, 'failed')
        print(f"Preparation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
