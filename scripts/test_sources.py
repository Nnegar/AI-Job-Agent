import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from collector.lever import fetch_lever_jobs, DEFAULT_LEVER_COMPANIES
from collector.ashby import fetch_ashby_jobs, DEFAULT_ASHBY_COMPANIES
from collector.arbeitnow import fetch_arbeitnow_jobs
from collector.linkedin_guest import fetch_linkedin_guest_jobs

print("=== TESTING LEVER ===")
for comp, slug in DEFAULT_LEVER_COMPANIES.items():
    try:
        jobs = fetch_lever_jobs(slug, comp, filter_europe=False)
        print(f"Lever {comp} (no filter): {len(jobs)} jobs")
        jobs_eu = fetch_lever_jobs(slug, comp, filter_europe=True)
        print(f"Lever {comp} (Europe filter): {len(jobs_eu)} jobs")
        if jobs_eu:
            print("  Sample EU job:", jobs_eu[0]["title"], "|", jobs_eu[0]["location"])
    except Exception as e:
        print(f"Lever {comp} error:", e)

print("\n=== TESTING ASHBY ===")
for comp, slug in DEFAULT_ASHBY_COMPANIES.items():
    try:
        jobs = fetch_ashby_jobs(slug, comp, filter_europe=False)
        print(f"Ashby {comp} (no filter): {len(jobs)} jobs")
        jobs_eu = fetch_ashby_jobs(slug, comp, filter_europe=True)
        print(f"Ashby {comp} (Europe filter): {len(jobs_eu)} jobs")
        if jobs_eu:
            print("  Sample EU job:", jobs_eu[0]["title"], "|", jobs_eu[0]["location"])
    except Exception as e:
        print(f"Ashby {comp} error:", e)

print("\n=== TESTING ARBEITNOW ===")
try:
    jobs = fetch_arbeitnow_jobs(max_pages=2, filter_europe=True)
    print(f"Arbeitnow EU: {len(jobs)} jobs")
    if jobs:
        print("  Sample job:", jobs[0]["title"], "|", jobs[0]["company"], "|", jobs[0]["location"])
except Exception as e:
    print("Arbeitnow error:", e)

print("\n=== TESTING LINKEDIN ===")
try:
    jobs = fetch_linkedin_guest_jobs(keywords="network security engineer", location="Italy", max_results=5)
    print(f"LinkedIn jobs: {len(jobs)} jobs")
    for j in jobs:
        print("  LinkedIn job:", j["title"], "|", j["company"], "|", j["location"])
except Exception as e:
    print("LinkedIn error:", e)
