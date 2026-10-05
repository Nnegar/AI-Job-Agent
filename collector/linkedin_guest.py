"""
LinkedIn Safe Guest Collector.
Collects jobs without credentials using LinkedIn's public guest search API.
Supports time-window filtering (f_TPR=r604800 for 7 days, f_TPR=r86400 for 24h).
Implements polite pacing and rate-limit safety.
"""

import datetime
import re
import time
import urllib.parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

DEFAULT_LINKEDIN_QUERIES = [
    {"keywords": "5G network", "location": "Italy"},
    {"keywords": "network security engineer", "location": "Italy"},
    {"keywords": "QA automation engineer", "location": "Italy"},
    {"keywords": "network engineer", "location": "Germany"},
    {"keywords": "5G analytics", "location": "Netherlands"},
]


def extract_job_id_from_url(url: str) -> Optional[str]:
    match = re.search(r"(\d{8,12})", url)
    return match.group(1) if match else None


def fetch_job_description(job_id: str, timeout: int = 15) -> str:
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENTS[0],
            "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            soup = BeautifulSoup(resp.read(), "html.parser")
            desc_div = soup.find("div", class_="show-more-less-html__markup")
            return desc_div.get_text("\n", strip=True) if desc_div else ""
    except Exception as e:
        return ""


def fetch_linkedin_guest_jobs(
    keywords: str,
    location: str,
    time_window: str = "r604800",  # r604800 = 7 days, r86400 = 24 hours
    max_results: int = 15,
    delay_between_requests: float = 1.5,
) -> List[Dict[str, Any]]:
    """
    Safely queries LinkedIn public guest search for a specific keyword and European location.
    """
    params = {
        "keywords": keywords,
        "location": location,
        "f_TPR": time_window,
        "start": 0,
    }
    encoded_query = urllib.parse.urlencode(params)
    search_url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?{encoded_query}"

    req = Request(
        search_url,
        headers={
            "User-Agent": USER_AGENTS[0],
            "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
        },
    )

    try:
        with urlopen(req, timeout=25) as resp:
            soup = BeautifulSoup(resp.read(), "html.parser")
    except HTTPError as e:
        if e.code == 429:
            print(f"[LinkedIn] Rate-limited (HTTP 429) for '{keywords}' in '{location}'. Skipping query.")
            return []
        print(f"[LinkedIn] HTTP error {e.code} for '{keywords}': {e}")
        return []
    except Exception as e:
        print(f"[LinkedIn] Error querying '{keywords}': {e}")
        return []

    cards = soup.find_all("li")
    collected = []

    for card in cards[:max_results]:
        title_el = card.find("h3", class_="base-search-card__title")
        company_el = card.find("h4", class_="base-search-card__subtitle")
        location_el = card.find("span", class_="job-search-card__location")
        link_el = card.find("a", class_="base-card__full-link")

        if not title_el or not link_el:
            continue

        raw_url = link_el.get("href", "")
        job_id = extract_job_id_from_url(raw_url)
        if not job_id:
            continue

        title = title_el.get_text(strip=True)
        company = company_el.get_text(strip=True) if company_el else "Unknown"
        job_location = location_el.get_text(strip=True) if location_el else location

        # Polite pacing before details fetch
        time.sleep(delay_between_requests)
        description = fetch_job_description(job_id)

        clean_url = raw_url.split("?")[0] if raw_url else f"https://www.linkedin.com/jobs/view/{job_id}"

        collected.append({
            "source": "linkedin",
            "source_job_id": job_id,
            "company": company,
            "title": title,
            "location": job_location,
            "url": clean_url,
            "description": description or f"{title} at {company} in {job_location}",
            "requirements": keywords,
            "posted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "posting_locations": [job_location],
        })

    return collected
