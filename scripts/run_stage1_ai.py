import json

from database.job_repository import JobRepository
from database.job_ai_repository import JobAIRepository

from analyzer.llm.stage1_runtime import (
    Stage1DailyLimitReached,
    Stage1NoAvailableModels,
    Stage1JobRequestLimitReached,
    Stage1ConsecutiveRateLimitReached,
    
)

from analyzer.stage1.job_intelligence import (
    analyze_job_intelligence,
)


DB_PATH = "database/jobs.db"


def main():
    job_repository = JobRepository(DB_PATH)
    ai_repository = JobAIRepository(DB_PATH)

    processed = 0
    failed = 0
    sent_to_stage2 = 0
    rejected = 0

    try:
        jobs = job_repository.get_unanalyzed_jobs()

        print(
            f"Jobs waiting for AI: {len(jobs)}"
        )

        for job in jobs:
            print("\n" + "=" * 60)
            print(f"Job ID:   {job['id']}")
            print(f"Company:  {job['company']}")
            print(f"Title:    {job['title']}")
            print(f"Location: {job['location']}")
            print("=" * 60)

            try:
                result = analyze_job_intelligence(job)

                # Ensure repository always receives the database ID.
                result["job_id"] = job["id"]

                ai_repository.save_analysis(result)

                processed += 1

                if result["recommendation"] == "send_to_stage_2":
                    sent_to_stage2 += 1
                else:
                    rejected += 1

                print(
                    json.dumps(
                        result,
                        indent=2,
                        ensure_ascii=False,
                    )
                )

                print("Saved to job_ai_analysis.")

            except Stage1DailyLimitReached as error:
                print("\nSTOPPING STAGE 1")
                print(error)
                break

            except Stage1NoAvailableModels as error:
                print("\nSTOPPING STAGE 1")
                print(error)
                break

            except Stage1JobRequestLimitReached as error:
                failed += 1
                print(
                    f"Stage 1 request limit reached for "
                    f"job {job['id']}: {error}"
                )
                continue

            except Exception as error:
                failed += 1
                print(
                    f"Stage 1 failed for job "
                    f"{job['id']}: {error}"
                )
                continue

    finally:
        job_repository.close()
        ai_repository.close()

    print("\n" + "=" * 60)
    print("STAGE 1 SUMMARY")
    print("=" * 60)
    print(f"Processed:        {processed}")
    print(f"Sent to Stage 2:  {sent_to_stage2}")
    print(f"Rejected:         {rejected}")
    print(f"Failed:           {failed}")


if __name__ == "__main__":
    main()
