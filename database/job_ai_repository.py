import sqlite3


class JobAIRepository:

    def __init__(self, db_path):
        self.connection = sqlite3.connect(db_path)

    def save_analysis(self, analysis):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO job_ai_analysis
            (
                job_id,
                relevance_score,
                career_tracks,
                role_category,
                seniority,
                location_assessment,
                summary,
                why_relevant,
                concerns,
                recommendation,
                model
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis["job_id"],
                analysis.get("relevance_score"),
                str(analysis.get("career_tracks")),
                analysis.get("role_category"),
                analysis.get("seniority"),
                analysis.get("location_assessment"),
                analysis.get("summary"),
                str(analysis.get("why_relevant")),
                str(analysis.get("concerns")),
                analysis.get("recommendation"),
                analysis.get("model"),
            )
        )

        self.connection.commit()


    def get_unprocessed_jobs(self):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT jobs.*
            FROM jobs
            LEFT JOIN job_ai_analysis
            ON jobs.id = job_ai_analysis.job_id
            WHERE job_ai_analysis.id IS NULL
            """
        )

        return cursor.fetchall()


    def close(self):
        self.connection.close()