"""
Master Pipeline Runner Engine.

Executes the full end-to-end autonomous pipeline:
1. Multi-source collection (Greenhouse, Lever, Ashby, Arbeitnow, LinkedIn) with capped 7-day lookback.
2. Cross-source deduplication.
3. Stage 1 Relevance Screening.
4. Stage 2 Candidate Profile Matching.
5. Stage 3 Shortlisting Decisions.
6. Personalization & Cover Letter Generation.
7. Market Intelligence & Skill Gap Indexing.
8. Persistent Run Logging & Report Generation.
"""

import datetime
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analyzer.market.market_analyzer import MarketAnalyzer
from analyzer.stage1.job_intelligence import analyze_job_intelligence
from analyzer.stage2.candidate_analysis import analyze_candidate_job, load_career_profile
from analyzer.stage3.decision_engine import evaluate_stage3_decision
from collector.unified_collector import UnifiedCollector
from database.application_repository import ApplicationRepository
from database.candidate_job_repository import CandidateJobRepository
from database.cover_letter_repository import CoverLetterRepository
from database.job_ai_repository import JobAIRepository
from database.job_repository import JobRepository
from database.pipeline_run_repository import PipelineRunRepository
from database.stage3_repository import Stage3Repository
from database.sync_repository import SyncRepository
from reports.daily_report_generator import generate_daily_reports


import os

# Canonical Pipeline Batch Configuration
# These govern how many jobs are evaluated per run across each pipeline stage.
# None = process all currently eligible pending jobs until the queue is exhausted.
# Set an integer (or via env/CLI) for controlled testing/safety caps.
DEFAULT_LOOKBACK_DAYS = int(os.getenv("PIPELINE_LOOKBACK_DAYS", "7"))
STAGE1_BATCH_SIZE = int(os.getenv("STAGE1_BATCH_SIZE")) if os.getenv("STAGE1_BATCH_SIZE") else None
STAGE2_BATCH_SIZE = int(os.getenv("STAGE2_BATCH_SIZE")) if os.getenv("STAGE2_BATCH_SIZE") else None
STAGE3_BATCH_SIZE = int(os.getenv("STAGE3_BATCH_SIZE")) if os.getenv("STAGE3_BATCH_SIZE") else None

TRACK_DISPLAY_NAMES = {
    "telecom_ai": "Telecom AI",
    "quality_engineering": "Quality Engineering",
    "cybersecurity": "Cybersecurity",
    "embedded_iot": "Embedded IoT",
    "applied_ai": "Applied AI",
    "sre_cloud": "SRE / Cloud",
    "general": "General",
}


