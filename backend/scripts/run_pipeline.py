"""Phase 2 CLI: resolve -> profile -> recommend -> explain for one hard-coded community.
Run: cd backend && .venv/bin/python -m scripts.run_pipeline [--mock]
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import Member, PlanOptions, Taste  # noqa: E402
from app.profile import build_profile  # noqa: E402
from app.qloo_client import QlooClient  # noqa: E402
from app.recommend import recommend, recommend_venues  # noqa: E402
from app.resolve import resolve_city, resolve_members  # noqa: E402


def m(name: str, *tastes: str) -> Member:
    """'Burna Boy:artist' -> typed taste; plain text -> kind 'any'."""
    out = []
    for t in tastes:
        text, _, kind = t.partition(":")
        out.append(Taste(text=text, kind=kind or "any"))  # type: ignore[arg-type]
    return Member(name=name, tastes=out)


COMMUNITY = {
    "city": "Lagos",
    "members": [
        m("Ada", "Burna Boy:artist", "Tems:artist", "Black Mirror:tv_show", "Nike:brand"),
        m("Tunde", "Wizkid:artist", "Burna Boy:artist", "Money Heist:tv_show", "Guaranty Trust Bank:brand"),
        m("Chioma", "Tems:artist", "Rema:artist", "Call Her Daddy:podcast", "Zara:brand"),
        m("Emeka", "Davido:artist", "Asake:artist", "Succession:tv_show", "Apple:brand"),
        m("Zainab", "Burna Boy", "Wizkid", "The Joe Budden Podcast:podcast", "Adidas:brand"),
        m("Seun", "Rema:artist", "Asake:artist", "Narcos:tv_show", "Nike:brand"),
    ],
}


async def main(mock: bool) -> None:
    client = QlooClient(mock=True if mock else None)
    print(f"Qloo mode: {'mock' if client.mock else 'live'}")
    t0 = time.perf_counter()
    members = COMMUNITY["members"]
    resolved, locality = await asyncio.gather(
        resolve_members(client, members), resolve_city(client, COMMUNITY["city"])
    )
    print(f"\nLocality: {locality.name if locality else None} ({locality.id if locality else '-'})")
    print("\nRESOLVED")
    for r in resolved:
        print(f"  {r.member:<8} {r.input:<28} -> {r.entity.name + ' [' + r.entity.type.rsplit(':', 1)[-1] + ']' if r.entity else '*** UNRESOLVED ***'}")
    profile = build_profile(resolved)
    shared = [(pe.entity.name, pe.weight) for pe in profile.entities.values() if pe.weight > 1]
    print(f"\nPROFILE: {len(profile.entities)} entities, up to {len(profile.ids())} sent as signal per query; shared by 2+ members: {shared}")

    opts = PlanOptions()
    results = await asyncio.gather(
        recommend(client, "music", profile, options=opts),
        recommend_venues(client, profile, locality=locality, city=COMMUNITY["city"], options=opts),
        recommend(client, "brands", profile, options=opts),
        recommend(client, "content", profile, options=opts),
    )
    for res in results:
        print(f"\n== {res.domain.upper()} ({len(res.recommendations)}) {res.warnings or ''}")
        for rec in res.recommendations:
            e = rec.entity
            who = ", ".join(f"{c.member} {c.score:.0%} (via {'/'.join(c.via)})" for c in rec.why[:3]) or "-"
            print(f"  {e.name[:38]:<38} {e.type.rsplit(':', 1)[-1]:<8} pop={e.popularity or 0:.2f} img={'Y' if e.image else 'N'}"
                  f" | {rec.explanation_method[:6]} | {who} | tags: {', '.join(rec.shared_tags[:3]) or '-'}")
    bad = [r.entity.name for res in results for r in res.recommendations if not r.why and not r.shared_tags]
    print(f"\nUnexplained results (no contributor and no shared tag): {bad or 'none'}  [{time.perf_counter() - t0:.1f}s]")
    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main("--mock" in sys.argv))
