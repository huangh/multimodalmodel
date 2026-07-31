"""Usage tracking for hub scripts.

Every render of a script is written to a small SQLite database so the hub can
surface the plots people actually use. SQLite (WAL mode, short-lived
connections) keeps the prototype dependency-free while still being safe for
the multiple kernel processes a marimo server spawns — one per viewer.
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_ENV = "MBTA_HUB_USAGE_DB"
DEFAULT_DB_PATH = Path(".hub/usage.db")

#: Repeat renders of the same script by the same session inside this window
#: count once. Marimo re-runs dependent cells on any upstream change, so
#: without this a slider drag would inflate a script's popularity.
DEFAULT_DEDUPE_WINDOW_S = 30.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    script_id   TEXT    NOT NULL,
    user        TEXT,
    session_id  TEXT,
    action      TEXT    NOT NULL DEFAULT 'render',
    ts          REAL    NOT NULL,
    duration_ms REAL,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_script ON usage_events (script_id);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_events (ts);
"""


@dataclass(frozen=True)
class ScriptUsage:
    """Aggregated usage for one script."""

    script_id: str
    uses: int
    unique_users: int
    last_used: float | None
    errors: int = 0

    @property
    def last_used_iso(self) -> str:
        if not self.last_used:
            return ""
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.last_used))


def default_db_path() -> Path:
    """Database location, overridable via ``MBTA_HUB_USAGE_DB``."""
    return Path(os.environ.get(DEFAULT_DB_ENV) or DEFAULT_DB_PATH).expanduser()


class UsageStore:
    """Append-only event log with a few aggregate queries."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_db_path()
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn: sqlite3.Connection | None = None
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if str(self.db_path) == ":memory:":
            # An in-memory database dies with its connection, so keep one open.
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(":memory:")
                self._memory_conn.row_factory = sqlite3.Row
            yield self._memory_conn
            self._memory_conn.commit()
            return
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -- writes ---------------------------------------------------------

    def record(
        self,
        script_id: str,
        *,
        user: str | None = None,
        session_id: str | None = None,
        action: str = "render",
        duration_ms: float | None = None,
        error: str | None = None,
        dedupe_window_s: float = DEFAULT_DEDUPE_WINDOW_S,
        now: float | None = None,
    ) -> bool:
        """Record one use. Returns ``False`` when deduplicated away."""
        ts = time.time() if now is None else now
        with self._connect() as conn:
            if dedupe_window_s > 0:
                row = conn.execute(
                    """
                    SELECT ts FROM usage_events
                    WHERE script_id = ?
                      AND action = ?
                      AND IFNULL(session_id, '') = IFNULL(?, '')
                    ORDER BY ts DESC LIMIT 1
                    """,
                    (script_id, action, session_id),
                ).fetchone()
                if row is not None and ts - row["ts"] < dedupe_window_s:
                    return False
            conn.execute(
                """
                INSERT INTO usage_events
                    (script_id, user, session_id, action, ts, duration_ms, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (script_id, user, session_id, action, ts, duration_ms, error),
            )
        return True

    # -- reads ----------------------------------------------------------

    def _since_clause(self, since_days: float | None) -> tuple[str, tuple[float, ...]]:
        if since_days is None:
            return "", ()
        return " AND ts >= ?", (time.time() - since_days * 86400.0,)

    def summary(
        self, *, since_days: float | None = None, limit: int | None = None
    ) -> list[ScriptUsage]:
        """Per-script totals, most used first."""
        where, params = self._since_clause(since_days)
        sql = f"""
            SELECT script_id,
                   COUNT(*)                       AS uses,
                   COUNT(DISTINCT IFNULL(user, session_id)) AS unique_users,
                   MAX(ts)                        AS last_used,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) AS errors
            FROM usage_events
            WHERE action = 'render'{where}
            GROUP BY script_id
            ORDER BY uses DESC, last_used DESC
        """
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            ScriptUsage(
                script_id=r["script_id"],
                uses=r["uses"],
                unique_users=r["unique_users"],
                last_used=r["last_used"],
                errors=r["errors"] or 0,
            )
            for r in rows
        ]

    def counts(self, *, since_days: float | None = None) -> dict[str, int]:
        return {u.script_id: u.uses for u in self.summary(since_days=since_days)}

    def top(
        self, limit: int = 10, *, since_days: float | None = None
    ) -> list[ScriptUsage]:
        return self.summary(since_days=since_days, limit=limit)

    def recent(self, limit: int = 25) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT script_id, user, session_id, action, ts, error
                FROM usage_events ORDER BY ts DESC LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [dict(r) for r in rows]

    def total_events(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0])
