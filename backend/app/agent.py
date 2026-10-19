"""Tool-calling agent. Decides which domains and filters fit the organizer's event goal."""
import asyncio
import json
import logging
import time

from .llm import LLM
from .tools import TOOL_SCHEMAS, PlanContext, execute

log = logging.getLogger("tasteroom.agent")

MAX_TOOL_CALLS = 10
BUDGET_SECONDS = 60

SYSTEM_PROMPT = """You are an event-programming agent for community organizers. Use the tools to gather Qloo \
taste-data recommendations that fit this community and the event goal.
- Always call resolve_tastes first.
- Decide which domains matter for the goal. Include every domain that could plausibly help the event (music for any \
social gathering, party or mixer; sponsors for anything with a budget or an audience; content for watch parties and \
listening events). Skip a domain only when the goal clearly makes it irrelevant, for example no music at a \
podcast-listening meetup or no content at a run-club social.
- If a city is given, call find_venues and choose a venue_kind that suits the event. Set day or price_level_max ONLY \
if the event goal or form options state one; never assume them, because each filter narrows the venue list.
- content_type applies only to the content domain.
- Call explain for every domain you use.
- Be fast: call independent tools together in ONE step. For example, after resolve_tastes, request resolve_city, \
every recommend call and find_venues all at once; then request explain for every domain at once together with finish.
- Never name a recommendation that a tool did not return. Do not write the event brief; a separate step does that.
- Call finish when done. Use as few tool calls as you need (maximum 10)."""


def user_message(ctx: PlanContext) -> str:
    r = ctx.request
    return json.dumps({
        "community": r.community_name, "city": r.city, "event_goal": r.event_goal,
        "form_options": r.options.model_dump(exclude_none=True),
        "members": [{"name": m.name, "tastes": [t.text for t in m.tastes]} for m in r.members],
    })


async def run_agent(ctx: PlanContext, llm: LLM) -> bool:
    """Run the loop. Returns True if the agent called finish; False if it stopped, ran out of calls or
    ran out of time. Raises on LLM errors; the planner falls back to the pipeline."""
    input_items: list = [{"role": "user", "content": user_message(ctx)}]
    deadline = time.monotonic() + BUDGET_SECONDS
    used, finished = 0, False
    while used < MAX_TOOL_CALLS and not finished:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            ctx.warn("Agent ran out of time.")
            return False
        step = await asyncio.wait_for(
            llm.tool_step(instructions=SYSTEM_PROMPT, input_items=input_items, tools=TOOL_SCHEMAS), remaining
        )
        input_items += step.raw
        if not step.calls:  # the model answered in text without finishing
            return False
        for call in step.calls:
            if used >= MAX_TOOL_CALLS:
                result = {"error": "tool-call budget exhausted"}
            else:
                result = await execute(ctx, call.name, call.arguments)
                used += 1
                finished = finished or call.name == "finish"
            input_items.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)})
    return finished
