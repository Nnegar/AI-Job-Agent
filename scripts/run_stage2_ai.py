"""
Stage 2 Batch Runner: Candidate-to-Job Matching.

Processes eligible jobs from database/jobs.db that passed Stage 1,
evaluating them against profile/career_profile.yaml.
"""

import argparse
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


def main():
    parser = argparse.ArgumentParser(
        description="Run Stage 2 Candidate-to-Job Fit AI evaluation."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of jobs to analyze in this run.",
    )
    args = parser.parse_args()

    repo = CandidateJobRepository(DB_PATH)
    profile = load_career_profile()

    processed = 0
    failed = 0

    try:
        jobs = repo.get_eligible_stage2_jobs(limit=args.limit)

        print("=" * 60)
        print("STAGE 2 BATCH RUNNER")
        print("=" * 60)
        print(f"Jobs waiting for Stage 2 AI: {len(jobs)}")
        if args.limit:
            print(f"Processing limit: {args.limit}")

        for idx, job in enumerate(jobs, 1):
            print("\n" + "=" * 60)
            print(f"[{idx}/{len(jobs)}] Job ID:   {job['id']}")
            print(f"Company:  {job['company']}")
            print(f"Title:    {job['title']}")
            print(f"Location: {job['location']}")
            print(f"Stage 1 Relevance: {job['relevance_score']} | Tracks: {job['career_tracks']}")
            print("=" * 60)

            try:
                result = analyze_candidate_job(
                    job=job,
                    stage1_analysis=job,
                    career_profile=profile,
                )

                repo.save_analysis(result)
                processed += 1

                print(
                    json.dumps(
                        result,
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                print("Saved to candidate_job_analysis.")

            except Stage2DailyLimitReached as error:
                print("\nSTOPPING STAGE 2 (Daily limit reached)")
                print(error)
                break

            except Stage2NoAvailableModels as error:
                print("\nSTOPPING STAGE 2 (No models available)")
                print(error)
                break

            except (
                Stage2JobRequestLimitReached,
                Stage2ConsecutiveRateLimitReached,
            ) as error:
                failed += 1
                print(
                    f"Stage 2 request limit reached for job {job['id']}: {error}"
                )
                continue

            except Exception as error:
                failed += 1
                print(f"Stage 2 failed for job {job['id']}: {error}")
                continue

    finally:
        repo.close()

    print("\n" + "=" * 60)
    print("STAGE 2 SUMMARY")
    print("=" * 60)
    print(f"Processed: {processed}")
    print(f"Failed:    {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()
