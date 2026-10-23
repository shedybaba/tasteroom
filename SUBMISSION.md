# TasteRoom: Devpost submission text

Paste each section into the matching Devpost field. Links and numbers below are real and checked; update only if you redeploy.

- **Live demo:** https://tasteroom-production-d52a.up.railway.app
- **Code (MIT):** https://github.com/shedybaba/tasteroom
- **Tagline:** Share a link, members add their tastes, the agent builds a plan you can refine.

## Short description (one or two sentences, for the project card)

TasteRoom lets anyone planning a get-together (friends, family, a team retreat or a community) share one link, collects what everyone likes, and has an AI agent turn it into an event brief
(artists, venues, sponsors, shows) that every pick comes from Qloo and is explained. Refine it by chatting with the agent, check that
every member is represented, and share or post it.

## Try it in 60 seconds (put this in the "Try it out" / testing instructions field)

No sign-up. Open https://tasteroom-production-d52a.up.railway.app and:

1. Click the **Lagos Creators** example. The brief opens instantly (it is a saved real run).
2. Open the **Compare** tab: the same request answered by a plain LLM, measured against the Qloo-grounded plan.
3. Back on **Brief**, scroll to **Something for everyone** (one personal pick per member, found from their own tastes). **How are these picked?** holds the rules.
4. In the **Brief**, the venue section shows a **Top pick** and a **Cheapest option** (the lowest Qloo price level among that city's venue results; "Price not available" when Qloo has none). Then in **Tell the agent what to change** tap **More hidden gems**: it takes 20 to 40 seconds, changes only music, sponsors and content (the **How it worked** tab shows which calls ran), and **Undo last change** puts the plan back.
5. Go to the landing page and click **See a live room**: an invite room with 8 member responses, and a plan you can build from them.

Everything else is optional: **Plan an event** (guided prompts with live Qloo autocomplete), **Collect tastes from members** (invite link
and QR code), **Share**, **Copy a poll for my members**. Live plans are limited to 5 per visitor per hour to control cost.

## Inspiration

Whoever organizes a group (a friend picking the night out, a relative planning a family day, a team lead booking an offsite, a Discord moderator or run-club lead) plans by guessing.
They poll a few loud voices, copy what worked elsewhere, or ask a chatbot, and chatbots recommend whatever is popular.
The result is a headline act half the group has never heard of, a venue nobody wanted, or a sponsor that doesn't fit.
The information they need exists, as the tastes of the people coming, but nothing turns it into decisions, and the quiet
ones never get heard. Qloo's taste graph is exactly that missing layer, so we built the host's tool around it.

## What it does

1. **Collect.** The organizer shares one link in Discord or WhatsApp (a QR code is included). Members open it on their phones and fill
   up to five optional, guided prompts (an artist on repeat, a show to rewatch, a brand they buy, a podcast, a favourite spot) with live
   Qloo autocomplete. About 30 seconds, no sign-up, first names only. The organizer page updates as members respond. (Prefer to type the
   members in yourself? The Builder does that too, with a paste-a-list box.)
2. **Plan.** An AI agent matches every taste to a Qloo entity and the city to a Qloo locality, builds one community taste profile
   (entities several members share count more), decides what this event needs (a launch party and a podcast-listening meetup need different
   things), queries Qloo for music, venues in the city, sponsors and content, explains every pick from Qloo's own explainability data, and
   writes an event brief: concept, run of show, picks with reasons, and an announcement line.
3. **Refine.** The organizer types or taps a change ("cheaper venue", "more hidden gems", "more chill music", "a different neighbourhood").
   The agent re-queries only the domains that change affects, everything else is kept verbatim, and the plan is updated in place with a
   "What changed" strip and an "Undo last change" link. (A shared example is never changed: the visitor gets their own copy.) The venue
   section always shows a **Top pick** and a **Cheapest option**, both from Qloo's own venue results and price levels.
4. **Something for everyone.** Every member gets a personal pick: we ask Qloo what that one person would like from their own tastes alone (one
   query per member), keep the first result that also fits the group, and show how it fits ("it is #2 in the group's results", or "Qloo ties it to
   the group at 97% of the average pull"). The Compare tab counts two things separately: members with a pick that *stands out* for them in the
   lineup (the strict rule: 2 of 8 in the Lagos example) and members with a personal pick (8 of 8). A member with no fitting pick is listed with the
   reason, never hidden.
5. **Act.** Share a read-only link, copy a ready-to-paste poll of the top 3 venues, or post the announcement to Discord (you see exactly what
   will be posted and confirm first).

Throughout: every card has a **Why this pick** panel, a **How it worked** tab shows every tool call, and a **Compare** tab answers the same
request with a plain LLM and measures the difference. Five examples open instantly: a friends' night out in San Francisco, team offsite drinks in New York, a Lagos creator mixer, an Austin anime and gaming Discord, and a
London run club.

## How we built it

- **Backend:** FastAPI (Python), httpx, Pydantic v2, SQLite for invite rooms and saved plans (on a mounted volume). One service serves the API
  and the built React app on one URL.
- **Frontend:** React, Vite, TypeScript, Tailwind CSS. Responsive down to 375 px; accessible tabs, combobox autocomplete and focus states.
- **Agent:** OpenAI Responses API with real tool calling (`resolve_tastes`, `resolve_city`, `recommend`, `find_venues`, `explain`, `finish`, plus
  `find_tags` and `list_neighbourhoods` for refinements), a call and time budget, and a visible trace. A refinement restricts the agent in code to
  the domains the request can touch; out-of-scope calls are refused. The agent loop uses a cheap model; only the brief uses the stronger one.
- **Reliability:** if the agent errors, times out or is incomplete, a deterministic pipeline runs the same tools in a fixed order and keeps what
  the agent already did. If the brief writer fails, a templated brief is built from the same Qloo data. With no keys the whole app runs on saved samples.
- **Grounding:** the LLM may only choose entities Qloo returned. A validator drops anything else, restores Qloo's canonical names, and the count of
  removed picks is returned with every plan. The brief writer is also told not to invent logistics (times, dates, prices, RSVP steps).
- **Safety:** invite-room organizer tokens are stored only as hashes; per-visitor rate limits on every costly or write route; Discord webhook URLs are
  used once and never stored or logged, the server posts only to a Discord address it builds itself, and messages cannot ping anyone.
- **Deploy:** multi-stage Docker image (non-root, health-checked) on Railway with a persistent volume. 216 backend tests and 34 frontend tests, plus
  end-to-end checks in a real browser against the live site.

## How Qloo powers it

Qloo is not decoration here; remove it and nothing is left.

- `GET /search` resolves every member's taste to an entity (typed, then untyped retry, with similarity checks so "Kenshi Yonezu" can't become
  "Kenshin"), powers the live autocomplete, and resolves the city to a **locality**, validated against its name and aliases.
- `GET /entities` resolves the suggestions members picked in one batch call.
- `GET /v2/insights` produces all recommendations: artists, venues, brands, podcasts and TV shows, each query seeded by the community's combined
  entities, with a signal tailored to each domain. Venues use the locality ID as a location filter, plus optional price, day and venue-type
  filters. "Hidden gems" uses `filter.popularity.max`. With no taste signal at all it also powers the "Need ideas?" chips.
- **Personal picks use `/v2/insights` once per member**, seeded only with that member's own entities (4 at a time, cached), and then
  `filter.results.entities` with the group's signal to measure how strongly Qloo ties a candidate to the whole group (its `affinity`). The one
  fact that made this safe: Qloo never returns an entity you seeded with, so personal picks are always new discoveries.
- `GET /v2/tags` turns "lounge", "event venue" or "chill" into valid tag IDs for venue and mood filters.
- **`feature.explainability`** gives, for each result, how much each input entity contributed. We map those back to the members who named them to
  produce the Why panel and the Compare tab's coverage row.
- A per-type **parameter whitelist** guards every call, because Qloo silently ignores parameters it doesn't support.

We tested the API live and wrote down what it really does (`API_FINDINGS.md`). Several findings changed the product: Qloo's explainability split is
close to uniform, so we normalise it against what each member's entity count alone predicts and against their usual pull across the list; brands in
the seed drag music and venue results toward global luxury names, so each domain gets its own seed; venues need an explicit location filter or Qloo
infers the city from taste; a neighbourhood's entity id works as a location filter, which is what "different neighbourhood" uses.

## Challenges we ran into

- **Honest explanations, twice.** Our first "why" showed the same two members as the reason for every pick. We rebuilt it to show only pick-specific
  deviation, so most picks say "a crowd-pleaser: fits all members". Then the Coverage feature exposed the same fact at group level: on the examples
  only 2 of 8, 0 of 7 and 0 of 7 members have a pick that stands out for them. Lowering the bar would have flipped that to "everyone" within a few
  hundredths, so we kept the bar and fixed the cause instead: we stopped trying to find "their" pick inside a group answer and asked Qloo about each
  member separately. We still report both numbers, and 16 of the 27 personal picks are also group results, so the card says which is which.
- **Fitting one person into a group.** A member's own results often don't belong to the group (for two Pixel Pact members none of their top 20 music
  results is in the group's top 50). We measured Qloo's group-level affinity for candidates with `filter.results.entities` and require a pick to be a
  group result or within 5% of the group's average pull. That cut-off is a round number, and we checked that the outcome doesn't depend on it.
- **The model kept inventing event details.** The first example promo said "Saturday, 6 to 9 pm" when the organizer only said "Saturday evening",
  and that line gets posted to a real channel. We added a rule against invented logistics, found the first fix made everything "to be confirmed",
  and narrowed it so the plan still names the real venue and picks.
- **Qloo behaves differently from its docs** (explainability, weights, geocode filters, parameter names). We verified everything live instead of
  trusting the matrix.
- **Rate limits.** Ten parallel Qloo requests triggered 429s and silently lost lookups; we measured the safe level (six), added backoff, and report a
  busy Qloo as "busy" rather than blaming the organizer's spelling.
- **A fair comparison.** Our first LLM-vs-Qloo stats punished the LLM unfairly and then flattered Qloo. We fixed the verifier and replaced the metric
  with one that measures discovery beyond the input.
- **A credential in the user's hands.** A Discord webhook URL is a secret, and our server would be posting to it. We validate it strictly, post only to
  a `discord.com` address we build from its id and token (no server-side request forgery, no redirects), build the message ourselves from the saved
  plan, and test that the token never reaches logs, responses, the cache or the database.
- **Stale copies.** Regenerating an example would have left visitors' saved copies built on the old brief. They are now dropped automatically when the
  example's saved content changes.

## Accomplishments we're proud of

- Every pick on screen is a Qloo result, with a reason from Qloo's data, and the AI can't smuggle in its own.
- A complete organizer loop, not a one-shot generator: collect from members, plan, refine, check coverage, share.
- The agent genuinely chooses, and refining it provably changes only what the request affects (the trace shows exactly which calls a refinement ran).
- A comparison and a coverage score that report bad news too (the strict standout count is 2 of 8, 0 of 7 and 0 of 7, shown next to the personal-pick count): the LLM names real things (it just can't explain them for *this* community or go beyond
  what members already said: 3 of its 12 Lagos picks were new, every Qloo pick was), and Qloo's per-member signal is weak enough that most members are
  served by crowd-pleasers.
- It is a finished product: checked tastes with thumbnails, loading and error states for every call, copy-ready brief and announcement, mobile layout,
  a CSP, rate limiting, and a deploy that survives the agent failing and keeps its data across redeploys.

## What we learned

- The seed you give a taste graph matters as much as the graph: mixed seeds dilute, tailored seeds sharpen.
- Explainability scores need context before they are explanations, and a metric built on them needs a threshold you refuse to tune.
- Verify third-party APIs empirically, and keep a record of what you verified.
- Anything an LLM writes that will be posted publicly needs a preview-and-confirm step and a rule against invented specifics.
- A skeptical comparison earns more trust than a flattering one.

## What's next

- Audience "community type" signals (the client already implements `/v2/audiences`).
- Streaming progress while the agent works.
- A map of the recommended venues, and importing tastes from Spotify or Letterboxd links via Qloo's external-ID lookups.
- Editing the announcement before posting, and asking a member who has no fitting pick for more tastes.

## Built with

Qloo API (search, entities, insights, explainability, tags) · OpenAI (Responses API, tool calling, structured output) · Python · FastAPI · httpx ·
Pydantic · SQLite · React · TypeScript · Vite · Tailwind CSS · Docker · Railway

---

# 60-second demo script

Open the live URL in a fresh tab beforehand. Keep the **Lagos Creators** example ready. Times are approximate; building a *new* live plan takes 40 to
60 seconds, so **do not wait on it on camera**: show the precomputed example. A refinement takes 20 to 40 seconds, so narrate it while it runs or skip it.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Landing page hero | "Hosts plan get-togethers by guessing, whether it is friends, family, a team or a community. TasteRoom plans them from what everyone actually likes: share a link, everyone adds their tastes, the agent builds a plan you can refine. Every recommendation comes from Qloo; the AI only organizes it." |
| 0:08 | Click **Lagos Creators**; Brief tab | "Eight members of a Lagos creator community, one Saturday mixer. The agent turned their tastes into this brief: concept, run of show, and picks with reasons." |
| 0:16 | **Music** tab, **Why this pick** on Travis Scott | "Each pick is explained from Qloo's own explainability data. Most suit the whole group; this one stands out for Ada. The bars compare each member's pull against their usual pull, so it isn't just whoever listed the most tastes." |
| 0:26 | **Compare** tab | "Same request to a plain LLM. It names real, popular things, but only three of its twelve picks go beyond what members already said, none has a data-backed reason, and it can't measure who the plan serves. Every Qloo pick is new and explained." |
| 0:36 | Back to **Brief**, scroll to **Something for everyone** | "Does every member get something made for them? The group answer stands out for only two of the eight. So we ask Qloo about each member on their own and keep a result that also fits the group: here is Ada's, with the reason. Every member has a pick made for them; the Compare tab counts honestly that two stand out and eight have a personal pick." |
| 0:46 | On **Brief**, point at the venue section; then tap **More hidden gems** | "The venue is a top pick for the group, and next to it the cheapest option from the same Qloo results, with its price level. Now I tell the agent what to change: it re-runs only music, sponsors and content, and I can undo it." (The refinement takes 20 to 40 seconds.) |
| 0:54 | Landing, **See a live room** | "And members don't have to be typed in: this is an invite room. One link, members add their picks on their phones, and the plan builds from their answers. TasteRoom: plan events from real taste data." |

**If asked live:** the build step uses the agent for 40 to 60 seconds, which is why the examples are precomputed. The per-visitor limit is 5 live
plans an hour (refinements count toward it) to control cost.

# Judging criteria map

| Criterion | Where it shows |
|---|---|
| Technological implementation | Multi-endpoint Qloo use (search, entities, locality, insights, tags, explainability), parameter whitelist, live-verified findings, tool-calling agent with trace, deterministic fallback and scoped refinement, grounding validator, rooms with hashed tokens, a hardened Discord integration, 216 + 34 tests |
| Design | One flow (Collect or Builder, Results, Refine, Share), guided prompts with live autocomplete, real Qloo images, loading and error states everywhere, responsive and accessible, CSP |
| Potential impact | A specific user (whoever hosts a group get-together: friends, family, teams, communities), a specific pain (guessing, and quiet people never heard), a concrete output (a brief they can refine, share, poll and post) |
| Quality of the idea | Group taste fusion, per-pick explanations, a coverage check that says whose taste a plan serves, and a comparison that measures what Qloo adds rather than asserting it |
