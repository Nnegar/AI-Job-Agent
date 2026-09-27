import json

from analyzer.job_repository import JobRepository
from analyzer.stage1_job_intelligence import (
    analyze_job_intelligence
)


repo = JobRepository(
    "database/jobs.db"
)


jobs = repo.get_unanalyzed_jobs()


print(
    f"Jobs waiting for AI: {len(jobs)}"
)


for row in jobs[:5]:

    job = {

        "id": row[0],
        "source": row[1],
        "source_job_id": row[2],
        "company": row[3],
        "title": row[4],
        "location": row[5],
        "description": row[7],
    }


    print("\n===================")
    print(job["company"])
    print(job["title"])


    result = analyze_job_intelligence(job)


    print(
        json.dumps(
            result,
            indent=2
        )
    )


    result["job_id"] = job["id"]

    result["career_tracks"] = json.dumps(
        result["career_tracks"]
    )

    result["why_relevant"] = json.dumps(
        result["why_relevant"]
    )

    result["concerns"] = json.dumps(
        result["concerns"]
    )


    repo.save_ai_analysis(result)


repo.close()
