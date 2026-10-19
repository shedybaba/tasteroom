"""OpenAI wrapper (Responses API). Everything else talks to the small `LLM` interface, so tests use
a scripted fake and the app runs without a key. Logs token COUNTS only, never prompts or keys."""
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from .config import settings

log = logging.getLogger("tasteroom.llm")
T = TypeVar("T", bound=BaseModel)


@dataclass
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolStep:
    calls: list[ToolCall]
    raw: list[Any] = field(default_factory=list)  # model output items, echoed back next turn
    text: str = ""


class LLM(Protocol):
    async def tool_step(self, *, instructions: str, input_items: list[Any], tools: list[dict]) -> ToolStep: ...

    async def structured(self, *, instructions: str, user: str, schema: type[T], smart: bool = True) -> T: ...


def _log_usage(label: str, model: str, resp: Any) -> None:
    u = getattr(resp, "usage", None)
    if u:
        log.info("llm %s model=%s in=%s out=%s", label, model, u.input_tokens, u.output_tokens)


class OpenAILLM:
    def __init__(self, api_key: str, fast: str, smart: str):
        from openai import AsyncOpenAI

        self.fast, self.smart = fast, smart
        self._client = AsyncOpenAI(api_key=api_key, timeout=45, max_retries=2)

    async def tool_step(self, *, instructions: str, input_items: list[Any], tools: list[dict]) -> ToolStep:
        import json

        resp = await self._client.responses.create(
            model=self.fast, instructions=instructions, input=input_items, tools=tools,
            tool_choice="auto", max_output_tokens=1500,
        )
        _log_usage("tool_step", self.fast, resp)
        calls = [
            ToolCall(it.call_id, it.name, json.loads(it.arguments or "{}"))
            for it in resp.output if it.type == "function_call"
        ]
        return ToolStep(calls=calls, raw=list(resp.output), text=resp.output_text or "")

    async def structured(self, *, instructions: str, user: str, schema: type[T], smart: bool = True) -> T:
        model = self.smart if smart else self.fast
        resp = await self._client.responses.parse(
            model=model, instructions=instructions, input=user, text_format=schema, max_output_tokens=3000,
        )
        _log_usage("structured", model, resp)
        if resp.output_parsed is None:
            raise ValueError("model returned no parseable output")
        return resp.output_parsed


def get_llm() -> LLM | None:
    """None means mock mode: no key, so briefs are templated and the agent is skipped."""
    if not settings.openai_api_key:
        return None
    return OpenAILLM(settings.openai_api_key, settings.openai_model_fast, settings.openai_model_smart)
