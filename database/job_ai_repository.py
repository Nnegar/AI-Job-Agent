import json
import sqlite3


class JobAIRepository:

    def __init__(self, db_path):
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row


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
                json.dumps(
                    analysis.get("career_tracks", []),
                    ensure_ascii=False
                ),
                analysis.get("role_category"),
                analysis.get("seniority"),
                analysis.get("location_assessment"),
                analysis.get("summary"),
                json.dumps(
                    analysis.get("why_relevant", []),
                    ensure_ascii=False
                ),
                json.dumps(
                    analysis.get("concerns", []),
                    ensure_ascii=False
                ),
                analysis.get("recommendation"),
                analysis.get("model"),
            )
        )

        self.connection.commit()


    def get_analysis_by_job_id(self, job_id):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM job_ai_analysis
            WHERE job_id = ?
            """,
            (job_id,)
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return dict(row)


    def close(self):
        self.connection.close()