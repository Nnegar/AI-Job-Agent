import csv
import json
import re
import sys
import zipfile
from pathlib import Path

from collector.description_filter import analyze_description
from collector.job_filter import is_relevant_title


SENIOR = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|director|"
    r"head of|lead|manager)\b",
    re.I,
)


ROLE_REVIEW = re.compile(
    r"\b(?:sales|account executive|marketing|recruiter|"
    r"product manager|customer engineer|partner engineer)\b",
    re.I,
)


def load_export(path):
    if str(path).endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            return json.loads(
                archive.read("all_jobs.json")
            )

    return json.loads(
        Path(path).read_text(encoding="utf-8")
    )


def main(path):

    data = load_export(path)

    rows = []

    for source in data["sources"]:

        company = source["company"]

        for job in source["jobs"]:

            evidence = analyze_description(
                job.get("content")
            )

            title = job["title"]

            rows.append(
                {
                    "company": company,
                    "job_id": job["id"],
                    "title": title,
                    "location": job.get(
                        "location", {}
                    ).get("name", ""),
                    "categories": "; ".join(
                        evidence
                    ),
                    "evidence": " | ".join(
                        f"{category}: {examples[0]}"
                        for category, examples
                        in evidence.items()
                    ),
                    "old_title_match":
                        is_relevant_title(title),
                    "senior_title_flag":
                        bool(SENIOR.search(title)),
                    "role_review_flag":
                        bool(ROLE_REVIEW.search(title)),
                    "url":
                        job["absolute_url"],
                }
            )

    output = Path(
        "reports/description_filter_audit.csv"
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    fieldnames = [
        "company",
        "job_id",
        "title",
        "location",
        "categories",
        "evidence",
        "old_title_match",
        "senior_title_flag",
        "role_review_flag",
        "url",
    ]

    with output.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(rows)

    matched = [
        row
        for row in rows
        if row["categories"]
    ]

    newly_found = [
        row
        for row in matched
        if not row["old_title_match"]
    ]

    print(
        "Total postings:",
        len(rows)
    )

    print(
        "Description matches:",
        len(matched)
    )

    print(
        "Missed by original title check:",
        len(newly_found)
    )

    print(
        "Saved:",
        output
    )

    print(
        "\nFirst 20 newly discovered titles:"
    )

    for job in newly_found[:20]:

        print(
            job["company"],
            "|",
            job["title"],
            "|",
            job["categories"],
        )


if __name__ == "__main__":

    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "reports/full_greenhouse_export.zip"
    )

    main(path)