from copy import deepcopy
import json


def validate_adaptation(value, adapter_id):
    """Validate a self-reported integration record, not its factual accuracy."""
    prefix = f"adapter {adapter_id}.adaptation"

    def object_fields(item, required, optional, path):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: expected object")
        for field in required:
            if field not in item:
                raise ValueError(f"{path}.{field}: required")
        unknown = set(item) - set(required) - set(optional)
        if unknown:
            raise ValueError(f"{path}.{sorted(unknown)[0]}: unsupported field")

    def text(item, path):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{path}: expected nonempty string")

    object_fields(value, ("target", "ownership", "changes"), ("effort_notes",), prefix)
    text(value["target"], prefix + ".target")
    object_fields(value["ownership"], ("loop", "history", "recovery"), (), prefix + ".ownership")
    for area, owner in value["ownership"].items():
        if not isinstance(owner, str) or owner not in {"candidate", "adapter", "shared"}:
            raise ValueError(f"{prefix}.ownership.{area}: expected candidate, adapter or shared")
    if not isinstance(value["changes"], list):
        raise ValueError(f"{prefix}.changes: expected array")
    fields = ("area", "default_behavior", "adapted_behavior", "reason")
    for number, change in enumerate(value["changes"]):
        path = f"{prefix}.changes[{number}]"
        object_fields(change, fields, (), path)
        for field in fields:
            text(change[field], path + "." + field)
    if "effort_notes" in value:
        text(value["effort_notes"], prefix + ".effort_notes")


def validate_policy(policy):
    if policy.get("tool_error") not in {"recover", "terminate"}:
        raise ValueError("declare tool_error recover or terminate")
    if policy.get("context") not in {"error", "truncate", "compress"}:
        raise ValueError("declare context error, truncate or compress")
    if policy.get("tool_execution") not in {"serial", "parallel"}:
        raise ValueError("declare tool_execution serial or parallel")
    retries = policy.get("max_tool_retries", 0)
    if type(retries) is not int or not 0 <= retries <= 3:
        raise ValueError("max_tool_retries must be between 0 and 3")


def normal_messages(messages):
    value = deepcopy(messages)
    for message in value:
        if message.get("role") == "tool":
            message["content"] = json.loads(message["content"])
        for call in message.get("tool_calls", []):
            call["function"]["arguments"] = json.loads(call["function"]["arguments"])
    return value
