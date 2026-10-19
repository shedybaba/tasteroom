import pytest

from app.allowed_params import ARTIST, PLACE, clean_params


def test_drops_unknown_and_none():
    cleaned, dropped = clean_params(
        {"filter.type": ARTIST, "take": 5, "filter.location": "x", "typo.param": 1, "offset": None}
    )
    assert cleaned == {"filter.type": ARTIST, "take": "5"}
    assert set(dropped) == {"filter.location", "typo.param"}  # location is place-only


def test_lists_and_bools_serialised():
    cleaned, _ = clean_params(
        {"filter.type": PLACE, "signal.interests.entities": ["A", "B"], "feature.explainability": True}
    )
    assert cleaned["signal.interests.entities"] == "A,B"
    assert cleaned["feature.explainability"] == "true"


def test_place_params_allowed_for_place():
    cleaned, dropped = clean_params({"filter.type": PLACE, "filter.location": "LOC", "filter.price_level.max": 2})
    assert not dropped and cleaned["filter.location"] == "LOC"


def test_known_non_working_params_are_dropped():
    _, dropped = clean_params({"filter.type": PLACE, "filter.price_range.max": 2, "filter.exists": "properties.image"})
    assert set(dropped) == {"filter.price_range.max", "filter.exists"}


def test_test_mode_lets_unverified_through():
    cleaned, dropped = clean_params({"filter.type": ARTIST, "filter.exists": "properties.image"}, test_mode=True)
    assert "filter.exists" in cleaned and not dropped


def test_unsupported_type_rejected():
    with pytest.raises(ValueError):
        clean_params({"filter.type": "urn:entity:music"})
    with pytest.raises(ValueError):
        clean_params({"take": 5})
