"""Shared API settings and private sibling overrides for explicit llama.cpp use."""
from copy import deepcopy
import json
import math
from pathlib import Path


API_FIELDS = {"base_url", "model", "api_key_env", "timeout", "max_tokens", "top_k", "temperature",
              "seed", "generation", "enable_thinking", "thinking_budget_tokens"}
PROFILE_FIELDS = {"timeout", "max_tokens", "enable_thinking", "thinking_budget_tokens", "generation"}
GENERATION_FIELDS = {"temperature", "seed", "top_p", "top_k", "min_p", "presence_penalty",
                     "frequency_penalty", "repeat_penalty"}
SERVER_FIELDS = {"executable", "model_path", "device", "ctx_size", "gpu_layers", "parallel",
                 "batch_size", "ubatch_size", "flash_attn", "cache_type_k", "cache_type_v"}


def _object(value, allowed):
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError("unsupported configuration fields; credentials must use api_key_env")


def _check_shape(settings):
    _object(settings, API_FIELDS | {"profile", "profiles", "llama_cpp"})
    _object(settings.get("generation", {}), GENERATION_FIELDS)
    _object(settings.get("llama_cpp", {}), SERVER_FIELDS)
    profiles = settings.get("profiles", {})
    if not isinstance(profiles, dict):
        raise ValueError("profiles must be an object")
    for name, profile in profiles.items():
        if not isinstance(name, str) or not name:
            raise ValueError("profile names must be nonempty strings")
        _object(profile, PROFILE_FIELDS)
        _object(profile.get("generation", {}), GENERATION_FIELDS)


def _merge(base, override):
    result = deepcopy(base)
    for key, value in override.items():
        result[key] = _merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else deepcopy(value)
    return result


def load_settings(path):
    """Merge api.json with optional api.local.json; never write or expand paths."""
    path = Path(path)
    settings = json.loads(path.read_text(encoding="utf-8-sig"))
    _check_shape(settings)
    local = path.with_name(path.stem + ".local" + path.suffix)
    if local.is_file():
        override = json.loads(local.read_text(encoding="utf-8-sig"))
        _check_shape(override)
        settings = _merge(settings, override)
    return settings


def api_config(settings, profile=None):
    """Project only API fields; private launch paths never reach client manifests."""
    _check_shape(settings)
    result = {key: deepcopy(value) for key, value in settings.items() if key in API_FIELDS}
    profiles = settings.get("profiles", {})
    selected = profile if profile is not None else settings.get("profile")
    if selected is not None:
        if not isinstance(selected, str) or selected not in profiles:
            raise ValueError("unknown generation profile")
        result = _merge(result, profiles[selected])
        result["profile"] = selected
    elif profiles:
        raise ValueError("select a generation profile")
    generation_options(result)
    if "timeout" in result:
        _number(result["timeout"], minimum=0, exclusive=True)
    if "top_k" in result:
        _integer(result["top_k"], minimum=1)
    if result.get("api_key_env") is not None and (not isinstance(result["api_key_env"], str) or not result["api_key_env"].strip()):
        raise ValueError("api_key_env must name an environment variable")
    return result


def load_api_config(path, profile=None):
    return api_config(load_settings(path), profile)


def _integer(value, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ValueError("invalid integer configuration value")


def _number(value, minimum, maximum=None, exclusive=False):
    if (type(value) not in {int, float} or not math.isfinite(value) or value < minimum
            or (exclusive and value == minimum) or (maximum is not None and value > maximum)):
        raise ValueError("invalid numeric configuration value")


def generation_options(config):
    """Build llama.cpp request fields; root top_k always means retrieval."""
    generation = config.get("generation", {})
    _object(generation, GENERATION_FIELDS)
    options = {"temperature": config.get("temperature", 0), "seed": config.get("seed", 42),
               "max_tokens": config.get("max_tokens", 768), **generation}
    _integer(options["max_tokens"], minimum=1)
    _integer(options["seed"])
    _number(options["temperature"], 0, 2)
    for key in ("top_p", "min_p"):
        if key in options:
            _number(options[key], 0, 1)
    if "top_k" in options:
        _integer(options["top_k"], minimum=0)
    for key in ("presence_penalty", "frequency_penalty"):
        if key in options:
            _number(options[key], -2, 2)
    if "repeat_penalty" in options:
        _number(options["repeat_penalty"], 0, exclusive=True)
    thinking = config.get("enable_thinking", False)
    if type(thinking) is not bool:
        raise ValueError("enable_thinking must be boolean")
    if "thinking_budget_tokens" in config:
        budget = config["thinking_budget_tokens"]
        _integer(budget, minimum=0)
        if budget >= options["max_tokens"] or (not thinking and budget != 0):
            raise ValueError("thinking budget must leave room for final content")
        options["thinking_budget_tokens"] = budget
    options["chat_template_kwargs"] = {"enable_thinking": thinking}
    options["reasoning_format"] = "deepseek"
    return options
