import json
import zipfile

from collector.hybrid_filter import filter_export
from collector.career_scorer import score_job


with zipfile.ZipFile(
    "reports/full_greenhouse_export.zip"
) as archive:

    data = json.loads(
        archive.read("all_jobs.json")
    )


candidates, stretch, stats = filter_export(data)


print("Candidates:", len(candidates))


for item in candidates:

    job = item["job"]

    result = score_job(job)

    print("\n--------------------")
    print(job["title"])
    print(item["company"])

    print(
        "Ranking:",
        result["ranking"][:3]
    )

    print(
        "Matched:",
        result["matched"]
    )
