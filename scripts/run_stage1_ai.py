import json

from database.job_repository import JobRepository
from database.job_ai_repository import JobAIRepository
from analyzer.stage1.job_intelligence import analyze_job_intelligence


DB_PATH = "database/jobs.db"


def main():

    job_repository = JobRepository(DB_PATH)
    ai_repository = JobAIRepository(DB_PATH)

    jobs = job_repository.get_unanalyzed_jobs()

    print(f"Jobs waiting for AI: {len(jobs)}")

    for job in jobs:

        print("\n===================")
        print(f"Company: {job['company']}")
        print(f"Title: {job['title']}")
        print(f"Location: {job['location']}")

        try:

            result = analyze_job_intelligence(job)

            result["job_id"] = job["id"]

            ai_repository.save_analysis(result)

            print(
                json.dumps(
                    result,
                    indent=2,
                    ensure_ascii=False
                )
            )

            print("Saved to job_ai_analysis.")

        except Exception as error:

            print(
                f"Stage 1 failed for job "
                f"{job['id']}: {error}"
            )

            continue

    job_repository.close()
    ai_repository.close()


if __name__ == "__main__":
    main()