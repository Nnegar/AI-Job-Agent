import sqlite3
from pathlib import Path


DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "jobs.db"
)


def create_cover_letter_table():
    connection = sqlite3.connect(DB_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        connection.execute(
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

                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (job_id)
                    REFERENCES jobs(id)
            )
            """
        )

        connection.commit()

        print("Cover-letter drafts table is ready.")

    finally:
        connection.close()


if __name__ == "__main__":
    create_cover_letter_table()
