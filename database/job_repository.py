import sqlite3


class JobRepository:

    def __init__(self, db_path):
        self.connection = sqlite3.connect(db_path)


    def save_job(self, job):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT OR IGNORE INTO jobs
            (
                source,
                source_job_id,
                company,
                title,
                location,
                url,
                description,
                requirements,
                posted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job["source"],
                str(job["id"]),
                job.get("company"),
                job.get("title"),
                job.get("location"),
                job.get("url"),
                job.get("description"),
                job.get("requirements"),
                job.get("posted_at"),
            )
        )

        self.connection.commit()


    def get_unanalyzed_jobs(self):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT
                jobs.*
            FROM jobs

            LEFT JOIN job_ai_analysis
            ON jobs.id = job_ai_analysis.job_id

            WHERE job_ai_analysis.id IS NULL
            """
        )

        return cursor.fetchall()



    def get_job_by_id(self, job_id):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM jobs
            WHERE id = ?
            """,
            (job_id,)
        )

        return cursor.fetchone()



    def close(self):

        self.connection.close()