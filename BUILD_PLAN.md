# BUILD_PLAN.md: TasteRoom (working name)
### Step-by-step build spec for Claude Code: Qloo Agentic Hackathon entry

> **How to use this file:** Put this file and `CLAUDE.md` in an empty project folder. Open Claude Code there and paste the **Phase prompts** (section 12) one at a time. Each phase has acceptance criteria. Do not start the next phase until the current one passes.
>
> **Today:** Oct 19, 2026. **Hard deadline:** Oct 30, 2026, 11:45pm EDT (about 4:45am Oct 31 in Lagos). **Target submission:** Oct 28.

---

## 1. Product in one paragraph

**TasteRoom** is an AI agent for community organizers. The organizer types in what a handful of their members like (artists, shows, brands, places), the city, and the kind of event they want. The agent turns those tastes into Qloo entities, builds one combined community taste profile, and queries Qloo across **music (artists)**, **venues (places in that city)**, **sponsors and merch (brands)**, and **content themes (podcasts / TV shows)**. It returns a ready-to-use **event brief** where every pick comes from Qloo and is explained ("picked mainly because of Ada's and Tunde's tastes"). A **Compare** tab shows the same request answered by a plain LLM, so judges can see what Qloo adds.

**Tagline:** "Stop guessing what your community wants. Plan events from real taste data."

**Audience:** Discord / Telegram community managers, meetup and campus-club organizers, brand community teams.

---

## 2. What judges score, and the feature that answers each

| Criterion | Feature that wins it |
|---|---|
| Technological Implementation | Multi-domain `/v2/insights` calls, entity resolution, locality resolution, per-member explanations, real agent with tool calls and a visible trace |
| Design | One clean flow: Examples → Builder → Results (tabs), images on every card, polished brief |
| Potential Impact | Specific user (organizers), specific pain (guessing), concrete output (an event brief they can act on) |
| Quality of the Idea | Group taste fusion + "why this pick" + Qloo vs LLM-only comparison |

Hard rule: **every recommended artist, venue, brand, or show shown to the user must exist in a Qloo response.** The LLM writes and organizes; it never invents picks.

---

## 3. Architecture decisions (already made, do not revisit)

1. **One deployable service.** FastAPI serves the API under `/api/*` AND the built React app as static files. One URL, no CORS problems, one host to keep awake.
2. **Backend:** Python 3.11+, FastAPI, httpx, Pydantic v2, `diskcache` (or SQLite) for caching, `slowapi` for rate limiting.
3. **Frontend:** React + Vite + TypeScript + Tailwind CSS. Built output copied into the backend image.
4. **LLM:** OpenAI via the official `openai` Python SDK, wrapped in `backend/app/llm.py`. Model names come from env vars (`OPENAI_MODEL_FAST`, `OPENAI_MODEL_SMART`). Check OpenAI's current docs for model names and tool-calling syntax; do not rely on memory.
5. **Deploy:** Dockerfile (multi-stage: build frontend, then Python runtime) on Render (or Railway / Fly.io). Must not cold-start during judging: use an always-on plan or a keep-alive ping.
6. **Mock mode:** if `QLOO_API_KEY` is missing, the Qloo client serves saved JSON from `backend/samples/`. If `OPENAI_API_KEY` is missing, LLM calls return a templated brief. The app must run end to end with zero keys.

```
Browser (React)
   │  /api/*
   ▼
FastAPI ──► Agent (OpenAI tool calling) ──► tools ──► Qloo client ──► hackathon.api.qloo.com
   │              │ (fails / times out)
   │              └──► Deterministic pipeline (same tools, fixed order)
   ├──► Brief writer (OpenAI, grounded in Qloo results only)
   └──► Baseline (OpenAI only, no Qloo) for Compare tab
```

---

## 4. Repository layout

