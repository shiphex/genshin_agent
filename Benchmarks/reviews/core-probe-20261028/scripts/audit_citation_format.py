"""Supplemental membership audit only; leave the public citation checker unchanged."""
from collections import defaultdict
import json
import sys
from pathlib import Path
import re

run = Path(__file__).resolve().parents[1] / "evidence/agent_story/agent/core-probe-live-r001"
rows = [json.loads(x) for x in (run / "results.jsonl").read_text(encoding="utf-8").splitlines()]
groups = defaultdict(lambda: {"turns": 0, "recognized_by_public_checker": 0,
                             "nonstandard_format_turns": 0, "citation_occurrences": 0,
                             "known_occurrences": 0, "unknown_occurrences": 0})
audit = []
for row in rows:
    seen = set()
    for turn in row["turns"]:
        for record in row["provider_records"]:
            if record["provider"] == "tool" and record["turn"] <= turn["turn"]:
                seen.update(s["id"] for s in record["response"].get("result", {}).get("evidence", []))
        ids = re.findall(r"\[片段ID:\s*([A-Za-z0-9_-]+)\]", turn["result"]["content"])
        unknown = [c for c in ids if c not in seen]
        counts = groups[row["adapter_id"]]
        counts["turns"] += 1
        counts["recognized_by_public_checker"] += bool(turn["citations"]["has_citations"])
        counts["nonstandard_format_turns"] += bool(ids)
        counts["citation_occurrences"] += len(ids)
        counts["unknown_occurrences"] += len(unknown)
        counts["known_occurrences"] += len(ids) - len(unknown)
        audit.append({"sample_id": row["sample_id"], "turn": turn["turn"], "nonstandard_ids": ids,
                      "unknown_ids": unknown, "seen_ids": sorted(seen)})
result = {"scope": "supplemental nonstandard [片段ID: ID] membership only; not a public-checker pass or semantic-support verdict",
          "groups": dict(groups), "turns": audit}
output = Path(sys.argv[1])
output.mkdir(parents=True, exist_ok=True)
with (output / "citation-format-audit.json").open("x", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
print(json.dumps({"groups": dict(groups)}, indent=2))
