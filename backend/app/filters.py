"""Which venue / popularity filters actually apply to a plan, and where each one came from.

The agent is told not to assume filters, but each one narrows Qloo's results, so this is enforced in code.
A filter applies only if (a) the organizer set it in the form, or (b) the event goal states or clearly implies it.
Anything the agent passes beyond that is dropped, and filters taken from the goal are labelled
"inferred from your goal" in the trace. Pure functions: easy to test, no I/O.
"""
import re
from dataclasses import dataclass, field

from .models import PlanOptions

DAY_RE = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b", re.I)
CHEAP_RE = re.compile(r"\b(budget|cheap(?:er|est|ly)?|affordable|more affordable|low[- ]cost|inexpensive|less expensive|"
                      r"lower[- ]priced?|free)\b|\$", re.I)
HIDDEN_RE = re.compile(r"hidden gems?|underground|undiscovered|lesser[- ]known|up[- ]and[- ]coming|off the beaten|"
                       r"less mainstream|not mainstream|\bniche\b|\bindie\b", re.I)

# A venue type named outright in the goal ("rooftop bar night", "coffee meetup")
EXPLICIT_VENUE = [
    (r"\b(night ?club|clubbing)\b", "nightclub"), (r"\blounge\b", "lounge"),
    (r"\b(bar|pub|taproom|brewery)\b", "bar"), (r"\b(cafe|café|coffee shop|coffee)\b", "cafe"),
    (r"\b(park|picnic)\b", "park"), (r"\b(restaurant|dinner|brunch|lunch)\b", "restaurant"),
    (r"\bevent (venue|space|hall)\b", "event venue"),
]
# Looser implications of the kind of event (checked after the explicit words; order matters)
VENUE_KIND_HINTS = [
    (r"\b(party|launch|club|celebrat\w*)\b", "lounge"),
    (r"\b(network\w*|conference|workshop|demo|panel|summit)\b", "event venue"),
    (r"\b(chill|hang ?out|meetup|social|drinks|mixer|night out|catch ?up|reunion)\b", "bar"),
    (r"\b(family|families|kids?|birthday|anniversary|offsite|off-site|team[- ]building|retreat)\b", "restaurant"),
    (r"\b(study|book|read\w*)\b", "cafe"),
    (r"\b(run|running|hike|hiking|outdoors?|walk|sport\w*)\b", "park"),
]


def venue_kind_from_goal(goal: str) -> str | None:
    g = goal.lower()
    for pattern, kind in EXPLICIT_VENUE + VENUE_KIND_HINTS:
        if re.search(pattern, g):
            return kind
    return None


@dataclass
class Applied:
    args: dict = field(default_factory=dict)       # what is actually applied (this is what the trace shows)
    inferred: list[str] = field(default_factory=list)  # args taken from the goal, not the form
    ignored: list[str] = field(default_factory=list)   # args the agent passed that were not applied


def venue_filters(goal: str, options: PlanOptions, agent: dict) -> Applied:
    out = Applied()

    def done(name: str, value: object, source: str) -> None:
        out.args[name] = value
        if source == "goal":
            out.inferred.append(name)

    if options.venue_kind:
        done("venue_kind", options.venue_kind, "form")
    elif (kind := venue_kind_from_goal(goal)):
        done("venue_kind", kind, "goal")

    if options.day:
        done("day", options.day.lower(), "form")
    elif (m := DAY_RE.search(goal)):
        done("day", m.group(1).lower(), "goal")

    if options.price_level_max:
        done("price_level_max", options.price_level_max, "form")
    elif CHEAP_RE.search(goal):
        asked = agent.get("price_level_max")
        done("price_level_max", asked if isinstance(asked, int) and 1 <= asked <= 3 else 2, "goal")

    gems, source = decide_hidden_gems(goal, options, None)
    if gems:
        done("hidden_gems", True, source)

    for name in ("venue_kind", "day", "price_level_max", "hidden_gems"):
        given = agent.get(name)
        if given not in (None, "", False) and name not in out.args:
            out.ignored.append(name)
    return out


def decide_hidden_gems(goal: str, options: PlanOptions, agent_value: bool | None) -> tuple[bool, str]:
    """(apply?, source). The form wins; otherwise only if the goal asks for less mainstream picks."""
    if options.hidden_gems:
        return True, "form"
    if HIDDEN_RE.search(goal):
        return True, "goal"
    return False, ""
