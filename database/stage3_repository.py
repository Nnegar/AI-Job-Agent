"""
Stage 3 Repository: Final Application Decisions and Shortlist.

Interfaces with `job_stage3_analysis` in SQLite database.
"""

import json
import sqlite3
from typing import Any, Dict, List, Optional


class Stage3Repository:
    def __init__(self, db_path: str):
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row

    def get_stage2_jobs_for_filtering(
        self, only_unanalyzed: bool = True, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve jobs that have completed Stage 2 analysis.
        If only_unanalyzed is True, returns jobs not yet in job_stage3_analysis.
        """
        cursor = self.connection.cursor()

        query = """
            SELECT
                j.id,
                j.company,
                j.title,
                j.location,
                j.url,
                j.description,
                j.source,
                j.posted_at,
                -- Stage 1 fields
                a.relevance_score,
                a.career_tracks,
                a.role_category,
                a.seniority,
                a.location_assessment,
                a.summary,
                -- Stage 2 fields
                c.match_score,
                c.technical_fit_score,
                c.career_track_fit_score,
                c.career_growth_score,
                c.ai_resilience_score,
                c.seniority_fit,
                c.location_fit,
                c.primary_track,
                c.strengths,
                c.skill_gaps,
                c.concerns,
                c.reasoning,
                c.model AS stage2_model
            FROM jobs j
            JOIN job_ai_analysis a ON j.id = a.job_id
            JOIN candidate_job_analysis c ON j.id = c.job_id
            LEFT JOIN job_stage3_analysis s ON j.id = s.job_id
        """

        if only_unanalyzed:
            query += " WHERE s.id IS NULL"

        query += " ORDER BY c.match_score DESC, j.id ASC"

        if limit is not None and limit > 0:
            query += f" LIMIT {int(limit)}"

        cursor.execute(query)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            data = dict(row)
            for json_field in ("career_tracks", "strengths", "skill_gaps", "concerns"):
                raw = data.get(json_field)
                if isinstance(raw, str):
                    try:
                        data[json_field] = json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        data[json_field] = []
            results.append(data)

        return results

    def save_decision(self, decision: Dict[str, Any]) -> None:
        """
        Save or replace a Stage 3 application decision.
        """
        cursor = self.connection.cursor()

        reasons = decision.get("decision_reasons", [])
        if not isinstance(reasons, str):
            reasons = json.dumps(reasons, ensure_ascii=False)

        cursor.execute(
            """
            INSERT OR REPLACE INTO job_stage3_analysis
            (
                job_id,
                decision,
                priority,
                final_score,
                application_method,
                readiness,
                decision_reasons
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision["job_id"],
                decision["decision"],
                decision["priority"],
                float(decision["final_score"]),
                decision.get("application_method", "manual"),
                decision.get("readiness", "ready"),
                reasons,
            ),
        )
        self.connection.commit()

    def get_decision_by_job_id(self, job_id: int) -> Optional[Dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT *
            FROM job_stage3_analysis
            WHERE job_id = ?
            """,
            (job_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        data = dict(row)
        reasons = data.get("decision_reasons")
        if isinstance(reasons, str):
            try:
                data["decision_reasons"] = json.loads(reasons)
            except (json.JSONDecodeError, ValueError):
                data["decision_reasons"] = []
        return data

    def get_shortlist(
        self,
        decision: Optional[str] = None,
        priority: Optional[str] = None,
        min_final_score: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve formatted shortlist of jobs with full Stage 1, 2, and 3 attributes.
        """
        cursor = self.connection.cursor()

        query = """
            SELECT
                j.id,
                j.company,
                j.title,
                j.location,
                j.url,
                a.relevance_score,
                a.career_tracks,
                c.match_score,
                c.technical_fit_score,
                c.career_growth_score,
                c.ai_resilience_score,
                c.seniority_fit,
                c.location_fit,
                c.primary_track,
                c.strengths,
                c.skill_gaps,
                c.concerns,
                c.reasoning,
                s.decision,
                s.priority,
                s.final_score,
                s.application_method,
                s.readiness,
                s.decision_reasons,
                s.created_at AS decision_created_at
            FROM jobs j
            JOIN job_ai_analysis a ON j.id = a.job_id
            JOIN candidate_job_analysis c ON j.id = c.job_id
            JOIN job_stage3_analysis s ON j.id = s.job_id
            WHERE 1=1
        """

        params = []
        if decision:
            query += " AND s.decision = ?"
            params.append(decision)
        if priority:
            query += " AND s.priority = ?"
            params.append(priority)
        if min_final_score is not None:
            query += " AND s.final_score >= ?"
            params.append(min_final_score)

        query += " ORDER BY s.final_score DESC, c.match_score DESC, j.id ASC"

        if limit is not None and limit > 0:
            query += f" LIMIT {int(limit)}"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            data = dict(row)
            for json_field in ("career_tracks", "strengths", "skill_gaps", "concerns", "decision_reasons"):
                raw = data.get(json_field)
                if isinstance(raw, str):
                    try:
                        data[json_field] = json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        data[json_field] = []
            results.append(data)

        return results

    def close(self) -> None:
        self.connection.close()
