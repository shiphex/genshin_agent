"""Standard-library Core with a synchronous spike-jsonl-v1 broker bridge.

The parent owns providers. This worker owns the loop, unmodified chat history,
serial tool execution and bounded recovery. It never imports benchmark or RAG.
"""
from copy import deepcopy
import json
import sys


MAX_LINE = 4_194_304
POLICIES = {"tool_execution": "serial", "tool_error": "recover", "context": "error", "max_tool_retries": 0}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def receive():
    line = sys.stdin.readline(MAX_LINE + 2)
    if not line:
        raise EOFError("parent input closed")
    if len(line.rstrip("\r\n")) > MAX_LINE or not line.endswith("\n"):
        raise ValueError("invalid JSONL line length or framing")
    message = json.loads(line)
    if not isinstance(message, dict) or any(not isinstance(message.get(key), str) or not message[key]
                                            for key in ("type", "request_id", "session_id")):
        raise ValueError("invalid message envelope")
    return message


def send(message):
    line = encoded(message)
    if len(line) > MAX_LINE:
        raise ValueError("outgoing JSONL line exceeds limit")
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def error(code):
    return {"ok": False, "error": {"code": code}}


def tool_result(response):
    """Keep only the tool wrapper, preserving nested evidence/error details."""
    if response.get("ok") is True and isinstance(response.get("result"), dict):
        return {"ok": True, "result": response["result"]}
    if response.get("ok") is False and isinstance(response.get("error"), dict):
        if isinstance(response["error"].get("code"), str) and response["error"]["code"]:
            return {"ok": False, "error": response["error"]}
    return error("invalid_result")


class Core:
    def __init__(self):
        self.serial = 0
        self.initialized = False
        self.histories = {}

    def initialize(self, request):
        if self.initialized or request.get("protocol_version") != 1 or request["session_id"] != "control":
            raise ValueError("invalid initialization")
        if request.get("policies") != POLICIES:
            raise ValueError("only serial/recover/error/0 policies are supported")
        steps, limit = request.get("max_steps"), request.get("context_limit")
        if type(steps) is not int or steps < 1:
            raise ValueError("max_steps must be a positive integer")
        if limit is not None and (type(limit) is not int or limit < 0):
            raise ValueError("context_limit must be a nonnegative integer or null")
        counter = request.get("context_counter")
        if counter not in {"unicode_content_codepoints_v1", "service_managed"}:
            raise ValueError("unsupported context counter")
        if counter == "service_managed" and limit is not None:
            raise ValueError("service-managed context requires a null limit")
        system = request.get("system")
        if not isinstance(system, str) or not isinstance(request.get("tools"), list):
            raise ValueError("invalid system or tool definitions")
        self.system, self.max_steps, self.context_limit = system, steps, limit
        self.initialized = True

    def provide(self, turn, provider, payload):
        self.serial += 1
        identity = f"p{self.serial}"
        send({"type": "provider_call", "request_id": identity, "session_id": turn["session_id"],
              "parent_id": turn["request_id"], "provider": provider, "payload": payload})
        response = receive()
        if (response["type"], response["request_id"], response["session_id"]) != (
                "provider_result", identity, turn["session_id"]):
            raise ValueError("provider result correlation mismatch")
        return response

    def execute_tool(self, turn, call):
        function = call["function"]
        try:
            arguments = json.loads(function["arguments"])
            if not isinstance(arguments, dict):
                return error("invalid_arguments")
        except (ValueError, TypeError):
            return error("invalid_arguments")
        # The broker validates registered names and tool-specific argument schemas.
        return tool_result(self.provide(turn, "tool", {"call_id": call["id"],
                           "name": function["name"], "arguments": arguments}))

    @staticmethod
    def valid_calls(calls):
        if not isinstance(calls, list):
            return False
        seen = set()
        for call in calls:
            if not isinstance(call, dict) or call.get("type") != "function":
                return False
            identity, function = call.get("id"), call.get("function")
            if not isinstance(identity, str) or not identity or identity in seen or not isinstance(function, dict):
                return False
            if not isinstance(function.get("name"), str) or not function["name"]:
                return False
            if not isinstance(function.get("arguments"), str):
                return False
            seen.add(identity)
        return True

    def turn(self, request):
        content = request.get("content")
        if not isinstance(content, str):
            raise ValueError("turn content must be a string")
        session = request["session_id"]
        if session not in self.histories:
            self.histories[session] = [{"role": "system", "content": self.system}] if self.system else []
        history = self.histories[session]
        history.append({"role": "user", "content": content})
        for _ in range(self.max_steps):
            if self.context_limit is not None:
                units = sum(len(message.get("content") or "") for message in history)
                if units > self.context_limit:
                    return "context_limit", ""
            response = self.provide(request, "model", {"messages": history})
            result = response.get("result")
            if response.get("ok") is not True or not isinstance(result, dict):
                return "failed", ""
            message = result.get("message")
            if not isinstance(message, dict) or message.get("role") != "assistant":
                return "failed", ""
            if message.get("content") is not None and not isinstance(message["content"], str):
                return "failed", ""
            calls = message.get("tool_calls")
            if calls is None:
                calls = []
            if not self.valid_calls(calls):
                return "failed", ""
            history.append(deepcopy(message))
            if calls:
                if result.get("finish_reason") != "tool_calls":
                    return "failed", ""
                for call in calls:
                    wrapper = self.execute_tool(request, call)
                    history.append({"role": "tool", "tool_call_id": call["id"], "content": encoded(wrapper)})
            else:
                if result.get("finish_reason") != "stop" or not isinstance(message.get("content"), str):
                    return "failed", ""
                return "completed", message["content"]
        return "step_limit", ""

    def run(self):
        while True:
            request = receive()
            kind = request["type"]
            reply = {key: request[key] for key in ("request_id", "session_id")}
            if kind == "init":
                self.initialize(request)
                reply.update(type="ready", protocol_version=1)
            elif not self.initialized:
                raise ValueError("worker must be initialized")
            elif kind == "reset":
                self.histories.pop(request["session_id"], None)
                reply.update(type="reset_done")
            elif kind == "turn":
                status, content = self.turn(request)
                reply.update(type="turn_result", status=status, content=content)
            elif kind == "shutdown":
                reply.update(type="closed")
                send(reply)
                return
            else:
                raise ValueError("unsupported control message")
            send(reply)


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="strict")
    try:
        Core().run()
    except EOFError:
        return 0
    except Exception as exc:
        print(f"core_self: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
