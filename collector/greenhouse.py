
import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

def extract_posting_locations(job):
    # Prefer the explicit posting-location metadata.
    for field in job.get("metadata") or []:
        if field.get("name") == "Job Posting Location":
            value = field.get("value")

            if isinstance(value, list):
                return value

            if isinstance(value, str) and value:
                return [value]

    # Fall back to the company's office information.
    offices = job.get("offices") or []

    if offices:
        return [
            office["name"]
            for office in offices
            if office.get("name")
        ]

    # Don't mistake "Hybrid" for a geographical location.
    location = job.get("location") or {}
    name = location.get("name", "")

    if name.lower() not in [
        "hybrid", "remote", "in-office"
    ]:
        return [name] if name else []

    return []

def fetch_greenhouse_jobs(board_token, company):
    url = (
        "https://boards-api.greenhouse.io/v1/boards/"
        f"{board_token}/jobs?content=true"
    )

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "AI-Job-Agent/0.1",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)

    except (HTTPError, URLError) as error:
        raise RuntimeError(
            f"Could not fetch {company} jobs: {error}"
        ) from error

    jobs = []

    for item in data["jobs"]:
        jobs.append({
            "external_id": str(item["id"]),
            "title": item["title"],
            "company": company,
            "location": item.get("location", {}).get("name", ""),
            "url": item["absolute_url"],
            "description": item.get("content", ""),
            "source": "greenhouse",
            "posting_locations": extract_posting_locations(item),
        })

    return jobs


if __name__ == "__main__":
    board = sys.argv[1] if len(sys.argv) > 1 else "cloudflare"
    company = sys.argv[2] if len(sys.argv) > 2 else board.title()

    jobs = fetch_greenhouse_jobs(board, company)

    print(f"\nCollected {len(jobs)} jobs from {company}")

    for job in jobs[:10]:
        print(f"\n{job['title']}")
        print(f"Location: {job['location']}")
        print(f"URL: {job['url']}")

