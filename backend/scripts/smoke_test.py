"""Phase 1 live checks (CLAUDE.md checklist). Run: cd backend && .venv/bin/python -m scripts.smoke_test

Saves trimmed raw responses to backend/samples/ and a compact summary to
samples/_smoke_summary.json. Never prints or stores the API key.
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.qloo_client import QlooClient  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
SAMPLES.mkdir(exist_ok=True)
ARTIST, BRAND, PLACE = "urn:entity:artist", "urn:entity:brand", "urn:entity:place"
PODCAST, TV, LOC = "urn:entity:podcast", "urn:entity:tv_show", "urn:entity:locality"
summary: dict[str, Any] = {}


def trim(body: Any, keep: int = 5) -> Any:
    """Shrink a response for committing: cap results, drop the heavy akas/short_descriptions."""
    def strip(o: Any) -> Any:
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k not in ("akas", "short_descriptions")}
        if isinstance(o, list):
            return [strip(v) for v in o[:25]]
        return o
    body = strip(body)
    if isinstance(body, dict):
        res = body.get("results")
        if isinstance(res, list):
            body["results"] = res[:keep]
        elif isinstance(res, dict):
            for k, v in res.items():
                if isinstance(v, list):
                    res[k] = v[:keep]
    return body


def save(name: str, body: Any) -> None:
    (SAMPLES / f"{name}.json").write_text(json.dumps(trim(body), indent=1, ensure_ascii=False))


def ents(body: Any) -> list[dict]:
    res = (body or {}).get("results", {}) if isinstance(body, dict) else {}
    if isinstance(res, list):
        return res
    return res.get("entities", []) if isinstance(res, dict) else []


def names(body: Any, n: int = 6) -> list[str]:
    return [e.get("name", "?") for e in ents(body)[:n]]


def note(key: str, **kv: Any) -> None:
    summary[key] = kv
    print(f"\n[{key}]")
    for k, v in kv.items():
        print(f"  {k}: {str(v)[:300]}")


async def ins(c: QlooClient, **p: Any):
    r = await c.request("/v2/insights", {k: v for k, v in p.items() if v is not None}, use_cache=False)
    return r


async def main() -> None:
    c = QlooClient(mock=False)
    if not c.api_key:
        sys.exit("No QLOO_API_KEY in .env: add it and rerun.")

    # 1. /search shape per type + tags present?
    ids: dict[str, str] = {}
    for label, q, t in [("artist", "Burna Boy", ARTIST), ("artist2", "Wizkid", ARTIST),
                        ("artist3", "Tems", ARTIST), ("brand", "Nike", BRAND),
                        ("podcast", "Call Her Daddy", PODCAST), ("tv_show", "Money Heist", TV)]:
        r = await c.request("/search", {"query": q, "types": t, "take": 3})
        es = ents(r.body)
        if es:
            ids[label] = es[0]["entity_id"]
        if label in ("artist", "brand", "podcast", "tv_show"):
            save(f"search_{label}", r.body)
        note(f"1.search.{label}", status=r.status, n=len(es), top=names(r.body, 3),
             tags_included=bool(es and es[0].get("tags")), entity_keys=list(es[0].keys()) if es else None)

    # 2. locality for 3+ cities
    for city in ["Lagos", "Abuja", "Ibadan", "Austin", "London"]:
        r = await c.request("/search", {"query": city, "types": LOC, "take": 3})
        es = ents(r.body)
        if city == "Lagos":
            save("search_locality", r.body)
            ids["lagos"] = es[0]["entity_id"] if es else ""
        note(f"2.locality.{city}", status=r.status, n=len(es),
             found=[(e["name"], e["entity_id"], e.get("properties", {}).get("admin_level")) for e in es])
        if city == "Abuja" and es:
            ids["abuja"] = es[0]["entity_id"]
        if city == "Austin" and es:
            ids["austin"] = es[0]["entity_id"]

    seed = ",".join([ids["artist"], ids["artist2"], ids["artist3"]])

    # 3. native explainability on artist, brand, place
    for t, extra in [(ARTIST, {}), (BRAND, {}), (PLACE, {"filter.location": ids["lagos"]})]:
        r = await ins(c, **{"filter.type": t, "signal.interests.entities": seed, "take": 5,
                            "feature.explainability": "true", **extra})
        es = ents(r.body)
        save(f"insights_{t.rsplit(':', 1)[-1]}", r.body)
        note(f"3.explainability.{t.rsplit(':', 1)[-1]}", status=r.status, n=len(es), names=names(r.body),
             top_level=bool((r.body.get("query") or {}).get("explainability")),
             per_entity=bool(es and (es[0].get("query") or {}).get("explainability")),
             entity_query=es[0].get("query") if es else None)
    for label, t in [("podcast", PODCAST), ("tv_show", TV)]:
        r = await ins(c, **{"filter.type": t, "signal.interests.entities": seed, "take": 5,
                            "feature.explainability": "true"})
        save(f"insights_{label}", r.body)
        note(f"3.explainability.{label}", status=r.status, n=len(ents(r.body)), names=names(r.body))

    # 4. entity weights
    base = await ins(c, **{"filter.type": ARTIST, "signal.interests.entities": seed, "take": 8,
                           "feature.explainability": "true"})
    for wval in ["10,1,1", "2", "very_high"]:  # per-entity list is rejected; a single value is accepted
        r = await ins(c, **{"filter.type": ARTIST, "signal.interests.entities": seed, "take": 8,
                            "signal.interests.entities.weight": wval})
        note(f"4.weights.{wval}", status=r.status, same_as_base=names(r.body, 8) == names(base.body, 8),
             error=(r.body.get("errors") or [{}])[0].get("message") if r.status != 200 else None)

    # 5. place: locality id vs geocode
    for label, extra in [("locality_id", {"filter.location": ids["lagos"]}),
                         ("geocode_name_cc", {"filter.geocode.name": "Lagos", "filter.geocode.country_code": "NG"}),
                         ("geocode_admin1_cc", {"filter.geocode.admin1_region": "Lagos", "filter.geocode.country_code": "NG"}),
                         ("location_query", {"filter.location.query": "Lagos, Nigeria"}),
                         ("abuja_locality", {"filter.location": ids.get("abuja", "")}),
                         ("austin_locality", {"filter.location": ids.get("austin", "")}),
                         ("austin_location_query", {"filter.location.query": "Austin, Texas"}),
                         ("no_location", {})]:
        r = await ins(c, **{"filter.type": PLACE, "signal.interests.entities": seed, "take": 5, **extra})
        note(f"5.place.{label}", status=r.status, n=len(ents(r.body)), names=names(r.body, 4))

    # 6. hidden gems
    def avg_pop(body: Any) -> float:
        p = [e.get("popularity", 0) or 0 for e in ents(body)]
        return round(sum(p) / len(p), 3) if p else -1
    a = await ins(c, **{"filter.type": ARTIST, "signal.interests.entities": seed, "take": 20})
    b = await ins(c, **{"filter.type": ARTIST, "signal.interests.entities": seed, "take": 20,
                        "filter.popularity.max": 0.7})
    note("6.popularity_max", avg_pop_without=avg_pop(a.body), avg_pop_with=avg_pop(b.body),
         max_pop_with=max([e.get("popularity", 0) or 0 for e in ents(b.body)] or [0]), n_with=len(ents(b.body)))

    # 7. /search types: repeated keys vs comma list
    import httpx
    for label, params in [("comma", {"query": "Nike", "types": f"{ARTIST},{BRAND}", "take": 5}),
                          ("repeated", {"query": "Nike", "types": [ARTIST, BRAND], "take": 5})]:
        r = await c.request("/search", params, use_cache=False)
        note(f"7.types.{label}", status=r.status, n=len(ents(r.body)),
             types_seen=sorted({t for e in ents(r.body) for t in e.get("types", [])}))

    # 8. /entities batch size, tags present
    big = await ins(c, **{"filter.type": ARTIST, "signal.interests.entities": seed, "take": 50})
    all_ids = [e["entity_id"] for e in ents(big.body)]
    for n in (1, 20, 50):
        r = await c.request("/entities", {"entity_ids": ",".join(all_ids[:n])}, use_cache=False)
        es = ents(r.body)
        if n == 20:
            save("entities", r.body)
        note(f"8.entities.{n}", status=r.status, asked=min(n, len(all_ids)), returned=len(es),
             tags_present=bool(es and es[0].get("tags")), body_keys=list(r.body.keys()) if isinstance(r.body, dict) else None)

    # 9/10. audiences: filter.query alone is exact-match-ish; list by parent type instead.
    r = await c.request("/v2/audiences", {"filter.parents.types": "urn:audience:leisure", "take": 20}, use_cache=False)
    save("audiences", r.body)
    res = r.body.get("results") if isinstance(r.body, dict) else None
    aud_list = res.get("audiences", []) if isinstance(res, dict) else (res or [])
    note("9.audiences", status=r.status, n=len(aud_list), names=[a.get("name") for a in aud_list[:8]],
         first_keys=list(aud_list[0].keys()) if aud_list else None)
    q = await c.request("/v2/audiences", {"filter.query": "gaming", "filter.parents.types": "urn:audience:hobbies_and_interests"}, use_cache=False)
    note("9.audiences.query_gaming", n=len((q.body.get("results") or {}).get("audiences", [])))
    if aud_list:
        mf = next((a for a in aud_list if "music" in a.get("name", "").lower()), aud_list[0])
        for label, val in [("urn_id", mf["id"]), ("entity_id", mf["entity_id"])]:
            w = await ins(c, **{"filter.type": ARTIST, "signal.interests.entities": seed, "take": 8,
                                "signal.demographics.audiences": val})
            note(f"10.audience_signal.{label}", audience=mf["name"], status=w.status,
                 changed=names(w.body, 8) != names(a.body, 8), with_aud=names(w.body, 4), without=names(a.body, 4))

    # 11. pagination
    p1 = await ins(c, **{"filter.type": ARTIST, "signal.interests.entities": seed, "take": 50})
    p2 = await ins(c, **{"filter.type": ARTIST, "signal.interests.entities": seed, "take": 50, "offset": 50})
    p3 = await ins(c, **{"filter.type": ARTIST, "signal.interests.entities": seed, "take": 10, "page": 2})
    s1 = {e["entity_id"] for e in ents(p1.body)}
    note("11.pagination", take50=len(s1), offset50=len(ents(p2.body)),
         overlap_offset=len(s1 & {e["entity_id"] for e in ents(p2.body)}),
         page2_take10=len(ents(p3.body)), page2_overlap=len(s1 & {e["entity_id"] for e in ents(p3.body)}))

    # 12. image filters
    def with_img(body: Any) -> str:
        es = ents(body)
        n = sum(1 for e in es if (e.get("properties") or {}).get("image") or (e.get("properties") or {}).get("images"))
        return f"{n}/{len(es)}"
    for t, extra in [(ARTIST, {}), (PLACE, {"filter.location": ids["lagos"]})]:
        t_s = t.rsplit(":", 1)[-1]
        plain = await ins(c, **{"filter.type": t, "signal.interests.entities": seed, "take": 20, **extra})
        for pname, pval in [("filter.exists", "properties.image"), ("filter.external.exists", "spotify" if t == ARTIST else "tripadvisor")]:
            r = await ins(c, **{"filter.type": t, "signal.interests.entities": seed, "take": 20, pname: pval, **extra})
            note(f"12.exists.{t_s}.{pname}", status=r.status, images_plain=with_img(plain.body),
                 images_filtered=with_img(r.body), n_plain=len(ents(plain.body)), n_filtered=len(ents(r.body)))

    # 13. per-member affinity with filter.results.entities
    group = await ins(c, **{"filter.type": ARTIST, "signal.interests.entities": seed, "take": 10})
    top_ids = ",".join(e["entity_id"] for e in ents(group.body))
    out = {}
    for label in ("artist", "artist2", "artist3"):
        r = await ins(c, **{"filter.type": ARTIST, "signal.interests.entities": ids[label],
                            "filter.results.entities": top_ids, "take": 10})
        es = ents(r.body)
        out[label] = [(e["name"], round((e.get("query") or {}).get("affinity", -1), 3)) for e in es[:4]]
        if label == "artist":
            save("insights_member_affinity", r.body)
    note("13.per_member_affinity", n_group=len(ents(group.body)), per_member=out)

    # 14. tags
    for kw in ["bar", "lounge", "event venue", "restaurant", "nightclub", "park"]:
        r = await c.request("/v2/tags", {"filter.query": kw, "take": 5}, use_cache=False)
        if kw == "bar":
            save("tags", r.body)
        res = r.body.get("results") if isinstance(r.body, dict) else None
        tags = res.get("tags", []) if isinstance(res, dict) else (res or [])
        note(f"14.tags.{kw}", status=r.status, n=len(tags), first=tags[:3],
             body_head=str(r.body)[:300] if not tags else "")

    # Extras: tag filter on places, price/op param spellings
    lag = ids["lagos"]
    plain = await ins(c, **{"filter.type": PLACE, "signal.interests.entities": seed, "filter.location": lag, "take": 20})
    r = await c.request("/v2/tags", {"filter.query": "bar", "take": 5}, use_cache=False)
    res = r.body.get("results") if isinstance(r.body, dict) else None
    tags = res.get("tags", []) if isinstance(res, dict) else (res or [])
    place_tag = next((t.get("id") or t.get("tag_id") for t in tags if "place" in str(t).lower() or "venue" in str(t).lower()), None) \
        or (tags[0].get("id") if tags else None)
    if place_tag:
        r2 = await ins(c, **{"filter.type": PLACE, "signal.interests.entities": seed, "filter.location": lag,
                             "filter.tags": place_tag, "take": 10})
        note("X.place_tag_filter", tag=place_tag, status=r2.status, n=len(ents(r2.body)), plain_n=len(ents(plain.body)),
             names=names(r2.body, 4), plain_names=names(plain.body, 4))
    for pname, pval in [("filter.price_level.max", 2), ("filter.price_range.to", 2), ("filter.price_range.max", 2),
                        ("filter.hours", "saturday"), ("bias.quality", "1"), ("sort_by", "distance")]:
        r = await ins(c, **{"filter.type": PLACE, "signal.interests.entities": seed, "filter.location": lag,
                            "take": 10, pname: pval})
        note(f"X.place_param.{pname}", status=r.status, n=len(ents(r.body)),
             same_as_plain=names(r.body, 10) == names(plain.body, 10), names=names(r.body, 4))

    (SAMPLES / "_smoke_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    await c.aclose()
    print("\nDone. Samples in backend/samples/, summary in samples/_smoke_summary.json")


if __name__ == "__main__":
    asyncio.run(main())
