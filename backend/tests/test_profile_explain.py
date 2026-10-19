from app.explain import explain, shared_tags
from app.models import ResolvedTaste, SlimEntity
from app.profile import build_profile


def ent(name, type="artist", tags=(), id=None):
    return SlimEntity(
        id=id or name.upper(), name=name, type=f"urn:entity:{type}",
        tags=[t.title() for t in tags], tag_ids=[f"urn:tag:genre:{t}" for t in tags],
    )


def resolved(member, e):
    return ResolvedTaste(member=member, input=e.name, entity=e)


def make_profile():
    burna = ent("Burna Boy", tags=["afrobeats", "rap"])
    tems = ent("Tems", tags=["afrobeats", "rnb"])
    nike = ent("Nike", "brand", tags=["footwear"])
    show = ent("Money Heist", "tv_show", tags=["heist"])
    return build_profile([
        resolved("Ada", burna), resolved("Ada", tems), resolved("Ada", nike),
        resolved("Tunde", burna), resolved("Tunde", show),
        ResolvedTaste(member="Seun", input="???", entity=None),
    ]), (burna, tems, nike, show)


def test_profile_weights_and_members():
    p, (burna, *_ ) = make_profile()
    assert p.members == ["Ada", "Tunde", "Seun"]  # unresolved-only member is still listed
    assert p.entities[burna.id].weight == 2 and p.entities[burna.id].members == ["Ada", "Tunde"]
    assert p.ids()[0] == burna.id  # shared first


def test_profile_member_naming_twice_counts_once():
    e = ent("X")
    p = build_profile([resolved("A", e), resolved("A", e)])
    assert p.entities[e.id].weight == 1


def test_ids_cap_round_robin_and_type_fallback():
    es = [ent(f"E{i}") for i in range(12)]
    rs = [resolved("A", e) for e in es[:6]] + [resolved("B", e) for e in es[6:9]] + [resolved("C", e) for e in es[9:]]
    p = build_profile(rs)
    ids = p.ids(cap=6)
    owners = {m for i in ids for m in p.entities[i].members}
    assert len(ids) == 6 and owners == {"A", "B", "C"}  # every member represented
    brand_only = build_profile([resolved("A", ent("Nike", "brand"))])
    assert brand_only.ids(types={"artist"}) == [brand_only.ids()[0]]  # empty filter falls back to all


def test_ids_type_filter_excludes_brands():
    p, (burna, tems, nike, show) = make_profile()
    ids = p.ids(types={"artist", "tv_show"})
    assert nike.id not in ids and show.id in ids


def test_shared_tags_ignore_generic_and_rank_by_spread():
    p, _ = make_profile()
    result = SlimEntity(
        id="R", name="R", type="urn:entity:artist",
        tags=["Afrobeats", "Loyal", "Heist", "Jazz"],
        tag_ids=["urn:tag:genre:afrobeats", "urn:tag:audience:qloo:loyal", "urn:tag:genre:heist", "urn:tag:genre:jazz"],
    )
    assert shared_tags(result, p) == ["Afrobeats", "Heist"]  # afrobeats shared by 2 entities, jazz by none


def test_native_explanation_uses_lift_not_entity_count():
    p, (burna, tems, nike, show) = make_profile()
    signal = [burna.id, tems.id, show.id]
    # Qloo gives a uniform split: Ada owns 2 of 3 entities (burna shared), Tunde owns burna + show.
    r = SlimEntity(id="R", name="R", type="urn:entity:artist", tags=["Afrobeats"], tag_ids=["urn:tag:genre:afrobeats"],
                   explain={burna.id: 1 / 3, tems.id: 1 / 3, show.id: 1 / 3})
    rec = explain(r, "music", p, signal)
    assert rec.explanation_method == "qloo_explainability"
    scores = {c.member: c.score for c in rec.why}
    assert abs(sum(scores.values()) - 1) < 0.01
    assert abs(scores["Ada"] - scores["Tunde"]) < 0.01  # uniform Qloo split -> equal lift
    assert rec.why[0].via and rec.shared_tags == ["Afrobeats"]


def test_native_explanation_rewards_real_extra_pull():
    p, (burna, tems, nike, show) = make_profile()
    signal = [burna.id, tems.id, show.id]
    r = SlimEntity(id="R", name="R", type="urn:entity:artist",
                   explain={burna.id: 0.1, tems.id: 0.8, show.id: 0.1})  # tems (Ada only) dominates
    scores = {c.member: c.score for c in explain(r, "music", p, signal).why}
    assert scores["Ada"] > scores["Tunde"]


def test_fallback_tag_overlap_when_no_explainability():
    p, _ = make_profile()
    r = SlimEntity(id="R", name="R", type="urn:entity:artist", tags=["Afrobeats"], tag_ids=["urn:tag:genre:afrobeats"])
    rec = explain(r, "music", p)
    assert rec.explanation_method == "tag_overlap"
    assert {c.member for c in rec.why} == {"Ada", "Tunde"} and abs(sum(c.score for c in rec.why) - 1) < 0.01
    assert "Burna Boy" in rec.why[0].via


def test_no_signal_no_fabricated_reason():
    p, _ = make_profile()
    r = SlimEntity(id="R", name="R", type="urn:entity:artist", tags=["Jazz"], tag_ids=["urn:tag:genre:jazz"])
    rec = explain(r, "music", p)
    assert rec.why == [] and rec.shared_tags == []
