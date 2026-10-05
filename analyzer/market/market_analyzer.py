"""
Market Intelligence Coordinator & Analyzer.
Synchronizes market skill tracking for all analyzed jobs and compiles market trend analytics.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from analyzer.market.skill_extractor import extract_skills_for_job
from database.market_intelligence_repository import MarketIntelligenceRepository

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "database" / "jobs.db"


class MarketAnalyzer:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.repo = MarketIntelligenceRepository(str(self.db_path))

    def index_all_analyzed_jobs(self, force: bool = False) -> int:
        """
        Scans all jobs in candidate_job_analysis and indexes their skills into job_market_skills.
        Returns the number of jobs processed.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                j.id,
                j.description,
                c.strengths,
                c.skill_gaps,
                c.primary_track
            FROM candidate_job_analysis c
            JOIN jobs j ON j.id = c.job_id
            """
        )
        rows = cursor.fetchall()
        conn.close()

        processed = 0
        for r in rows:
            job_id = r["id"]
            if not force and self.repo.has_skills_for_job(job_id):
                continue

            try:
                strengths = json.loads(r["strengths"]) if r["strengths"] else []
            except Exception:
                strengths = []

            try:
                skill_gaps = json.loads(r["skill_gaps"]) if r["skill_gaps"] else []
            except Exception:
                skill_gaps = []

            skills = extract_skills_for_job(
                job_id=job_id,
                description=r["description"] or "",
                strengths=strengths,
                skill_gaps=skill_gaps,
            )

            self.repo.record_skills(job_id, skills)
            processed += 1

        return processed

    def get_market_intelligence_report(self) -> Dict[str, Any]:
        """
        Compiles the full market intelligence report:
        - Top in-demand technologies overall
        - Top candidate skill gaps (skills to add for highest ROI)
        - Track-specific skill breakdowns
        - Geographic & hiring company distributions
        - Market direction synthesis
        """
        top_skills = self.repo.get_top_market_skills(limit=12)
        top_gaps_shortlist = self.repo.get_top_candidate_gaps(limit=8, shortlisted_only=True)
        top_gaps_all = self.repo.get_top_candidate_gaps(limit=8, shortlisted_only=False)
        track_breakdown = self.repo.get_track_skills_breakdown()
        stats = self.repo.get_market_statistics()

        # Actionable recommendations for the candidate
        high_roi_skills = []
        for g in top_gaps_shortlist:
            skill = g["skill_name"]
            count = g["gap_count"]
            companies = g["companies"].split(",") if g.get("companies") else []
            high_roi_skills.append({
                "skill": skill,
                "category": g["category"],
                "shortlist_mentions": count,
                "companies": [c.strip() for c in companies[:4]],
                "action_recommendation": _generate_recommendation(skill, g["category"]),
            })

        return {
            "stats": stats,
            "top_skills": top_skills,
            "high_roi_skills_to_learn": high_roi_skills,
            "overall_top_gaps": top_gaps_all,
            "track_breakdown": track_breakdown,
        }

    def close(self):
        self.repo.close()


def _generate_recommendation(skill: str, category: str) -> str:
    recommendations = {
        "Kubernetes": "Deploy a containerized microservice or 5G telemetry pipeline on a local k3s/minikube cluster. Highlight pod lifecycle & network policies.",
        "Docker": "Containerize your thesis Python data pipeline and push a clean Dockerfile with multi-stage builds to GitHub.",
        "Terraform": "Write basic Infrastructure-as-Code scripts provisioning cloud networking resources (VPCs, subnets, security groups) on AWS or Azure.",
        "Go (Golang)": "Build a lightweight CLI or network packet counter in Go to demonstrate systems programming competency alongside Python.",
        "SIEM": "Set up a local Elastic/Splunk instance, ingest sample Syslog or Suricata logs, and write basic detection alerts for port scans or brute force.",
        "Playwright / Selenium": "Automate an end-to-end web test suite with Playwright & pytest; assert network response headers and API payloads.",
        "CI/CD": "Configure GitHub Actions workflows running automated flake8 linting and pytest test suites on every pull request.",
        "Prometheus / Grafana": "Expose Prometheus network metrics in a Python script and build a Grafana dashboard monitoring packet throughput and latency.",
        "AWS": "Complete hands-on labs for AWS VPC, Route 53, and EC2 networking fundamentals.",
    }
    return recommendations.get(
        skill,
        f"Build a small, documented GitHub demonstration project showcasing practical usage of {skill} in a networking or security context.",
    )