```
tasteroom/
├── CLAUDE.md
├── BUILD_PLAN.md
├── API_FINDINGS.md          # written in Phase 1 from live tests
├── README.md
├── LICENSE                  # MIT
├── .gitignore               # .env, node_modules, dist, __pycache__, .cache
├── .env.example
├── Dockerfile
├── render.yaml              # optional infra-as-code for Render
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py          # FastAPI app, routes, static file serving
│   │   ├── config.py        # env vars via pydantic-settings
│   │   ├── models.py        # Pydantic request/response models
│   │   ├── qloo_client.py   # all HTTP to Qloo, cache, retries, mock mode
│   │   ├── allowed_params.py# per-filter.type whitelist
│   │   ├── resolve.py       # member tastes -> Qloo entities; city -> locality
│   │   ├── profile.py       # combined community profile + weights
│   │   ├── recommend.py     # one function per domain
│   │   ├── explain.py       # native explainability or per-member fallback
│   │   ├── agent.py         # tool-calling loop + trace
│   │   ├── pipeline.py      # deterministic fallback (same steps, fixed order)
│   │   ├── brief.py         # grounded brief writer + validator
│   │   ├── baseline.py      # LLM-only answer
│   │   ├── llm.py           # OpenAI wrapper (swappable)
│   │   ├── cache.py
│   │   └── examples.py      # pre-loaded example communities
│   ├── samples/             # raw Qloo JSON captured in Phase 1
│   ├── precomputed/         # saved full results for example communities
│   ├── scripts/
│   │   ├── smoke_test.py    # Phase 1 live checks
│   │   └── precompute_examples.py
│   └── tests/
└── frontend/
    ├── package.json
    ├── index.html
    └── src/
        ├── main.tsx, App.tsx, api.ts, types.ts
        ├── pages/ Landing.tsx, Builder.tsx, Results.tsx
        └── components/ MemberCard.tsx, EntityCard.tsx, WhyPanel.tsx,
                        BriefView.tsx, CompareView.tsx, AgentTrace.tsx,
                        LoadingSteps.tsx
```

---

## 5. Qloo usage map (the core of the app)

All calls: `GET https://hackathon.api.qloo.com/...` with header `X-Api-Key`. Lists are comma-joined unless Phase 1 proves otherwise.

| Step | Endpoint | Key params | Purpose |
|---|---|---|---|
| Resolve a taste | `/search` | `query`, `types` (e.g. `urn:entity:artist`), `take=3` | "Burna Boy" → entity ID. Try the member-selected type first; if 404/empty, retry without `types` |
| Resolve the city | `/search` | `query=<city>`, `types=urn:entity:locality`, `take=1` | City or neighborhood → locality ID |
| Entity details | `/entities` | `entity_ids` | Tags for explanation fallback; rebuild saved plans |
| Music | `/v2/insights` | `filter.type=urn:entity:artist`, `signal.interests.entities`, `take=10`, optional `filter.popularity.max` | Artists for the event |
| Venues | `/v2/insights` | `filter.type=urn:entity:place`, `signal.interests.entities`, `filter.location=<locality_id>` (fallback `filter.geocode.name` + `filter.geocode.country_code`), optional `filter.price_level.max`, `filter.hours`, `filter.tags` (venue type) | Places in the city |
| Sponsors / merch | `/v2/insights` | `filter.type=urn:entity:brand`, `signal.interests.entities`, `take=10` | Brand partners |
| Content theme | `/v2/insights` | `filter.type=urn:entity:podcast` and/or `urn:entity:tv_show`, `signal.interests.entities`, `take=8` | Watch-party / theme ideas |
| Venue-type tags | `/v2/tags` | keyword search (e.g. "bar", "lounge", "event space") | Valid tag IDs for `filter.tags` on places |
| Community type (optional) | `/v2/audiences` | `filter.query`, `filter.parents.types` | Audience IDs for `signal.demographics.audiences` (route is marked deprecated; optional) |
| Explanations | `/v2/insights` | `feature.explainability=true` if verified; otherwise per-member scoring (section 7) | "Why this pick" |

**Always:** run params through `allowed_params.clean_params()` before calling, add `filter.exists=properties.image` only if Phase 1 shows it works (it is in the Deep Dive, not the matrix), and slim every entity before passing it on.

---

## 6. Data models (Pydantic, mirrored in `frontend/src/types.ts`)

