# TasteRoom: Devpost submission text

Paste each section into the matching Devpost field. Links and numbers below are real and checked; update only if you redeploy.

- **Live demo:** https://tasteroom-production-d52a.up.railway.app
- **Code (MIT):** https://github.com/shedybaba/tasteroom
- **Tagline:** Stop guessing what your community wants. Plan events from real taste data.

## Short description (one or two sentences, for the project card)

TasteRoom is an AI agent that turns what a community's members like into a ready-to-run event brief: artists, venues,
sponsors and shows, every pick sourced from Qloo and explained by the members behind it.

## Inspiration

Community organizers (Discord moderators, run-club leads, campus societies, brand community teams) plan events by guessing.
They poll a few loud members, copy what worked elsewhere, or ask a chatbot, and chatbots recommend whatever is popular.
The result is a headline act half the community has never heard of, a venue nobody wanted, or a sponsor that doesn't fit.
The information they need exists, as the tastes of their own members, but nothing turns it into decisions. Qloo's taste
graph is exactly that missing layer, so we built the organizer's tool around it.

## What it does

You enter a community name, a city, the kind of event, and 3 to 15 members with a few tastes each (artists, shows, brands,
podcasts, games; a paste-a-list box is built in). "Check tastes" shows which ones Qloo recognises. Then an AI agent:

1. matches every taste to a Qloo entity and the city to a Qloo locality,
2. builds one community taste profile (entities several members share count more),
3. decides what this event needs, because a launch party and a podcast-listening meetup need different things,
4. queries Qloo for music, venues in your city, sponsors and content,
5. explains every pick from Qloo's own explainability data, and
6. writes an event brief: concept, run of show, top picks with reasons, and an announcement line you can post.

Everything is browsable by tab (Music, Venues, Sponsors, Content), each card has a **Why this pick** panel, and a
**How it worked** tab shows every tool call the agent made. A **Compare** tab answers the same request with a plain LLM
and measures the difference. Three example communities (a Lagos creator mixer, an Austin anime and gaming Discord, a London
run club) open instantly.

## How we built it

- **Backend:** FastAPI (Python), httpx, Pydantic v2. One service serves the API and the built React app on one URL.
- **Frontend:** React, Vite, TypeScript, Tailwind CSS. Responsive down to 375 px.
- **Agent:** OpenAI Responses API with real tool calling (`resolve_tastes`, `resolve_city`, `recommend`, `find_venues`,
  `explain`, `finish`), a 10-call / 60 s budget, and a visible trace. The agent loop uses a cheap model; only the brief uses
  the stronger one.
- **Reliability:** if the agent errors, times out or is incomplete, a deterministic pipeline runs the same tools in a fixed
  order and keeps what the agent already did. If the brief writer fails, a templated brief is built from the same Qloo data.
  With no keys the whole app runs on saved samples.
- **Grounding:** the LLM may only choose entities Qloo returned. A validator drops anything else, restores Qloo's canonical
  names, and the count of removed picks is returned with every plan.
- **Deploy:** multi-stage Docker image (non-root, health-checked) on Railway. 87 backend tests and 7 frontend tests, plus
  live end-to-end checks in a real browser.

## How Qloo powers it

Qloo is not decoration here; remove it and nothing is left.

- `GET /search` resolves every member's taste to an entity (typed, then untyped retry, with similarity checks so
  "Kenshi Yonezu" can't become "Kenshin") and resolves the city to a **locality**, validated against its name and aliases.
- `GET /v2/insights` produces all recommendations: artists, venues, brands, podcasts and TV shows, each query seeded by
  the community's combined entities. Venues use the locality ID as a location filter, plus optional price, day and venue-type
  (`/v2/tags`) filters. "Hidden gems" uses `filter.popularity.max`.
- **`feature.explainability`** gives, for each result, how much each input entity contributed. We map those back to the
  members who named them to produce the Why panel.
- A per-type **parameter whitelist** guards every call, because Qloo silently ignores parameters it doesn't support.

We tested the API live and wrote down what it really does (`API_FINDINGS.md`). Several findings changed the product:
Qloo's explainability split is close to uniform, so we normalise it against what each member's entity count alone predicts and
against their usual pull across the list; brands in the seed drag music and venue results toward global luxury names, so each
domain gets its own seed; venues need an explicit location filter or Qloo infers the city from taste.

## Challenges we ran into

- **Honest explanations.** Our first "why" showed the same two members as the reason for every pick. They simply had the
  most central entities, not the best fit. We rebuilt the explanation to show only pick-specific deviation, so most picks now say
  "suits all members" and a few truly stand out for someone.
- **Qloo behaves differently from its docs** (explainability, weights, geocode filters, parameter names). We verified everything
  live instead of trusting the matrix.
