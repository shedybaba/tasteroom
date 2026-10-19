from app.slim import slim_entity


def test_search_result_shape(sample):
    e = slim_entity(sample("search_artist")["results"][0])
    assert e.id == e.id.upper() and e.name == "Burna Boy"
    assert e.type == "urn:entity:artist"
    assert e.image and e.description
    assert e.tags and e.tag_ids and all(t.startswith("urn:tag:") for t in e.tag_ids)
    assert e.affinity is None and e.explain == {}


def test_audience_tags_listed_last(sample):
    e = slim_entity(sample("search_artist")["results"][0])
    assert e.tags[0] == "Rap"  # genre first, "Loyal"/"Passionate" afterwards


def test_insights_place_with_explainability(sample):
    raw = sample("insights_place")["results"]["entities"][0]
    e = slim_entity(raw)
    assert e.type == "urn:entity:place"  # from subtype, not the generic "urn:entity"
    assert e.address and e.image
    assert e.affinity and 0 < e.affinity <= 1
    assert e.explain and abs(sum(e.explain.values()) - 1) < 0.01  # shares of the score sum to 1
    assert all(k == k.upper() for k in e.explain)


def test_slim_is_much_smaller_than_raw(sample):
    import json
    raw = sample("search_locality")["results"][0]
    assert len(slim_entity(raw).model_dump_json()) < len(json.dumps(raw)) / 2


def test_every_saved_entity_sample_parses(sample):
    for name in ["search_artist", "search_brand", "search_podcast", "search_tv_show", "search_locality"]:
        for raw in sample(name)["results"]:
            assert slim_entity(raw).id
    for name in ["insights_artist", "insights_brand", "insights_place", "insights_podcast", "insights_tv_show"]:
        ents = sample(name)["results"]["entities"]
        assert ents and all(slim_entity(r).id for r in ents)
    assert sample("entities")["results"]
