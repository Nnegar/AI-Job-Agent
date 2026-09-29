"""
Stage 3 Runner: Final Application Filter and Daily Shortlist Generator.

Runs the Stage 3 decision engine across all Stage 2 candidate evaluations,
stores final decisions in job_stage3_analysis, and outputs the Daily Shortlist.
"""

import argparse
import sys
from pathlib import Path
from typing import List

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analyzer.stage3.decision_engine import (
    evaluate_stage3_decision,
    load_profile_rules,
)
from database.stage3_repository import Stage3Repository


DB_PATH = "database/jobs.db"


def run_stage3(re_evaluate_all: bool = True):
    print("=" * 65)
    print("STAGE 3: FINAL APPLICATION FILTER & SHORTLIST ENGINE")
    print("=" * 65)

    repo = Stage3Repository(DB_PATH)
    profile = load_profile_rules()

    jobs = repo.get_stage2_jobs_for_filtering(only_unanalyzed=not re_evaluate_all)
    print(f"Jobs for Stage 3 evaluation: {len(jobs)}\n")

    decisions_count = {"apply": 0, "manual_review": 0, "skip": 0}
    priorities_count = {"high": 0, "medium": 0, "low": 0, "none": 0}

    for job in jobs:
        decision_result = evaluate_stage3_decision(job, profile)
        repo.save_decision(decision_result)

        decisions_count[decision_result["decision"]] += 1
        priorities_count[decision_result["priority"]] += 1

    print("Stage 3 Filtering Complete.")
    print("-" * 65)
    print(f"Decisions:  Apply={decisions_count['apply']} | "
          f"Manual Review={decisions_count['manual_review']} | "
          f"Skip={decisions_count['skip']}")
    print(f"Priorities: High={priorities_count['high']} | "
          f"Medium={priorities_count['medium']} | "
          f"Low={priorities_count['low']} | "
          f"None={priorities_count['none']}")
    print("=" * 65)

    # Output formatted Daily Job Intelligence Shortlist
    print_daily_shortlist(repo)
    repo.close()


def print_daily_shortlist(repo: Stage3Repository):
    high_priority = repo.get_shortlist(decision="apply", priority="high")
    medium_priority = repo.get_shortlist(decision="apply", priority="medium")
    manual_review = repo.get_shortlist(decision="manual_review")

    print("\n" + "#" * 65)
    print("DAILY JOB INTELLIGENCE SHORTLIST")
    print("#" * 65)

    print(f"\n[SECTION 1: HIGH PRIORITY APPLICATIONS] ({len(high_priority)} opportunities)")
    print("=" * 65)
    for idx, item in enumerate(high_priority, 1):
        print(f"\n{idx}. [{item['company']}] {item['title']}")
        print(f"   Score:     Final={item['final_score']} (Match={item['match_score']}, TechFit={item['technical_fit_score']})")
        print(f"   Location:  {item['location']} | Track: {item['primary_track']} | Seniority: {item['seniority_fit']}")
        print(f"   Readiness: {item['readiness'].upper()} | Method: {item['application_method']}")
        print(f"   URL:       {item['url']}")
        print("   Reasons:")
        for r in item["decision_reasons"][:3]:
            print(f"     * {r}")

    if medium_priority:
        print(f"\n\n[SECTION 2: MEDIUM PRIORITY APPLICATIONS] ({len(medium_priority)} opportunities)")
        print("=" * 65)
        for idx, item in enumerate(medium_priority, 1):
            print(f"\n{idx}. [{item['company']}] {item['title']}")
            print(f"   Score:     Final={item['final_score']} (Match={item['match_score']}) | Location: {item['location']}")
            print(f"   URL:       {item['url']}")

    if manual_review:
        print(f"\n\n[SECTION 3: MANUAL REVIEW RECOMMENDED] ({len(manual_review)} opportunities)")
        print("=" * 65)
        for idx, item in enumerate(manual_review[:10], 1):
            print(f"{idx}. [{item['company']}] {item['title']} - {item['location']} (Score: {item['final_score']})")
        if len(manual_review) > 10:
            print(f"   ... and {len(manual_review) - 10} more in database.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Stage 3 Final Application Filter.")
    parser.add_argument(
        "--all",
        action="store_true",
        default=True,
        help="Re-evaluate all Stage 2 jobs (default: True).",
    )
    args = parser.parse_args()
    run_stage3(re_evaluate_all=args.all)
