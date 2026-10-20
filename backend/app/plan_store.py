"""Saved plans, in the same SQLite file as invite rooms (on the mounted volume in production).

Why not only the disk cache: a plan's versions (refinements) and its shareable /plan/<id> link should survive a
redeploy. The disk cache stays as the fast path; this is the durable copy. Plans are pruned after 30 days."""
import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import settings
from .models import PlanResponse
from .rooms import Tx

log = logging.getLogger("tasteroom.plans")
RETENTION = timedelta(days=30)


class PlanStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS plans (
                    plan_id TEXT PRIMARY KEY, root_id TEXT NOT NULL, parent_id TEXT, version INTEGER NOT NULL,
                    instruction TEXT, mode TEXT NOT NULL, created_at TEXT NOT NULL, json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_plans_root ON plans(root_id, version);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    def _conn(self) -> Tx:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return Tx(conn)

    def save(self, plan: PlanResponse) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO plans(plan_id, root_id, parent_id, version, instruction, mode, created_at, json) "
                      "VALUES (?,?,?,?,?,?,?,?)",
                      (plan.plan_id, plan.root_id or plan.plan_id, plan.parent_id, plan.version,
                       plan.refinement.instruction if plan.refinement else None, plan.mode,
                       datetime.now(timezone.utc).isoformat(timespec="seconds"), plan.model_dump_json()))

    def load(self, plan_id: str) -> PlanResponse | None:
        with self._conn() as c:
            row = c.execute("SELECT json FROM plans WHERE plan_id=?", (plan_id,)).fetchone()
        return PlanResponse.model_validate(json.loads(row["json"])) if row else None

    def family(self, root_id: str) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT plan_id, version, parent_id, instruction, mode, created_at FROM plans "
                             "WHERE root_id=? ORDER BY version, created_at", (root_id,)).fetchall()
        return [dict(r) for r in rows]

    def max_version(self, root_id: str) -> int:
        with self._conn() as c:
            return c.execute("SELECT COALESCE(MAX(version), 0) FROM plans WHERE root_id=?", (root_id,)).fetchone()[0]

    def reset_stale_families(self, fingerprints: dict[str, str]) -> list[str]:
        """A refinement is only valid for the exact plan it was made from. For each root plan (a saved example, the demo
        room's plan) compare a fingerprint of its content with the one recorded last time; if it changed, or was never
        recorded, delete that root's refinements so nobody is shown a version built on an older brief. Returns the roots cleared."""
        cleared = []
        with self._conn() as c:
            for root, fp in fingerprints.items():
                row = c.execute("SELECT value FROM meta WHERE key=?", (f"family:{root}",)).fetchone()
                if row and row["value"] == fp:
                    continue
                c.execute("DELETE FROM plans WHERE root_id=? AND plan_id != ?", (root, root))
                c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (f"family:{root}", fp))
                cleared.append(root)
        return cleared

    def prune(self, older_than: timedelta = RETENTION) -> int:
        cutoff = (datetime.now(timezone.utc) - older_than).isoformat(timespec="seconds")
        with self._conn() as c:
            return c.execute("DELETE FROM plans WHERE created_at < ?", (cutoff,)).rowcount


_store: PlanStore | None = None


def get_store() -> PlanStore:
    global _store
    if _store is None:
        _store = PlanStore(settings.data_path / "tasteroom.sqlite3")
    return _store


def set_store(store: PlanStore | None) -> None:  # tests
    global _store
    _store = store
