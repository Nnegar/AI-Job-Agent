"""
Application Repository.
Manages application state transitions and tracking in SQLite database.
Lifecycle: discovered -> shortlisted -> prepared -> applied -> screening -> interview -> offered / rejected / withdrawn
"""

import datetime
import math
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "jobs.db"
)

VALID_STATUSES = {
    "discovered",
    "shortlisted",
    "prepared",
    "applied",
    "screening",
    "interview",
    "interviewing",
    "offered",
    "offer",
    "rejected",
    "withdrawn",
    "archived",
}


def normalize_status(status: str) -> str:
    s = (status or "").strip().lower()
    if s == "interviewing":
        return "interview"
    if s == "offer":
        return "offered"
    return s


class ApplicationRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row

    def upsert_application(
        self,
        job_id: int,
        status: str = "discovered",
        application_url: Optional[str] = None,
        notes: Optional[str] = None,
        applied_date: Optional[str] = None,
    ) -> int:
        norm_status = normalize_status(status)
        if norm_status not in VALID_STATUSES and status not in VALID_STATUSES:
            raise ValueError(f"Invalid application status: '{status}'. Valid statuses: {VALID_STATUSES}")

        # If transitioning to applied/screening/interview and applied_date is not set, set it to today
        if norm_status in ("applied", "screening", "interview", "offered") and not applied_date:
            applied_date = datetime.date.today().isoformat()

        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO applications (
                job_id,
                status,
                application_url,
                notes,
                applied_date,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(job_id) DO UPDATE SET
                status = excluded.status,
                application_url = COALESCE(excluded.application_url, applications.application_url),
                notes = COALESCE(excluded.notes, applications.notes),
                applied_date = COALESCE(excluded.applied_date, applications.applied_date)
            """,
            (job_id, norm_status, application_url, notes, applied_date),
        )
        self.connection.commit()
        return cursor.lastrowid

    def update_status(
        self,
        job_id: int,
        status: str,
        notes: Optional[str] = None,
        applied_date: Optional[str] = None,
    ) -> bool:
        norm_status = normalize_status(status)
        if norm_status not in VALID_STATUSES and status not in VALID_STATUSES:
            raise ValueError(f"Invalid application status: '{status}'. Valid statuses: {VALID_STATUSES}")

        if norm_status in ("applied", "screening", "interview", "offered") and not applied_date:
            applied_date = datetime.date.today().isoformat()

        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE applications
            SET status = ?,
                notes = COALESCE(?, notes),
                applied_date = COALESCE(?, applied_date)
            WHERE job_id = ?
            """,
            (norm_status, notes, applied_date, job_id),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def get_by_job_id(self, job_id: int) -> Optional[Dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT
                a.id,
                a.job_id,
                a.status,
                a.application_url,
                a.applied_date,
                a.notes,
                a.created_at,
                j.company,
                j.title,
                j.location
            FROM applications a
            JOIN jobs j ON j.id = a.job_id
            WHERE a.job_id = ?
            """,
            (job_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        cursor = self.connection.cursor()
        if status:
            cursor.execute(
                """
                SELECT
                    a.id,
                    a.job_id,
                    a.status,
                    a.application_url,
                    a.applied_date,
                    a.notes,
                    a.created_at,
                    j.company,
                    j.title,
                    j.location
                FROM applications a
                JOIN jobs j ON j.id = a.job_id
                WHERE a.status = ?
                ORDER BY a.created_at DESC
                """,
                (normalize_status(status),),
            )
        else:
            cursor.execute(
                """
                SELECT
                    a.id,
                    a.job_id,
                    a.status,
                    a.application_url,
                    a.applied_date,
                    a.notes,
                    a.created_at,
                    j.company,
                    j.title,
                    j.location
                FROM applications a
                JOIN jobs j ON j.id = a.job_id
                ORDER BY a.created_at DESC
                """
            )
        return [dict(row) for row in cursor.fetchall()]

    def get_status_counts(self) -> Dict[str, int]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM applications GROUP BY status")
        counts: Dict[str, int] = {}
        for row in cursor.fetchall():
            s = normalize_status(row[0])
            counts[s] = counts.get(s, 0) + row[1]
        return counts

    def get_pipeline_summary(self) -> Dict[str, int]:
        """
        Returns active pipeline metrics:
        applied, screening, interview, offered, rejected, withdrawn, prepared.
        """
        counts = self.get_status_counts()
        applied = counts.get("applied", 0)
        screening = counts.get("screening", 0)
        interview = counts.get("interview", 0) + counts.get("interviewing", 0)
        offered = counts.get("offered", 0) + counts.get("offer", 0)
        rejected = counts.get("rejected", 0)
        withdrawn = counts.get("withdrawn", 0)
        prepared = counts.get("prepared", 0)

        total_pipeline = applied + screening + interview + offered + rejected + withdrawn
        return {
            "applied": applied,
            "screening": screening,
            "interview": interview,
            "offered": offered,
            "rejected": rejected,
            "withdrawn": withdrawn,
            "prepared": prepared,
            "total_pipeline": total_pipeline,
        }

    def get_action_queue(self) -> List[Dict[str, Any]]:
        """
        Returns actionable jobs that currently require candidate action.
        Only jobs where Stage 3 decided 'apply' and status is 'prepared'.
        Once marked as 'applied', the job vanishes from this list.
        """
        cursor = self.connection.cursor()
        query = """
            SELECT
                j.id,
                j.company,
                j.title,
                j.location,
                j.url,
                j.posted_at,
                j.collected_at,
                s3.decision,
                s3.priority,
                s3.final_score,
                s3.application_method,
                s3.readiness,
                s3.decision_reasons,
                s2.primary_track,
                s2.match_score,
                s2.technical_fit_score,
                s2.career_growth_score,
                s2.strengths,
                s2.skill_gaps,
                s2.reasoning,
                c.recommended_cv,
                c.letter_text,
                c.review_status,
                COALESCE(a.status, 'prepared') AS app_status,
                a.applied_date,
                a.notes
            FROM jobs j
            JOIN job_stage3_analysis s3 ON j.id = s3.job_id
            JOIN candidate_job_analysis s2 ON j.id = s2.job_id
            LEFT JOIN cover_letter_drafts c ON j.id = c.job_id
            LEFT JOIN applications a ON j.id = a.job_id
            WHERE s3.decision = 'apply'
              AND (a.status IS NULL OR a.status = 'prepared')
            ORDER BY
                CASE s3.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                s3.final_score DESC
        """
        cursor.execute(query)
        return [dict(r) for r in cursor.fetchall()]

    def get_pipeline_jobs(self, stage: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Returns all jobs currently active or tracked in the application pipeline:
        applied, screening, interview, offered, rejected, withdrawn.
        """
        cursor = self.connection.cursor()
        query = """
            SELECT
                j.id,
                j.company,
                j.title,
                j.location,
                j.url,
                j.posted_at,
                j.collected_at,
                s3.decision,
                s3.priority,
                s3.final_score,
                s2.primary_track,
                s2.match_score,
                s2.strengths,
                s2.skill_gaps,
                c.recommended_cv,
                c.letter_text,
                a.status AS app_status,
                a.applied_date,
                a.notes,
                a.created_at AS application_created_at
            FROM applications a
            JOIN jobs j ON j.id = a.job_id
            LEFT JOIN job_stage3_analysis s3 ON j.id = s3.job_id
            LEFT JOIN candidate_job_analysis s2 ON j.id = s2.job_id
            LEFT JOIN cover_letter_drafts c ON j.id = c.job_id
            WHERE a.status IN ('applied', 'screening', 'interview', 'interviewing', 'offered', 'offer', 'rejected', 'withdrawn')
        """
        params: List[Any] = []
        if stage:
            norm_stage = normalize_status(stage)
            if norm_stage == "interview":
                query += " AND a.status IN ('interview', 'interviewing')"
            elif norm_stage == "offered":
                query += " AND a.status IN ('offered', 'offer')"
            else:
                query += " AND a.status = ?"
                params.append(norm_stage)

        query += """
            ORDER BY
                CASE a.status
                    WHEN 'interview' THEN 1
                    WHEN 'interviewing' THEN 1
                    WHEN 'screening' THEN 2
                    WHEN 'applied' THEN 3
                    WHEN 'offered' THEN 4
                    WHEN 'offer' THEN 4
                    WHEN 'rejected' THEN 5
                    ELSE 6
                END,
                a.applied_date DESC,
                a.created_at DESC
        """
        cursor.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]

    def get_database_jobs(
        self,
        search: Optional[str] = None,
        company: Optional[str] = None,
        track: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        location: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Full historical database query with multi-field filtering and pagination.
        """
        page = max(1, page)
        limit = max(1, min(10000, limit))
        offset = (page - 1) * limit

        where_clauses: List[str] = []
        params: List[Any] = []

        if search:
            s_clean = f"%{search.strip().lower()}%"
            where_clauses.append("(LOWER(j.company) LIKE ? OR LOWER(j.title) LIKE ? OR LOWER(COALESCE(j.location, '')) LIKE ? OR LOWER(COALESCE(s2.primary_track, '')) LIKE ?)")
            params.extend([s_clean, s_clean, s_clean, s_clean])

        if company and company.lower() != "all":
            where_clauses.append("LOWER(j.company) = ?")
            params.append(company.strip().lower())

        if track and track.lower() != "all":
            where_clauses.append("LOWER(COALESCE(s2.primary_track, '')) = ?")
            params.append(track.strip().lower())

        if priority and priority.lower() != "all":
            where_clauses.append("LOWER(COALESCE(s3.priority, 'none')) = ?")
            params.append(priority.strip().lower())

        if source and source.lower() != "all":
            where_clauses.append("LOWER(j.source) = ?")
            params.append(source.strip().lower())

        if location and location.lower() != "all":
            where_clauses.append("LOWER(COALESCE(j.location, '')) LIKE ?")
            params.append(f"%{location.strip().lower()}%")

        if status and status.lower() != "all":
            norm_st = normalize_status(status)
            if norm_st == "prepared":
                where_clauses.append("(a.status = 'prepared' OR (s3.decision = 'apply' AND a.status IS NULL))")
            elif norm_st == "discovered":
                where_clauses.append("(a.status = 'discovered' OR (a.status IS NULL AND (s3.decision IS NULL OR s3.decision != 'apply')))")
            elif norm_st == "interview":
                where_clauses.append("a.status IN ('interview', 'interviewing')")
            elif norm_st == "offered":
                where_clauses.append("a.status IN ('offered', 'offer')")
            else:
                where_clauses.append("a.status = ?")
                params.append(norm_st)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        count_sql = f"""
            SELECT COUNT(*)
            FROM jobs j
            LEFT JOIN job_stage3_analysis s3 ON j.id = s3.job_id
            LEFT JOIN candidate_job_analysis s2 ON j.id = s2.job_id
            LEFT JOIN applications a ON j.id = a.job_id
            {where_sql}
        """

        cursor = self.connection.cursor()
        cursor.execute(count_sql, params)
        total = cursor.fetchone()[0]

        total_pages = max(1, math.ceil(total / limit))

        data_sql = f"""
            SELECT
                j.id,
                j.source,
                j.company,
                j.title,
                j.location,
                j.url,
                j.posted_at,
                j.collected_at,
                COALESCE(s3.decision, 'unfiltered') AS stage3_decision,
                COALESCE(s3.priority, 'none') AS priority,
                COALESCE(s3.final_score, s2.match_score, 0) AS match_score,
                COALESCE(s2.primary_track, 'general') AS primary_track,
                COALESCE(a.status, CASE WHEN s3.decision = 'apply' THEN 'prepared' ELSE 'discovered' END) AS app_status,
                a.applied_date,
                a.notes
            FROM jobs j
            LEFT JOIN job_stage3_analysis s3 ON j.id = s3.job_id
            LEFT JOIN candidate_job_analysis s2 ON j.id = s2.job_id
            LEFT JOIN applications a ON j.id = a.job_id
            {where_sql}
            ORDER BY
                CASE COALESCE(s3.priority, 'none')
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                    ELSE 4
                END,
                j.id DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(data_sql, params + [limit, offset])
        items = [dict(r) for r in cursor.fetchall()]

        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }

    def get_filter_options(self) -> Dict[str, List[str]]:
        cursor = self.connection.cursor()

        cursor.execute("SELECT DISTINCT company FROM jobs WHERE company IS NOT NULL AND company != '' ORDER BY company")
        companies = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT source FROM jobs WHERE source IS NOT NULL AND source != '' ORDER BY source")
        sources = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT primary_track FROM candidate_job_analysis WHERE primary_track IS NOT NULL ORDER BY primary_track")
        tracks = [r[0] for r in cursor.fetchall()]

        statuses = ["prepared", "applied", "screening", "interview", "offered", "rejected", "withdrawn", "discovered"]
        priorities = ["high", "medium", "low", "none"]

        return {
            "companies": companies,
            "sources": sources,
            "tracks": tracks,
            "statuses": statuses,
            "priorities": priorities,
        }

    def close(self):
        self.connection.close()
