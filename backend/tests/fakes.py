import json

from app.llm import ToolCall, ToolStep
from app.models import BaselineBrief, BaselinePick, Brief, BriefPick

PARTY = [("resolve_tastes", {}), ("recommend", {"domain": "music"}), ("find_venues", {"venue_kind": "lounge", "day": "saturday"}),
         ("recommend", {"domain": "brands", "hidden_gems": True}), ("explain", {"domain": "music"}), ("finish", {"notes": "ok"})]
PODCAST = [("resolve_tastes", {}), ("recommend", {"domain": "content", "content_type": "podcast"}),
           ("find_venues", {"venue_kind": "cafe"}), ("explain", {"domain": "content"}), ("finish", {})]


class FakeLLM:
    """Scripted agent (plan chosen from the event goal) + a brief writer that can be told to cheat."""

    def __init__(self, scripts=None, fail=False, cheat=True, loop_forever=False, overshoot=0):
        self.scripts = scripts or (lambda goal: PODCAST if "podcast" in goal.lower() else PARTY)
        self.fail, self.cheat, self.loop_forever, self.overshoot = fail, cheat, loop_forever, overshoot
        self.structured_calls = 0

    async def tool_step(self, *, instructions, input_items, tools):
        if self.fail:
            raise RuntimeError("boom")
        goal = json.loads(input_items[0]["content"])["event_goal"]
        n = sum(1 for i in input_items if isinstance(i, dict) and i.get("type") == "function_call_output")
        if self.loop_forever:
            return ToolStep(calls=[ToolCall(f"c{n}", "resolve_city", {})])
        plan = self.scripts(goal)
        if n >= len(plan):
            return ToolStep(calls=[], text="done")
        name, args = plan[n]
        return ToolStep(calls=[ToolCall(f"c{n}", name, args)])

    async def structured(self, *, instructions, user, schema, smart=True):
        self.structured_calls += 1
        if self.fail and schema is Brief:
            raise RuntimeError("boom")
        data = json.loads(user)
        if schema is BaselineBrief:
            p = lambda n: BaselinePick(name=n, reason="from memory")  # noqa: E731
            pools = {"music": ["Burna Boy", "Totally Made Up Band", "Wizkid", "Tems"], "venue": ["Roma Lagos", "Cabaret Avignon", "Crescendo Lounge And Bar"],
                     "sponsors": ["Nike", "Adidas", "Puma"], "content": ["Call Her Daddy", "Money Heist", "Black Mirror"]}
            # Like the real prompt it is asked for exactly `pick_counts` per list; `overshoot` makes it ignore that (to test trimming).
            want = {k: (v + self.overshoot) if v else v for k, v in data["pick_counts"].items()} if "pick_counts" in data else {"music": 2, "venue": 1, "sponsors": 1, "content": 1}
            lists = {k: [p(pools[k][i] if i < len(pools[k]) else f"{k} extra {i}") for i in range(want[k])] for k in pools}
            return BaselineBrief(title="t", concept="c", vibe_words=["a"], run_of_show=["x"], promo_line="p", **lists)
        recs = data["recommendations"]
        pick = lambda d, i: BriefPick(entity_id=recs[d][i]["entity_id"].lower(), name="LLM spelling", reason=f"Because of {recs[d][i]['name']}")  # noqa: E731
        bad = [BriefPick(entity_id="NOT-A-QLOO-ID", name="Invented Artist", reason="made up")] if self.cheat else []
        wrong_domain = [BriefPick(entity_id=recs["music"][0]["entity_id"], name="x", reason="wrong section")] if self.cheat and recs["music"] else []
        return Brief(
            title="T", concept="C", vibe_words=["v"], run_of_show=["r"], promo_line="P",
            music=([pick("music", 0)] if recs["music"] else []) + bad,
            venue=([pick("venues", 0)] if recs["venues"] else []) + wrong_domain,
            sponsors=[pick("brands", 0)] if recs["brands"] else [],
            content=[pick("content", 0)] if recs["content"] else [],
        )
