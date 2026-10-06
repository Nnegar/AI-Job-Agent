"""
Pipeline Run Repository.
Tracks master end-to-end pipeline execution runs and their persistent timestamps.
"""

import datetime
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "database" / "jobs.db"


class PipelineRunRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._ensure_table()

    def _ensure_table(self):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_execution_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'running',
                total_collected INTEGER DEFAULT 0,
                duplicates_skipped INTEGER DEFAULT 0,
                new_jobs_saved INTEGER DEFAULT 0,
                stage1_evaluated INTEGER DEFAULT 0,
                stage2_evaluated INTEGER DEFAULT 0,
                shortlisted INTEGER DEFAULT 0,
                summary_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.commit()

    def start_run(self) -> int:
        cursor = self.connection.cursor()
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO pipeline_execution_runs (started_at, status)
            VALUES (?, 'running')
            """,
            (now_str,),
        )
        self.connection.commit()
        return cursor.lastrowid

    def complete_run(self, run_id: int, summary: Dict[str, Any]) -> bool:
        cursor = self.connection.cursor()
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        summary_json = json.dumps(summary, ensure_ascii=False)
        cursor.execute(
            """
            UPDATE pipeline_execution_runs
            SET completed_at = ?,
                status = 'completed',
                total_collected = ?,
                duplicates_skipped = ?,
                new_jobs_saved = ?,
                stage1_evaluated = ?,
                stage2_evaluated = ?,
                shortlisted = ?,
                summary_json = ?
            WHERE id = ?
            """,
            (
                now_str,
                summary.get("collected", 0),
                summary.get("duplicates", 0),
                summary.get("new_jobs", 0),
                summary.get("stage1_evaluated", 0),
                summary.get("stage2_evaluated", 0),
                summary.get("shortlisted", 0),
                summary_json,
                run_id,
            ),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def get_last_completed_run(self) -> Optional[Dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT * FROM pipeline_execution_runs
            WHERE status = 'completed'
            ORDER BY id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_last_run_display(self) -> str:
        """
        Returns a clean human-readable timestamp of the last completed run.
        e.g. '5 Oct, 22:57' or '6 Oct, 08:41'.
        """
        last = self.get_last_completed_run()
        if last and last.get("completed_at"):
            try:
                dt = datetime.datetime.fromisoformat(last["completed_at"].replace("Z", "+00:00"))
                return f"{dt.day} {dt.strftime('%b')}, {dt.strftime('%H:%M')}"
            except Exception:
                pass

        # Fallback to latest pull time from source_sync_state
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT last_pull_at FROM source_sync_state
            WHERE last_pull_at IS NOT NULL
            ORDER BY last_pull_at DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if row and row[0]:
            try:
                dt = datetime.datetime.fromisoformat(row[0].replace("Z", "+00:00"))
                return f"{dt.day} {dt.strftime('%b')}, {dt.strftime('%H:%M')}"
            except Exception:
                pass

        return "29 Sep, 18:00"

    def close(self):
        self.connection.close()
