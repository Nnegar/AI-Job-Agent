import json
import sqlite3
from typing import Any, Dict, List, Optional


class CandidateJobRepository:
    """
    Repository for Stage 2 candidate-to-job fit analysis.

    Interfaces with `candidate_job_analysis` in SQLite database.
    """

    def __init__(self, db_path: str):
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row

    def get_eligible_stage2_jobs(
        self, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve jobs eligible for Stage 2 analysis.

        Selection criteria:
        1. Analyzed by Stage 1 with recommendation = 'send_to_stage_2'.
        2. Stage 1 relevance_score >= 60 (protects against corrupted legacy records).
        3. Not yet analyzed in Stage 2 (candidate_job_analysis.id IS NULL).

        Ordered by relevance_score descending, then job id ascending.
        """
        cursor = self.connection.cursor()

        query = """
            SELECT
                j.id,
                j.source,
                j.source_job_id,
                j.company,
                j.title,
                j.location,
                j.url,
                j.description,
                j.requirements,
                j.posted_at,
                a.relevance_score,
                a.career_tracks,
                a.role_category,
                a.seniority,
                a.location_assessment,
                a.summary,
                a.why_relevant,
                a.concerns,
                a.recommendation,
                a.model AS stage1_model
            FROM jobs j
            JOIN job_ai_analysis a
                ON j.id = a.job_id
            LEFT JOIN candidate_job_analysis c
                ON j.id = c.job_id
            WHERE a.recommendation = 'send_to_stage_2'
              AND a.relevance_score >= 60
              AND c.id IS NULL
            ORDER BY a.relevance_score DESC, j.id ASC
        """

        if limit is not None and limit > 0:
            query += f" LIMIT {int(limit)}"

        cursor.execute(query)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            data = dict(row)

            # Safely parse JSON fields from Stage 1
            for field in ("career_tracks", "why_relevant", "concerns"):
                raw_val = data.get(field)
                if isinstance(raw_val, str):
                    try:
                        data[field] = json.loads(raw_val)
                    except (json.JSONDecodeError, ValueError):
                        data[field] = []

            results.append(data)

        return results

    def save_analysis(self, analysis: Dict[str, Any]) -> None:
        """
        Save or update a Stage 2 candidate analysis record.
        """
        cursor = self.connection.cursor()

        strengths = analysis.get("strengths", [])
        if not isinstance(strengths, str):
            strengths = json.dumps(strengths, ensure_ascii=False)

        skill_gaps = analysis.get("skill_gaps", [])
        if not isinstance(skill_gaps, str):
            skill_gaps = json.dumps(skill_gaps, ensure_ascii=False)

        concerns = analysis.get("concerns", [])
        if not isinstance(concerns, str):
            concerns = json.dumps(concerns, ensure_ascii=False)

        cursor.execute(
            """
            INSERT OR REPLACE INTO candidate_job_analysis
            (
                job_id,
                match_score,
                technical_fit_score,
                career_track_fit_score,
                career_growth_score,
                ai_resilience_score,
                seniority_fit,
                location_fit,
                primary_track,
                strengths,
                skill_gaps,
                concerns,
                reasoning,
                model
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis["job_id"],
                analysis.get("match_score"),
                analysis.get("technical_fit_score"),
                analysis.get("career_track_fit_score"),
                analysis.get("career_growth_score"),
                analysis.get("ai_resilience_score"),
                analysis.get("seniority_fit"),
                analysis.get("location_fit"),
                analysis.get("primary_track"),
                strengths,
                skill_gaps,
                concerns,
                analysis.get("reasoning", ""),
                analysis.get("model", ""),
            ),
        )

        self.connection.commit()

    def get_analysis_by_job_id(self, job_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve Stage 2 analysis for a given job_id.
        """
        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM candidate_job_analysis
            WHERE job_id = ?
            """,
            (job_id,),
        )

        row = cursor.fetchone()
        if row is None:
            return None

        data = dict(row)
        for field in ("strengths", "skill_gaps", "concerns"):
            raw_val = data.get(field)
            if isinstance(raw_val, str):
                try:
                    data[field] = json.loads(raw_val)
                except (json.JSONDecodeError, ValueError):
                    data[field] = []

        return data

    def close(self) -> None:
        self.connection.close()
