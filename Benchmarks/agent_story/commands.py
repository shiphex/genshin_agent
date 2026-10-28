"""Story-specific input validation, model configuration and preflight."""
from .providers import QwenClient
from .runner import run_agent
from .scenarios import load_scenarios
from Benchmarks.support.common import BENCH, ROOT, file_hash, read_json, read_rows, write_json
from Benchmarks.support.execution import _store
from rag.scripts.local_model_config import load_api_config


def preflight(args, output):
    client = QwenClient(load_api_config(args.config, getattr(args, "profile", None)))
    store = _store(output, "preflight", [], [], {}, [args.config, ROOT / "rag/scripts/local_model_config.py"], implementation=BENCH / "agent_story")
    try:
        check = client.preflight()
        write_json(output / "preflight.json", {"model": client.config, **check}, exclusive=True)
        store.finish("completed")
    except BaseException as exc:
        store.finish("failed", type(exc).__name__)
        raise
    return output


def execute(args, adapters, output):
    suite = load_scenarios(ROOT)
    if args.scenarios:
        known = {scene["id"] for scene in suite["scenarios"]}
        if set(args.scenarios) - known:
            raise ValueError("unknown selected ID")
        suite["scenarios"] = [s for s in suite["scenarios"] if s["id"] in args.scenarios]
    catalog = read_json(ROOT / "rag/catalog.json")
    corpus_path = args.corpus or ROOT / catalog["datasets"]["full_corpus"]["path"]
    if not args.corpus and file_hash(corpus_path) != catalog["files"][catalog["datasets"]["full_corpus"]["path"]]["sha256"]:
        raise ValueError("baseline corpus fingerprint mismatch")
    corpus = read_rows(corpus_path)
    if not corpus or len({r["id"] for r in corpus}) != len(corpus):
        raise ValueError("corpus must have nonempty unique IDs")
    client = QwenClient(load_api_config(args.config, getattr(args, "profile", None)))
    return run_agent(adapters, output, suite, corpus, client, args.raw_root or ROOT / catalog["raw_root"],
        args.repeats, args.max_steps, args.top_k, args.measure, args.timeout, model_service_pid=args.model_service_pid,
        input_paths=[args.adapters, args.config, corpus_path, ROOT / "rag/eval/questions.json", ROOT / "rag/catalog.json"])
