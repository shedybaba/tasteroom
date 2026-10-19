"""Run the full plan + LLM baseline for each example community and save to backend/precomputed/.
Run: cd backend && .venv/bin/python -m scripts.precompute_examples [--no-llm] [id ...]
--no-llm builds with the templated brief / canned baseline (dev data only; rerun with a valid key
before submitting). The saved files record which mode produced them."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import cache  # noqa: E402
from app.baseline import llm_baseline, qloo_stats, verify_baseline  # noqa: E402
from app.examples import EXAMPLES  # noqa: E402
from app.llm import get_llm  # noqa: E402
from app.models import BaselineResponse  # noqa: E402
from app.planner import make_plan  # noqa: E402
from app.qloo_client import QlooClient  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "precomputed"


async def main(ids: list[str], use_llm: bool) -> None:
    OUT.mkdir(exist_ok=True)
    cache._cache.clear()  # saved traces should show real latencies, not cache hits
    client = QlooClient()
    llm = get_llm() if use_llm else None
    print(f"Qloo: {'mock' if client.mock else 'live'} | LLM: {'live' if llm else 'none (templated)'}")
    for eid in ids:
        req = EXAMPLES[eid]["request"]
        plan = await make_plan(req, client, llm)
        ran_as = plan.mode  # "agent" or "pipeline"; saved so we know what produced the example
        plan.plan_id, plan.mode = eid, "precomputed"
        inputs = list({r.entity.id: r.entity for r in plan.resolved if r.entity}.values())
        try:
            brief, bmode = await llm_baseline(req, llm)
        except Exception as exc:  # e.g. bad key: keep going with the canned baseline
            print(f"  baseline LLM failed ({type(exc).__name__}); using canned baseline")
            brief, bmode = (await llm_baseline(req, None))
        stats = await verify_baseline(client, brief, req.city, plan.locality.name if plan.locality else None, inputs)
        baseline = BaselineResponse(baseline=brief, baseline_stats=stats,
                                    qloo_stats=qloo_stats(plan.brief, plan.recommendations, inputs), mode=bmode)  # type: ignore[arg-type]
        (OUT / f"{eid}.json").write_text(json.dumps(
            {"plan": plan.model_dump(mode="json"), "baseline": baseline.model_dump(mode="json"),
             "built_with": {"llm_brief": llm is not None and not any("templated" in w for w in plan.warnings),
                            "llm_baseline": bmode == "llm", "ran_as": ran_as}},
            indent=1, ensure_ascii=False))
        counts = {d: len(r) for d, r in plan.recommendations.items()}
        print(f"  {eid}: {counts} | dropped={plan.dropped_picks} | warnings={plan.warnings} | baseline={bmode} {stats.model_dump()}")
    await client.aclose()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    asyncio.run(main(args or list(EXAMPLES), "--no-llm" not in sys.argv))
