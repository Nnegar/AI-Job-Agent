"""
Application Repository.
Manages application state transitions and tracking in SQLite database.
Lifecycle: discovered -> shortlisted -> prepared -> applied -> interviewing -> rejected/offered
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "jobs.db"
)

VALID_STATUSES = {
    "discovered",
    "shortlisted",
    "prepared",
    "applied",
    "interviewing",
    "rejected",
    "offered",
    "archived",
}


class ApplicationRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row

    def upsert_application(
        self,
        job_id: int,
        status: str = "discovered",
        application_url: Optional[str] = None,
        notes: Optional[str] = None,
        applied_date: Optional[str] = None,
    ) -> int:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid application status: '{status}'. Valid statuses: {VALID_STATUSES}")

        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO applications (
                job_id,
                status,
                application_url,
                notes,
                applied_date,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(job_id) DO UPDATE SET
                status = excluded.status,
                application_url = COALESCE(excluded.application_url, applications.application_url),
                notes = COALESCE(excluded.notes, applications.notes),
                applied_date = COALESCE(excluded.applied_date, applications.applied_date)
            """,
            (job_id, status, application_url, notes, applied_date),
        )
        self.connection.commit()
        return cursor.lastrowid

    def update_status(
        self,
        job_id: int,
        status: str,
        notes: Optional[str] = None,
        applied_date: Optional[str] = None,
    ) -> bool:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid application status: '{status}'. Valid statuses: {VALID_STATUSES}")

        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE applications
            SET status = ?,
                notes = COALESCE(?, notes),
                applied_date = COALESCE(?, applied_date)
            WHERE job_id = ?
            """,
            (status, notes, applied_date, job_id),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def get_by_job_id(self, job_id: int) -> Optional[Dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT
                a.id,
                a.job_id,
                a.status,
                a.application_url,
                a.applied_date,
                a.notes,
                a.created_at,
                j.company,
                j.title,
                j.location
            FROM applications a
            JOIN jobs j ON j.id = a.job_id
            WHERE a.job_id = ?
            """,
            (job_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        cursor = self.connection.cursor()
        if status:
            cursor.execute(
                """
                SELECT
                    a.id,
                    a.job_id,
                    a.status,
                    a.application_url,
                    a.applied_date,
                    a.notes,
                    a.created_at,
                    j.company,
                    j.title,
                    j.location
                FROM applications a
                JOIN jobs j ON j.id = a.job_id
                WHERE a.status = ?
                ORDER BY a.created_at DESC
                """,
                (status,),
            )
        else:
            cursor.execute(
                """
                SELECT
                    a.id,
                    a.job_id,
                    a.status,
                    a.application_url,
                    a.applied_date,
                    a.notes,
                    a.created_at,
                    j.company,
                    j.title,
                    j.location
                FROM applications a
                JOIN jobs j ON j.id = a.job_id
                ORDER BY a.created_at DESC
                """
            )
        return [dict(row) for row in cursor.fetchall()]

    def get_status_counts(self) -> Dict[str, int]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM applications GROUP BY status")
        return dict(cursor.fetchall())

    def close(self):
        self.connection.close()
