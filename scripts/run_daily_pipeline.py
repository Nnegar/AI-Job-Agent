#!/usr/bin/env python3
"""
Master End-of-Day Pipeline Runner.

Executes the autonomous AI Job Agent end-to-end pipeline:
1. Stage 1: Job-only relevance filtering (on new jobs).
2. Stage 2: Candidate-to-job matching & deep scoring.
3. Stage 3: Final application decisions & shortlisting.
4. Personalization: CV selection, story injection, and cover letter generation.
5. Market Intelligence: Skill demand tracking & candidate gap indexing.
6. Reporting: Generates interactive HTML and Markdown daily digests.
7. (Optional) Starts the interactive dashboard server.

Usage:
    python scripts/run_daily_pipeline.py [--serve] [--report-only]
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analyzer.market.market_analyzer import MarketAnalyzer
from database.application_repository import ApplicationRepository
from database.cover_letter_repository import CoverLetterRepository
from database.stage3_repository import Stage3Repository
from reports.daily_report_generator import generate_daily_reports


def run_stage3_evaluations() -> int:
    from analyzer.stage3.decision_engine import evaluate_stage2_job
    repo = Stage3Repository(str(PROJECT_ROOT / "database" / "jobs.db"))
    unanalyzed = repo.get_stage2_jobs_for_filtering(only_unanalyzed=True)
    if not unanalyzed:
        return 0

    count = 0
    for job in unanalyzed:
        decision = evaluate_stage2_job(job)
        repo.save_stage3_decision(decision)
        count += 1
    return count


def run_personalization(limit: int = None) -> int:
    from scripts.generate_shortlist_letters import fetch_shortlisted_jobs, build_candidate_header
    from analyzer.llm.openrouter_client import OpenRouterClient
    from analyzer.personalization.cv_selector import CVSelector
    from analyzer.personalization.resume_loader import load_resume
    from analyzer.personalization.story_selector import select_personal_context

    jobs = fetch_shortlisted_jobs(db_path=PROJECT_ROOT / "database" / "jobs.db")
    cover_repo = CoverLetterRepository()
    app_repo = ApplicationRepository()
    cv_selector = CVSelector()
    llm_client = None

    generated = 0
    for job in jobs:
        if limit and generated >= limit:
            break
        job_id = job["id"]
        existing = cover_repo.get_draft_by_job_id(job_id)
        if existing:
            continue

        if llm_client is None:
            llm_client = OpenRouterClient()

        track = job.get("primary_track") or "general"
        cv_match = cv_selector.select(job_text=job.get("description", ""), category=track)
        recommended_cv = cv_match["recommended_cv"]
        category = cv_match["category"]

        resume_text = load_resume(recommended_cv)
        context = select_personal_context(category)

        raw_letter = llm_client.generate_cover_letter(
            job={
                "title": job["title"],
                "company": job["company"],
                "description": job.get("description", ""),
            },
            resume=resume_text,
            personal_story=context["stories"],
            candidate_name=context["name"],
        )

        header = build_candidate_header(context)
        final_letter = f"{header}\n\n{raw_letter.strip()}"

        cover_repo.save_draft(
            job_id=job_id,
            recommended_cv=recommended_cv,
            letter_text=final_letter,
            review_status="draft",
        )

        app_repo.upsert_application(
            job_id=job_id,
            status="prepared",
            application_url=job.get("url"),
            notes=f"CV: {recommended_cv} | Track: {category} | Priority: {job['priority'].upper()} | Score: {job['final_score']:.1f}",
        )
        generated += 1

    cover_repo.close()
    app_repo.close()
    return generated


def main():
    parser = argparse.ArgumentParser(description="Run autonomous AI Job Agent daily pipeline.")
    parser.add_argument("--collect", action="store_true", help="Run multi-source collection before evaluation")
    parser.add_argument("--lookback", type=int, default=7, help="Max lookback window in days (default: 7)")
    parser.add_argument("--serve", action="store_true", help="Launch interactive dashboard server after completion")
    parser.add_argument("--port", type=int, default=8080, help="Dashboard port (default: 8080)")
    parser.add_argument("--report-only", action="store_true", help="Only refresh reports and market intelligence without running LLM stages")
    args = parser.parse_args()

    print("\n========================================================")
    print("   AI JOB AGENT — DAILY AUTONOMOUS PIPELINE EXECUTION   ")
    print("========================================================")

    if args.collect and not args.report_only:
        print("\n[Step 0/4] Collecting from European Sources & LinkedIn...")
        from collector.unified_collector import UnifiedCollector
        collector = UnifiedCollector()
        stats = collector.collect_from_all_sources(max_lookback_days=args.lookback)
        collector.close()
        print(f"       -> Fetched {stats['total_fetched']}, skipped {stats['duplicates_skipped']} dupes, saved {stats['new_jobs_saved']} new unique jobs.")

    if not args.report_only:
        # 1. Run Stage 3 Shortlisting
        print("\n[Step 1/4] Checking Stage 3 Shortlist & Decisions...")
        s3_count = run_stage3_evaluations()
        print(f"       -> Evaluated {s3_count} new candidate matches.")

        # 2. Run Personalization & Cover Letters
        print("\n[Step 2/4] Generating Tailored Cover Letters for Shortlist...")
        new_letters = run_personalization()
        print(f"       -> Generated {new_letters} new cover letter packages.")


    # 3. Market Intelligence Tracking
    print("\n[Step 3/4] Indexing Market Intelligence & Skill Demand...")
    market_analyzer = MarketAnalyzer()
    indexed_jobs = market_analyzer.index_all_analyzed_jobs()
    market_analyzer.close()
    print(f"       -> Synced skill demand and candidate gaps across {indexed_jobs} jobs.")

    # 4. Generate Reports
    print("\n[Step 4/4] Compiling Daily Reports & Interactive HTML Dashboard...")
    report_res = generate_daily_reports()
    print(f"       -> Generated Markdown digest: {report_res['md_path']}")
    print(f"       -> Generated HTML dashboard:  {report_res['html_path']}")
    print(f"       -> Latest view available at:  {report_res['latest_html']}")

    print("\n========================================================")
    print("               PIPELINE RUN COMPLETE                    ")
    print(f"Actionable Shortlist: {report_res['jobs_count']} opportunities ready for application.")
    print("========================================================\n")

    if args.serve:
        from scripts.serve_dashboard import run_server
        run_server(port=args.port)
    else:
        print("To launch the interactive dashboard with live status buttons, run:")
        print("    python scripts/serve_dashboard.py\n")


if __name__ == "__main__":
    main()
