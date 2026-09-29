"""
Small batch test runner for Stage 2 Candidate-to-Job Fit.

Processes a limited number of eligible jobs (default 5) to verify
model behavior, schema validity, and database storage.
"""

import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analyzer.stage2.candidate_analysis import (
    analyze_candidate_job,
    load_career_profile,
)
from analyzer.llm.stage2_runtime import (
    Stage2DailyLimitReached,
    Stage2NoAvailableModels,
    Stage2JobRequestLimitReached,
    Stage2ConsecutiveRateLimitReached,
)
from database.candidate_job_repository import CandidateJobRepository


DB_PATH = "database/jobs.db"


def run_test_batch(limit: int = 5):
    print("=" * 60)
    print(f"STAGE 2 TEST RUNNER (Batch limit: {limit})")
    print("=" * 60)

    repo = CandidateJobRepository(DB_PATH)
    profile = load_career_profile()

    eligible = repo.get_eligible_stage2_jobs(limit=limit)

    if not eligible:
        print("No eligible jobs found for Stage 2 (or all already processed).")
        repo.close()
        return

    print(f"Retrieved {len(eligible)} eligible jobs for testing.\n")

    processed = 0
    failed = 0

    try:
        for idx, job in enumerate(eligible, 1):
            print("-" * 60)
            print(f"[{idx}/{len(eligible)}] Job #{job['id']} - {job['company']}")
            print(f"Title:    {job['title']}")
            print(f"Location: {job['location']}")
            print(
                f"Stage 1:  Score={job['relevance_score']}, "
                f"Tracks={job['career_tracks']}, Seniority={job['seniority']}"
            )
            print("-" * 60)

            try:
                result = analyze_candidate_job(
                    job=job,
                    stage1_analysis=job,
                    career_profile=profile,
                )

                repo.save_analysis(result)
                processed += 1

                print("\nStage 2 Output:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                print("\nSaved to candidate_job_analysis.")

            except Stage2DailyLimitReached as error:
                print(f"\nSTOPPING: {error}")
                break

            except Stage2NoAvailableModels as error:
                print(f"\nSTOPPING: {error}")
                break

            except (
                Stage2JobRequestLimitReached,
                Stage2ConsecutiveRateLimitReached,
            ) as error:
                failed += 1
                print(f"Limit error for job #{job['id']}: {error}")
                continue

            except Exception as error:
                failed += 1
                print(f"Failed for job #{job['id']}: {error}")
                continue

    finally:
        repo.close()

    print("\n" + "=" * 60)
    print("STAGE 2 TEST BATCH SUMMARY")
    print("=" * 60)
    print(f"Processed: {processed}")
    print(f"Failed:    {failed}")
    print("=" * 60)


if __name__ == "__main__":
    batch_limit = 5
    if len(sys.argv) > 1:
        try:
            batch_limit = int(sys.argv[1])
        except ValueError:
            pass
    run_test_batch(limit=batch_limit)
