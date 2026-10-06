"""
Lever Jobs Collector.
Fetches jobs from Lever's public JSON API: https://api.lever.co/v0/postings/{company}?mode=json
Filters by European locations and applies incremental lookback window.
"""

import datetime
import json
import re
import urllib.parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any, Dict, List, Optional

EUROPE_LOCATIONS = [
    "europe", "remote europe", "emea", "eu",
    "italy", "milan", "rome", "turin",
    "germany", "berlin", "munich", "frankfurt", "hamburg",
    "netherlands", "amsterdam", "rotterdam", "utrecht", "eindhoven",
    "switzerland", "zurich", "geneva", "lausanne",
    "united kingdom", "uk", "london", "manchester", "edinburgh", "cambridge",
    "ireland", "dublin", "cork",
    "sweden", "stockholm", "gothenburg",
    "austria", "vienna",
    "denmark", "copenhagen",
    "finland", "helsinki",
    "france", "paris",
    "spain", "madrid", "barcelona",
    "portugal", "lisbon", "porto",
]

DEFAULT_LEVER_COMPANIES = {
    "Spotify": "spotify",
    "Palantir": "palantir",
}


def is_european_location(location_str: str, all_locations: Optional[List[str]] = None) -> bool:
    text = (location_str or "").lower()
    if any(loc in text for loc in EUROPE_LOCATIONS):
        return True
    for alt in (all_locations or []):
        if any(loc in alt.lower() for loc in EUROPE_LOCATIONS):
            return True
    return False


def fetch_lever_jobs(
    company_slug: str,
    company_name: str,
    since_date: Optional[datetime.datetime] = None,
    filter_europe: bool = True,
) -> List[Dict[str, Any]]:
    """
    Fetch and normalize jobs from Lever for a specific company slug.
    """
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Job-Agent/0.2",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            postings = json.load(response)
    except (HTTPError, URLError) as error:
        print(f"[Lever] Could not fetch {company_name} ({company_slug}): {error}")
        return []

    collected_jobs = []

    for item in postings:
        # Check created_at (epoch milliseconds)
        created_ms = item.get("createdAt")
        job_date = None
        if created_ms:
            job_date = datetime.datetime.fromtimestamp(
                created_ms / 1000.0, tz=datetime.timezone.utc
            )

        if since_date and job_date and job_date < since_date:
            continue

        categories = item.get("categories") or {}
        primary_loc = categories.get("location") or ""
        all_locs = categories.get("allLocations") or []

        if filter_europe and not is_european_location(primary_loc, all_locs):
            continue

        # Format locations string
        loc_str = ", ".join(all_locs) if all_locs else primary_loc
        if not loc_str:
            loc_str = "Europe / Remote"

        description_html = item.get("description", "")
        description_plain = item.get("descriptionPlain", "")
        desc = description_plain if description_plain else description_html

        # Append lists (qualifications, responsibilities, requirements)
        lists_content = []
        for l in (item.get("lists") or []):
            header = l.get("text") or ""
            content = l.get("content") or ""
            clean_content = re.sub(r"<[^>]+>", " ", content).strip()
            if header or clean_content:
                lists_content.append(f"{header}:\n{clean_content}")

        if lists_content:
            desc += "\n\n" + "\n\n".join(lists_content)

        additional = item.get("additionalPlain") or item.get("additional") or ""
        if additional:
            desc += f"\n\n{additional}"

        collected_jobs.append({
            "source": "lever",
            "source_job_id": str(item["id"]),
            "company": company_name,
            "title": item.get("text", "").strip(),
            "location": loc_str,
            "url": item.get("hostedUrl") or item.get("applyUrl") or "",
            "description": desc,
            "requirements": categories.get("team", ""),
            "posted_at": job_date.isoformat() if job_date else None,
            "posting_locations": all_locs if all_locs else [primary_loc],
        })

    return collected_jobs