```python
class Taste(BaseModel):
    text: str                                   # "Burna Boy"
    kind: Literal["artist","tv_show","movie","brand","place","podcast","book","video_game","any"] = "any"

class Member(BaseModel):
    name: str                                   # display name or "Member 3"
    tastes: list[Taste]                         # 1–6 per member

class PlanOptions(BaseModel):
    hidden_gems: bool = False                   # filter.popularity.max ~0.7
    price_level_max: int | None = None          # 1–4, venues only
    day: str | None = None                      # "saturday", venues only
    venue_kind: str | None = None               # free text -> /v2/tags lookup

class PlanRequest(BaseModel):
    community_name: str
    city: str
    event_goal: str                             # "chill Saturday meetup for 40 people"
    members: list[Member]                       # 3–15
    options: PlanOptions = PlanOptions()

class ResolvedTaste(BaseModel):
    member: str
    input: str
    entity: SlimEntity | None                   # None = unresolved (shown in UI)

class SlimEntity(BaseModel):
    id: str; name: str; type: str
    popularity: float | None = None
    description: str | None = None
    image: str | None = None
    address: str | None = None
    tags: list[str] = []
    tag_ids: list[str] = []

class Contribution(BaseModel):
    member: str
    score: float                                # 0–1 normalized
    via: list[str]                              # member's entities that drove it

class Recommendation(BaseModel):
    entity: SlimEntity
    domain: Literal["music","venues","brands","content"]
    why: list[Contribution]
    shared_tags: list[str] = []
    explanation_method: Literal["qloo_explainability","per_member_affinity","tag_overlap"]

class TraceStep(BaseModel):
    step: int; tool: str; args: dict; summary: str; ms: int; ok: bool

class PlanResponse(BaseModel):
    plan_id: str
    request: PlanRequest
    resolved: list[ResolvedTaste]
    locality: SlimEntity | None
    recommendations: dict[str, list[Recommendation]]
    brief: Brief
    trace: list[TraceStep]
    mode: Literal["agent","pipeline","precomputed","mock"]
    warnings: list[str] = []

class Brief(BaseModel):
    title: str
    concept: str                                # 2–3 sentences
    vibe_words: list[str]                       # 3–5
    run_of_show: list[str]                      # 4–6 short lines
    music: list[BriefPick]
    venue: list[BriefPick]                      # top 1 + 2 backups
    sponsors: list[BriefPick]
    content: list[BriefPick]
    promo_line: str                             # one-line announcement for Discord/X

class BriefPick(BaseModel):
    entity_id: str                              # MUST be a Qloo ID from recommendations
    name: str
    reason: str                                 # cites members / shared tags
```

---

## 7. Explanation logic (`explain.py`)

Pick the first method that Phase 1 proved works, record it in `API_FINDINGS.md`, and set `explanation_method` on every result.

**A. Native (`qloo_explainability`).** If `feature.explainability=true` returns per-result contributions, map each contributing input entity back to the member(s) who named it. Sum and normalize per member.

