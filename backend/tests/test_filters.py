from app.filters import DAY_RE, decide_hidden_gems, venue_filters, venue_kind_from_goal
from app.models import PlanOptions


def test_weekday_must_be_a_whole_word():
    assert not DAY_RE.search("Friends meetup at the sunset market, month end")  # "fri", "sun", "mon" inside other words
    assert DAY_RE.search("Saturday launch party").group(1).lower() == "saturday"
    assert DAY_RE.search("every Fridays social") is not None


def test_nothing_applies_for_a_vague_goal():
    a = venue_filters("our next thing", PlanOptions(), {"venue_kind": "bar", "day": "monday", "price_level_max": 1, "hidden_gems": True})
    assert a.args == {} and a.inferred == []
    assert set(a.ignored) == {"venue_kind", "day", "price_level_max", "hidden_gems"}


def test_form_beats_goal_and_is_not_labelled_inferred():
    a = venue_filters("Saturday bar night, cheap", PlanOptions(venue_kind="park", day="Sunday", price_level_max=3), {})
    assert a.args == {"venue_kind": "park", "day": "sunday", "price_level_max": 3} and a.inferred == []


def test_goal_implications_are_labelled_inferred():
    a = venue_filters("Saturday rooftop bar night on a budget", PlanOptions(), {"price_level_max": 1})
    assert a.args == {"venue_kind": "bar", "day": "saturday", "price_level_max": 1}
    assert set(a.inferred) == {"venue_kind", "day", "price_level_max"}


def test_price_from_goal_is_a_sane_ceiling():
    assert venue_filters("cheap drinks", PlanOptions(), {"price_level_max": 4}).args["price_level_max"] == 2  # 4 is not a budget
    assert venue_filters("cheap drinks", PlanOptions(), {}).args["price_level_max"] == 2
    assert "price_level_max" not in venue_filters("luxury launch", PlanOptions(), {"price_level_max": 1}).args  # not a ceiling


def test_venue_kind_from_goal():
    assert venue_kind_from_goal("coffee and code") == "cafe"
    assert venue_kind_from_goal("Sunday brunch") == "restaurant"          # not "park" via "run" in "brunch"
    assert venue_kind_from_goal("Post-run social after the long run") == "bar"
    assert venue_kind_from_goal("launch party") == "lounge" and venue_kind_from_goal("quarterly review") is None


def test_venue_kind_for_friends_family_and_teams():
    assert venue_kind_from_goal("Saturday night out with friends") == "bar"
    assert venue_kind_from_goal("Family event") == "restaurant"
    assert venue_kind_from_goal("Mum's birthday") == "restaurant"
    assert venue_kind_from_goal("Team offsite") == "restaurant"
    assert venue_kind_from_goal("Team offsite dinner") == "restaurant"


def test_hidden_gems_rules():
    assert decide_hidden_gems("launch party", PlanOptions(), True) == (False, "")
    assert decide_hidden_gems("launch party", PlanOptions(hidden_gems=True), None) == (True, "form")
    assert decide_hidden_gems("find us underground acts", PlanOptions(), None) == (True, "goal")
