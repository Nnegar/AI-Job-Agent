"""
Unified Multi-Source Job Collector.
Orchestrates collection across Greenhouse, Lever, Ashby, Arbeitnow, and LinkedIn.
Applies:
1. 7-Day Capped Lookback Window (via SyncRepository).
2. Hybrid Job Relevance Filter.
3. Cross-Source Deduplication (via JobDeduplicator).
4. Direct persistence into jobs.db.
"""

import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from collector.arbeitnow import fetch_arbeitnow_jobs
from collector.ashby import fetch_ashby_jobs, DEFAULT_ASHBY_COMPANIES
from collector.deduplicator import JobDeduplicator
from collector.greenhouse import fetch_greenhouse_jobs
from collector.hybrid_filter import filter_jobs_for_ai
from collector.lever import fetch_lever_jobs, DEFAULT_LEVER_COMPANIES
from collector.linkedin_guest import fetch_linkedin_guest_jobs, DEFAULT_LINKEDIN_QUERIES
from database.job_repository import JobRepository
from database.sync_repository import SyncRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "database" / "jobs.db"

# Greenhouse European-friendly tech & telecom roster
DEFAULT_GREENHOUSE_COMPANIES = {
    "Canonical": "canonical",      # Ubuntu / Telecom / Cloud
    "Deliveroo": "deliveroo",      # UK / European tech
    "Wise": "wise",                # UK / EU fintech & systems
    "Cloudflare": "cloudflare",
    "Datadog": "datadog",
    "Elastic": "elastic",
}


class UnifiedCollector:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.job_repo = JobRepository(str(self.db_path))
        self.sync_repo = SyncRepository(str(self.db_path))
        self.deduplicator = JobDeduplicator(self.db_path)

    def collect_from_all_sources(
        self,
        enable_greenhouse: bool = True,
        enable_lever: bool = True,
        enable_ashby: bool = True,
        enable_arbeitnow: bool = True,
        enable_linkedin: bool = True,
        max_lookback_days: int = 7,
    ) -> Dict[str, Any]:
        """
        Runs the full multi-source collection with capped lookback and deduplication.
        """
        stats = {
            "total_fetched": 0,
            "passed_hybrid_filter": 0,
            "duplicates_skipped": 0,
            "new_jobs_saved": 0,
            "sources_summary": {},
        }

        # 1. Greenhouse Companies
        if enable_greenhouse:
            for company, token in DEFAULT_GREENHOUSE_COMPANIES.items():
                since = self.sync_repo.get_since_date("greenhouse", token, max_lookback_days)
                print(f"[Collector] Fetching Greenhouse: {company} (Since: {since.strftime('%Y-%m-%d')})...")
                try:
                    fetched = fetch_greenhouse_jobs(token, company)
                    saved, dupes = self._process_and_save_jobs(fetched, "greenhouse", token)
                    stats["total_fetched"] += len(fetched)
                    stats["duplicates_skipped"] += dupes
                    stats["new_jobs_saved"] += saved
                    stats["sources_summary"][f"greenhouse:{company}"] = saved
                except Exception as err:
                    print(f"[Collector] Greenhouse error for {company}: {err}")

        # 2. Lever Companies
        if enable_lever:
            for company, slug in DEFAULT_LEVER_COMPANIES.items():
                since = self.sync_repo.get_since_date("lever", slug, max_lookback_days)
                print(f"[Collector] Fetching Lever: {company} (Since: {since.strftime('%Y-%m-%d')})...")
                try:
                    fetched = fetch_lever_jobs(slug, company, since_date=since, filter_europe=True)
                    saved, dupes = self._process_and_save_jobs(fetched, "lever", slug)
                    stats["total_fetched"] += len(fetched)
                    stats["duplicates_skipped"] += dupes
                    stats["new_jobs_saved"] += saved
                    stats["sources_summary"][f"lever:{company}"] = saved
                except Exception as err:
                    print(f"[Collector] Lever error for {company}: {err}")

        # 3. Ashby Companies
        if enable_ashby:
            for company, slug in DEFAULT_ASHBY_COMPANIES.items():
                since = self.sync_repo.get_since_date("ashby", slug, max_lookback_days)
                print(f"[Collector] Fetching Ashby: {company} (Since: {since.strftime('%Y-%m-%d')})...")
                try:
                    fetched = fetch_ashby_jobs(slug, company, since_date=since, filter_europe=True)
                    saved, dupes = self._process_and_save_jobs(fetched, "ashby", slug)
                    stats["total_fetched"] += len(fetched)
                    stats["duplicates_skipped"] += dupes
                    stats["new_jobs_saved"] += saved
                    stats["sources_summary"][f"ashby:{company}"] = saved
                except Exception as err:
                    print(f"[Collector] Ashby error for {company}: {err}")

        # 4. Arbeitnow European Tech Board
        if enable_arbeitnow:
            since = self.sync_repo.get_since_date("arbeitnow", "all_tech", max_lookback_days)
            print(f"[Collector] Fetching Arbeitnow EU (Since: {since.strftime('%Y-%m-%d')})...")
            try:
                fetched = fetch_arbeitnow_jobs(since_date=since, max_pages=2, filter_europe=True)
                saved, dupes = self._process_and_save_jobs(fetched, "arbeitnow", "all_tech")
                stats["total_fetched"] += len(fetched)
                stats["duplicates_skipped"] += dupes
                stats["new_jobs_saved"] += saved
                stats["sources_summary"]["arbeitnow"] = saved
            except Exception as err:
                print(f"[Collector] Arbeitnow error: {err}")

        # 5. LinkedIn European Guest Mode
        if enable_linkedin:
            for q in DEFAULT_LINKEDIN_QUERIES[:3]:  # Top 3 queries per run to avoid 429
                target_key = f"{q['keywords']}:{q['location']}"
                print(f"[Collector] Fetching LinkedIn: '{q['keywords']}' in {q['location']}...")
                try:
                    time_filter = "r604800" if max_lookback_days >= 7 else "r86400"
                    fetched = fetch_linkedin_guest_jobs(
                        keywords=q["keywords"],
                        location=q["location"],
                        time_window=time_filter,
                        max_results=8,
                        delay_between_requests=1.2,
                    )
                    saved, dupes = self._process_and_save_jobs(fetched, "linkedin", target_key)
                    stats["total_fetched"] += len(fetched)
                    stats["duplicates_skipped"] += dupes
                    stats["new_jobs_saved"] += saved
                    stats["sources_summary"][f"linkedin:{target_key}"] = saved
                except Exception as err:
                    print(f"[Collector] LinkedIn error for '{q['keywords']}': {err}")

        return stats

    def _process_and_save_jobs(
        self, raw_jobs: List[Dict[str, Any]], source: str, target: str
    ) -> (int, int):
        if not raw_jobs:
            self.sync_repo.update_sync_state(source, target, jobs_collected=0)
            return 0, 0

        # Filter for AI/technical relevance
        candidates, _ = filter_jobs_for_ai(raw_jobs)
        saved_count = 0
        dupes_count = 0

        for job in candidates:
            is_dup, reason = self.deduplicator.is_duplicate(job)
            if is_dup:
                dupes_count += 1
                continue

            # Save unique job
            self.job_repo.save_job(job)
            self.deduplicator.register_job(job)
            saved_count += 1

        self.sync_repo.update_sync_state(source, target, jobs_collected=saved_count)
        return saved_count, dupes_count

    def close(self):
        self.job_repo.close()
        self.sync_repo.close()
