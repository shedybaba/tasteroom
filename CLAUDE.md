# CLAUDE.md: TasteRoom, Community Taste Programmer (Qloo Agentic Hackathon)

> Persistent context for Claude Code. The step-by-step build spec, data models, routes, UI spec and phase prompts are in **BUILD_PLAN.md**. Where the two differ, BUILD_PLAN.md wins on architecture and scope; this file wins on API facts and rules.

## Mission
Build and ship a web app for the **Qloo Agentic Hackathon** (Devpost). Deadline: **Oct 30, 2026, 11:45pm EDT**. Build started **Oct 19**. Target submission: **Oct 28**, with Oct 29 as buffer.

**What the app does:** A community organizer (Discord, meetup, club, brand) enters what 5-10 members like. An AI agent resolves those tastes to Qloo entities, builds a combined community taste profile, queries Qloo across artists, brands, places (venues), and podcasts/TV shows, and produces an **event brief** with a "why this was recommended" explanation for every pick. A comparison view shows the same input answered by an LLM alone vs. the Qloo-grounded agent.

**Judging criteria (build for these):**
1. Technological Implementation: thorough, non-trivial use of Qloo
2. Design: complete, coherent product, not a proof of concept
3. Potential Impact: specific audience, real problem
4. Quality of the Idea: creative, non-obvious use of Qloo

**Hard rule from the hackathon:** if the app would work the same without Qloo, it is the wrong app. Every recommendation shown must come from Qloo results, never invented by the LLM.

**Submission requirements:** live hosted demo (local-only does not qualify), public GitHub repo with all source and run instructions, open-source license (MIT) visible in the repo's About section, and a text description. No demo video needed.

## Security rules (non-negotiable)
- Secrets live only in `.env` (local) and the host's environment settings (deployed). Never print, log, or commit them.
- `.gitignore` must contain `.env` BEFORE the first commit. Provide `.env.example` with placeholder names only.
- Qloo and OpenAI are called from the backend only. Never expose keys to the React app.
- Run `git status` and check history for secrets before any push.

## Stack (decided; see BUILD_PLAN.md section 3)
- ONE deployable service: FastAPI serves `/api/*` and the built React app (frontend/dist) as static files
- Backend: Python 3.11+, FastAPI, httpx, Pydantic v2, pydantic-settings, diskcache, slowapi
- LLM: OpenAI via the official `openai` SDK, wrapped in `llm.py`; model names from env (`OPENAI_MODEL_FAST`, `OPENAI_MODEL_SMART`). Check current OpenAI docs for tool calling and structured output.
- Frontend: React + Vite + TypeScript + Tailwind CSS
- Deploy: multi-stage Dockerfile on Render (or Railway/Fly.io); always-on or keep-alive during judging
- Repo: public GitHub, MIT license
- Mock mode: the app must run end to end with no keys (saved samples + templated brief)

## Qloo API findings (from the docs)

### Access
- Hackathon base URL: `https://hackathon.api.qloo.com` (hackathon keys return 401 on staging or production URLs)
- Auth header: `X-Api-Key: <key>` (not Bearer, not a query param)
- `/v2/insights` is **GET** with query-string params. POST with a JSON body fails.
- Do NOT use `/recommendations` or `/recs` (legacy, unsupported)
- Rate limits exist (429). Retry with backoff and cache aggressively.
- Invalid or unsupported parameters are **silently ignored** (200 with empty or unchanged results). Always validate against the whitelist below.
- 404 on `/search` and `/entities` means "no results". Treat as an empty list, not an error.
- No field filtering is available. Responses are heavy (`akas`, `short_descriptions`, long tag lists), so slim every entity before sending to the LLM or the frontend.

### Endpoints used
- `GET /search`: params `query`, `types` (array), `take`, `page`, `sort_by` (match|distance|popularity), `filter.location`, `filter.radius` (miles), `filter.tags`, `filter.popularity`, etc. Includes search-only type `urn:entity:locality` (use it to resolve a city or neighborhood name to a locality ID).
- `GET /entities`: params `entity_ids` (array of uuids) plus many `external.*.ids` lookups (spotify, imdb, instagram, wikidata, etc.). Batch fetch details by ID.
- `GET /v2/insights`: main recommendations endpoint. `filter.type` is always required.
- `GET /v2/tags`: look up valid tag IDs by keyword (tags are structured IDs like `urn:tag:genre:media:comedy`, not free text).
- `GET /v2/audiences`: **marked deprecated** in the docs, but the hackathon guide still references it. Optional feature. Params: `filter.query`, `filter.parents.types`, `take` (max 50), `page`.

