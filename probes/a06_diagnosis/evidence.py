"""Keep source coverage, delivered evidence and semantic judgments distinct."""
from copy import deepcopy
import json
from pathlib import Path

from Benchmarks.agent_story.providers import freeze_sources
from Benchmarks.support.common import read_json
from rag.scripts.evaluate_rag_mvp import map_source_evidence, evidence_coverage
from rag.scripts.prepare_eval import resolve_pointer


def source_anchors(scene, raw_root):
    anchors = []
    for source in freeze_sources(scene, raw_root):
        text = source["text"]
        document = read_json(Path(raw_root) / source["source_file"])
        try:
            speaker = resolve_pointer(document, source["source_pointer"].rsplit("/", 1)[0] + "/说话者")
        except (ValueError, KeyError):
            speaker = None
        anchors.append({**source, "start": 0, "end": len(text),
                        "speaker": speaker})
    return anchors


def map_anchors(anchors, corpus):
    mapped = []
    for anchor in anchors:
        try:
            question = {"id": "diagnostic-anchor", "expected_source_evidence": [[anchor]]}
            ids = map_source_evidence([question], corpus)[0]["expected_evidence"][0]
        except ValueError:
            ids = []
        mapped.append({**anchor, "ids": ids})
    return mapped


def coverage(mapped, hits):
    groups = [a["ids"] for a in mapped]
    result = evidence_coverage(groups, hits)
    ranks = {h["id"]: i for i, h in enumerate(hits, 1)}
    return {**(result or {"covered_groups": 0, "total_groups": 0, "recall": None, "all_covered": False}),
            "unmapped_groups": sum(not a["ids"] for a in mapped),
            "anchors": [{"source_file": a["source_file"], "source_pointer": a["source_pointer"],
                         "rank": min((ranks[i] for i in a["ids"] if i in ranks), default=None)} for a in mapped],
            "semantic_sufficiency": "pending_review"}


def audit_transfers(trace, records):
    """Compare complete tool wrappers with all subsequent API request messages."""
    calls = {e["message"]["request_id"]: e["message"]["payload"].get("call_id")
             for e in trace if e["message"].get("type") == "provider_call"
             and e["message"].get("provider") == "tool"}
    results = []
    for entry in trace:
        message = entry["message"]
        if message.get("type") != "provider_result" or message["request_id"] not in calls:
            continue
        cid = calls[message["request_id"]]
        wrapper = {k: deepcopy(message[k]) for k in ("ok", "result", "error") if k in message}
        matches = []
        for record in records:
            if record.get("event") != "request" or not isinstance(record.get("payload"), dict):
                continue
            for item in record["payload"].get("messages", []):
                if item.get("role") == "tool" and item.get("tool_call_id") == cid:
                    try:
                        exact = json.loads(item["content"]) == wrapper
                    except (ValueError, TypeError, KeyError):
                        exact = False
                    matches.append({"turn": record["turn"], "request": record["request"], "exact_match": exact})
        results.append({"call_id": cid, "delivered": bool(matches),
                        "exact_match": bool(matches) and all(m["exact_match"] for m in matches), "requests": matches})
    return results


def audit_injected_history(fixture, records):
    expected = fixture["messages"]
    requests = [{"turn": r["turn"], "request": r["request"],
                 "exact_match": r["payload"]["messages"][:len(expected)] == expected}
                for r in records if r.get("event") == "request" and r.get("endpoint") == "chat/completions"]
    return {"kind": "controlled_history_delivery", "delivered": bool(requests),
            "exact_match": bool(requests) and all(r["exact_match"] for r in requests), "requests": requests}
