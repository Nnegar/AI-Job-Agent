import sqlite3
from contextlib import closing
from pathlib import Path


DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "jobs.db"
)


def get_job(job_id: int) -> dict:
    with closing(sqlite3.connect(DB_PATH)) as connection:
        connection.row_factory = sqlite3.Row

        row = connection.execute(
            """
            SELECT
                id,
                title,
                company,
                description,
                category,
                recommended_cv,
                url
            FROM jobs
            WHERE id = ?
            """,
            (job_id,),
        ).fetchone()

    if row is None:
        raise ValueError(f"Job {job_id} does not exist")

    return dict(row)
