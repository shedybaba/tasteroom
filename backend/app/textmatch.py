"""Name matching shared by taste resolution and city (locality) resolution."""
import re
import unicodedata
from difflib import SequenceMatcher

MIN_SIMILARITY = 0.75  # 0.6-0.7 let 'Kenshi Yonezu' resolve to 'Kenshin'


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def similarity(query: str, name: str) -> float:
    a, b = norm(query), norm(name)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    if b.startswith(a):  # "Nike" -> "Nike Training Club" is a decent match; the reverse (a truncated
        ratio = max(ratio, 0.85)  # candidate like "Kenshi" for "Kenshi Yonezu") is not
    return ratio