- **Rate limits.** Ten parallel Qloo requests triggered 429s and silently lost lookups; we measured the safe level (six), added
  backoff, and report a busy Qloo as "busy" rather than blaming the organizer's spelling.
- **A fair comparison.** Our first LLM-vs-Qloo stats punished the LLM unfairly (it wrote "Top pick: Terra Kulture, Victoria
  Island", which failed lookup) and then flattered Qloo (the LLM mostly echoed members' own tastes, which Qloo never recommends
  back). We fixed the verifier and replaced the metric with one that measures discovery beyond the input.
- **Fuzzy city search.** "Zzyzx Atlantis Narnia" resolved to a real place called Atlantis. City matches are now validated.

## Accomplishments we're proud of

- Every pick on screen is a Qloo result, with a reason from Qloo's data, and the AI can't smuggle in its own.
- The agent genuinely chooses: a launch party and a podcast meetup produce different tool sequences and different briefs.
- A comparison that reports bad news too: the LLM names real things; it just can't explain them for *this* community or go
  beyond what members already said (about 3 of its 12 picks were new; every Qloo pick was).
- It is a finished product, not a demo: checked tastes with thumbnails, loading and error states for every call, copy-ready
  brief and announcement, mobile layout, a CSP, rate limiting, and a deploy that survives the agent failing.

## What we learned

- The seed you give a taste graph matters as much as the graph: mixed seeds dilute, tailored seeds sharpen.
- Explainability scores need context before they are explanations.
- Verify third-party APIs empirically, and keep a record of what you verified.
- A skeptical comparison earns more trust than a flattering one.

## What's next

- Member survey links so members add their own tastes (the data model already supports named members).
- Audience "community type" signals (the client already implements `/v2/audiences`).
- Streaming progress while the agent works, and shareable saved briefs.
- A map of the recommended venues, and importing tastes from Spotify or Letterboxd links via Qloo's external-ID lookups.

## Built with

Qloo API (search, insights, explainability, tags) · OpenAI (Responses API, tool calling, structured output) · Python · FastAPI ·
httpx · Pydantic · React · TypeScript · Vite · Tailwind CSS · Docker · Railway

---

# 60-second demo script

Open the live URL in a fresh tab beforehand. Keep the **Lagos Creators** example ready. Times are approximate; the
"live plan" step takes 40 to 60 seconds, so **do not wait on it on camera**: start it first, talk over it, or show the
precomputed example. Examples open instantly.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Landing page hero | "Community organizers plan events by guessing. TasteRoom plans them from taste data. Every recommendation comes from Qloo; the AI only organizes it." |
| 0:08 | Click **Lagos Creators**; Brief tab | "Eight members of a Lagos creator community, one Saturday mixer. The agent turned their tastes into this brief: concept, run of show, and picks with reasons." |
| 0:18 | **Music** tab, click **Why this pick** on Travis Scott | "Each pick is explained from Qloo's own explainability data. Most suit the whole group; this one stands out for Ada. Bars compare each member's pull against their usual pull, so it isn't just whoever listed the most tastes." |
| 0:30 | **Venues** tab | "Venues come from Qloo for the right city: here, real Lagos lounges and event spaces, filtered by a Qloo locality." |
| 0:36 | **How it worked** tab | "This is the agent's real trace: it matched 32 tastes, found the city, then chose which domains this event needs. A podcast meetup gets a different path. If the agent ever fails, a fixed pipeline takes over with the same tools." |
| 0:46 | **Compare** tab, point at the stats | "Same request to a plain LLM. It names real, popular things, but only three of its twelve picks go beyond what members already said, none has a data-backed reason, and only one of its three venues can be confirmed in the city. Every Qloo pick is new, explained, and confirmed local." |
| 0:56 | Back to landing / **Plan an event** | "Paste your own community, check tastes against Qloo, and get a brief. TasteRoom: plan events from real taste data." |

**If asked live:** the build step uses the agent for 40 to 60 seconds, which is why the examples are precomputed.
The per-visitor limit is 5 live plans an hour to control cost.

# Judging criteria map

| Criterion | Where it shows |
|---|---|
| Technological implementation | Multi-endpoint Qloo use (search, locality, insights, tags, explainability), parameter whitelist, live-verified findings, real tool-calling agent with trace and deterministic fallback, grounding validator, 87 + 7 tests |
| Design | One flow (Examples, Builder, Results), real Qloo images, checked-taste states, loading and error states everywhere, responsive and accessible (tabs, labels, focus), CSP |
| Potential impact | A specific user (community organizers), a specific pain (guessing), a concrete output (a brief they can run and post) |
| Quality of the idea | Group taste fusion, per-pick explanations, and a comparison that measures what Qloo adds rather than asserting it |
