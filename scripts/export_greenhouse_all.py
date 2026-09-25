
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


COMPANIES = {
    "Cloudflare": "cloudflare",
    "Datadog": "datadog",
    "Elastic": "elastic",
}

OUTPUT = Path("reports/full_greenhouse_export.zip")


def main():
    export = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sources": [],
    }

    total = 0

    for company, token in COMPANIES.items():
        url = (
            "https://boards-api.greenhouse.io/v1/boards/"
            f"{token}/jobs?content=true"
        )

        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "AI-Job-Agent/0.1",
            },
        )

        with urlopen(request, timeout=45) as response:
            jobs = json.load(response)["jobs"]

        export["sources"].append({
            "company": company,
            "board_token": token,
            "jobs": jobs,
        })

        total += len(jobs)
        print(f"{company}: {len(jobs)} jobs")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(
        OUTPUT, "w", zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr(
            "all_jobs.json",
            json.dumps(export, ensure_ascii=False),
        )

    print(f"\nTotal exported: {total}")
    print(f"Saved to: {OUTPUT.resolve()}")


if __name__ == "__main__":
    main()
