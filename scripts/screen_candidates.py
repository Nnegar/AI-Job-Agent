
import json
import re
import sqlite3
from pathlib import Path

from scripts.inspect_candidates import extract_requirements


DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "jobs.db"
)

YEARS_PATTERN = re.compile(
    r"\b(\d+)\s*(?:\+|[-–]\s*\d+)?"
    r"\s*years?\s+(?:of\s+)?"
    r"(?:proven\s+)?experience\b",
    re.IGNORECASE,
)


def screen_jobs():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("PRAGMA foreign_keys = ON")

        # Keep screening separate from job records.
        db.execute("""
            CREATE TABLE IF NOT EXISTS job_screenings (
                raw_job_id INTEGER PRIMARY KEY,
                experience_evidence TEXT NOT NULL,
                screening_status TEXT NOT NULL,
                screened_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (raw_job_id)
                    REFERENCES raw_jobs(id)
            )
        """)

        jobs = db.execute("""
            SELECT id, title, description
            FROM raw_jobs
        """).fetchall()

        for job_id, title, description in jobs:
            requirements = extract_requirements(description)

            evidence = []

            for requirement in requirements:
                match = YEARS_PATTERN.search(requirement)

                if match:
                    evidence.append({
                        "years": int(match.group(1)),
                        "text": requirement,
                    })

            if evidence:
                status = "review_experience"
            else:
                status = "review_requirements"

            db.execute("""
                INSERT INTO job_screenings (
                    raw_job_id,
                    experience_evidence,
                    screening_status
                )
                VALUES (?, ?, ?)

                ON CONFLICT(raw_job_id)
                DO UPDATE SET
                    experience_evidence =
                        excluded.experience_evidence,
                    screening_status =
                        excluded.screening_status,
                    screened_at = CURRENT_TIMESTAMP
            """, (
                job_id,
                json.dumps(evidence),
                status,
            ))

            print(f"\n{title}")
            print(f"Status: {status}")

            for item in evidence:
                print(
                    f"Experience reference: "
                    f"{item['years']}+ years"
                )

        print(f"\nScreened {len(jobs)} jobs.")


if __name__ == "__main__":
    screen_jobs()
