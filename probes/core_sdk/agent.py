"""LangChain owns the graph loop; this bridge owns the fixed-history wire format."""
from copy import deepcopy
import json
import os

# This worker has exactly one external I/O boundary: the parent JSONL broker.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from pydantic import PrivateAttr


POLICIES = {"tool_execution": "serial", "tool_error": "recover", "context": "error", "max_tool_retries": 0}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def from_chat(raw):
    """Retain the raw assistant including null content and unparsed arguments."""
    role = raw["role"]
    if role == "assistant":
        calls = []
        for call in raw.get("tool_calls") or []:
            try:
                arguments = json.loads(call["function"]["arguments"])
            except (ValueError, TypeError):
                arguments = {}
            # SDK scheduling needs an object; the tool bridge validates the raw copy.
            calls.append({"name": call["function"]["name"], "args": arguments if isinstance(arguments, dict) else {},
                          "id": call["id"], "type": "tool_call"})
        return AIMessage(content=raw.get("content") or "", tool_calls=calls,
                         additional_kwargs={"_spike_raw": deepcopy(raw)})
    if role == "tool":
        return ToolMessage(content=raw["content"], tool_call_id=raw["tool_call_id"])
    if role == "system":
        return SystemMessage(content=raw["content"])
    if role == "user":
        return HumanMessage(content=raw["content"])
    raise ValueError("unsupported message role")


def to_chat(messages):
    result = []
    for message in messages:
        if isinstance(message, AIMessage):
            result.append(deepcopy(message.additional_kwargs["_spike_raw"]))
        elif isinstance(message, ToolMessage):
            result.append({"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content})
        else:
            result.append({"role": "system" if isinstance(message, SystemMessage) else "user", "content": message.content})
    return result


class TurnStop(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__(status)


class BrokerModel(BaseChatModel):
    """A real SDK chat-model implementation whose transport is the parent broker."""
    _owner: object = PrivateAttr()

    def __init__(self, owner):
        super().__init__(cache=False)
        self._owner = owner

    @property
    def _llm_type(self):
        return "spike-parent-broker"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        # The parent fixes tool schemas and generation parameters from init.
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        owner = self._owner
        owner.current = list(messages)
        if owner.steps >= owner.config["max_steps"]:
            raise TurnStop("step_limit")
        wire = to_chat(messages)
        if owner.config["context_limit"] is not None and sum(len(message.get("content") or "") for message in wire) > owner.config["context_limit"]:
            raise TurnStop("context_limit")
        owner.steps += 1
        response = owner.broker("model", {"messages": wire})
        if response.get("ok") is not True:
            raise TurnStop("failed")
        result = response["result"]
        raw = result["message"]
        if raw.get("role") != "assistant" or not isinstance(raw.get("content"), (str, type(None))):
            raise TurnStop("failed")
        message = from_chat(raw)
        owner.current.append(message)
        owner.raw_calls = {call["id"]: deepcopy(call) for call in raw.get("tool_calls") or []}
        has_calls = bool(raw.get("tool_calls"))
        if (result.get("finish_reason") != ("tool_calls" if has_calls else "stop") or
                (not has_calls and not isinstance(raw.get("content"), str))):
            raise TurnStop("failed")
        return ChatResult(generations=[ChatGeneration(message=message)])


def tool_result(response):
    """Strip transport fields and detect invalid tool output without retrying."""
    if isinstance(response, dict):
        if response.get("ok") is True and isinstance(response.get("result"), dict):
            return {"ok": True, "result": response["result"]}
        error = response.get("error")
        if response.get("ok") is False and isinstance(error, dict) and isinstance(error.get("code"), str):
            return {"ok": False, "error": error}
    return {"ok": False, "error": {"code": "invalid_result"}}


class BrokerTools(AgentMiddleware):
    def __init__(self, owner):
        self.owner = owner

    def wrap_tool_call(self, request, handler):
        # ToolNode still schedules each model-issued call. The broker, rather than
        # SDK argument coercion / error prose, is the protocol's tool executor.
        call = self.owner.raw_calls[request.tool_call["id"]]
        try:
            arguments = json.loads(call["function"]["arguments"])
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must be an object")
        except (ValueError, TypeError):
            result = {"ok": False, "error": {"code": "invalid_arguments"}}
        else:
            result = tool_result(self.owner.broker("tool", {"call_id": call["id"],
                                 "name": call["function"]["name"], "arguments": arguments}))
        message = ToolMessage(content=encoded(result), tool_call_id=call["id"])
        self.owner.current.append(message)
        return message


def unavailable_tool(**kwargs):
    """Tool execution is exclusively performed by BrokerTools middleware."""
    raise RuntimeError("broker middleware required")


class CoreAgent:
    def __init__(self, config, broker):
        if config["policies"] != POLICIES:
            raise ValueError("only serial/recover/error/0 is supported")
        if config["context_counter"] not in {"unicode_content_codepoints_v1", "service_managed"}:
            raise ValueError("unsupported context counter")
        if type(config["max_steps"]) is not int or config["max_steps"] < 1:
            raise ValueError("invalid budget")
        limit = config["context_limit"]
        if config["context_counter"] == "service_managed":
            if limit is not None:
                raise ValueError("service-managed context must have no local limit")
        elif type(limit) is not int or limit < 1:
            raise ValueError("invalid context limit")
        self.config, self.broker = deepcopy(config), broker
        self.histories, self.raw_calls = {}, {}
        self.current, self.steps = [], 0
        tools = [StructuredTool.from_function(func=unavailable_tool, name=tool["function"]["name"],
                 description=tool["function"].get("description") or tool["function"]["name"],
                 args_schema=tool["function"]["parameters"]) for tool in config["tools"]]
        self.graph = create_agent(BrokerModel(self), tools=tools, middleware=[BrokerTools(self)])

    def reset(self, session):
        self.histories.pop(session, None)
        self.current, self.raw_calls, self.steps = [], {}, 0

    def turn(self, session, content):
        initial = [SystemMessage(content=self.config["system"])] if self.config["system"] else []
        self.current = list(self.histories.get(session, initial)) + [HumanMessage(content=content)]
        self.steps, self.raw_calls = 0, {}
        try:
            # Serializes both graph Send scheduling and ToolNode's sync executor.
            # The graph itself continues model -> tools -> model until completion.
            state = self.graph.invoke({"messages": self.current},
                                      config={"max_concurrency": 1, "recursion_limit": 4 * self.config["max_steps"] + 10})
            self.current = state["messages"]
            status, result = "completed", self.current[-1].content
        except TurnStop as exc:
            status, result = exc.status, ""
        self.histories[session] = list(self.current)
        return {"status": status, "content": result}
