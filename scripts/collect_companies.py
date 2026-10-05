import sys
import time
from collections import Counter

from collector.greenhouse import fetch_greenhouse_jobs
from collector.hybrid_filter import filter_jobs_for_ai
from scripts.import_greenhouse import import_jobs


COMPANIES = {
    "Cloudflare": "cloudflare",
    "Datadog": "datadog",
    "Elastic": "elastic",
}


def main():

    save = "--save" in sys.argv

    successful = 0

    for company, token in COMPANIES.items():

        print(
            f"\n{'=' * 45}"
        )

        print(
            f"Company: {company}"
        )

        try:

            if save:

                import_jobs(
                    token,
                    company,
                )

            else:

                jobs = fetch_greenhouse_jobs(
                    token,
                    company,
                )

                candidates, stats = (
                    filter_jobs_for_ai(jobs)
                )

                print(
                    f"Retrieved: {len(jobs)}"
                )

                print(
                    f"Passed initial filter: "
                    f"{len(candidates)}"
                )

                print(
                    "Filter statistics:",
                    dict(stats),
                )

                locations = Counter(
                    job.get(
                        "filter_location_priority",
                        "unknown",
                    )
                    for job in candidates
                )

                print(
                    "Location distribution:",
                    dict(locations),
                )

                print(
                    "\nFirst candidates:"
                )

                for job in candidates[:10]:

                    print(
                        f"- {job['title']} | "
                        f"{', '.join(job.get('posting_locations', []))}"
                    )

            successful += 1

        except RuntimeError as error:

            print(
                f"Could not collect "
                f"{company}: {error}"
            )

        time.sleep(1)

    print(
        f"\nSuccessful company collections: "
        f"{successful}"
    )


if __name__ == "__main__":
    main()