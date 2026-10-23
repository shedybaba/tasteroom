"""Pre-loaded examples: friends, a team and three communities. Their full results are precomputed (scripts/precompute_examples.py)
and served from backend/precomputed/, so judges clicking them cost no API calls."""
from .models import Member, PlanRequest, Taste

KIND_WORDS = {"a": "artist", "t": "tv_show", "b": "brand", "p": "podcast", "g": "video_game", "m": "movie"}


def _m(name: str, *tastes: str) -> Member:
    """"Burna Boy|a" -> Taste(text="Burna Boy", kind="artist"). Suffix: a artist, t tv_show, b brand, p podcast, g video_game."""
    out = []
    for t in tastes:
        text, _, k = t.rpartition("|")
        out.append(Taste(text=text, kind=KIND_WORDS[k]))  # type: ignore[arg-type]
    return Member(name=name, tastes=out)


EXAMPLES: dict[str, dict] = {
    "saturday-crew": {
        "tagline": "Five friends planning a Saturday night out in Austin.",
        "request": PlanRequest(
            community_name="The Saturday Crew", city="Austin",
            event_goal="Saturday night out with 5 friends",
            members=[
                _m("Jo", "Tame Impala|a", "Phoebe Bridgers|a", "The Bear|t", "Patagonia|b"),
                _m("Maya", "Beyoncé|a", "SZA|a", "Abbott Elementary|t", "Sephora|b"),
                _m("Dev", "Khruangbin|a", "Leon Bridges|a", "Severance|t", "YETI|b"),
                _m("Lena", "Taylor Swift|a", "Noah Kahan|a", "Ted Lasso|t", "Trader Joe's|b"),
                _m("Theo", "Tyler, the Creator|a", "Kendrick Lamar|a", "Atlanta|t", "Nike|b"),
            ],
        ),
    },
    "team-atlas": {
        "tagline": "A seven-person team planning an offsite dinner in London.",
        "request": PlanRequest(
            community_name="Team Atlas", city="London",
            event_goal="Team offsite dinner for 7 colleagues",
            members=[
                _m("Priya", "Fred again..|a", "Jessie Ware|a", "Ted Lasso|t", "Monzo|b"),
                _m("Ben", "Arctic Monkeys|a", "Radiohead|a", "Peaky Blinders|t", "Nike|b"),
                _m("Chloe", "Dua Lipa|a", "RAYE|a", "Fleabag|t", "Pret A Manger|b"),
                _m("Idris", "Stormzy|a", "Dave|a", "Top Boy|t", "Adidas|b"),
                _m("Hannah", "Adele|a", "Coldplay|a", "The Great British Bake Off|t", "Waitrose|b"),
                _m("Sam", "Bicep|a", "Four Tet|a", "The Diary Of A CEO|p", "Spotify|b"),
                _m("Mo", "Little Simz|a", "Kano|a", "The Rest Is Football|p", "Apple|b"),
            ],
        ),
    },
    "lagos-creators": {
        "tagline": "A creator and tech community planning a Saturday mixer in Lagos.",
        "request": PlanRequest(
            community_name="Lagos Creators", city="Lagos",
            event_goal="Saturday evening creator mixer for 50 people",
            members=[
                _m("Ada", "Burna Boy|a", "Tems|a", "Black Mirror|t", "Nike|b"),
                _m("Tunde", "Wizkid|a", "Burna Boy|a", "Money Heist|t", "Guaranty Trust Bank|b"),
                _m("Chioma", "Tems|a", "Rema|a", "Call Her Daddy|p", "Zara|b"),
                _m("Emeka", "Davido|a", "Asake|a", "Succession|t", "Apple|b"),
                _m("Zainab", "Burna Boy|a", "Wizkid|a", "The Joe Budden Podcast|p", "Adidas|b"),
                _m("Seun", "Rema|a", "Asake|a", "Narcos|t", "Nike|b"),
                _m("Folake", "Ayra Starr|a", "Tems|a", "How I Built This|p", "Spotify|b"),
                _m("Kelechi", "Fela Kuti|a", "Kendrick Lamar|a", "The Last Dance|t", "Puma|b"),
            ],
        ),
    },
    "pixel-pact": {
        "tagline": "An anime and gaming Discord planning a watch party and game night in Austin.",
        "request": PlanRequest(
            community_name="Pixel Pact", city="Austin",
            event_goal="Anime watch party and game night for 30 members",
            members=[
                _m("Kai", "Attack on Titan|t", "Elden Ring|g", "Hikaru Utada|a", "Nintendo|b"),
                _m("Mina", "Demon Slayer|t", "Genshin Impact|g", "LiSA|a", "Crunchyroll|b"),
                _m("Jonas", "Cyberpunk: Edgerunners|t", "Hades|g", "Porter Robinson|a", "PlayStation|b"),
                _m("Priya", "Jujutsu Kaisen|t", "Baldur's Gate 3|g", "YOASOBI|a", "Nintendo|b"),
                _m("Omar", "One Piece|t", "The Legend of Zelda|g", "Hiroyuki Sawano|a", "Razer|b"),
                _m("Tessa", "Arcane|t", "League of Legends|g", "Imagine Dragons|a", "Red Bull|b"),
                _m("Diego", "Spy x Family|t", "Stardew Valley|g", "Nujabes|a", "Crunchyroll|b"),
            ],
        ),
    },
    "sunrise-run-club": {
        "tagline": "A London run club planning a post-run social after the Saturday long run.",
        "request": PlanRequest(
            community_name="Sunrise Run Club", city="London",
            event_goal="Post-run social after the Saturday long run, 35 people",
            members=[
                _m("Sam", "Fred again..|a", "Four Tet|a", "Strava|b", "The Rich Roll Podcast|p"),
                _m("Leah", "Jessie Ware|a", "Disclosure|a", "Lululemon|b", "Ted Lasso|t"),
                _m("Marcus", "Bicep|a", "Floating Points|a", "ASICS|b", "Formula 1: Drive to Survive|t"),
                _m("Ines", "Fred again..|a", "Jungle|a", "Hoka|b", "The Diary Of A CEO|p"),
                _m("Tom", "Four Tet|a", "Bonobo|a", "Nike|b", "Peaky Blinders|t"),
                _m("Aisha", "Jessie Ware|a", "Disclosure|a", "Garmin|b", "Lex Fridman Podcast|p"),
                _m("Joe", "Bicep|a", "Fred again..|a", "Adidas|b", "Ted Lasso|t"),
            ],
        ),
    },
}
