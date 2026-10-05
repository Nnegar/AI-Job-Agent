"""
Run Multi-Source Job Collection.
Fetches new European jobs from Greenhouse, Lever, Ashby, Arbeitnow, and LinkedIn.
Applies capped 7-day lookback and cross-source deduplication.

Usage:
    python scripts/run_collection.py [--source all|greenhouse|lever|ashby|arbeitnow|linkedin] [--lookback 7]
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collector.unified_collector import UnifiedCollector


def main():
    parser = argparse.ArgumentParser(description="Collect jobs from European sources.")
    parser.add_argument(
        "--source",
        choices=["all", "greenhouse", "lever", "ashby", "arbeitnow", "linkedin"],
        default="all",
        help="Target source to collect from (default: all)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=7,
        help="Maximum lookback window in days (default: 7)",
    )
    args = parser.parse_args()

    print("==================================================")
    print("   AI JOB AGENT — MULTI-SOURCE JOB COLLECTION    ")
    print(f"   Target: {args.source.upper()} | Lookback: {args.lookback} days")
    print("==================================================")

    collector = UnifiedCollector()

    enable_gh = args.source in ("all", "greenhouse")
    enable_lever = args.source in ("all", "lever")
    enable_ashby = args.source in ("all", "ashby")
    enable_arbeitnow = args.source in ("all", "arbeitnow")
    enable_linkedin = args.source in ("all", "linkedin")

    stats = collector.collect_from_all_sources(
        enable_greenhouse=enable_gh,
        enable_lever=enable_lever,
        enable_ashby=enable_ashby,
        enable_arbeitnow=enable_arbeitnow,
        enable_linkedin=enable_linkedin,
        max_lookback_days=args.lookback,
    )

    collector.close()

    print("\n==================================================")
    print("COLLECTION SUMMARY")
    print(f"Total Fetched:        {stats['total_fetched']}")
    print(f"Duplicates Skipped:   {stats['duplicates_skipped']}")
    print(f"New Unique Saved:     {stats['new_jobs_saved']}")
    print("By Source Breakdown:")
    for src, count in stats["sources_summary"].items():
        print(f"  • {src:30s} -> {count} new jobs")
    print("==================================================")


if __name__ == "__main__":
    main()
