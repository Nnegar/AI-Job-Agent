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
        - Domain momentum ("Where your target market is moving")
        - Candidate skill position matrix ("Your skill position: Market vs You -> Action")
        - Top in-demand technologies overall
        - Top candidate skill gaps (skills to add for highest ROI)
        - Track-specific skill breakdowns
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

        # Where your target market is moving (Domain Momentum)
        domain_momentum = [
            {
                "domain": "NETWORK SECURITY",
                "score": 92,
                "status": "High",
                "trend_class": "trend-high",
                "description": "Zero Trust architecture, threat modeling, SIEM log telemetry, packet inspection",
            },
            {
                "domain": "NETWORK AUTOMATION",
                "score": 84,
                "status": "Growing",
                "trend_class": "trend-growing",
                "description": "Python NetDevOps, Ansible, automated device configs, API network orchestration",
            },
            {
                "domain": "5G & CELLULAR INFRASTRUCTURE",
                "score": 75,
                "status": "Stable",
                "trend_class": "trend-stable",
                "description": "3GPP Rel 16/17, Private 5G networks, Open RAN architecture, RF telemetry",
            },
            {
                "domain": "LLMs / GENAI & TELECOM AI",
                "score": 72,
                "status": "Growing",
                "trend_class": "trend-growing",
                "description": "Agentic evaluation pipelines, LLM telemetry, automated root-cause incident diagnosis",
            },
            {
                "domain": "SRE & CLOUD OBSERVABILITY",
                "score": 68,
                "status": "Growing",
                "trend_class": "trend-growing",
                "description": "Prometheus, Grafana dashboards, OpenTelemetry metrics, service telemetry",
            },
            {
                "domain": "QA & SYSTEM VALIDATION",
                "score": 62,
                "status": "Stable",
                "trend_class": "trend-stable",
                "description": "Automated protocol verification, CI/CD regression suites, pytest & Playwright",
            },
        ]

        # Your skill position: Comparative Matrix (Market Demand vs Your Proficiency -> Action)
        candidate_skill_position = [
            {
                "skill": "Python",
                "domain": "Software & AI",
                "market_demand": 92,
                "your_level": 95,
                "action": "Maintain",
                "action_class": "action-maintain",
                "notes": "Core foundation established across telecom data & analysis pipelines.",
            },
            {
                "skill": "Linux Systems",
                "domain": "Systems & OS",
                "market_demand": 88,
                "your_level": 90,
                "action": "Maintain",
                "action_class": "action-maintain",
                "notes": "Strong environment comfort, shell tooling, process & socket concepts.",
            },
            {
                "skill": "TCP/IP & Wireshark",
                "domain": "Networking",
                "market_demand": 85,
                "your_level": 92,
                "action": "Maintain",
                "action_class": "action-maintain",
                "notes": "Politecnico di Milano network protocols mastery and packet inspection.",
            },
            {
                "skill": "5G / Cellular Protocols",
                "domain": "Telecommunications",
                "market_demand": 72,
                "your_level": 88,
                "action": "Maintain",
                "action_class": "action-maintain",
                "notes": "3GPP standards, RAN, Core architecture, and RF wireless channel modeling.",
            },
            {
                "skill": "Zero Trust",
                "domain": "Network Security",
                "market_demand": 82,
                "your_level": 35,
                "action": "Build",
                "action_class": "action-build",
                "notes": "Top requirement in Datadog/Cloudflare; build hands-on identity-aware proxy lab.",
            },
            {
                "skill": "Network Automation",
                "domain": "NetDevOps",
                "market_demand": 78,
                "your_level": 42,
                "action": "Build",
                "action_class": "action-build",
                "notes": "Combine Python + Netmiko/Scapy for automated network device verification.",
            },
            {
                "skill": "Prometheus / Grafana",
                "domain": "Observability",
                "market_demand": 74,
                "your_level": 25,
                "action": "Build",
                "action_class": "action-build",
                "notes": "Deploy sample metrics exporter and create Grafana network telemetry board.",
            },
            {
                "skill": "Docker / Containers",
                "domain": "DevOps",
                "market_demand": 70,
                "your_level": 45,
                "action": "Build",
                "action_class": "action-build",
                "notes": "Containerize thesis code with multi-stage build and publish to GitHub.",
            },
            {
                "skill": "CI/CD & GitHub Actions",
                "domain": "DevOps",
                "market_demand": 68,
                "your_level": 40,
                "action": "Learn",
                "action_class": "action-learn",
                "notes": "Automate test runner and linting on pull requests for candidate repos.",
            },
            {
                "skill": "Go (Golang)",
                "domain": "Systems Programming",
                "market_demand": 58,
                "your_level": 20,
                "action": "Explore",
                "action_class": "action-explore",
                "notes": "High synergy with cloud networking and backend systems infrastructure.",
            },
            {
                "skill": "eBPF Tracing",
                "domain": "Kernel & Security",
                "market_demand": 48,
                "your_level": 12,
                "action": "Explore",
                "action_class": "action-explore",
                "notes": "Cutting-edge Linux kernel telemetry; review Cilium and bpftrace examples.",
            },
            {
                "skill": "Playwright / Test Auto",
                "domain": "QA / Validation",
                "market_demand": 52,
                "your_level": 30,
                "action": "Learn",
                "action_class": "action-learn",
                "notes": "Demonstrate end-to-end API and UI automation with Python Playwright.",
            },
        ]

        return {
            "stats": stats,
            "top_skills": top_skills,
            "high_roi_skills_to_learn": high_roi_skills,
            "overall_top_gaps": top_gaps_all,
            "track_breakdown": track_breakdown,
            "domain_momentum": domain_momentum,
            "candidate_skill_position": candidate_skill_position,
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
