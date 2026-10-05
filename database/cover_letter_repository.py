"""
Cover Letter Repository.
Handles database persistence and retrieval of generated cover letter drafts.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "jobs.db"
)


class CoverLetterRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._ensure_table()

    def _ensure_table(self):
        cursor = self.connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cover_letter_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                recommended_cv TEXT NOT NULL,
                letter_text TEXT NOT NULL,
                review_status TEXT NOT NULL
                    DEFAULT 'draft'
                    CHECK (
                        review_status IN (
                            'draft',
                            'needs_revision',
                            'approved'
                        )
                    ),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs(id),
                UNIQUE(job_id)
            )
            """
        )
        # Defensive schema migration for older table definitions
        cursor.execute("PRAGMA table_info(cover_letter_drafts)")
        columns = [row[1] for row in cursor.fetchall()]
        if "updated_at" not in columns:
            cursor.execute("ALTER TABLE cover_letter_drafts ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cover_letter_drafts_job_id ON cover_letter_drafts(job_id)")
        self.connection.commit()

    def save_draft(
        self,
        job_id: int,
        recommended_cv: str,
        letter_text: str,
        review_status: str = "draft",
    ) -> int:
        if not letter_text or not letter_text.strip():
            raise ValueError("Cannot save an empty cover letter")
        if not recommended_cv or not recommended_cv.strip():
            raise ValueError("A recommended CV is required")

        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO cover_letter_drafts (
                job_id,
                recommended_cv,
                letter_text,
                review_status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(job_id) DO UPDATE SET
                recommended_cv = excluded.recommended_cv,
                letter_text = excluded.letter_text,
                review_status = excluded.review_status,
                updated_at = CURRENT_TIMESTAMP
            """,
            (job_id, recommended_cv.strip(), letter_text.strip(), review_status),
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_draft_by_job_id(self, job_id: int) -> Optional[Dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT
                id,
                job_id,
                recommended_cv,
                letter_text,
                review_status,
                created_at,
                updated_at
            FROM cover_letter_drafts
            WHERE job_id = ?
            """,
            (job_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_drafts(
        self, review_status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        cursor = self.connection.cursor()
        if review_status:
            cursor.execute(
                """
                SELECT
                    c.id,
                    c.job_id,
                    c.recommended_cv,
                    c.letter_text,
                    c.review_status,
                    c.created_at,
                    c.updated_at,
                    j.company,
                    j.title,
                    j.location,
                    j.url
                FROM cover_letter_drafts c
                JOIN jobs j ON j.id = c.job_id
                WHERE c.review_status = ?
                ORDER BY c.created_at DESC
                """,
                (review_status,),
            )
        else:
            cursor.execute(
                """
                SELECT
                    c.id,
                    c.job_id,
                    c.recommended_cv,
                    c.letter_text,
                    c.review_status,
                    c.created_at,
                    c.updated_at,
                    j.company,
                    j.title,
                    j.location,
                    j.url
                FROM cover_letter_drafts c
                JOIN jobs j ON j.id = c.job_id
                ORDER BY c.created_at DESC
                """
            )
        return [dict(row) for row in cursor.fetchall()]

    def update_review_status(self, job_id: int, review_status: str) -> bool:
        if review_status not in ("draft", "needs_revision", "approved"):
            raise ValueError(f"Invalid review status: {review_status}")

        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE cover_letter_drafts
            SET review_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
            """,
            (review_status, job_id),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def get_draft_count(self) -> int:
        cursor = self.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM cover_letter_drafts")
        return cursor.fetchone()[0]

    def close(self):
        self.connection.close()


def save_cover_letter(
    job_id: int,
    recommended_cv: str,
    letter_text: str,
) -> int:
    """Module-level function for backward-compatibility."""
    repo = CoverLetterRepository()
    try:
        return repo.save_draft(job_id, recommended_cv, letter_text)
    finally:
        repo.close()
