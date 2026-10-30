"""Record the JSON sent to the existing client without changing its messages."""
from copy import deepcopy
from Benchmarks.agent_story.providers import QwenClient
from Benchmarks.support.common import digest

FORCED_SEARCH = {"type": "function", "function": {"name": "search_story"}}


def api_statistics(records):
    responses = [r for r in records if r.get("event") == "response" and r.get("endpoint") == "chat/completions"]
    return {"api_http_responses": len(responses),
            "api_completed_responses": sum(r["raw_response"].get("choices", [{}])[0].get("finish_reason")
                in {"stop", "tool_calls"} for r in responses),
            "new_model_requests": sum(r.get("event") == "request" and r.get("endpoint") == "chat/completions"
                and r.get("context_origin") == "captured_api_payload" for r in records)}


class ToolChoiceUnsupported(ValueError):
    pass


class ObservedClient(QwenClient):
    def __init__(self, config, emit, transport=None):
        super().__init__(config, transport=transport)
        original = self.transport
        self.emit = emit
        self.turn, self.number, self.force = 0, 0, False
        self.force_status = "not_requested"
        self.choice_guard = None

        def observed(endpoint, payload, timeout):
            metadata = {"turn": self.turn, "request": self.number, "endpoint": endpoint,
                        "context_origin": "captured_api_payload"}
            self.emit({**metadata, "event": "request", "payload": deepcopy(payload),
                       "payload_sha256": digest(payload)})
            try:
                response = original(endpoint, payload, timeout)
            except BaseException as exc:
                self.emit({**metadata, "event": "error", "exception_type": type(exc).__name__})
                raise
            self.emit({**metadata, "event": "response", "raw_response": deepcopy(response),
                       "response_sha256": digest(response)})
            return response
        self.transport = observed

    def begin(self, turn, force_first=False):
        self.turn, self.number, self.force = turn, 0, force_first

    def preflight(self):
        state = self.turn, self.number, self.force, self.force_status
        self.begin(0)
        try:
            return super().preflight()
        finally:
            self.turn, self.number, self.force, self.force_status = state

    def chat(self, messages, tools, remaining, tool_choice=None):
        self.number += 1
        forced = self.turn == 1 and self.number == 1 and self.force
        if forced:
            tool_choice = deepcopy(FORCED_SEARCH)
            self.force_status = "attempted"
        try:
            result = super().chat(messages, tools, remaining, tool_choice=tool_choice)
        except Exception as exc:
            if forced:
                if isinstance(exc, ValueError) and str(exc) == "specified native tool call was not honored":
                    self.force_status = "unsupported_or_ignored"
                    raise ToolChoiceUnsupported("specified search_story was not honored") from exc
                self.force_status = "request_failed"
            raise
        if forced:
            calls = result["message"].get("tool_calls") or []
            accepted = self.choice_guard() if self.choice_guard is not None else True
            if not accepted or result["finish_reason"] != "tool_calls" or not calls or any(
                    call["function"]["name"] != "search_story" for call in calls):
                self.force_status = "unsupported_or_ignored"
                raise ToolChoiceUnsupported("specified search_story was not honored")
            self.force_status = "succeeded"
        return result
