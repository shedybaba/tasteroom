import asyncio

from app.allowed_params import ARTIST, PLACE
from app.qloo_client import QlooClient


def run(coro):
    return asyncio.run(coro)


def test_mock_search_filters_by_query():
    c = QlooClient(api_key="", mock=True)
    found = run(c.search("Burna", ["urn:entity:artist"]))
    assert found and found[0].name == "Burna Boy"


def test_mock_locality_and_insights():
    c = QlooClient(api_key="", mock=True)
    assert run(c.find_locality("Lagos")).type == "urn:entity:locality"
    res = run(c.insights({"filter.type": PLACE, "signal.interests.entities": ["X"], "nope": 1}))
    assert res.entities and res.dropped_params == ["nope"]
    assert res.explainability  # top-level query.explainability preserved


def test_mock_other_endpoints():
    c = QlooClient(api_key="", mock=True)
    assert run(c.find_tags("bar"))[0]["id"].startswith("urn:tag:")
    assert run(c.find_audiences("x"))[0]["id"].startswith("urn:audience:")
    assert len(run(c.get_entities(["a"]))) > 0
    assert run(c.insights({"filter.type": ARTIST})).entities


def test_mock_mode_when_no_key():
    assert QlooClient(api_key="").mock is True
