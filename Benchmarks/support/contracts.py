from copy import deepcopy
import json


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
