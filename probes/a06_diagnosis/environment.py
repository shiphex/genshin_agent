"""Deployment identity and historical reuse gate; never starts a service."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import psutil

from Benchmarks.agent_story.providers import QwenClient, SYSTEM, SEARCH_TOOL
from Benchmarks.agent_story.scenarios import load_scenarios
from Benchmarks.support.common import ROOT, read_json, file_hash, write_json
from probes.core_self.worker import POLICIES
from rag.scripts.evaluate_rag_mvp import load_jsonl
from .runner import new_store, seal

REVIEW = ROOT / "Benchmarks/reviews/core-probe-20261028"
SOURCES = ["probes/core_self/worker.py", "Benchmarks/agent_story/providers.py",
           "Benchmarks/agent_story/http_worker.py", "Benchmarks/agent_story/scenarios.py",
           "Benchmarks/agent_story/scenarios.json", "Benchmarks/support/contracts.py",
           "rag/scripts/evaluate_rag_mvp.py", "rag/scripts/prepare_eval.py",
           "rag/scripts/artifact_catalog.py", "rag/eval/questions.json",
           "rag/scripts/local_model_config.py"]


def validate_diagnostic_config(current, historical):
    current, historical = deepcopy(current), deepcopy(historical)
    mode = current.pop("tool_choice_mode", "native")
    historical.pop("tool_choice_mode", None)
    if mode not in {"native", "required_single_tool", "required_single_tool_prefill"} or current != historical:
        raise ValueError("only tool_choice_mode may differ from historical diagnostic API config")


def public_config_matches(path, reference_bytes):
    return json.loads(Path(path).read_text(encoding="utf-8-sig")) == json.loads(reference_bytes)


def compare_environment(current, historical):
    checks = {"config": current["config"] == historical["config"],
              "source_and_input_hashes": current["hashes"] == historical["hashes"]}
    for key in ("model_sha256", "server_sha256"):
        checks[key] = bool(current["deployment"].get(key)) and current["deployment"].get(key) == historical["deployment"].get(key)
    for key in ("ready", "launch_configuration_verified"):
        checks[key] = current["deployment"].get(key) is True
    return {"reusable": all(checks.values()), "checks": checks}


def verify_raw_sources(raw_root, expected):
    observed = {name: file_hash(Path(raw_root) / name) for name in expected}
    if observed != expected:
        raise ValueError("frozen story source changed")
    return observed


def historical_identity(path):
    manifest = read_json(Path(path) / "manifest.json")
    files = manifest["provenance"]["files"]
    hashes = {}
    for rel in SOURCES:
        matches = [sha for name, sha in files.items()
                   if name.replace("\\", "/").endswith("/" + rel) or name == rel]
        hashes[rel] = matches[0] if len(set(matches)) == 1 else None
    corpus = [v for k, v in files.items() if k.replace("\\", "/").endswith("/rag/data/corpus/corpus.jsonl")]
    hashes["corpus"] = corpus[0] if len(corpus) == 1 else None
    return {"config": QwenClient(manifest["parameters"]["model"]).config, "hashes": hashes,
            "deployment": read_json(REVIEW / "evidence/reports/core-probe-live-r001/model-identity.json"),
            "manifest": manifest}


def expected_server_command(project):
    """Read the historical launch implementation externally; do not copy or edit it."""
    directory = project / "rag/scripts"
    source = directory / "serve_local_model.py"
    previous = list(sys.path)
    try:
        sys.path.insert(0, str(directory))
        spec = importlib.util.spec_from_file_location("a06_historical_launcher", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        command = module.server_command(module.load_settings(project / "rag/config/local_api.json"))
        command[0] = shutil.which(command[0]) or command[0]
        return command
    finally:
        sys.path[:] = previous


def inspect_environment(output, historical_run, config_path, corpus_path, raw_root, server_log=None):
    history = historical_identity(historical_run)
    config = QwenClient(read_json(config_path)).config
    validate_diagnostic_config(config, history["config"])
    store = new_store(output, "environment", {"config_path": str(Path(config_path).resolve())}, [config_path])
    try:
        project = Path(raw_root).resolve().parents[2]
        corpus = load_jsonl(corpus_path)
        scene = next(s for s in load_scenarios(ROOT)["scenarios"] if s["id"] == "a06")
        hashes = {name: file_hash(ROOT / name) for name in SOURCES}
        hashes["corpus"] = file_hash(corpus_path)
        expected = expected_server_command(project)
        model_path = Path(expected[expected.index("--model") + 1])
        deployment = {"ready": False, "launch_configuration_verified": False,
                      "model_path": str(model_path), "model_sha256": file_hash(model_path),
                      "server_sha256": file_hash(expected[0])}
        processes = [p for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() in {"llama-server", "llama-server.exe"}]
        if len(processes) == 1:
            process = processes[0]
            argv = process.cmdline()  # Never persist unfiltered command lines or headers.
            deployment.update(pid=process.pid, create_time=process.create_time(),
                              executable=str(Path(process.exe()).resolve()))
            def same_command(a, b):
                return Path(a[0]).resolve() == Path(b[0]).resolve() and a[1:] == b[1:]
            public_hash = file_hash(project / "rag/config/local_api.json")
            private_hash = file_hash(project / "rag/config/local_api.local.json")
            launch_sources = {}
            for name in ("serve_local_model.py", "local_model_config.py"):
                rel = "rag/scripts/" + name
                data = subprocess.run(["git", "show", f"fa31e46:{rel}"], cwd=project, capture_output=True, check=True).stdout
                launch_sources[rel] = file_hash(project / rel) == hashlib.sha256(data).hexdigest()
            deployment.update(public_config_sha256=public_hash, private_config_sha256=private_hash,
                              launcher_sources_match=launch_sources,
                              launch_configuration_verified=same_command(argv, expected) and all(launch_sources.values())
                              and public_config_matches(project / "rag/config/local_api.json", subprocess.run(
                                  ["git", "show", "fa31e46:rag/config/local_api.json"], cwd=project,
                                  capture_output=True, check=True).stdout)
                              and private_hash == history["deployment"]["private_config_sha256"])
            deployment["launch_reference_commit"] = "fa31e46"
            models = QwenClient(config).transport("models", None, 10)
            deployment["model_ids"] = [m["id"] for m in models["data"]]
            deployment["ready"] = config["model"] in deployment["model_ids"]
        env = {"config": config, "hashes": hashes, "deployment": deployment,
               "corpus": str(Path(corpus_path).resolve()), "corpus_rows": len(corpus),
               "raw_root": str(Path(raw_root).resolve()), "historical_run": str(Path(historical_run).resolve()),
               "server_log": str(Path(server_log).resolve()) if server_log else None,
               "system": SYSTEM, "tools": [SEARCH_TOOL], "policies": POLICIES}
        parameters = history["manifest"]["parameters"]
        env["historical_session_matches"] = (parameters["system"] == SYSTEM and parameters["tools"] == [SEARCH_TOOL]
            and parameters["max_steps"] == 8 and parameters["top_k"] == 5 and parameters["timeout"] == 240
            and all(a["policies"] == POLICIES for a in history["manifest"]["adapters"]))
        env["reuse_gate"] = compare_environment(env, history)
        env["reuse_gate"]["checks"]["session"] = env["historical_session_matches"]
        env["reuse_gate"]["reusable"] &= env["historical_session_matches"]
        write_json(store.path / "environment.json", env, exclusive=True)
        write_json(store.path / "scenario.json", scene, exclusive=True)
        store.finish("completed")
    except BaseException as exc:
        store.finish("failed", type(exc).__name__)
        raise
    finally:
        seal(store.path)
    return store.path


def load_environment(path, require_service=False):
    env = read_json(Path(path) / "environment.json")
    for name, sha in env["hashes"].items():
        target = Path(env["corpus"]) if name == "corpus" else ROOT / name
        if file_hash(target) != sha:
            raise ValueError(f"environment fingerprint changed: {name}")
    materials = read_json(REVIEW / "evidence/agent_story/agent/core-probe-live-r001/materials.json")
    expected_raw = {s["source_file"]: s["source_sha256"] for s in materials["a06"]["frozen_sources"]}
    env["raw_source_hashes"] = verify_raw_sources(env["raw_root"], expected_raw)
    if require_service:
        deployment = env["deployment"]
        if not deployment.get("ready"):
            raise ValueError("same-deployment model service is not ready")
        if not deployment.get("launch_configuration_verified"):
            raise ValueError("model launch configuration is not verified")
        process = psutil.Process(deployment["pid"])
        if process.create_time() != deployment["create_time"] or file_hash(process.exe()) != deployment["server_sha256"]:
            raise ValueError("model deployment changed")
    return env, read_json(Path(path) / "scenario.json")
