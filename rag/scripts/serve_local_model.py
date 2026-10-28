"""Explicit foreground llama.cpp launcher. Evaluators never invoke this script."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlparse

try:
    from .local_model_config import api_config, generation_options, load_settings
except ImportError:
    from local_model_config import api_config, generation_options, load_settings


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config/local_api.json"
CACHE_TYPES = {"f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1"}


def server_command(settings):
    api = api_config(settings)
    server = settings.get("llama_cpp", {})
    for key in ("executable", "model_path", "device"):
        if not isinstance(server.get(key), str) or not server[key].strip():
            raise ValueError("set executable, model_path and device in the private .local.json file")
    endpoint = urlparse(api["base_url"])
    if (endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}
            or endpoint.path.rstrip("/") != "/v1" or endpoint.username is not None
            or endpoint.query or endpoint.fragment):
        raise ValueError("launcher requires a loopback http:// host with /v1 and no credentials")
    if not isinstance(api.get("model"), str) or not api["model"].strip():
        raise ValueError("set an explicit API model alias")
    for key in ("ctx_size", "parallel", "batch_size", "ubatch_size"):
        if type(server.get(key)) is not int or server[key] < 1:
            raise ValueError("server sizes must be positive integers")
    if server["ubatch_size"] > server["batch_size"]:
        raise ValueError("ubatch_size must not exceed batch_size")
    if server.get("flash_attn") not in {"auto", "on", "off"}:
        raise ValueError("invalid flash_attn")
    if any(server.get(key) not in CACHE_TYPES for key in ("cache_type_k", "cache_type_v")):
        raise ValueError("invalid KV cache type")
    layers = server.get("gpu_layers")
    if not ((type(layers) is int and layers >= 0) or layers in ("auto", "all")):
        raise ValueError("invalid gpu_layers")
    # Reserve capacity for every configured profile, not just the default profile.
    profiles = settings.get("profiles", {})
    configs = [api_config(settings, name) for name in profiles] if profiles else [api]
    max_tokens = max(generation_options(value)["max_tokens"] for value in configs)
    if max_tokens >= server["ctx_size"] // server["parallel"]:
        raise ValueError("each slot needs input space beyond the maximum generation length")
    options = {"--model": server["model_path"], "--device": server["device"], "--split-mode": "none",
               "--host": endpoint.hostname, "--port": endpoint.port or 80, "--alias": api["model"],
               "--ctx-size": server["ctx_size"], "--gpu-layers": layers, "--parallel": server["parallel"],
               "--batch-size": server["batch_size"], "--ubatch-size": server["ubatch_size"],
               "--flash-attn": server["flash_attn"], "--cache-type-k": server["cache_type_k"],
               "--cache-type-v": server["cache_type_v"], "--fit": "off", "--reasoning": "auto",
               "--reasoning-format": "deepseek", "--reasoning-budget": api.get("thinking_budget_tokens", -1),
               "--predict": max_tokens}
    command = [server["executable"], "--offline", "--no-mmproj", "--jinja"]
    for flag, value in options.items():
        command.extend((flag, str(value)))
    return command


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--dry-run", action="store_true", help="check files and print redacted argv; do not start")
    args = parser.parse_args(argv)
    try:
        command = server_command(load_settings(args.config))
        executable = shutil.which(command[0])
        model = Path(command[command.index("--model") + 1])
        if executable is None or not model.is_file() or model.suffix.lower() != ".gguf":
            raise ValueError("local executable or GGUF is missing; check the private override")
        command[0] = executable
        if args.dry_run:
            redacted = list(command)
            redacted[0] = "<local executable>"
            for flag in ("--model", "--device"):
                redacted[redacted.index(flag) + 1] = "<local value>"
            print(json.dumps({"status": "dry_run_only", "argv": redacted}, ensure_ascii=False))
            return 0
        return subprocess.run(command, check=False).returncode
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, TypeError):
        print("Local model launch failed; check config, private paths and llama-server availability.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
