"""Invite rooms: an organizer shares one link, members add their own tastes, the organizer builds a plan from
the responses. Storage is SQLite (stdlib) in DATA_DIR; mount a volume there in production so rooms survive redeploys.

Privacy and safety choices:
- The organizer token is shown once and stored only as a SHA-256 hash, compared in constant time, so a leaked
  database cannot be used to open someone's room.
- Members give a first name or nickname only (no links, emails or phone numbers); every text is trimmed and
  length-limited; picked entity ids are verified against Qloo and replaced by Qloo's own name and image.
"""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import settings
from .models import Taste

SLUG_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no look-alikes (0/o, 1/l/i)
SLUG_LENGTH = 8
MAX_RESPONSES_PER_ROOM = 60        # abuse cap on a join link; the plan still uses at most 15 members
PLAN_MEMBER_CAP = 15               # PlanRequest.members limit
MIN_RESPONSES_TO_PLAN = 3
NAME_MAX = 24

# The demo room for judges: anyone may join (so they can watch a response arrive live), but it is small and self-cleaning.
DEMO_SLUG = "demo"
DEMO_TOKEN = "demo-room"           # public on purpose: it is linked from the landing page
DEMO_MAX_RESPONSES = 15
DEMO_PRUNE_AFTER = timedelta(hours=12)


