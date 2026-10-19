import asyncio

from app.models import Member, SlimEntity, Taste
from app.qloo_client import QlooClient, QlooError
from app.resolve import MIN_SIMILARITY, pick_best, resolve_city, resolve_members, similarity


def ent(name, pop=0.5, id=None, type="urn:entity:artist"):
    return SlimEntity(id=id or name.upper(), name=name, type=type, popularity=pop)


def test_similarity_basics():
    assert similarity("burna boy", "Burna Boy") == 1.0
    assert similarity("Tems", "TEms") == 1.0
    assert similarity("Nike", "Nike Training Club") >= 0.85
    assert similarity("Beyoncé", "Beyonce") == 1.0  # accents folded
    assert similarity("Burna Boy", "Fall Out Boy") < MIN_SIMILARITY + 0.2


def test_pick_best_prefers_similarity_then_popularity():
    got = pick_best("Burna Boy", [ent("Fall Out Boy", 0.99), ent("Burna Boy", 0.9), ent("Burna Boy & X", 0.99)])
    assert got.name == "Burna Boy"
    tie = pick_best("Drake", [ent("Drake", 0.5, "A"), ent("Drake", 0.9, "B")])
    assert tie.id == "B"


def test_pick_best_none_when_nothing_close():
    assert pick_best("Zzyzx Qwerty", [ent("Burna Boy"), ent("Wizkid")]) is None


def test_resolve_members_with_mock_client():
    c = QlooClient(api_key="", mock=True)
    members = [
        Member(name="A", tastes=[Taste(text="Burna Boy", kind="artist"), Taste(text="Nike", kind="brand")]),
        Member(name="B", tastes=[Taste(text="burna boy", kind="artist"), Taste(text="Qwxzv Nonsense", kind="artist")]),
    ]
    out = asyncio.run(resolve_members(c, members))
    assert [r.member for r in out] == ["A", "A", "B", "B"]
    assert out[0].entity and out[0].entity.name == "Burna Boy"
    assert out[0].entity.id == out[2].entity.id  # same entity named by two members
    assert out[3].entity is None  # unresolved is kept, not dropped


def test_qloo_error_leaves_taste_unresolved():
    class Boom(QlooClient):
        async def search(self, *a, **k):
            raise QlooError(500, "down")

    out = asyncio.run(resolve_members(Boom(api_key="", mock=True), [Member(name="A", tastes=[Taste(text="x")])]))
    assert out[0].entity is None


def test_resolve_city_mock_and_empty():
    c = QlooClient(api_key="", mock=True)
    assert asyncio.run(resolve_city(c, "Lagos")).name == "Lagos"
    assert asyncio.run(resolve_city(c, "  ")) is None


def test_dissimilar_lengths_do_not_match():
    assert pick_best("Kenshi Yonezu", [ent("Kenshin")]) is None
    assert pick_best("Kenshi Yonezu", [ent("Kenshi")]) is None
    assert pick_best("Wiz kid", [ent("Wizkid")]) is not None  # a typo still matches
