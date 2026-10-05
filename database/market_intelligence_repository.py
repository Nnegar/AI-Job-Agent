"""
Market Intelligence Repository.
Manages storage, extraction, and querying of market skills and candidate skill gaps.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "jobs.db"
)


class MarketIntelligenceRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._ensure_table()

    def _ensure_table(self):
        cursor = self.connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS job_market_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                skill_name TEXT NOT NULL,
                category TEXT NOT NULL,
                is_gap INTEGER NOT NULL DEFAULT 0,
                context TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(job_id) REFERENCES jobs(id),
                UNIQUE(job_id, skill_name, is_gap)
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_skills_name ON job_market_skills(skill_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_skills_gap ON job_market_skills(is_gap)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_skills_category ON job_market_skills(category)")
        self.connection.commit()

    def record_skills(self, job_id: int, skills: List[Dict[str, Any]]) -> int:
        """
        Record a list of skills for a given job.
        Each skill dict: {"name": str, "category": str, "is_gap": bool/int, "context": Optional[str]}
        """
        if not skills:
            return 0

        cursor = self.connection.cursor()
        inserted = 0
        for s in skills:
            name = s["name"].strip()
            category = s.get("category", "general").strip().lower()
            is_gap = 1 if s.get("is_gap") else 0
            context = s.get("context")

            cursor.execute(
                """
                INSERT INTO job_market_skills (
                    job_id,
                    skill_name,
                    category,
                    is_gap,
                    context,
                    recorded_at
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(job_id, skill_name, is_gap) DO UPDATE SET
                    category = excluded.category,
                    context = COALESCE(excluded.context, job_market_skills.context)
                """,
                (job_id, name, category, is_gap, context),
            )
            inserted += 1

        self.connection.commit()
        return inserted

    def has_skills_for_job(self, job_id: int) -> bool:
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT 1 FROM job_market_skills WHERE job_id = ? LIMIT 1",
            (job_id,),
        )
        return cursor.fetchone() is not None

    def get_top_market_skills(
        self, limit: int = 15, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns the most frequently demanded skills across all analyzed jobs.
        """
        cursor = self.connection.cursor()
        if category:
            cursor.execute(
                """
                SELECT
                    skill_name,
                    category,
                    COUNT(DISTINCT job_id) AS job_count,
                    SUM(CASE WHEN is_gap = 1 THEN 1 ELSE 0 END) AS gap_count
                FROM job_market_skills
                WHERE category = ?
                GROUP BY skill_name, category
                ORDER BY job_count DESC
                LIMIT ?
                """,
                (category, limit),
            )
        else:
            cursor.execute(
                """
                SELECT
                    skill_name,
                    category,
                    COUNT(DISTINCT job_id) AS job_count,
                    SUM(CASE WHEN is_gap = 1 THEN 1 ELSE 0 END) AS gap_count
                FROM job_market_skills
                GROUP BY skill_name, category
                ORDER BY job_count DESC
                LIMIT ?
                """,
                (limit,),
            )
        return [dict(r) for r in cursor.fetchall()]

    def get_top_candidate_gaps(
        self, limit: int = 10, shortlisted_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Returns skills that are most frequently flagged as gaps for the candidate.
        If shortlisted_only=True, only considers jobs approved in Stage 3 ('apply').
        """
        cursor = self.connection.cursor()
        if shortlisted_only:
            query = """
                SELECT
                    ms.skill_name,
                    ms.category,
                    COUNT(DISTINCT ms.job_id) AS gap_count,
                    GROUP_CONCAT(DISTINCT j.company) AS companies
                FROM job_market_skills ms
                JOIN job_stage3_analysis s3 ON ms.job_id = s3.job_id
                JOIN jobs j ON ms.job_id = j.id
                WHERE ms.is_gap = 1 AND s3.decision = 'apply'
                GROUP BY ms.skill_name, ms.category
                ORDER BY gap_count DESC
                LIMIT ?
            """
            cursor.execute(query, (limit,))
        else:
            query = """
                SELECT
                    ms.skill_name,
                    ms.category,
                    COUNT(DISTINCT ms.job_id) AS gap_count,
                    GROUP_CONCAT(DISTINCT j.company) AS companies
                FROM job_market_skills ms
                JOIN jobs j ON ms.job_id = j.id
                WHERE ms.is_gap = 1
                GROUP BY ms.skill_name, ms.category
                ORDER BY gap_count DESC
                LIMIT ?
            """
            cursor.execute(query, (limit,))

        return [dict(r) for r in cursor.fetchall()]

    def get_track_skills_breakdown(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Returns top skills grouped by career track.
        """
        cursor = self.connection.cursor()
        query = """
            SELECT
                s2.primary_track,
                ms.skill_name,
                ms.category,
                COUNT(DISTINCT ms.job_id) AS occurrences,
                SUM(CASE WHEN ms.is_gap = 1 THEN 1 ELSE 0 END) AS gap_occurrences
            FROM job_market_skills ms
            JOIN candidate_job_analysis s2 ON ms.job_id = s2.job_id
            WHERE s2.primary_track IS NOT NULL
            GROUP BY s2.primary_track, ms.skill_name, ms.category
            HAVING occurrences >= 2
            ORDER BY s2.primary_track, occurrences DESC
        """
        cursor.execute(query)
        result: Dict[str, List[Dict[str, Any]]] = {}
        for r in cursor.fetchall():
            track = r["primary_track"]
            if track not in result:
                result[track] = []
            if len(result[track]) < 8:  # top 8 per track
                result[track].append(dict(r))
        return result

    def get_market_statistics(self) -> Dict[str, Any]:
        """
        Returns overall market intelligence stats.
        """
        cursor = self.connection.cursor()
        cursor.execute("SELECT COUNT(DISTINCT job_id) FROM job_market_skills")
        analyzed_jobs = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT skill_name) FROM job_market_skills")
        unique_skills = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT skill_name) FROM job_market_skills WHERE is_gap = 1")
        unique_gaps = cursor.fetchone()[0]

        return {
            "total_jobs_indexed": analyzed_jobs,
            "unique_skills_tracked": unique_skills,
            "unique_gaps_identified": unique_gaps,
        }

    def close(self):
        self.connection.close()
