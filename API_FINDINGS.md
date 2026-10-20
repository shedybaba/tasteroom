# API_FINDINGS.md: Qloo live test results (Phase 1, Oct 19 2026)

Produced by `backend/scripts/smoke_test.py` against `https://hackathon.api.qloo.com`. Rerun with
`cd backend && .venv/bin/python -m scripts.smoke_test`. Trimmed raw responses are in `backend/samples/`
(`_smoke_summary.json` has the full per-check results). Seed used for most checks: Burna Boy + Wizkid + Tems.

## Decisions (read this first)

| Question | Decision |
|---|---|
| **Explanation method** | **A: native.** `feature.explainability=true` works on artist, brand, place. Each result has `query.explainability["signal.interests.entities"] = [{entity_id, score}]` (shares of that result's score per input entity, sum to 1). Map input entity -> member(s) who named it. No per-member extra calls needed. Method C (shared tags) is still computed to enrich the text. Method B (per-member `filter.results.entities`) works but scores differ by only ~0.01-0.03 between members, so it is the fallback only. |
| **How to pass the city** | **Resolve with `/search` `types=urn:entity:locality`, pass the ID as `filter.location`.** Fallback: `filter.location.query="City, Region"` (works). `filter.geocode.name` + `country_code` (and `admin1_region`) returned **0 results**: do not use. **A location filter is mandatory:** with no filter, a Nigerian seed still returned Lagos venues (Qloo infers location from taste), so a US community would get Lagos venues. |
| **Demo city** | **Lagos** (`1B96428C-69B1-4035-8628-88CD552218CB`, admin_level 4): real venues (Lekki Leisure, EbonyLife Place, Radisson Blu, Palazzo Dumont, event centres). Abuja resolves to "Federal Capital Territory" with real places too. Austin and London also have data. Ibadan resolves (neighbourhood level). Use Lagos + one US city for the examples. |
| **Weighting** | **Client-side.** `signal.interests.entities.weight` takes ONE positive number or `very_low..very_high` for the whole group; a per-entity list (`10,1,1`) is a 400. Order entities by member count and cap at 25. |
| **List params** | Comma-joined works for `types`, `signal.interests.entities`, `entity_ids`. Repeated keys (`types=a&types=b`) also works. We use commas. |
| **Audiences** | Optional feature works but via `filter.parents.types` (e.g. `urn:audience:leisure`, `urn:audience:communities`). `filter.query=gaming` returns empty; `filter.query=music` returns "Music Festivals". Pass the audience **URN `id`** (e.g. `urn:audience:leisure:music_festivals`) to `signal.demographics.audiences`: it changes results. The `entity_id` form is **silently ignored**. |
| **Images** | Every artist and place result in the tests had an image, so no image filter is needed. `filter.exists` / `filter.external.exists` had no observable effect: not used. |

## Results per checklist item

| # | Check | Result |
|---|---|---|
| 1 | `/search` per type | VERIFIED. artist/brand/podcast/tv_show all 200. Tags **are included**. Shape: `{results:[{name, entity_id, types:[..], properties:{image:{url}, short_description, external}, popularity, tags:[{name, tag_id, type, value}]}]}`. Fuzzy: "Tems" returned "TEms" (1 result); "Burna Boy" top hit exact. |
| 2 | Locality search | VERIFIED. Lagos, Abuja, Ibadan, Austin, London all resolve. Top hit may be a state/region (Lagos = admin_level 4, Abuja = "Federal Capital Territory"); multiple "Lagos"/"Austin" exist, take the first. Responses are huge (up to ~250 KB: `akas`), so slim + cache. |
| 3 | `feature.explainability` | VERIFIED on artist, brand, place (top-level `query.explainability` aggregate AND per-entity `query.explainability`). Podcast and tv_show calls returned results, but no explainability was checked there beyond the same parameter being accepted. |
| 4 | Entity weights | NOT WORKING per entity (400, message: must be a positive number or label). Single value accepted but cannot differentiate entities. Decision: client-side weighting. |
| 5 | City filter | `filter.location=<locality id>` VERIFIED (Lagos, Abuja, Austin each return in-city places). `filter.location.query` VERIFIED for Austin (changes results). `filter.geocode.*` NOT WORKING (0 results). `filter.location.radius` had no visible effect with a locality ID. |
| 6 | `filter.popularity.max=0.7` | VERIFIED. Mean popularity 0.82 -> 0.59, max 0.69. Powers "hidden gems". |
| 7 | `/search` `types` | Comma list and repeated keys both work. |
| 8 | `/entities` batch | VERIFIED 1, 20 and 50 IDs; tags included. Response `{results:[...]}`. |
| 9 | `/v2/audiences` | VERIFIED with caveats above. Shape `{results:{audiences:[{entity_id, id, name, type, parents, tags}]}}`. `parents.types` lists: leisure (11), communities (4: AAPI, Latino, LGBTQ, Black), global_issues (11), hobbies_and_interests (20). |
| 10 | Audience signal | VERIFIED with URN id: "Music Festivals" changed the top artists. |
| 11 | Pagination | VERIFIED. `take=50`, `offset=50` gives 50 non-overlapping results; `page=2&take=10` works. |
| 12 | Image filters | No effect observable (all results already had images). Skipped. |
| 13 | Per-member affinity | Works: `filter.results.entities=<ids>` + one member's entities gives `query.affinity` per result. Differences between members are tiny (0.94-0.98), so native explainability (A) is better. |
| 14 | `/v2/tags` | VERIFIED. `filter.query=<kw>` (not `query`). Shape `{results:{tags:[{id, name, type, parents, popularity}]}}`. Usable IDs: `urn:tag:genre:place:restaurant:bar` (Bar), `urn:tag:genre:place:lounge`, `urn:tag:category:place:event_venue`, `urn:tag:dining_option:qloo:nightclub`, `urn:tag:genre:place:park`. `filter.tags=<bar id>` on places in Lagos changed results (bar/lounge venues appear). |

## Venue filter parameters (extras)

| Param | Result |
|---|---|
| `filter.price_level.max=2` | WORKS (changes results) |
| `filter.price_range.to` | Works (changes results; `.from` is the pair) |
| `filter.price_range.min/max` | NOT WORKING: silently ignored. Removed from the whitelist. |
| `filter.hours=saturday` | Changes results; semantics unclear (some odd hits, e.g. a church). Use with care; label it as best-effort. |
| `bias.quality` | `true` is a 400; numeric/label values (`1`, `0.5`, `high`) accepted and push toward hotels. Not used. |
| `sort_by=distance` | Changes results |
| `filter.tags=<place tag id>` | WORKS |

## Other observations
- Insights response shape: `{success, results:{entities:[...]}, query:{explainability:{...}}}`. Entities have `type:"urn:entity"` and `subtype:"urn:entity:place"`; places carry `properties.address`, `images[]`, `website`, `keywords`, `hours`, `geocode`, `locality`.
- Cross-domain taste transfer is loose: a Nigerian-music seed gave Nigerian brands (GTBank, Pulse Ng) and venues, but generic US podcasts/TV (Joel Osteen Podcast, "For Life"). Content picks will look better when members name shows/podcasts too; the examples should include them.
- Errors come back as `{"errors":[{"message", "path"}]}` (400). Unknown params are silently ignored, which is why `allowed_params.py` exists.
- Qloo may also infer location from taste when no location filter is given (see decisions).
- No 429s occurred in ~150 calls with a concurrency cap of 6.

## Phase 2 findings (resolve / profile / recommend / explain)

- **Signal composition matters a lot** (same community, Lagos, 17 resolved entities). Sending everything
  gave global/luxury results (Drake-adjacent artists, Mercedes, Lamborghini, spas and hotels). Measured per domain:
  - music, venues, content: signal = every entity **except brands** -> Afrobeats artists, lounges/bars, relevant podcasts.
  - brands: signal = **artists + brands** -> Nigerian sponsors (Pulse Ng, GTBank-type banks, MTN, TECNO). Adding shows/podcasts drifts to Tesla/Mercedes.
  - If the filtered set is empty (e.g. only brands named), all entities are used.
  Implemented in `recommend.SIGNAL_TYPES` and `Profile.ids(types=...)`.
- **Qloo's explainability split is nearly uniform** (e.g. 0.34 / 0.34 / 0.32 across three inputs), so raw member
  shares mostly reflect how many tastes a member listed. `explain.py` divides each member's share by the share their
  entity count alone predicts ("lift") and normalises; `via` lists the member's entities sharing the most tags with the result.
  Result: most picks read as "A crowd-pleaser: fits all N members" (about 20% each for 5-6 members), and a higher score means a real extra pull. This is honest, not a bug.
- **`/search` type spelling:** `urn:entity:videogame` (no underscore); an untyped retry that includes `video_game` is a 400.
  Allowed `/search` types: actor, album, artist, author, book, brand, destination, director, locality, movie, person, place, podcast, tv_show, videogame, urn:demographics, urn:tag.
- **Untyped retry** only searches content types (never locality/person/audience) so "Burna Boy" cannot resolve to something odd.
- **Venues** from a music-heavy community are a mix of hotels and lounges; the agent should pass a `venue_kind` (bar, lounge, event venue) based on the event goal (Phase 3).
- **Venue shared tags are usually empty** (places and artists share few tag IDs); the Why panel for venues relies on member contributions.
- Resolution of the 24-taste Lagos test community: 24/24 resolved. Whole CLI run ~16 s cold, ~5 s warm cache.

## Phase 3 findings
- **`/search` `filter.location` takes `lat,lon` only** (a locality ID is a 400). So the Compare tab cannot ask Qloo "is this
  venue in Lagos" with a location filter; instead it searches the place by name and compares the result's own
  `properties.geocode.city` with the requested city (`SlimEntity.city`).
- Pipeline fallback was exercised live (expired OpenAI key): Qloo steps ran, the agent error was caught, a templated brief
  built only from Qloo results was returned (HTTP 200, ~11 s cold). Compare returns a friendly 503 when the LLM is down.
- OpenAI side (unverified against a live key): Responses API (`responses.create` for tool calls,
  `responses.parse(text_format=...)` for structured output), default models `gpt-6-luna` (agent loop) and `gpt-6.1-sol`
  (brief + baseline), taken from OpenAI's model docs; override with `OPENAI_MODEL_FAST` / `OPENAI_MODEL_SMART`.

## Phase 8 Part B findings (guided input: suggest + ideas)

- **`/v2/insights` works with no taste signal.** `filter.type` + `filter.popularity.min=0.9` + `take=8` returns the most
  popular entities (popularity about 1.0, all with images) for artist, tv_show, movie, brand, podcast and place. Used for the
  "Need ideas?" chips. Artists skew to a fixed rock-heavy list (Coldplay, Radiohead...), so the UI shows a rotating window
  of 4 per member rather than the same four everywhere.
- **Places without a location are useless as ideas** (Golden Gate Bridge, Arc de Triomphe). With a locality ID the results
  are popular but mostly hotels and a university. **A union of hangout tags gives real spots**:
  `filter.tags=urn:tag:genre:place:restaurant:bar,urn:tag:genre:place:lounge,urn:tag:genre:place:restaurant` (comma list
  behaves as a union): Lagos (Terra Kulture, Lekki Leisure, Farmcity Lekki lounge), Austin (Franklin Barbecue, Mohawk,
  Wonder Bar), London (Sky Garden, Duck & Waffle). `popularity.min=0.9` is thin for the `lounge` tag alone (1 to 3 results in
  Lagos/Austin), so place ideas retry at 0.7 when fewer than 4 come back. With no city the route returns nothing and the UI asks for one.
- **`/entities` as the resolver for picked suggestions.** A member who picks an autocomplete result gives us the Qloo entity id,
  so the plan fetches all picked entities in batches of 50 instead of searching per taste: for a 14-taste community the resolve
  step took 0.9 s (a typed community of similar size takes about 10 s cold). Unknown ids fall back to a text search.
- **Qloo `/search` is global**, so venue autocomplete over-fetches (15) and floats results whose own `geocode.city` matches the
  organizer's city to the top.
- `/api/suggest` and `/api/ideas` share a per-IP bucket (`RATE_LIMIT_SUGGEST`, default 60/minute), separate from the plan quota,
  and are cached by the client for 24 h (a repeated identical lookup does not reach Qloo; tested).

## Phase 8 Part D findings (refine with the agent)

How each quick refinement maps onto Qloo (all measured live on the Lagos Creators example):

| Request | Qloo mechanism | Measured |
|---|---|---|
| Cheaper venue | `filter.price_level.max` (lowered one level per request, 2 by default) | venues re-queried, 3 of 3 brief picks swapped |
| More hidden gems | `filter.popularity.max`: **0.7 for music/content/venues, 0.9 for brands** | music 10/10 results new at 0.7 (avg popularity 0.89 -> 0.56: DJ Tunez, Lojay, Cruel Santino...). Brands at 0.7 turn to noise (avg 0.38: Vskit, Antonio Banderas); at 0.9 the mega-brands drop out (Chelsea, Real Madrid) and local ones stay (Wakanow, Boomplay Music, WorldRemit) |
| Swap the music vibe: more chill | `/v2/tags?filter.query=chill` then `filter.tags=<ids>` on the artist query | Mood tags exist under several taxonomies and **some are empty**: `urn:tag:genre:music:chill` returns 0 artists, `urn:tag:style:qloo:relaxed` and `urn:tag:genre:music:mellow` return 10 mostly new ones (Jhene Aiko, The Internet, Khalid for "relaxed"). The tag tool prefers `style:qloo` / `music:qloo` ids, and recommend tries all tags together, then each alone, and falls back to the standard picks |
| Add a watch-party content theme | the content domain (podcast + tv_show insights) with the community signal | adds the domain, nothing else changes |
| Different neighbourhood | venue results carry `properties.locality.neighborhood {name, entity_id}`; **a neighbourhood's entity id works as `filter.location`** | Victoria Island 11 venues, Ikoyi 11, Maroko 6, Oregun 3 of the top 50; filtering by each id returned 10 venues in that area |

Design consequences:
- The agent is restricted in code to the domains the request can touch (a keyword classifier maps the request to domains;
  free text it cannot map leaves the agent free to decide). Out-of-scope tool calls are refused and never appear in the trace.
- Untouched sections of the brief are restored verbatim from the previous version after the LLM rewrite.
- If Qloo returns the same picks, the user is told "Nothing changed" and no version is saved (no wasted brief rewrite).
- A free-text request is genuinely agentic: for "make it feel more like a family reunion" the agent tried the tag "family reunion"
  (0 tags), then "family" (1 tag), applied it to music only, and left everything else alone.
- Plans and their versions are stored in SQLite next to invite rooms (on the volume), so versions and /plan/<id> links survive redeploys
  (pruned after 30 days). The disk cache stays as the fast path.

## Coverage ("something for everyone"), measured on the three saved examples
- A pick "stands out" for a member at >= 1.15x an even share (the Why-panel bar). Only about 6% of member-pick cells reach it,
  because Qloo's explainability scores are close to uniform. So on the examples, 1 of 8 (Lagos), 0 of 7 (Pixel Pact) and 0 of 7
  (Sunrise Run Club) members have a brief pick that stands out for them; the rest are served by crowd-pleasers.
- The score is hypersensitive to the bar: pixel-pact goes 0/7 (1.15x) -> 1/7 (1.10x) -> 3/7 (1.08x) -> 7/7 (1.05x). We keep 1.15x
  (consistent with the UI and the brief wording) instead of tuning it until the number looks good.
- Some members have no result that stands out anywhere in Qloo's list (pixel-pact Kai: strongest pull 1.08x). The card says so and
  suggests adding more of their tastes; it never invents a swap. "Balance the lineup" only uses results that stand out >= 1.15x.

## Personal picks (a query per member), measured on the three saved examples
- **`filter.results.entities` scores any candidate against a signal.** With the group's signal plus a list of candidate ids it returns those
  candidates with their group-level `query.affinity` (comma-separated ids, 40 per call used). Candidates it cannot score are absent, never guessed.
  Qloo never returns an entity that is part of the signal, so it also drops anything a member named; personal picks exclude those on purpose.
- **Affinity is compressed.** The group's top 10 average about 0.94, rank 50 is about 0.92; a candidate at 0.85 is already "far". So "close to the
  group average" has to be a ratio to that average, not an absolute number.
- **Member-only queries mostly overlap the group's results.** A member's own top 20 (music) has 5 to 8 results in the group's top 10 for most
  members, but 0 for some (Kelechi in Lagos; Jonas and Tessa in Pixel Pact have 0 of the group's top 50).
- **Rule used:** the first of a member's top 10 new results that is one of the group's results OR has group affinity >= 95% of the group's average
  (an arbitrary round number). **It is not what decides the outcome:** at 90%, 95% and 97% every member of every example still gets a personal
  pick (Jonas and Tessa through shows/podcasts, not music), because each member's top 10 contains something that fits.
- **Result:** 8 of 8 (Lagos), 7 of 7 (Pixel Pact), 7 of 7 (Sunrise) members have a personal pick, versus 1, 0 and 0 with a pick that *stands out*
  (the strict 1.15x rule, unchanged). 16 of the 27 personal picks (59%) are results the group query also returned, so a "personal" pick is often
  also a crowd-pleaser; the card says which ("it is #2 in the group's music results"). Both numbers are reported, never merged.
