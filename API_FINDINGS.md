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
