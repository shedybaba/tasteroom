"""Sponsors are only queried when a member added a brand taste AND the event is not clearly personal."""
import asyncio

import pytest

from app import discord, main, slack
from app.filters import sponsors_decision
from app.models import Member, PlanRequest, ResolvedTaste, SlimEntity, Taste
from app.planner import make_plan
from app.tools import PlanContext, execute
from tests.fakes import FakeLLM

run = asyncio.run


def request(goal="launch party", brand=True, kind="brand") -> PlanRequest:
    """Three members who all name Burna Boy (present in the saved samples), plus Nike as a brand when `brand`."""
    extra = [Taste(text="Nike", kind=kind)] if brand else []
    return PlanRequest(community_name="Lagos Creators", city="Lagos", event_goal=goal,
                       members=[Member(name=f"M{i}", tastes=[Taste(text="Burna Boy", kind="artist")] + extra) for i in range(3)])


# ---- rule 1: no brand taste, no sponsors ---------------------------------------------------------------------------

def test_without_a_brand_taste_sponsors_are_skipped():
    include, why = sponsors_decision(request("launch party", brand=False))
    assert include is False and "no member added a brand" in why


def test_with_a_brand_taste_and_a_normal_event_sponsors_stay():
    assert sponsors_decision(request("launch party")) == (True, "")
    assert sponsors_decision(request("Anime watch party and game night for 30 members"))[0] is True


def test_a_brand_typed_into_an_open_slot_counts_when_qloo_matched_it_to_a_brand():
    req = request("launch party", brand=True, kind="any")
    brand = SlimEntity(id="B1", name="Nike", type="urn:entity:brand")
    artist = SlimEntity(id="A1", name="Burna Boy", type="urn:entity:artist")
    assert sponsors_decision(req, [ResolvedTaste(member="M0", input="Nike", entity=artist)])[0] is False   # matched to an artist, not a brand
    assert sponsors_decision(req, [ResolvedTaste(member="M0", input="Nike", entity=brand)])[0] is True


# ---- rule 2: a clearly personal event never has sponsors, even with a brand ----------------------------------------

@pytest.mark.parametrize("goal", ["Friends hangout", "friends hangout on Saturday", "Family gathering", "Dinner with friends",
                                  "Mum's birthday", "Saturday night out with 5 friends", "Family event", "Our anniversary dinner",
                                  "Housewarming party", "Baby shower", "Date night", "College reunion", "BIRTHDAY BRUNCH"])
def test_personal_events_skip_sponsors_even_when_a_brand_was_added(goal):
    include, why = sponsors_decision(request(goal, brand=True))
    assert include is False and "personal event" in why


@pytest.mark.parametrize("goal", ["Launch party", "Networking night", "Team offsite drinks for 7 colleagues", "Saturday evening creator mixer for 50 people",
                                  "Post-run social after the Saturday long run, 35 people", "Chill community meetup"])
def test_other_events_are_not_called_personal(goal):
    assert sponsors_decision(request(goal, brand=True))[0] is True


# ---- what a plan looks like -----------------------------------------------------------------------------------------

def assert_no_sponsors(plan):
    assert "brands" not in plan.recommendations and plan.brief.sponsors == []
    assert not any(t.tool == "recommend" and t.args.get("domain") == "brands" for t in plan.trace)   # no Qloo query was made for brands


def test_agent_plan_without_a_brand_has_no_sponsors(offline_client):
    plan = run(make_plan(request("launch party", brand=False), offline_client, FakeLLM()))   # the scripted agent asks for brands: the tool refuses
    assert plan.mode == "agent" and plan.recommendations["music"] and plan.brief.music
    assert_no_sponsors(plan)


def test_agent_plan_for_a_friends_hangout_with_a_brand_has_no_sponsors(offline_client):
    assert_no_sponsors(run(make_plan(request("Friends hangout", brand=True), offline_client, FakeLLM())))


def test_pipeline_fallback_follows_the_same_rules(offline_client):
    for req in (request("launch party", brand=False), request("Friends hangout", brand=True)):
        plan = run(make_plan(req, offline_client, FakeLLM(fail=True)))
        assert plan.mode == "pipeline" and plan.recommendations["music"]
        assert_no_sponsors(plan)


def test_the_control_case_still_gets_sponsors(offline_client):
    plan = run(make_plan(request("launch party", brand=True), offline_client, FakeLLM()))
    assert plan.recommendations["brands"] and plan.brief.sponsors


def test_the_brands_tool_is_refused_quietly_and_leaves_no_trace_step(offline_client):
    ctx = PlanContext(request=request("Friends hangout", brand=True), client=offline_client)
    run(execute(ctx, "resolve_tastes", {}))
    steps = len(ctx.trace)
    out = run(execute(ctx, "recommend", {"domain": "brands"}))
    assert "Sponsors are skipped" in out["error"] and "brands" not in ctx.results and len(ctx.trace) == steps


# ---- where sponsors would show up ----------------------------------------------------------------------------------

def test_announcements_never_carry_sponsors(offline_client):
    """Discord and Slack posts hold the promo line, the venue and the artists, so a plan without sponsors posts the same way."""
    plan = run(make_plan(request("Friends hangout", brand=True), offline_client, FakeLLM()))
    assert_no_sponsors(plan)
    for text in (str(discord.announcement(plan, None)), str(slack.announcement(plan, None))):
        assert "Sponsor" not in text and "Nike" not in text


def test_the_llm_only_comparison_drops_sponsors_too(offline_client, monkeypatch):
    """The Compare tab must not show an LLM-only column that still lists sponsors the plan deliberately skipped."""
    plan = run(make_plan(request("Friends hangout", brand=True), offline_client, FakeLLM()))
    monkeypatch.setattr(main, "llm", FakeLLM())   # its LLM-only answer lists Nike as a sponsor
    out = run(main._baseline_for(plan))
    assert out.baseline.sponsors == []
