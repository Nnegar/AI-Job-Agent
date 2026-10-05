"""
Sync Repository.
Tracks incremental source collection timestamps and implements the capped 7-day lookback rule.
"""

import datetime
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "database" / "jobs.db"


class SyncRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._ensure_table()

    def _ensure_table(self):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS source_sync_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                last_pull_at TIMESTAMP NOT NULL,
                jobs_collected INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source, target)
            )
            """
        )
        self.connection.commit()

    def get_since_date(
        self,
        source: str,
        target: str,
        max_lookback_days: int = 7,
        current_time: Optional[datetime.datetime] = None,
    ) -> datetime.datetime:
        """
        Determines the earliest publication/update timestamp to collect for a given source & target.
        Implements the sliding window:
        - If first run: now - 7 days
        - If last run > 7 days ago: capped at now - 7 days (e.g. pulled Sep 4, run on Sep 15 -> returns Sep 8)
        - If last run <= 7 days ago: returns last_pull_at
        """
        now = current_time or datetime.datetime.now(datetime.timezone.utc)
        capped_cutoff = now - datetime.timedelta(days=max_lookback_days)

        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT last_pull_at FROM source_sync_state WHERE source = ? AND target = ?",
            (source, target),
        )
        row = cursor.fetchone()

        if not row or not row["last_pull_at"]:
            return capped_cutoff

        raw_str = row["last_pull_at"].replace("Z", "+00:00")
        try:
            last_pull = datetime.datetime.fromisoformat(raw_str)
            if last_pull.tzinfo is None:
                last_pull = last_pull.replace(tzinfo=datetime.timezone.utc)
        except Exception:
            return capped_cutoff

        # If gap is greater than 7 days, cap at 7 days
        if last_pull < capped_cutoff:
            return capped_cutoff

        return last_pull

    def update_sync_state(
        self,
        source: str,
        target: str,
        jobs_collected: int = 0,
        sync_time: Optional[datetime.datetime] = None,
    ) -> int:
        now_str = (sync_time or datetime.datetime.now(datetime.timezone.utc)).isoformat()
        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO source_sync_state (
                source,
                target,
                last_pull_at,
                jobs_collected,
                created_at
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(source, target) DO UPDATE SET
                last_pull_at = excluded.last_pull_at,
                jobs_collected = excluded.jobs_collected
            """,
            (source, target, now_str, jobs_collected),
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_all_sync_states(self) -> List[Dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT source, target, last_pull_at, jobs_collected FROM source_sync_state ORDER BY source, target"
        )
        return [dict(r) for r in cursor.fetchall()]

    def close(self):
        self.connection.close()
