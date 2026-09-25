
import sqlite3
import sys
from pathlib import Path

from collector.greenhouse import fetch_greenhouse_jobs
from collector.job_filter import filter_candidates


DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "jobs.db"
)


def import_jobs(board_token, company):
    # Fetch and filter jobs before saving them.
    fetched = fetch_greenhouse_jobs(board_token, company)
    jobs = filter_candidates(fetched)

    print(f"Retrieved: {len(fetched)}")
    print(f"Passed initial filters: {len(jobs)}")

    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS raw_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                board_token TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                url TEXT,
                description TEXT,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen TEXT DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(source, board_token, external_id)
            )
        """)

        before = db.execute(
            "SELECT COUNT(*) FROM raw_jobs"
        ).fetchone()[0]

        for job in jobs:
            db.execute("""
                INSERT INTO raw_jobs (
                    source, board_token, external_id,
                    title, company, location, url, description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)

                ON CONFLICT(source, board_token, external_id)
                DO UPDATE SET
                    title = excluded.title,
                    company = excluded.company,
                    location = excluded.location,
                    url = excluded.url,
                    description = excluded.description,
                    last_seen = CURRENT_TIMESTAMP
            """, (
                job["source"],
                board_token,
                job["external_id"],
                job["title"],
                job["company"],
                ", ".join(job["posting_locations"]) or "Unknown",
                job["url"],
                job["description"],
            ))

        after = db.execute(
            "SELECT COUNT(*) FROM raw_jobs"
        ).fetchone()[0]

    print(f"New jobs saved: {after - before}")
    print(f"Total raw jobs: {after}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python -m scripts.import_greenhouse "
            "BOARD_TOKEN COMPANY"
        )
        sys.exit(1)

    import_jobs(sys.argv[1], sys.argv[2])
