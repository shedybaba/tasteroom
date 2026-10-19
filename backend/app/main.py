from pathlib import Path

import asyncio
from contextlib import asynccontextmanager

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import json

from . import cache, planner, ratelimit
from .baseline import llm_baseline, qloo_stats, verify_baseline
from .config import REPO_ROOT, settings
from .examples import EXAMPLES
from .llm import get_llm
from .models import BaselineResponse, PlanRequest, PlanResponse, ResolveRequest, ResolveResponse
from .qloo_client import QlooClient, QlooError
from .resolve import resolve_city, resolve_members
from .tools import PlanError

log = logging.getLogger("tasteroom.api")
qloo = QlooClient()
llm = get_llm()  # None in mock mode (no OPENAI_API_KEY)


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await qloo.aclose()


app = FastAPI(title="TasteRoom", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)


app.add_middleware(GZipMiddleware, minimum_size=1000)  # example plans are ~200 KB of JSON


# Friendly JSON errors only: never a stack trace or an upstream message that might echo credentials.
@app.exception_handler(ApiError)
async def _api_error(_: Request, exc: ApiError):
    return JSONResponse({"error": exc.message}, status_code=exc.status)


@app.exception_handler(PlanError)
async def _plan_error(_: Request, exc: PlanError):
    return JSONResponse({"error": str(exc)}, status_code=422)


@app.exception_handler(QlooError)
async def _qloo_error(_: Request, exc: QlooError):
    log.warning("qloo error: status=%s", exc.status)
    return JSONResponse({"error": "The Qloo taste service is unavailable right now. Please try again shortly."}, status_code=502)


@app.exception_handler(Exception)
async def _unhandled(_: Request, exc: Exception):
    log.exception("unhandled error: %s", type(exc).__name__)
    return JSONResponse({"error": "Something went wrong on our side. Please try again."}, status_code=500)


@app.api_route("/api/health", methods=["GET", "HEAD"])  # uptime monitors often probe with HEAD
def health() -> dict:
    return {
        "ok": True,
        "qloo": "live" if settings.qloo_live else "mock",
        "llm": "live" if settings.llm_live else "mock",
    }


@app.post("/api/resolve", response_model=ResolveResponse)
async def resolve(req: ResolveRequest) -> ResolveResponse:
    """Check tastes and city before planning, so the organizer can fix misses."""
    resolved, locality = await asyncio.gather(
        resolve_members(qloo, req.members), resolve_city(qloo, req.city)
    )
    return ResolveResponse(resolved=resolved, locality=locality)


async def _get_or_make_plan(req: PlanRequest, request: Request) -> PlanResponse:
    """Cached plans are free; only a real run (live Qloo + OpenAI calls) counts against the IP limit."""
    plan = planner.cached_plan(planner.plan_id_for(req))
    if plan:
        return plan
    if not ratelimit.allow(request):
        raise ApiError(429, f"Live planning is limited to {settings.rate_limit_plan} per visitor to control costs. "
                            "Try one of the example communities, or come back later.")
    plan = await planner.make_plan(req, qloo, llm)
    planner.store_plan(plan)
    return plan


@app.post("/api/plan", response_model=PlanResponse)
async def plan(req: PlanRequest, request: Request) -> PlanResponse:
    return await _get_or_make_plan(req, request)


@app.get("/api/plan/{plan_id}", response_model=PlanResponse)
async def get_plan(plan_id: str) -> PlanResponse:
    found = planner.cached_plan(plan_id) if plan_id.isalnum() else None
    if not found:
        raise ApiError(404, "That plan was not found (it may have expired).")
    return found


def _inputs(plan: PlanResponse):
    """The distinct Qloo entities the members named (used to tell discoveries from echoes)."""
    return list({r.entity.id: r.entity for r in plan.resolved if r.entity}.values())


@app.post("/api/baseline", response_model=BaselineResponse)
async def baseline(req: PlanRequest, request: Request) -> BaselineResponse:
    """The same request answered by the LLM alone, with stats against the Qloo-grounded plan."""
    plan = await _get_or_make_plan(req, request)
    key = f"baseline:{plan.plan_id}"
    hit = cache.get(key)
    if hit:
        return BaselineResponse.model_validate(hit)
    try:
        brief, mode = await llm_baseline(req, llm)
    except Exception as exc:  # LLM outage / bad key: the Compare tab shows this message
        log.warning("baseline LLM failed: %s", type(exc).__name__)
        raise ApiError(503, "The AI service is unavailable right now, so the LLM-only comparison could not be generated.") from exc
    stats = await verify_baseline(qloo, brief, req.city, plan.locality.name if plan.locality else None, _inputs(plan))
    out = BaselineResponse(baseline=brief, baseline_stats=stats, qloo_stats=qloo_stats(plan.brief, plan.recommendations, _inputs(plan)),
                           mode=mode)  # type: ignore[arg-type]
    cache.put(key, out.model_dump(mode="json"), planner.PLAN_TTL)
    return out


PRECOMPUTED = REPO_ROOT / "backend" / "precomputed"


def _example_file(example_id: str) -> dict:
    f = PRECOMPUTED / f"{example_id}.json"
    if example_id not in EXAMPLES or not f.is_file():
        raise ApiError(404, "Example not found.")
    return json.loads(f.read_text())


@app.get("/api/examples")
def examples() -> list[dict]:
    return [{
        "id": eid, "name": ex["request"].community_name, "city": ex["request"].city,
        "goal": ex["request"].event_goal, "tagline": ex["tagline"],
        "members": [{"name": m.name, "tastes": [t.text for t in m.tastes]} for m in ex["request"].members],
        "request": ex["request"].model_dump(mode="json"),
    } for eid, ex in EXAMPLES.items()]


@app.get("/api/examples/{example_id}/plan", response_model=PlanResponse)
def example_plan(example_id: str) -> PlanResponse:
    return PlanResponse.model_validate(_example_file(example_id)["plan"])


@app.get("/api/examples/{example_id}/baseline", response_model=BaselineResponse)
def example_baseline(example_id: str) -> BaselineResponse:
    return BaselineResponse.model_validate(_example_file(example_id)["baseline"])


# Serve the built React app from the same service (one URL, no CORS).
DIST = REPO_ROOT / "frontend" / "dist"

if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"error": "not found"}, status_code=404)
        candidate = (DIST / path).resolve()
        if path and candidate.is_file() and DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
