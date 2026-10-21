from pathlib import Path
import os
import platform
import sys
import time
import psutil
from .common import ROOT, RunStore, digest, provenance, read_json
from .contracts import validate_policy
from .protocol import Worker


def load_adapters(path):
    document = read_json(path)
    adapters = document["adapters"]
    if not adapters or len({a["id"] for a in adapters}) != len(adapters):
        raise ValueError("adapter IDs must be nonempty and unique")
    for adapter in adapters:
        if not isinstance(adapter["id"], str) or not adapter["id"] or not all(
                ch.isascii() and (ch.isalnum() or ch in "_-") for ch in adapter["id"]):
            raise ValueError("adapter ID must use ASCII letters, digits, _ or -")
        validate_policy(adapter["policies"])
        command = adapter["command"]
        if not isinstance(command, list) or not command or not all(isinstance(s, str) and s for s in command):
            raise ValueError("adapter command must be an argv array")
        adapter["command"] = [sys.executable if token == "{python}" else token for token in command]
        identity = adapter.get("identity", {})
        if not identity.get("revision") or not identity.get("files"):
            raise ValueError("declare adapter identity.revision and identity.files for executed sources")
        adapter["identity"] = {"revision": identity["revision"],
                               "files": [str(Path(p).resolve()) for p in identity["files"]]}
        for source in adapter["identity"]["files"]:
            if not Path(source).is_file():
                raise ValueError("adapter identity file is missing")
    return adapters


def _store(output, suite, adapters, planned, parameters, paths=(), *, implementation, snapshot_paths=()):
    files = [Path(p) for a in adapters for p in a.get("identity", {}).get("files", [])]
    identity = provenance([*paths, *snapshot_paths, *files], implementation=implementation)
    store = RunStore(output, {"suite": suite, "protocol_id": "spike-jsonl-v1", "adapters": adapters,
        "planned_samples": planned, "parameters": parameters, "provenance": identity,
        "environment": {"platform": platform.platform(), "python": sys.version, "psutil": psutil.__version__,
                        "logical_cpus": os.cpu_count()}, "user_acceptance": "not_evaluated"})
    (store.path / "sources").mkdir()
    for name, sha in identity["files"].items():
        source = Path(name) if Path(name).is_absolute() else ROOT / name
        if source.suffix != ".py" and source not in files and source not in {
                *snapshot_paths, ROOT / "pyproject.toml", ROOT / "uv.lock", ROOT / ".python-version"}:
            continue  # inputs are fingerprinted; copy executed sources, not the corpus
        target = store.path / "sources" / (sha + "-" + source.name)
        if not target.exists():
            target.write_bytes(source.read_bytes())
    return store


def _worker(store, adapter, sample, initialization, timeout):
    def trace(direction, message):
        store.append("trace.jsonl", {"sample_id": sample, "direction": direction, "message": message})
    worker = Worker(adapter["command"], store.path / (digest(sample)[:20] + ".stderr.txt"),
                    timeout=timeout, trace=trace)
    try:
        started = time.perf_counter()
        worker.request("init", "control", {"protocol_version": 1, "policies": adapter["policies"], **initialization})
        return worker, worker.spawn_ms + (time.perf_counter() - started) * 1000
    except BaseException:
        worker.close()
        raise
