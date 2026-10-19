# TasteRoom

**Stop guessing what your community wants. Plan events from real taste data.**

TasteRoom is an AI agent for community organizers (Discord servers, meetups, run clubs, brand communities).
Enter what 3 to 15 members like and the city. The agent resolves those tastes to [Qloo](https://qloo.com) entities,
builds one community taste profile, queries Qloo for **music, venues, sponsors and content**, and writes an
**event brief** where every pick comes from Qloo and is explained. A **Compare** tab shows the same request answered
by a plain LLM, so you can see what Qloo adds.

**Live demo:** https://tasteroom-production-d52a.up.railway.app &nbsp;·&nbsp; **License:** MIT &nbsp;·&nbsp; Built for the Qloo Agentic Hackathon

![Landing page](docs/screenshots/landing.jpg)

## Why this needs Qloo

> If the app would work the same without Qloo, it is the wrong app.

- **Every recommendation shown is a Qloo result.** The LLM organizes and writes; it never supplies picks. A validator
  removes any pick in the brief that Qloo did not return for that section (and restores Qloo's canonical name).
  The number removed is returned with every plan (`dropped_picks`).
- **Explanations are Qloo's own.** "Why this pick" uses Qloo's `feature.explainability` scores mapped back to the members
  who named each input entity. Nothing is invented.
- **The Compare tab measures the difference** instead of claiming it (see [What Compare shows](#what-compare-shows)).

| Brief | Why this pick |
|---|---|
| ![Brief](docs/screenshots/brief.jpg) | ![Why this pick](docs/screenshots/why-this-pick.jpg) |

## How it works

```mermaid
flowchart LR
    U[Organizer<br/>React app] -->|/api/*| API[FastAPI<br/>one service, one URL]
    API --> AG{Agent<br/>OpenAI tool calling}
    AG -->|tools| T[resolve_tastes · resolve_city<br/>recommend · find_venues · explain]
    API -.->|agent errors, times out<br/>or is incomplete| PL[Deterministic pipeline<br/>same tools, fixed order]
    PL --> T
    T --> QC[Qloo client<br/>whitelist · retries · cache]
    QC --> Q[(Qloo<br/>hackathon API)]
    T --> BR[Brief writer<br/>OpenAI structured output]
    BR --> VAL[Grounding validator<br/>drops picks Qloo did not return]
    API --> BL[Baseline<br/>LLM only, no Qloo data]
    BL --> CMP[Compare tab stats]
```

1. **Resolve** each member's tastes to Qloo entities (typed search, then an untyped retry; best by name similarity,
   then popularity; weak matches are rejected). The city is resolved to a Qloo *locality* and validated against the
   locality's name and aliases, so a nonsense city cannot silently become a different place.
2. **Profile**: entities named by several members weigh more; for large groups the 25-entity signal is filled
   round-robin so no member is crowded out.
3. **Agent** (OpenAI Responses API, tool calling) reads the event goal and decides which domains and filters to use.
   A launch party gets music, venues and sponsors; a podcast-listening meetup gets content and venues.
   Every tool call is recorded and shown in the **How it worked** tab.
4. **Recommend**: one Qloo `/v2/insights` query per domain, each with its own signal (see
   [Findings that shaped the design](#findings-that-shaped-the-design)).
5. **Explain** each pick from Qloo's explainability data.
6. **Brief**: a stronger model writes the brief from a compact list of Qloo results; the validator enforces grounding.

If the agent errors, times out (60 s budget, max 10 tool calls) or finishes incompletely, the **deterministic pipeline**
runs the same tools in a fixed order and keeps whatever the agent already gathered. The demo cannot fail because of the
agent. If the brief writer fails, a templated brief is built from the same Qloo data. With no API keys at all, the app
runs end to end in **mock mode** on saved samples.

## How Qloo is used

| Qloo endpoint | Used for | Key parameters |
|---|---|---|
| `GET /search` | Resolve each taste to an entity; resolve the city to a locality | `query`, `types` (artist, brand, podcast, tv_show, movie, book, videogame, place, **locality**), `take` |
| `GET /v2/insights` | The recommendations: artists, venues, brands, podcasts + TV shows | `filter.type`, `signal.interests.entities`, **`feature.explainability`**, `filter.location` (locality ID), `filter.popularity.max` (hidden gems), `filter.price_level.max`, `filter.hours`, `filter.tags`, `take` |
| `GET /v2/tags` | Turn a venue kind ("lounge", "event venue") into a valid place tag ID | `filter.query` |

Also implemented and verified live, but not exposed in the UI: `/entities` (batch fetch, up to 50 IDs),
`/v2/audiences` (audience signal via `signal.demographics.audiences`), and per-member affinity via
`filter.results.entities`. All Qloo access goes through one client (`backend/app/qloo_client.py`) with a per-type
**parameter whitelist** (`allowed_params.py`), because Qloo silently ignores unknown parameters.

### Findings that shaped the design

Qloo's docs and its behavior differ in places, so everything was tested live ([`API_FINDINGS.md`](API_FINDINGS.md) has the
evidence for each point):

- **Native explainability works** (artist, brand, place), but its split across inputs is close to uniform, so raw
  per-member shares mostly show *how many tastes a member listed*. TasteRoom divides by the share that entity count alone
  would predict, then compares each member's pull on a pick with their *usual* pull across the whole list. What remains is
  pick-specific signal. Most picks honestly read "suits all N members"; a few genuinely stand out for someone.
- **What you feed Qloo matters.** Brands in the signal drag music, venue and content results toward global luxury
  names; artists + shows give on-taste results; sponsors match best from artists + brands. Each domain has its own signal.
- **A location filter is mandatory for venues.** Without one, a Nigerian taste profile still returns Lagos venues
  (Qloo infers location from taste). The locality-ID route works; `filter.geocode.*` returned nothing.
- **Per-entity weights are not supported** (`signal.interests.entities.weight` takes one number for the whole group), so
  weighting is done client-side.
- **Rate limits are real.** 6 parallel requests never hit a 429; 10 did, so concurrency is capped at 6 with exponential
  backoff, and a lookup that fails because Qloo is busy is reported as "busy" rather than blamed on the organizer's spelling.

## What Compare shows

![Compare tab](docs/screenshots/compare.jpg)

For the same community and goal, the LLM-only answer is compared with the Qloo-grounded one:

| Measured | LLM only | Qloo-grounded |
|---|---|---|
| Picks with a data-backed explanation | 0 | all |
| Picks that go beyond what members already named | ~3 of 12 (it mostly echoes the input) | all |
| Picks that exist in Qloo | ~all | all (by construction) |
| Venues confirmed in the city (by Qloo's own geocode) | 1 to 3 of 3 | 3 of 3 |

The LLM does name real, popular things. Those rows are shown anyway because an honest comparison matters more than a
dramatic one. What it cannot do is explain *why a pick suits this community* with data, or discover beyond the input.

## Screens

| Builder: check tastes against Qloo | How it worked: the agent's real tool calls | Mobile |
|---|---|---|
| ![Builder](docs/screenshots/builder.jpg) | ![Agent trace](docs/screenshots/agent-trace.jpg) | <img src="docs/screenshots/mobile-brief.jpg" width="220"> |

## Run it locally

```bash
cp .env.example .env     # add your keys; .env is git-ignored. With no keys the app runs in mock mode.
make setup
make dev-api             # terminal 1: FastAPI on :8000
make dev-web             # terminal 2: Vite on :5173 (proxies /api to :8000)
```

One-port, production style: `make serve`, then open http://localhost:8000.

| Variable | Purpose | Default |
|---|---|---|
| `QLOO_API_KEY` | Qloo hackathon key (unset = mock mode) | none |
| `OPENAI_API_KEY` | OpenAI key (unset = templated brief, no agent) | none |
| `OPENAI_MODEL_FAST` | Agent tool loop | `gpt-6-luna` |
| `OPENAI_MODEL_SMART` | Brief writer and LLM-only baseline | `gpt-6.1-sol` |
| `QLOO_BASE_URL` | Qloo host | `https://hackathon.api.qloo.com` |
| `RATE_LIMIT_PLAN` | Live plans per visitor (cached plans are free) | `5/hour` |
| `AGENT_DISABLED` | `1` skips the agent and runs the pipeline | `0` |
| `APP_ENV` | Environment label | `development` |

Keys are read only by the backend; the React app never sees them.

**Tests:** `make test` (86 backend tests: client retry/429/404 behavior, parameter whitelist, resolution, explanation
math, agent + fallback, grounding validator, API, rate limit, error paths) and `cd frontend && npm test`. Both run with no
network or keys.

**Regenerate the examples** (live Qloo + OpenAI): `cd backend && python -m scripts.precompute_examples`.
**Live Qloo checks:** `python -m scripts.smoke_test` (writes `backend/samples/`).

## Deploy

Single Docker service (FastAPI serves the API and the built React app on one port).

```bash
docker build -t tasteroom . && docker run --rm -p 8000:8000 -e QLOO_API_KEY=... -e OPENAI_API_KEY=... tasteroom
```

Railway and Render steps are in [`DEPLOY.md`](DEPLOY.md) (`railway.toml`, `render.yaml`). The image runs as a non-root user,
contains no secrets, and has a health check on `/api/health`. Before any push run `./scripts/check_secrets.sh`; it looks for
your actual key values in tracked files, git history and the built frontend bundle.

## Security and cost controls

- Secrets only in `.env` (local) and the host's variables; Qloo and OpenAI are called from the backend only.
- Content-Security-Policy and standard security headers; only `http(s)` links are rendered from third-party data.
- Per-visitor rate limit on live planning keyed on the proxy-provided client IP (forged headers tested not to evade it);
  responses are cached 24 h and plans 7 days; the three examples are precomputed and cost nothing to open.
- Cheaper model for the agent loop, stronger model only for the brief and baseline; prompts use slimmed entities only.
- Friendly JSON errors only; no stack traces or upstream messages reach the browser.

## Repository layout

```
backend/app/    qloo_client · allowed_params · slim · resolve · profile · recommend · explain
                tools · agent · pipeline · brief · baseline · llm · planner · ratelimit · main
backend/samples/      trimmed raw Qloo responses (mock mode + test fixtures)
backend/precomputed/  saved results for the 3 example communities
backend/scripts/      smoke_test · run_pipeline · precompute_examples
frontend/src/         pages (Landing, Builder, Results) · components · lib · api
API_FINDINGS.md       live-tested behavior of the Qloo API and the decisions it drove
```

## Known limitations

- A live plan takes about 40 to 60 seconds (about 75 for a 15-member, 90-taste community), mostly LLM time.
- Qloo's venue photos and descriptions are only as good as its data; thin cities return fewer venues.
- `filter.hours` has unclear semantics in Qloo, so the day filter is best-effort and only applied when the organizer states a day.
- Podcast and TV picks are looser than music and brand picks for communities that named no shows or podcasts.

## License

[MIT](LICENSE) © 2026 Shedrack Yashim
