import sys
from pathlib import Path

from collector.greenhouse import fetch_greenhouse_jobs
from collector.hybrid_filter import filter_jobs_for_ai
from database.job_repository import JobRepository


DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "jobs.db"
)


def import_jobs(board_token, company):

    fetched = fetch_greenhouse_jobs(
        board_token,
        company,
    )

    candidates, stats = filter_jobs_for_ai(
        fetched
    )

    print(f"Retrieved: {len(fetched)}")

    print(
        f"Passed initial filter: {len(candidates)}"
    )

    print(
        "Filter statistics:",
        dict(stats),
    )

    repository = JobRepository(
        str(DB_PATH)
    )

    saved = 0

    for job in candidates:

        repository.save_job(job)

        # We don't rely on row counts here because
        # INSERT OR IGNORE handles duplicates.

        saved += 1

    repository.close()

    print(
        f"Jobs sent to database: {saved}"
    )

    return candidates


if __name__ == "__main__":

    if len(sys.argv) != 3:

        print(
            "Usage: python -m "
            "scripts.import_greenhouse "
            "BOARD_TOKEN COMPANY"
        )

        sys.exit(1)

    import_jobs(
        sys.argv[1],
        sys.argv[2],
    )