### Supported `filter.type` values for the hackathon
`urn:entity:artist`, `book`, `brand`, `destination`, `movie`, `person`, `place`, `podcast`, `tv_show`, `video_game`. A 403 means the type is unsupported. Use `artist` for music (not `music`), and `place` or `brand` for food and drink (not `food_and_drink`).

### Valid insights parameters (from the Entity Type Parameter Guide)
Common to artist, brand, podcast, tv_show, place:
`filter.type`, `bias.trends`, `filter.exclude.entities`, `filter.exclude.tags`, `operator.exclude.tags`, `filter.external.exists`, `operator.filter.external.exists`, `filter.parents.types`, `filter.popularity.min`, `filter.popularity.max`, `filter.results.entities`, `filter.results.entities.query`, `filter.tags`, `operator.filter.tags`, `signal.interests.entities`, `signal.interests.tags`, `signal.demographics.age`, `signal.demographics.gender`, `signal.demographics.audiences`, `signal.demographics.audiences.weight`, `offset`, `take` (max 50), `page`.

Place only: `bias.quality`, `sort_by`, `filter.address`, `filter.hours`, `filter.geocode.name`, `filter.geocode.admin1_region`, `filter.geocode.admin2_region`, `filter.geocode.country_code`, `filter.location`, `filter.location.radius`, `filter.location.geohash`, `filter.exclude.location.geohash`, `filter.price_level.min/max`, `filter.price_range.from/to`, `filter.properties.business_rating.min/max`, `filter.external.tripadvisor.rating.min/max`, `filter.external.tripadvisor.rating.count.min/max`, `filter.references_brand`.

TV Show extras: `filter.rating.min/max`, `filter.content_rating`, `filter.release_year.min/max`, `filter.finale_year.min/max`.

Location filters exist ONLY for Place and Destination, not for artist, brand, podcast, or tv_show. In this app, only venues are location-filtered.

### UNVERIFIED items (test live in Phase 1; docs conflict or omit)
1. `feature.explainability=true` appears in the Deep Dive but NOT in the per-type matrix. It may be silently ignored.
2. `signal.interests.entities.weight` and `signal.interests.tags.weight` appear in the Deep Dive but NOT in the matrix. Only `signal.demographics.audiences.weight` is listed.
3. `filter.location.query` and `signal.location.query` are described for Place in the Parameter Reference but absent from the matrix. Preferred approach: resolve the city with `/search` (`types=["urn:entity:locality"]`), then pass the returned ID as `filter.location`. Fallback: `filter.geocode.name` + `filter.geocode.country_code`.
4. Docs disagree on some names (`operator.filter.exclude.tags` vs `operator.exclude.tags`; `filter.price_range.from/to` vs `.min/.max`). Test which actually changes results.
5. Exact `/search`, `/entities`, `/v2/audiences` response shapes. Capture real samples.
6. Whether `types` on `/search` needs repeated keys or a comma-separated list.
7. Max entity IDs per `/entities` call, and whether tags are included in results.
8. Whether the demo city has locality and place data. Hackathon data may be thin outside major cities.

### Response shape (insights)
`{"success": true, "results": {"entities": [...]}, "duration": N}`. Each entity: `name`, `entity_id`, `subtype`, `popularity` (0-1), `tags` [{id, name, type}], `properties` {description, image.url, ...}. Check for `query.explainability` at the top level of the body.

## Architecture
See BUILD_PLAN.md sections 3-4 (layout), 6 (data models), 8 (agent tools and fallback), 10 (routes), 11 (UI).

