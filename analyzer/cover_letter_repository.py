import sqlite3
from contextlib import closing
from pathlib import Path


DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "jobs.db"
)


def save_cover_letter(
    job_id: int,
    recommended_cv: str,
    letter_text: str,
) -> int:

    if not letter_text.strip():
        raise ValueError("Cannot save an empty cover letter")

    if not recommended_cv.strip():
        raise ValueError("A recommended CV is required")

    with closing(sqlite3.connect(DB_PATH)) as connection:

        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            cursor = connection.execute(
                """
                INSERT INTO cover_letter_drafts (
                    job_id,
                    recommended_cv,
                    letter_text
                )
                VALUES (?, ?, ?)
                """,
                (
                    job_id,
                    recommended_cv,
                    letter_text,
                ),
            )

        return cursor.lastrowid