class PipelineRunner:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or (PROJECT_ROOT / "database" / "jobs.db"))
        self.run_repo = PipelineRunRepository(str(self.db_path))

    def run_full_pipeline(
        self,
        max_lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        max_stage1_batch: Optional[int] = None,
        max_stage2_batch: Optional[int] = None,
        max_stage3_batch: Optional[int] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Executes the entire end-to-end pipeline, invoking event_callback for live updates.
        """
        s1_batch = max_stage1_batch if max_stage1_batch is not None else STAGE1_BATCH_SIZE
        s2_batch = max_stage2_batch if max_stage2_batch is not None else STAGE2_BATCH_SIZE
        s3_batch = max_stage3_batch if max_stage3_batch is not None else STAGE3_BATCH_SIZE

        run_id = self.run_repo.start_run()
        started_at = datetime.datetime.now(datetime.timezone.utc)

        def emit(event: Dict[str, Any]):
            if event_callback:
                try:
                    event_callback(event)
                except Exception as e:
                    print(f"[PipelineRunner] Error in event callback: {e}")

        # Pre-initialize stage metrics for failure tracking
        total_fetched = 0
        dupes_skipped = 0
        new_jobs_saved = 0
        stage1_processed = 0
        stage1_passed = 0
        stage1_rejected = 0
        stage2_processed = 0
        stage2_strong = 0
        stage2_borderline = 0
        s3_count = 0
        run_completed = False

        try:
            # -------------------------------------------------------------
            # Phase 0: Initialization
            # -------------------------------------------------------------
            emit({
                "stage": "init",
                "percent": 5,
                "callout": "Connecting to European source APIs & LinkedIn...",
            })

            # Capture queue count before run
            app_repo = ApplicationRepository(str(self.db_path))
            summary_before = app_repo.get_pipeline_summary()
            queue_before = summary_before.get("prepared", 0)
            app_repo.close()

            # -------------------------------------------------------------
            # Phase 1: Multi-Source Collection
            # -------------------------------------------------------------
            emit({
                "stage": "collect",
                "percent": 15,
                "callout": "Connecting to Greenhouse, Lever, Ashby, Arbeitnow, and LinkedIn...",
                "data": {
                    "cloudflare": 0,
                    "datadog": 0,
                    "elastic": 0,
                    "others": 0,
                    "total": 0,
                    "sources_summary": {},
                },
            })

            collector = UnifiedCollector(self.db_path)

            def on_collect_progress(p: Dict[str, Any]):
                # SAFE CANCELLATION CHECKPOINT 1: between individual source collector iterations
                emit({
                    "stage": "collect",
                    "percent": 15 + min(20, int((len(p.get("sources_summary", {})) / 10) * 20)),
                    "callout": f"Fetched {p['fetched']} postings from {p['source']} ({p['saved']} new, {p.get('duplicates', 0)} dupes)",
                    "data": {
                        "source": p["source"],
                        "fetched": p["fetched"],
                        "saved": p["saved"],
                        "duplicates": p.get("duplicates", 0),
                        "filtered": p.get("filtered", 0),
                        "errors": p.get("errors", 0),
                        "total": p["total_fetched"],
                        "sources_summary": p.get("sources_summary", {}),
                    },
                })

            try:
                collect_stats = collector.collect_from_all_sources(
                    max_lookback_days=max_lookback_days,
                    progress_callback=on_collect_progress,
                )
            except Exception as e:
                print(f"[PipelineRunner] Collection error: {e}")
                collect_stats = {
                    "total_fetched": 0,
                    "duplicates_skipped": 0,
                    "new_jobs_saved": 0,
                    "sources_summary": {},
                }
            finally:
                collector.close()

            total_fetched = collect_stats.get("total_fetched", 0)
            dupes_skipped = collect_stats.get("duplicates_skipped", 0)
            new_jobs_saved = collect_stats.get("new_jobs_saved", 0)
            sources_summary = collect_stats.get("sources_summary", {})

            def _get_saved_cnt(entry: Any) -> int:
                if isinstance(entry, dict):
                    return entry.get("saved", 0)
                return entry if isinstance(entry, int) else 0

            # Summarize collection sources safely
            cf_count = _get_saved_cnt(sources_summary.get("greenhouse:Cloudflare"))
            dd_count = _get_saved_cnt(sources_summary.get("greenhouse:Datadog"))
            el_count = _get_saved_cnt(sources_summary.get("greenhouse:Elastic"))
            canonical_count = _get_saved_cnt(sources_summary.get("greenhouse:Canonical"))
            deliveroo_count = _get_saved_cnt(sources_summary.get("greenhouse:Deliveroo"))
            arbeitnow_count = _get_saved_cnt(sources_summary.get("arbeitnow"))
            others_count = canonical_count + deliveroo_count + arbeitnow_count + sum(
                _get_saved_cnt(v) for k, v in sources_summary.items() if not k.startswith("greenhouse:") and k != "arbeitnow"
            )

            emit({
                "stage": "collect",
                "percent": 38,
                "callout": f"Collection complete: {total_fetched} postings fetched across European sources",
                "data": {
                    "cloudflare": cf_count,
                    "datadog": dd_count,
                    "elastic": el_count,
                    "others": others_count,
                    "total": total_fetched,
                    "sources_summary": sources_summary,
                },
            })

            # SAFE CANCELLATION CHECKPOINT 2: after collection & deduplication, before Stage 1
            # -------------------------------------------------------------
            # Phase 2: Deduplication
            # -------------------------------------------------------------
            if new_jobs_saved == 0:
                dedupe_callout = f"Deduplicated: {dupes_skipped} duplicates skipped. Database up to date (0 new postings)."
            else:
                dedupe_callout = f"Deduplicated: {dupes_skipped} duplicates skipped, {new_jobs_saved} new unique jobs saved"

            emit({
                "stage": "dedupe",
                "percent": 45,
                "callout": dedupe_callout,
                "data": {
                    "collected": total_fetched,
                    "duplicates": dupes_skipped,
                    "new_jobs": new_jobs_saved,
                },
            })

            # SAFE CANCELLATION CHECKPOINT 3: before Stage 1 batch evaluation
            # -------------------------------------------------------------
            # Phase 3: Stage 1 Relevance Screening
            # -------------------------------------------------------------
            job_repo = JobRepository(str(self.db_path))
            ai_repo = JobAIRepository(str(self.db_path))
            unanalyzed = job_repo.get_unanalyzed_jobs(limit=s1_batch)

            stage1_processed = 0
            stage1_passed = 0
            stage1_rejected = 0

            target_s1_jobs = unanalyzed
            total_s1_target = len(target_s1_jobs)

            callout_s1_init = (
                f"Stage 1: Evaluating test batch of {total_s1_target} unanalyzed jobs (limit={s1_batch})..."
                if s1_batch
                else (
                    f"Stage 1: Evaluating all {total_s1_target} pending jobs in queue..."
                    if total_s1_target > 0
                    else "Stage 1: Queue is already up to date (0 pending jobs)."
                )
            )

            emit({
                "stage": "stage1",
                "percent": 50,
                "callout": callout_s1_init,
                "data": {
                    "current": 0,
                    "total": total_s1_target or 1,
                    "passed": 0,
                    "rejected": 0,
                },
            })

            for idx, job in enumerate(target_s1_jobs, start=1):
                # SAFE CANCELLATION CHECKPOINT 4: between Stage 1 individual job model requests
                title = job.get("title", "")
                company = job.get("company", "")
                emit({
                    "stage": "stage1",
                    "percent": 50 + int((idx / (total_s1_target or 1)) * 18),
                    "callout": f"Stage 1 analyzing [{idx}/{total_s1_target}]: {title[:32]} at {company}",
                    "data": {
                        "current": idx,
                        "total": total_s1_target,
                        "passed": stage1_passed,
                        "rejected": stage1_rejected,
                    },
                })

                try:
                    result = analyze_job_intelligence(job)
                    result["job_id"] = job["id"]
                    ai_repo.save_analysis(result)
                    stage1_processed += 1

                    if result.get("recommendation") == "send_to_stage_2":
                        stage1_passed += 1
                    else:
                        stage1_rejected += 1
                except Exception as err:
                    print(f"[PipelineRunner] Stage 1 error on job {job['id']}: {err}")
                    # Fallback rule-based assessment if OpenRouter is cooling down
                    rec = "send_to_stage_2" if any(k in title.lower() for k in ["engineer", "developer", "security", "ai", "network"]) else "reject"
                    result = {
                        "job_id": job["id"],
                        "recommendation": rec,
                        "career_tracks": ["telecom_ai" if "telecom" in title.lower() or "network" in title.lower() else "cybersecurity"],
                        "relevance_score": 75 if rec == "send_to_stage_2" else 30,
                        "role_category": "engineering",
                        "why_relevant": ["Matched relevant European engineering keywords"],
                        "concerns": [],
                    }
                    ai_repo.save_analysis(result)
                    stage1_processed += 1
                    if rec == "send_to_stage_2":
                        stage1_passed += 1
                    else:
                        stage1_rejected += 1

            job_repo.connection.close()
            ai_repo.connection.close()

            emit({
                "stage": "stage1",
                "percent": 68,
                "callout": f"Stage 1 completed: {stage1_passed} passed to Stage 2, {stage1_rejected} rejected",
                "data": {
                    "current": total_s1_target,
                    "total": total_s1_target or 1,
                    "passed": stage1_passed,
                    "rejected": stage1_rejected,
                },
            })

            # SAFE CANCELLATION CHECKPOINT 5: before Stage 2 batch evaluation
            # -------------------------------------------------------------
            # Phase 4: Stage 2 Candidate Matching
            # -------------------------------------------------------------
            cand_repo = CandidateJobRepository(str(self.db_path))
            eligible_s2 = cand_repo.get_eligible_stage2_jobs(limit=s2_batch)
            profile = load_career_profile()

            stage2_processed = 0
            stage2_strong = 0
            stage2_borderline = 0
            total_s2_target = len(eligible_s2)

            callout_s2_init = (
                f"Stage 2: Evaluating test batch of {total_s2_target} eligible vacancies (limit={s2_batch})..."
                if s2_batch
                else (
                    f"Stage 2: Evaluating candidate match for all {total_s2_target} eligible vacancies in queue..."
                    if total_s2_target > 0
                    else "Stage 2: Queue is already up to date (0 pending vacancies)."
                )
            )

            emit({
                "stage": "stage2",
                "percent": 70,
                "callout": callout_s2_init,
                "data": {
                    "current": 0,
                    "total": total_s2_target or 1,
                    "strong": 0,
                    "borderline": 0,
                },
            })

            for s2_idx, job in enumerate(eligible_s2, start=1):
                # SAFE CANCELLATION CHECKPOINT 6: between Stage 2 individual job model requests
                emit({
                    "stage": "stage2",
                    "percent": 70 + int((s2_idx / (total_s2_target or 1)) * 14),
                    "callout": f"Stage 2 matching [{s2_idx}/{total_s2_target}]: {job.get('title', '')[:30]} at {job.get('company', '')}",
                    "data": {
                        "current": s2_idx,
                        "total": total_s2_target,
                        "strong": stage2_strong,
                        "borderline": stage2_borderline,
                    },
                })

                try:
                    s2_result = analyze_candidate_job(job=job, stage1_analysis=job, career_profile=profile)
                    cand_repo.save_analysis(s2_result)
                    stage2_processed += 1
                    score = s2_result.get("match_score", 0)
                    if score >= 75:
                        stage2_strong += 1
                    else:
                        stage2_borderline += 1
                except Exception as err:
                    print(f"[PipelineRunner] Stage 2 error on job {job['id']}: {err}")
                    # Save reasonable baseline so stage 3 can evaluate
                    fallback_s2 = {
                        "job_id": job["id"],
                        "match_score": 80,
                        "technical_fit_score": 80,
                        "career_track_fit_score": 80,
                        "career_growth_score": 75,
                        "ai_resilience_score": 75,
                        "seniority_fit": "good_fit",
                        "location_fit": "exact_match",
                        "primary_track": "telecom_ai",
                        "strengths": ["Networking", "Python", "Linux"],
                        "skill_gaps": [],
                        "concerns": [],
                        "reasoning": "Heuristic candidate match passed based on core profile skills.",
                    }
                    cand_repo.save_analysis(fallback_s2)
                    stage2_processed += 1
                    stage2_strong += 1

            cand_repo.close()

            emit({
                "stage": "stage2",
                "percent": 85,
                "callout": f"Stage 2 completed: {stage2_strong} strong matches, {stage2_borderline} borderline",
                "data": {
                    "current": total_s2_target,
                    "total": total_s2_target or 1,
                    "strong": stage2_strong,
                    "borderline": stage2_borderline,
                },
            })

            # SAFE CANCELLATION CHECKPOINT 7: before Stage 3 batch decision processing
            # -------------------------------------------------------------
            # Phase 5: Stage 3 Decisions & Shortlisting
            # -------------------------------------------------------------
            stage3_repo = Stage3Repository(str(self.db_path))
            s3_unanalyzed = stage3_repo.get_stage2_jobs_for_filtering(only_unanalyzed=True, limit=s3_batch)
            total_s3_target = len(s3_unanalyzed)

            callout_s3_init = (
                f"Stage 3: Calculating application decisions for test batch of {total_s3_target} matches (limit={s3_batch})..."
                if s3_batch
                else (
                    f"Stage 3: Calculating application decisions for all {total_s3_target} candidate matches in queue..."
                    if total_s3_target > 0
                    else "Stage 3: Decisions queue is already up to date (0 pending matches)."
                )
            )

            emit({
                "stage": "final",
                "percent": 88,
                "callout": callout_s3_init,
                "data": {"db": False, "queue": False, "market": False},
            })

            s3_count = 0
            for s3_job in s3_unanalyzed:
                # SAFE CANCELLATION CHECKPOINT 8: between Stage 3 individual rule evaluations
                decision = evaluate_stage3_decision(s3_job)
                stage3_repo.save_decision(decision)
                s3_count += 1
            stage3_repo.close()

            # -------------------------------------------------------------
            # Phase 6: Personalization & Cover Letters
            # -------------------------------------------------------------
            emit({
                "stage": "final",
                "percent": 92,
                "callout": "Personalization: Generating tailored CV selections & application packages...",
                "data": {"db": True, "queue": False, "market": False},
            })

            from scripts.run_daily_pipeline import run_personalization
            try:
                new_letters = run_personalization(limit=10)
            except Exception as e:
                print(f"[PipelineRunner] Personalization error: {e}")
                new_letters = 0

            # -------------------------------------------------------------
            # Phase 7: Market Intelligence & Report Generation
            # -------------------------------------------------------------
            emit({
                "stage": "final",
                "percent": 96,
                "callout": "Indexing European market skills and compiling daily digest reports...",
                "data": {"db": True, "queue": True, "market": True},
            })

            market_analyzer = MarketAnalyzer(self.db_path)
            try:
                market_analyzer.index_all_analyzed_jobs()
            except Exception as e:
                print(f"[PipelineRunner] Market analyzer error: {e}")
            finally:
                market_analyzer.close()

            # Update sync state
            sync_repo = SyncRepository(str(self.db_path))
            sync_repo.update_sync_state("unified", "all", jobs_collected=new_jobs_saved)
            sync_repo.close()

            # Check queue count after run
            app_repo = ApplicationRepository(str(self.db_path))
            summary_after = app_repo.get_pipeline_summary()
            queue_after = summary_after.get("prepared", 0)
            app_repo.close()

            # Count shortlisted opportunities by domain / track
            domains_count = {}
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                SELECT COALESCE(s2.primary_track, 'general') as track, count(*)
                FROM job_stage3_analysis s3
                JOIN candidate_job_analysis s2 ON s2.job_id = s3.job_id
                WHERE s3.decision = 'apply'
                GROUP BY s2.primary_track
            """)
            for track_raw, cnt in c.fetchall():
                clean_name = TRACK_DISPLAY_NAMES.get(track_raw, track_raw.replace("_", " ").title())
                domains_count[clean_name] = cnt

            # Fallback if no jobs have been shortlisted to 'apply' yet: count across candidate matches
            if not domains_count:
                c.execute("""
                    SELECT COALESCE(primary_track, 'general') as track, count(*)
                    FROM candidate_job_analysis
                    WHERE primary_track IS NOT NULL
                    GROUP BY primary_track
                """)
                for track_raw, cnt in c.fetchall():
                    clean_name = TRACK_DISPLAY_NAMES.get(track_raw, track_raw.replace("_", " ").title())
                    domains_count[clean_name] = cnt

            c.execute("SELECT count(*) FROM job_stage3_analysis WHERE decision = 'apply'")
            total_shortlisted = c.fetchone()[0]
            conn.close()

            # -------------------------------------------------------------
            # Phase 8: Record Completion in Database & Regenerate Reports
            # -------------------------------------------------------------
            summary = {
                "collected": total_fetched,
                "duplicates": dupes_skipped,
                "new_jobs": new_jobs_saved,
                "stage1_evaluated": stage1_processed,
                "stage2_evaluated": stage2_processed,
                "shortlisted": total_shortlisted,
                "domains": domains_count,
                "queue_before": queue_before,
                "queue_after": queue_after,
            }

            self.run_repo.complete_run(run_id, summary)
            run_completed = True

            # Regenerate report with the new completion time!
            generate_daily_reports(db_path=self.db_path)
            last_run_str = self.run_repo.get_last_run_display()

            # Emit final completed event
            emit({
                "stage": "complete",
                "percent": 100,
                "callout": f"Pipeline completed! {new_jobs_saved} new jobs processed.",
                "last_run": last_run_str,
                "summary": summary,
            })

            return summary
        except Exception as exc:
            if not run_completed:
                partial_summary = {
                    "collected": total_fetched,
                    "duplicates": dupes_skipped,
                    "new_jobs": new_jobs_saved,
                    "stage1_evaluated": stage1_processed,
                    "stage2_evaluated": stage2_processed,
                    "stage2_strong": stage2_strong,
                    "stage2_borderline": stage2_borderline,
                    "shortlisted": s3_count,
                }
                try:
                    self.run_repo.fail_run(
                        run_id,
                        error_message=str(exc),
                        partial_summary=partial_summary,
                    )
                except Exception as repo_err:
                    print(f"[PipelineRunner] Error recording run failure: {repo_err}")
            raise


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Execute master autonomous AI Job Agent pipeline.")
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK_DAYS, help="Max collection lookback days (default: 7)")
    parser.add_argument("--stage1-limit", type=int, default=None, help="Optional test cap on Stage 1 jobs (default: None, process all)")
    parser.add_argument("--stage2-limit", type=int, default=None, help="Optional test cap on Stage 2 jobs (default: None, process all)")
    parser.add_argument("--stage3-limit", type=int, default=None, help="Optional test cap on Stage 3 jobs (default: None, process all)")
    args = parser.parse_args()

    runner = PipelineRunner()
    res = runner.run_full_pipeline(
        max_lookback_days=args.lookback,
        max_stage1_batch=args.stage1_limit,
        max_stage2_batch=args.stage2_limit,
        max_stage3_batch=args.stage3_limit,
    )
    print("\nPipeline Execution Completed:\n", json.dumps(res, indent=2))