### Design requirements
- **Parameter whitelist** (`allowed_params.py`): per-`filter.type` set of allowed params; drop and warn on anything else (since the API ignores them silently). Include a `test_mode` that lets UNVERIFIED params through.
- **`slim_entity()`**: keep id, name, type, popularity, description, image, address, a few tag names, and tag ids. Drop `akas`, `short_descriptions`, `websites`, and so on.
- **Client helpers**: `search`, `find_locality`, `get_entities`, `find_audiences`, `insights`. 429 backoff, 404 to empty, cache everything.
- **Profile builder**: resolve each member's tastes to entity IDs, weight by how many members named an entity (client-side weighting; do not rely on request-level weights unless verified), optional audience signals.
- **Recommendations**: separate query per domain (artist, brand, place, podcast/tv_show). Venues use the locality ID or geocode filters, plus optional price, hours, and quality filters. Optional "hidden gems" mode via `filter.popularity.max` (about 0.7).
- **Explanations**: use native explainability if verified. Otherwise compute a fallback: for each result, show which members' named entities it is most related to, using per-member scoring via `filter.results.entities` and/or shared tags. Never fabricate reasons.
- **Agent**: LLM with tools decides which domains and filters to query for the organizer's goal (for example, "chill Saturday meetup" vs "launch party"). Provide a **deterministic fallback pipeline** that runs if the agent fails. Show the agent's tool-call trace in the UI.
- **Brief generator**: the LLM may recommend ONLY entities returned by Qloo and must cite the explanation data. Validate that every named recommendation exists in the Qloo results.
- **Baseline** (`baseline.py`): same input answered by the LLM alone, for the side-by-side comparison view.
- **Mock mode**: if `QLOO_API_KEY` is unset, serve saved sample responses so the UI can be developed offline.
- **Cost control**: small prompts (slimmed entities), cache briefs, 2-3 pre-loaded example communities with saved outputs, per-IP rate limit on live runs, cheaper model for tool routing and stronger model only for the final brief. Set a spending limit on the LLM account.

## Feature priorities
**Must have:** input form (community name, city, 5-10 member tastes); entity resolution; taste profile; multi-domain recommendations; explanations; agent loop with real tool calls; event brief; Qloo vs LLM-only comparison view; live deployment, public repo, MIT license, README.
**Nice to have (only after the above works):** audience "community type" picker, member survey link, shareable saved briefs, map of venues, price and hidden-gems controls, link-based member input via `/entities` external IDs.

## Build phases
Follow the phase prompts in BUILD_PLAN.md section 12 (Phase 0 scaffold → 1 Qloo client + live tests → 2 resolve/profile/recommend/explain → 3 agent/brief/baseline → 4 examples + frontend → 5 deploy → 6 harden + submission assets → 7 owner submits). Finish each phase's acceptance criteria before starting the next.

## Phase 1 live test checklist (run with the real key; save raw responses to `backend/samples/`)
1. `/search` for an artist, brand, podcast, TV show: shape, and are tags included?
2. `/search` with `types=["urn:entity:locality"]` for 3 cities, including a Nigerian city (for example Lagos or Abuja) and a US city.
3. `feature.explainability=true` on artist, brand, place: does `query.explainability` appear?
4. Entity weights: do `signal.interests.entities.weight` values change results?
5. Place query using locality ID in `filter.location` vs. `filter.geocode.name` + `country_code`.
6. `filter.popularity.max=0.7` on artists: less mainstream results?
7. `/search` `types`: repeated keys vs comma list.
8. `/entities` with 1, 20, and 50 IDs: tags present? batch limit?
9. `/v2/audiences` with `filter.parents.types=urn:audience:hobbies_and_interests` and `filter.query=gaming`: works? shape?
10. One artist insight with and without an audience ID: do results change?
11. `take=50` and `offset=50` pagination.
12. `filter.exists=properties.image` on artist and place: honored or ignored?
13. Per-member affinity: insights with one member's entity IDs plus `filter.results.entities=<result IDs>`. Where is the affinity score in the response (each entity's `query` object?)
14. `/v2/tags` keyword search for venue kinds ("bar", "lounge", "event venue"): shape and usable tag IDs.

Record findings and the decisions they drive (demo city, explanation approach, weighting approach) in `API_FINDINGS.md`.

## Working agreements
- Work in small steps, run the code, and fix real errors. After each phase, summarize what works, what was verified live, and what is still assumed.
- Commit after each working milestone with clear messages. Never commit secrets or large raw sample dumps that include anything sensitive.
- Explain non-obvious design choices briefly in code comments and the README. The owner must be able to explain every part of this repo to judges.
- If a live result contradicts this file, trust the live result and update this file.
- Do not add features outside the priority list until the "Must have" set works end to end on the deployed URL.
