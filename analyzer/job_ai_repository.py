import json


class JobAIRepository:

    def __init__(self, connection):
        self.connection = connection


    def exists(self, job_id):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT id
            FROM job_ai_screenings
            WHERE job_id = ?
            """,
            (job_id,)
        )

        return cursor.fetchone() is not None



    def save(self, result):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO job_ai_screenings
            (
                job_id,
                company,
                title,
                decision,
                role_category,
                role_summary,
                evidence,
                gaps,
                reasoning,
                model
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["job_id"],
                result["company"],
                result["title"],
                result["decision"],
                result["role_category"],
                result["role_summary"],
                json.dumps(result["evidence"]),
                json.dumps(result["gaps_or_unknowns"]),
                result["reason"],
                result["model"],
            )
        )

        self.connection.commit()
