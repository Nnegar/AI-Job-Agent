"""
Arbeitnow European Tech Jobs Collector.
Fetches jobs from the official Arbeitnow European Job Board API:
https://www.arbeitnow.com/api/job-board-api
Filters for European tech roles and visa sponsorship.
"""

import datetime
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any, Dict, List, Optional

from collector.lever import is_european_location

TARGET_KEYWORDS = [
    "network", "telecom", "5g", "security", "cyber", "qa",
    "test", "automation", "python", "cloud", "devops", "infrastructure",
    "software", "sdet", "linux", "systems", "data", "ai",
]


def _is_relevant_tech_role(title: str, tags: List[str]) -> bool:
    title_lower = title.lower()
    if any(kw in title_lower for kw in TARGET_KEYWORDS):
        return True
    tags_lower = [t.lower() for t in tags]
    return any(any(kw in t for kw in TARGET_KEYWORDS) for t in tags_lower)


def fetch_arbeitnow_jobs(
    since_date: Optional[datetime.datetime] = None,
    max_pages: int = 3,
    filter_europe: bool = True,
) -> List[Dict[str, Any]]:
    collected_jobs = []

    for page in range(1, max_pages + 1):
        url = f"https://www.arbeitnow.com/api/job-board-api?page={page}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Job-Agent/0.2",
            },
        )

        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except (HTTPError, URLError) as error:
            print(f"[Arbeitnow] Could not fetch page {page}: {error}")
            break

        postings = payload.get("data", [])
        if not postings:
            break

        for item in postings:
            created_sec = item.get("created_at")
            job_date = None
            if created_sec:
                try:
                    job_date = datetime.datetime.fromtimestamp(
                        created_sec, tz=datetime.timezone.utc
                    )
                except Exception:
                    job_date = None

            if since_date and job_date and job_date < since_date:
                continue

            title = item.get("title", "").strip()
            tags = item.get("tags") or []
            if not _is_relevant_tech_role(title, tags):
                continue

            location = item.get("location") or "Europe / Remote"
            if filter_europe and not is_european_location(location):
                # If remote is true, accept
                if not item.get("remote"):
                    continue

            collected_jobs.append({
                "source": "arbeitnow",
                "source_job_id": str(item.get("slug") or item.get("url")),
                "company": item.get("company_name", "Unknown").strip(),
                "title": title,
                "location": location,
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "requirements": ", ".join(tags),
                "posted_at": job_date.isoformat() if job_date else None,
                "posting_locations": [location],
            })

    return collected_jobs
