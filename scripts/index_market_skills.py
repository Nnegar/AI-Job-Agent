"""
Script to extract and index market skills across all candidate-analyzed jobs in jobs.db.
"""

from analyzer.market.market_analyzer import MarketAnalyzer

def main():
    print("Indexing market skills and candidate gaps across all analyzed jobs...")
    analyzer = MarketAnalyzer()
    count = analyzer.index_all_analyzed_jobs(force=True)
    print(f"Successfully indexed skills for {count} jobs.")

    report = analyzer.get_market_intelligence_report()
    stats = report["stats"]
    print("\n=== MARKET INTELLIGENCE OVERVIEW ===")
    print(f"Total jobs indexed:       {stats['total_jobs_indexed']}")
    print(f"Unique skills tracked:    {stats['unique_skills_tracked']}")
    print(f"Unique gaps identified:   {stats['unique_gaps_identified']}")

    print("\n--- TOP DEMANDED MARKET SKILLS ---")
    for s in report["top_skills"]:
        print(f"  * {s['skill_name']:30s} | {s['category']:18s} | Required in {s['job_count']} jobs")

    print("\n--- TOP CANDIDATE GAPS IN SHORTLISTED ROLES (HIGH ROI TO LEARN) ---")
    for g in report["high_roi_skills_to_learn"]:
        print(f"  * {g['skill']:25s} (in {g['shortlist_mentions']} shortlisted roles) - Companies: {', '.join(g['companies'])}")
        print(f"    -> Recommendation: {g['action_recommendation']}")

    analyzer.close()

if __name__ == "__main__":
    main()
