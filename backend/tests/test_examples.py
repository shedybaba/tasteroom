import json
from pathlib import Path

from app.examples import EXAMPLES
from app.models import PlanResponse

PRECOMPUTED = Path(__file__).resolve().parents[1] / "precomputed"


def test_every_example_has_a_saved_plan_that_only_names_qloo_results():
    assert {"saturday-crew", "team-atlas"} <= set(EXAMPLES)      # friends and a team, next to the communities
    for eid, ex in EXAMPLES.items():
        plan = PlanResponse.model_validate(json.loads((PRECOMPUTED / f"{eid}.json").read_text())["plan"])
        assert plan.plan_id == eid and plan.mode == "precomputed"
        assert len(ex["request"].members) >= 3
        ids = {r.entity.id for recs in plan.recommendations.values() for r in recs}
        for field in ("music", "venue", "sponsors", "content"):
            assert all(p.entity_id in ids for p in getattr(plan.brief, field)), (eid, field)