class RoomError(Exception):
    """A user-facing problem (bad name, duplicate, room full...). `status` is the HTTP status to use."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


@dataclass
class Room:
    id: int
    slug: str
    community_name: str
    city: str
    event_goal: str
    created_at: str


@dataclass
class StoredResponse:
    id: int
    member_name: str
    tastes: list[dict]
    created_at: str

    @property
    def matched(self) -> int:
        return sum(1 for t in self.tastes if t.get("entity_id"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def clean_text(value: str, limit: int) -> str:
    """Single line, no control characters, collapsed whitespace, length-limited."""
    return " ".join("".join(ch if ch.isprintable() else " " for ch in value).split())[:limit].strip()


_LINKISH = re.compile(r"@|https?:|www\.|\.(com|net|org|io|co|app|me|ly)\b|://", re.I)


def clean_member_name(raw: str) -> str:
    name = clean_text(raw, NAME_MAX + 1)
    if not name:
        raise RoomError(422, "Please add your first name or a nickname.")
    if len(name) > NAME_MAX:
        raise RoomError(422, f"Keep your name to {NAME_MAX} characters or fewer.")
    if _LINKISH.search(name) or sum(ch.isdigit() for ch in name) >= 7:
        raise RoomError(422, "Use just a first name or nickname (no links, emails or phone numbers).")
    return name


def clean_tastes(tastes: list[Taste]) -> list[dict]:
    out, seen = [], set()
    for t in tastes:
        text = clean_text(t.text, 80)
        key = (text.lower(), t.entity_id or "")
        if not text or key in seen:
            continue
        seen.add(key)
        out.append({"text": text, "kind": t.kind, **({"entity_id": t.entity_id.upper()} if t.entity_id else {})})
    if not out:
        raise RoomError(422, "Add at least one thing you like.")
    return out[:6]


def select_for_plan(responses: list[StoredResponse], cap: int = PLAN_MEMBER_CAP) -> tuple[list[StoredResponse], list[StoredResponse]]:
    """(used, left_out). More than `cap` responses: keep the ones with the most Qloo-matched tastes (ties: earliest),
    in the order they arrived."""
    if len(responses) <= cap:
        return responses, []
    ranked = sorted(responses, key=lambda r: (-r.matched, r.id))
    keep = {r.id for r in ranked[:cap]}
    return [r for r in responses if r.id in keep], [r for r in responses if r.id not in keep]


class RoomStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS rooms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE NOT NULL, community_name TEXT NOT NULL,
                    city TEXT NOT NULL, event_goal TEXT NOT NULL, created_at TEXT NOT NULL,
                    organizer_token TEXT NOT NULL            -- SHA-256 hash of the token, never the token itself
                );
                CREATE TABLE IF NOT EXISTS responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                    member_name TEXT NOT NULL, tastes_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    seed INTEGER NOT NULL DEFAULT 0          -- 1 = pre-filled demo response
                );
                CREATE INDEX IF NOT EXISTS idx_responses_room ON responses(room_id);
            """)

    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        return Tx(conn)

    # ---- rooms ----
    def create_room(self, community_name: str, city: str, event_goal: str, slug: str | None = None,
                    token: str | None = None) -> tuple[Room, str]:
        token = token or secrets.token_urlsafe(24)
        for _ in range(8):
            candidate = slug or "".join(secrets.choice(SLUG_ALPHABET) for _ in range(SLUG_LENGTH))
            try:
                with self._conn() as c:
                    cur = c.execute("INSERT INTO rooms(slug, community_name, city, event_goal, created_at, organizer_token) "
                                    "VALUES (?,?,?,?,?,?)", (candidate, community_name, city, event_goal, _now(), hash_token(token)))
                    return self.get_room(candidate, c), token
            except sqlite3.IntegrityError:
                if slug:
                    raise
        raise RoomError(503, "Could not create a room right now. Please try again.")

    def get_room(self, slug: str, conn=None) -> Room | None:
        def q(c):
            r = c.execute("SELECT id, slug, community_name, city, event_goal, created_at FROM rooms WHERE slug=?", (slug,)).fetchone()
            return Room(**dict(r)) if r else None
        if conn is not None:
            return q(conn)
        with self._conn() as c:
            return q(c)

    def check_token(self, slug: str, token: str) -> bool:
        with self._conn() as c:
            r = c.execute("SELECT organizer_token FROM rooms WHERE slug=?", (slug,)).fetchone()
        # compare even when the room is missing, so timing does not reveal which slugs exist
        stored = r["organizer_token"] if r else hash_token("no-such-room")
        return hmac.compare_digest(stored, hash_token(token or "")) and r is not None

    # ---- responses ----
    def count(self, room_id: int) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM responses WHERE room_id=?", (room_id,)).fetchone()[0]

    def add_response(self, room: Room, member_name: str, tastes: list[dict], seed: bool = False) -> int:
        limit = DEMO_MAX_RESPONSES if room.slug == DEMO_SLUG else MAX_RESPONSES_PER_ROOM
        with self._conn() as c:
            if c.execute("SELECT COUNT(*) FROM responses WHERE room_id=?", (room.id,)).fetchone()[0] >= limit:
                raise RoomError(409, "This room is full. Ask your organizer to start a new one."
                                if room.slug != DEMO_SLUG else "The demo room is full. Create your own room from the Builder.")
            if c.execute("SELECT 1 FROM responses WHERE room_id=? AND lower(member_name)=lower(?)", (room.id, member_name)).fetchone():
                raise RoomError(409, "Someone already used that name in this room. Add an initial or pick a nickname.")
            cur = c.execute("INSERT INTO responses(room_id, member_name, tastes_json, created_at, seed) VALUES (?,?,?,?,?)",
                            (room.id, member_name, json.dumps(tastes), _now(), 1 if seed else 0))
            return int(cur.lastrowid)

    def responses(self, room_id: int) -> list[StoredResponse]:
        with self._conn() as c:
            rows = c.execute("SELECT id, member_name, tastes_json, created_at FROM responses WHERE room_id=? ORDER BY id", (room_id,)).fetchall()
        return [StoredResponse(r["id"], r["member_name"], json.loads(r["tastes_json"]), r["created_at"]) for r in rows]

    def delete_response(self, room_id: int, response_id: int) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM responses WHERE id=? AND room_id=?", (response_id, room_id)).rowcount > 0

    def prune_demo(self, older_than: timedelta = DEMO_PRUNE_AFTER) -> int:
        """Remove responses visitors added to the demo room more than `older_than` ago (the seeded ones stay)."""
        cutoff = (datetime.now(timezone.utc) - older_than).isoformat(timespec="seconds")
        with self._conn() as c:
            return c.execute("DELETE FROM responses WHERE seed=0 AND created_at < ? AND room_id IN "
                             "(SELECT id FROM rooms WHERE slug=?)", (cutoff, DEMO_SLUG)).rowcount

    def ensure_demo(self, community_name: str, city: str, event_goal: str, members: list[tuple[str, list[dict]]]) -> Room:
        """Create the demo room and its seed responses if missing. Idempotent; refreshes the seeds if they drifted."""
        room = self.get_room(DEMO_SLUG)
        if room is None:
            room, _ = self.create_room(community_name, city, event_goal, slug=DEMO_SLUG, token=DEMO_TOKEN)
        with self._conn() as c:
            have = {r["member_name"]: r["id"] for r in c.execute("SELECT id, member_name FROM responses WHERE room_id=? AND seed=1", (room.id,))}
            for name, tastes in members:
                if name not in have:
                    c.execute("DELETE FROM responses WHERE room_id=? AND lower(member_name)=lower(?) AND seed=0", (room.id, name))
                    c.execute("INSERT INTO responses(room_id, member_name, tastes_json, created_at, seed) VALUES (?,?,?,?,1)",
                              (room.id, name, json.dumps(tastes), _now()))
        return room


class Tx:
    """sqlite3 connection as a context manager that commits on success, rolls back on error, always closes."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        with closing(self.conn):
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()


_store: RoomStore | None = None


def get_store() -> RoomStore:
    global _store
    if _store is None:
        _store = RoomStore(settings.data_path / "tasteroom.sqlite3")
    return _store


def set_store(store: RoomStore | None) -> None:  # tests
    global _store
    _store = store
