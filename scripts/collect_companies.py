
import sys
import time
from collections import Counter

from collector.greenhouse import fetch_greenhouse_jobs
from collector.job_filter import filter_candidates
from scripts.import_greenhouse import import_jobs
from scripts.screen_candidates import screen_jobs


# Company name -> Greenhouse board token
COMPANIES = {
    "Cloudflare": "cloudflare",
    "Datadog": "datadog",
    "Elastic": "elastic",
}


def main():
    save = "--save" in sys.argv
    successful = 0

    for company, token in COMPANIES.items():
        print(f"\n{'=' * 45}")
        print(f"Company: {company}")

        try:
            if save:
                # Reuse our existing filtered importer.
                import_jobs(token, company)
            else:
                # Preview without changing the database.
                jobs = fetch_greenhouse_jobs(token, company)
                candidates = filter_candidates(jobs)

                print(f"Retrieved: {len(jobs)}")
                print(f"Passed filters: {len(candidates)}")

                locations = Counter(
                    job["location_priority"]
                    for job in candidates
                )

                print("Location distribution:", dict(locations))

                for job in candidates[:10]:
                    print(
                        f"- {job['title']} | "
                        f"{', '.join(job['posting_locations'])}"
                    )

            successful += 1

        except RuntimeError as error:
            print(f"Could not collect {company}: {error}")

        # Avoid sending requests in immediate succession.
        time.sleep(1)

    print(f"\nSuccessful company collections: {successful}")

    if save and successful:
        print("\nRunning experience screening...")
        screen_jobs()


if __name__ == "__main__":
    main()
