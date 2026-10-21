"""Immutable run records, input identity and explicit report denominators."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import threading
import uuid


BENCH = Path(__file__).resolve().parents[1]
ROOT = BENCH.parent
SCHEMA = 1


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode("utf-8")).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value, exclusive=False):
    with Path(path).open("x" if exclusive else "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def positive(value):
    if type(value) is not int or value < 1:
        raise ValueError("expected a positive integer")
    return value


def distribution(values):
    values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return {"n": len(values), "median": statistics.median(values) if values else None,
            "min": min(values) if values else None, "max": max(values) if values else None}


def summarize(rows):
    return {"total": len(rows),
            "completed": sum(r.get("execution_status") == "completed" for r in rows),
            "correct": sum(r.get("correct") is True for r in rows),
            "incorrect": sum(r.get("correct") is False for r in rows),
            "unjudged": sum(r.get("correct") is None for r in rows),
            "conformance": {"total": len(rows),
                **{status: sum(r.get("conformance_status") == status for r in rows)
                   for status in ("passed", "failed", "not_evaluated")},
                "not_recorded": sum("conformance_status" not in r for r in rows)},
            "elapsed_ms": distribution([r.get("elapsed_ms") for r in rows]),
            "semantic_status": "not_evaluated", "user_acceptance": "not_evaluated"}


def provenance(paths=(), *, implementation=None):
    sources = set(BENCH.glob("*.py")) | set((BENCH / "support").glob("*.py"))
    if implementation is not None:
        sources.update(Path(implementation).glob("*.py"))
    sources.update(Path(p).resolve() for p in paths)
    sources.update(ROOT / name for name in ("pyproject.toml", "uv.lock", ".python-version"))
    sources = sorted(sources)
    hashes = {(p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p)): file_hash(p)
              for p in sources if p.is_file()}
    def git(*args):
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    return {"git_commit": git("rev-parse", "HEAD"), "git_status": git("status", "--porcelain"),
            "files": hashes}


def output_path(suite, requested=None, *, category=None):
    base = (BENCH / "outputs").resolve()
    parent = base / category / suite if category else base / suite
    target = Path(requested).resolve() if requested else parent / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:10])
    if not target.is_relative_to(parent) or target == parent:
        raise ValueError(f"output must be a new run directory under {parent}")
    return target


class RunStore:
    def __init__(self, output, metadata):
        self.path = Path(output)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.mkdir()  # exclusive; an interrupted run is never reusable
        self.manifest = {"schema_version": SCHEMA, "layout_version": 2, "run_id": self.path.name,
                         "started_at": utc_now(), "status": "running", **metadata}
        write_json(self.path / "manifest.json", self.manifest, exclusive=True)
        (self.path / "results.jsonl").touch(exist_ok=False)
        (self.path / "trace.jsonl").touch(exist_ok=False)
        self.lock = threading.Lock()

    def append(self, name, value):
        with self.lock:
            with (self.path / name).open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(encoded(value) + "\n")
                handle.flush()

    def result(self, row):
        self.append("results.jsonl", row)

    def finish(self, status, error=None):
        rows = read_rows(self.path / "results.jsonl")
        seen = {r["sample_id"] for r in rows}
        for planned in self.manifest.get("planned_samples", []):
            if planned["sample_id"] not in seen:
                self.result({**planned, "execution_status": "not_started", "correct": None,
                             "error": error or "run stopped before this sample"})
        self.manifest.update(status=status, finished_at=utc_now(), error=error)
        write_json(self.path / "manifest.json", self.manifest)
        rows = read_rows(self.path / "results.jsonl")
        write_json(self.path / "summary.json", summarize(rows))
