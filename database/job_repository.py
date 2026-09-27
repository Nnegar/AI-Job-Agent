import sqlite3


class JobRepository:

    def __init__(self, db_path):

        self.connection = sqlite3.connect(db_path)

        self.connection.row_factory = sqlite3.Row


    def save_job(self, job):

        cursor = self.connection.cursor()

        location = ", ".join(
            job.get("posting_locations") or []
        )

        if not location:
            location = job.get("location", "")

        source_job_id = (
            job.get("external_id")
            or job.get("id")
        )

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
                str(source_job_id),
                job.get("company"),
                job.get("title"),
                location,
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
            SELECT jobs.*
            FROM jobs

            LEFT JOIN job_ai_analysis
                ON jobs.id = job_ai_analysis.job_id

            WHERE job_ai_analysis.id IS NULL

            ORDER BY jobs.id
            """
        )

        return [
            dict(row)
            for row in cursor.fetchall()
        ]


    def get_job_by_id(self, job_id):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM jobs
            WHERE id = ?
            """,
            (job_id,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return dict(row)


    def close(self):

        self.connection.close()