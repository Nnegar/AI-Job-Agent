
import sqlite3
import json
import yaml
from analyzer.cv_selector import CVSelector

from analyzer.scorer import JobScorer



def load_profile():

    with open("profile/career_profile.yaml") as file:
        return yaml.safe_load(file)



def get_jobs():

    connection = sqlite3.connect(
        "database/jobs.db"
    )

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id, title, description
        FROM jobs
        """
    )

    jobs = cursor.fetchall()

    connection.close()

    return jobs



def save_analysis(job_id, result):

    connection = sqlite3.connect(
        "database/jobs.db"
    )

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE jobs

	SET
	match_score = ?,
	matched_skills = ?,
	recommended_cv = ?,
	category = ?,
	analysis_status = ?

        WHERE id = ?
	        """,

        (
            (
	result["total_score"],
	json.dumps(result),
	result["recommended_cv"],
	result["category"],
	"completed",
	job_id
	)    )
	)

    connection.commit()
    connection.close()



profile = load_profile()

scorer = JobScorer()

cv_selector = CVSelector()

jobs = get_jobs()


for job in jobs:

    job_data = {

        "title": job[1],

        "description": job[2] or ""

    }


    result = scorer.score(job_data)
    cv_result = cv_selector.select(
    job_data["title"] + " " + job_data["description"]
    )

    result["recommended_cv"] = cv_result["recommended_cv"]

    result["category"] = cv_result["category"]

    save_analysis(
        job[0],
        result
    )


    print(
        job[1],
        "→",
        result["total_score"]
    )
