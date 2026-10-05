"""
Ashby Jobs Collector.
Fetches jobs from Ashby's public JSON API: https://api.ashbyhq.com/posting-api/job-board/{company}
Filters by European locations and incremental lookback window.
"""

import datetime
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any, Dict, List, Optional

from collector.lever import is_european_location

DEFAULT_ASHBY_COMPANIES = {
    "Linear": "linear",
}


def fetch_ashby_jobs(
    company_slug: str,
    company_name: str,
    since_date: Optional[datetime.datetime] = None,
    filter_europe: bool = True,
) -> List[Dict[str, Any]]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Job-Agent/0.2",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
    except (HTTPError, URLError) as error:
        print(f"[Ashby] Could not fetch {company_name} ({company_slug}): {error}")
        return []

    jobs_data = data.get("jobs", [])
    collected_jobs = []

    for item in jobs_data:
        published_at_str = item.get("publishedAt")
        job_date = None
        if published_at_str:
            try:
                job_date = datetime.datetime.fromisoformat(
                    published_at_str.replace("Z", "+00:00")
                )
            except Exception:
                job_date = None

        if since_date and job_date and job_date < since_date:
            continue

        location_str = item.get("location") or "Remote"
        secondary_locations = [
            loc.get("location") for loc in (item.get("secondaryLocations") or []) if loc.get("location")
        ]

        if filter_europe and not is_european_location(location_str, secondary_locations):
            continue

        desc = item.get("descriptionHtml") or item.get("descriptionPlain") or ""
        job_url = item.get("jobUrl") or f"https://jobs.ashbyhq.com/{company_slug}/{item['id']}"

        collected_jobs.append({
            "source": "ashby",
            "source_job_id": str(item["id"]),
            "company": company_name,
            "title": item.get("title", "").strip(),
            "location": location_str,
            "url": job_url,
            "description": desc,
            "requirements": item.get("department", ""),
            "posted_at": job_date.isoformat() if job_date else None,
            "posting_locations": [location_str] + secondary_locations,
        })

    return collected_jobs