**B. Per-member affinity (`per_member_affinity`).** For each domain's top N results (N ≤ 10):
for each member, call `/v2/insights` with that member's entity IDs as `signal.interests.entities` and `filter.results.entities=<top N result IDs>`. Read each result's affinity score from the response (field name to confirm in Phase 1; look in each entity's `query` object). Normalize across members. Cache aggressively; this is `members × domains` extra calls, so cap members used for explanation at 8 and run calls concurrently with a small semaphore (4).

**C. Tag overlap (`tag_overlap`).** Fetch tags for member entities (`/entities`) and result entities. Shared tag names = `shared_tags`; members whose entities share the most tags = contributors. Always compute `shared_tags` even when A or B is used; it makes the "why" text richer.

Never write a reason that is not backed by one of these computations.

---

## 8. The agent (`agent.py`) and the fallback (`pipeline.py`)

**Tools exposed to the LLM** (JSON-schema function tools):

| Tool | Args | Does |
|---|---|---|
| `resolve_tastes` | none (uses request) | Runs `resolve.py`, returns resolved/unresolved counts + entity names |
| `resolve_city` | `city: str` | Locality lookup; returns name + whether found |
| `recommend` | `domain: music\|brands\|content`, `hidden_gems: bool`, `content_type: podcast\|tv_show` | Calls `recommend.py`, returns top names (slim) |
| `find_venues` | `venue_kind?: str`, `price_level_max?: int`, `day?: str`, `hidden_gems?: bool` | Tag lookup if `venue_kind`, then place insights |
| `explain` | `domain` | Runs `explain.py` on that domain's results |
| `finish` | `notes: str` | Ends the loop |

**System prompt (summary):** "You are an event-programming agent. Use tools to gather Qloo recommendations that fit the community and the event goal. Decide which domains matter for this goal (e.g., a podcast-listening meetup needs content; a launch party needs music, venue, and sponsors). Always resolve tastes first. Always get venues if a city is given. Call `explain` for every domain you use. Never name a recommendation that a tool did not return. Call `finish` when done."

**Loop rules:** max 10 tool calls, 60-second total budget, every call recorded as a `TraceStep` (tool, args, short summary, duration, ok). Use `OPENAI_MODEL_FAST` for the loop.

**Fallback:** if the agent errors, times out, or finishes without venues + at least two other domains, run `pipeline.py`: resolve → city → music → venues → brands → content → explain all, in that order, with the same functions. Set `mode="pipeline"` and add a warning. The demo must never fail because of the agent.

---

## 9. Brief writer (`brief.py`) and baseline (`baseline.py`)

**Brief:** one call to `OPENAI_MODEL_SMART` with structured JSON output matching `Brief`. Input = event goal, community name, city, and a compact list of recommendations per domain: `{entity_id, name, short description, top contributors, shared_tags}`. Instructions: use only listed entities, reference members by name in reasons, keep it practical.

**Validator (required):** after the call, drop any `BriefPick` whose `entity_id` is not in the recommendations; if a section ends up empty, fill it with the top-ranked recommendation and a reason built from its `why` data. Log how many picks were dropped (useful in the README as proof of grounding).

**Baseline:** same goal, city, and raw member tastes sent to the LLM with no Qloo data, asking for the same `Brief` shape (no entity IDs). The Compare tab shows both side by side with labels: "LLM only" vs "Qloo-grounded agent", plus a small stat row: picks with explanations, picks verifiable in Qloo, venues confirmed in city.

---

## 10. Backend routes (`main.py`)

| Method & path | Body / params | Returns |
|---|---|---|
| `GET /api/health` | none | `{ok, qloo: live|mock, llm: live|mock}` |
| `GET /api/examples` | none | list of example communities (name, city, goal, members) |
| `GET /api/examples/{id}/plan` | none | precomputed `PlanResponse` (no API cost) |
| `POST /api/resolve` | `{members, city}` | resolved tastes + locality, so the user can fix misses before planning |
| `POST /api/plan` | `PlanRequest` | `PlanResponse` (agent → fallback) |
| `POST /api/plan/stream` (stretch) | `PlanRequest` | Server-Sent Events: one event per trace step, final event = `PlanResponse` |
| `POST /api/baseline` | `PlanRequest` | `Brief` |
| `GET /api/plan/{plan_id}` | none | saved `PlanResponse` (cache) |

Rate limit `POST /api/plan` and `/api/baseline` (e.g. 5/hour per IP). Cache plans by a hash of the normalized request. Return friendly error JSON, never stack traces.

Static: mount `frontend/dist` at `/`, with SPA fallback to `index.html` for unknown non-`/api` paths.

---

## 11. Frontend spec

**Visual direction:** warm, social, a little nightlife-flavored. Dark-on-light default with a single accent color, rounded cards, real images from Qloo results. Must look good at 375px width. Use the `frontend-design` sensibility: avoid generic template look.

**Pages**

1. **Landing** (`/`): headline + tagline, 3 example community cards (click → precomputed results instantly), "Plan for my community" button, a short 3-step "how it works" strip, and a small "Powered by Qloo taste data" note.
2. **Builder** (`/build`):
   - Community name, city, event goal (with 4 quick-pick chips: "Chill meetup", "Launch party", "Watch party", "Networking night").
   - Member cards: name + up to 6 taste chips; each chip has a kind dropdown (Artist, Show, Movie, Brand, Place, Podcast, Any). "Add member" up to 15. "Paste list" option: one line per member, format `Name: taste, taste, taste`.
   - Options drawer: hidden gems toggle, max price (1–4), day of week, venue kind.
   - "Check tastes" button → `/api/resolve` → each chip turns green (matched, shows Qloo name + thumbnail) or amber (no match, editable).
   - "Build event plan" → Results.
3. **Results** (`/plan/:id`):
   - Loading state: `LoadingSteps` shows agent steps as they happen (stream) or a staged animation (non-stream).
   - Header: event title, city, community, mode badge (Agent / Pipeline / Example).
   - Tabs: **Brief** (default) · **Music** · **Venues** · **Sponsors** · **Content** · **Compare** · **How the agent worked**.
   - Each recommendation card: image, name, type, address (venues), and a **Why** panel with contributor bars per member + shared tags + method label.
   - Brief tab: concept, vibe words, run of show, top picks with reasons, promo line with a Copy button, and "Copy whole brief as Markdown".
   - Compare tab: two columns + stat row (section 9).
   - Agent tab: `AgentTrace` timeline (tool name, args summary, duration, ok/fail).

---

## 12. Phase prompts (paste into Claude Code one at a time)

### Phase 0: Scaffold (Day 1, Oct 19)
```
Read CLAUDE.md and BUILD_PLAN.md fully. Do Phase 0 only.
- git init. Create .gitignore FIRST (.env, node_modules, dist, __pycache__, .cache, *.sqlite).
- Create .env.example with QLOO_API_KEY, OPENAI_API_KEY, OPENAI_MODEL_FAST, OPENAI_MODEL_SMART, APP_ENV, RATE_LIMIT_PLAN.
- Scaffold backend (FastAPI, config via pydantic-settings, /api/health) and frontend (Vite + React + TS + Tailwind) per section 4.
- Add MIT LICENSE (copyright holder: the repo owner; ask me for the name if unknown) and a starter README.
- Make `make dev` (or two documented commands) run both locally, and make FastAPI serve frontend/dist in production mode.
- Commit.
Acceptance: /api/health returns JSON locally; the React page loads; `git status` shows .env is ignored.
```

### Phase 1: Qloo client + live tests (Day 1–2, Oct 19–20)
```
Do Phase 1 only. Follow section 5 and the UNVERIFIED list in CLAUDE.md.
- Write allowed_params.py (per-type whitelist, test_mode passthrough for unverified params) and qloo_client.py (search, find_locality, get_entities, find_tags, find_audiences, insights; slim_entity; 429 exponential backoff; 404 -> []; disk cache; mock mode reading backend/samples/).
- Write scripts/smoke_test.py covering every item in the Phase 1 checklist in CLAUDE.md. Save each raw response to backend/samples/<name>.json. Never print the API key.
- Run it with my .env. Then write API_FINDINGS.md: for each item, what was sent, what came back, VERIFIED/NOT WORKING, and the decision it drives (explanation method A/B/C, how to pass city, list vs repeated params, demo city).
- Update the whitelist and CLAUDE.md to match reality.
- Add pytest tests for slim_entity, clean_params, and parsing of each saved sample.
Acceptance: smoke test runs; API_FINDINGS.md has a clear decision for explanation method and demo city; tests pass.
If the Qloo key is not in .env yet: build everything, write realistic placeholder samples clearly marked FAKE, and stop with a note telling me to add the key and rerun.
```

### Phase 2: Resolve, profile, recommend, explain (Day 2–4, Oct 20–22)
```
Do Phase 2 only. Implement resolve.py, profile.py, recommend.py, explain.py per sections 5–7, plus POST /api/resolve.
- Resolution: typed search first, untyped retry, pick best by name similarity then popularity; dedupe the same entity named by several members (weight = number of members who named it).
- Profile: ordered entity list (highest weight first, cap 25 IDs per request) + member->entity map.
- Recommend: one function per domain; venues use locality ID, else geocode fallback, per API_FINDINGS.md.
- Explain: implement the method chosen in API_FINDINGS.md, always compute shared_tags; concurrency semaphore 4; cache.
- Write a CLI script that runs the whole thing for one hard-coded community and prints a readable table per domain with the why data.
- Tests using saved samples (no network).
Acceptance: the CLI produces non-empty music, venues, brands, content for the demo city, and every result has at least one contributor or shared tag.
```

### Phase 3: Agent, fallback, brief, baseline (Day 4–5, Oct 22–23)
```
Do Phase 3 only. Implement llm.py (OpenAI SDK; read current docs for tool calling and structured output; models from env), agent.py, pipeline.py, brief.py with the validator, baseline.py per sections 8–9. Wire POST /api/plan, POST /api/baseline, GET /api/plan/{id}, rate limiting, request-hash caching.
- Force-test the fallback: add an env flag AGENT_DISABLED=1 and a test that makes the agent raise; both must return a valid PlanResponse with mode="pipeline".
- Log token usage per request to the console (counts only).
Acceptance: POST /api/plan returns a full PlanResponse for two different event goals and the agent chooses different domains for them; validator drops any invented pick (unit test with a fake LLM output).
```

### Phase 4: Examples + frontend (Day 5–7, Oct 23–25)
```
Do Phase 4 only.
- examples.py: 3 example communities (a Lagos or Abuja creative/tech meetup if the demo city has data, a gaming/anime Discord, a run club or campus club; use whatever cities API_FINDINGS.md says have good data). 6–10 members each with realistic, varied tastes.
- scripts/precompute_examples.py: run the full plan + baseline for each, save to backend/precomputed/. Wire GET /api/examples and /api/examples/{id}/plan.
- Build the frontend per section 11. Use the frontend-design approach for a distinctive look. Fully responsive. Loading, empty, and error states for everything.
- Implement /api/plan/stream (SSE) if time allows; otherwise staged loading animation.
Acceptance: from the Landing page, an example opens fully rendered results in under 2 seconds; the Builder flow works end to end locally with live keys; it looks good at 375px and 1440px.
```

### Phase 5: Deploy (Day 7–8, Oct 25–26)
```
Do Phase 5 only.
- Multi-stage Dockerfile: node builds frontend -> python:3.11-slim runs uvicorn and serves frontend/dist. Healthcheck on /api/health.
- render.yaml for a single web service (env vars declared without values).
- Write DEPLOY.md: exact click-by-click steps for me (create Render account, connect GitHub repo, set env vars, choose an always-on instance or set up a free keep-alive ping, custom domain optional).
- Build and run the Docker image locally to prove it works.
- Before any push: scan the repo and git history for secrets; confirm .env is untracked.
Acceptance: docker run serves the full app locally on one port; DEPLOY.md is complete.
```
*(You do the account clicks in DEPLOY.md. If you have the Render or GitHub CLI logged in, Claude Code can do more of it.)*

### Phase 6: Harden + submission assets (Day 8–9, Oct 26–27)
```
Do Phase 6 only.
- Test the deployed URL end to end (I will paste it). Fix anything broken.
- Error handling review: Qloo empty results, 429, 400 on locality, OpenAI timeout, unresolved tastes, 15 members.
- README.md: what it is, screenshots (generate them with a headless browser if available), how Qloo is used (endpoint table), architecture diagram (Mermaid), explanation method and why, local setup, env vars, deploy, license.
- SUBMISSION.md: Devpost text (inspiration, what it does, how we built it, how Qloo powers it, challenges, accomplishments, what we learned, what's next), plus a 60-second spoken demo script.
- Final check: MIT license present, no secrets in history, all tests pass.
Acceptance: deployed app works for all 3 examples and one custom community; README and SUBMISSION.md complete.
```

### Phase 7: Submit (Oct 28, buffer through Oct 29)
You do this: paste SUBMISSION.md into Devpost, add the live URL and repo URL, set the repo's About section to show the MIT license and the live URL, submit. Then keep the service awake through judging.

---

## 13. Cost and reliability rules
- Slim entities before any LLM call; never send raw Qloo JSON to OpenAI.
- Cheap model for the agent loop, stronger model only for the brief and baseline.
- Cache Qloo responses (24h) and full plans (by request hash).
- Examples are precomputed, so judges clicking them cost nothing.
- Rate limit live planning; show a friendly message when exceeded.
- Set a monthly spending limit on the OpenAI account before Phase 3.
- Keep the service always on from submission until judging ends.

## 14. Cut list if behind schedule (cut from the top)
1. SSE streaming (use staged animation)
2. Audience "community type" option
3. Podcast + TV both (keep one)
4. Paste-list input
5. Shareable `/plan/:id` links

**Never cut:** grounded picks, explanations, the Compare tab, the agent trace, the 3 examples, live deployment.

## 15. Things only the owner can do
1. Put `QLOO_API_KEY` and `OPENAI_API_KEY` in `.env` (never paste them into chat).
2. Set an OpenAI spending limit.
3. Create the GitHub repo (public) and the Render account; follow DEPLOY.md.
4. Approve Claude Code's commands and pushes.
5. Paste the deployed URL back for Phase 6 testing.
6. Submit on Devpost.
7. Be able to explain the app: read README and API_FINDINGS.md before submitting.
