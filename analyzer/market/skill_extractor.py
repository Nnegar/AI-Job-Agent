"""
Market Skill Extractor Module.
Extracts normalized technologies, tools, and domain skills from job descriptions,
Stage 2 candidate strengths, and Stage 2 skill gaps.
"""

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Comprehensive taxonomy of industry technologies & skills
SKILL_TAXONOMY = {
    # Cloud & DevOps
    "Kubernetes": ("cloud_devops", [r"\bkubernetes\b", r"\bk8s\b"]),
    "Docker": ("cloud_devops", [r"\bdocker\b", r"\bcontainers?\b"]),
    "Terraform": ("cloud_devops", [r"\bterraform\b", r"\biac\b"]),
    "AWS": ("cloud_devops", [r"\baws\b", r"\bamazon web services\b"]),
    "Azure": ("cloud_devops", [r"\bazure\b", r"\bmicrosoft cloud\b"]),
    "GCP": ("cloud_devops", [r"\bgcp\b", r"\bgoogle cloud\b"]),
    "Linux": ("cloud_devops", [r"\blinux\b", r"\bunix\b"]),
    "CI/CD": ("cloud_devops", [r"\bci/cd\b", r"\bcicd\b", r"\bjenkins\b", r"\bgithub actions\b", r"\bgitlab ci\b"]),
    "Ansible": ("cloud_devops", [r"\bansible\b"]),
    "Prometheus / Grafana": ("cloud_devops", [r"\bprometheus\b", r"\bgrafana\b", r"\bdatadog\b"]),

    # Networking & Telecom
    "5G": ("networking_telecom", [r"\b5g\b", r"\b5g-ran\b", r"\b5g core\b", r"\bnarrowband\b"]),
    "4G / LTE": ("networking_telecom", [r"\b4g\b", r"\blte\b"]),
    "RAN / O-RAN": ("networking_telecom", [r"\bran\b", r"\bo-ran\b", r"\bradio access\b", r"\bvran\b"]),
    "IP Networking / TCP/IP": ("networking_telecom", [r"\btcp/ip\b", r"\bip networking\b", r"\bipv[46]\b"]),
    "BGP / OSPF": ("networking_telecom", [r"\bbgp\b", r"\bospf\b", r"\brouting protocols?\b"]),
    "Wireshark / Packet Analysis": ("networking_telecom", [r"\bwireshark\b", r"\btcpdump\b", r"\bpacket capture\b", r"\bpacket analysis\b"]),
    "DNS / CDN": ("networking_telecom", [r"\bdns\b", r"\bcdn\b", r"\banycast\b"]),
    "Routing & Switching": ("networking_telecom", [r"\brouting\b", r"\bswitching\b", r"\bipbb\b", r"\bbackbone\b"]),
    "Network Automation": ("networking_telecom", [r"\bnetwork automation\b", r"\bnetmiko\b", r"\bnornir\b", r"\bscapy\b"]),

    # Cybersecurity
    "SIEM": ("security", [r"\bsiem\b", r"\bsplunk\b", r"\belasticsearch security\b", r"\bqradar\b"]),
    "SOC / Security Operations": ("security", [r"\bsoc\b", r"\bsecurity operations\b"]),
    "Vulnerability Management": ("security", [r"\bvulnerability\b", r"\bcve\b", r"\bvulnerability management\b", r"\bvulnerability assessment\b"]),
    "Threat Detection & Incident Response": ("security", [r"\bincident response\b", r"\bthreat detection\b", r"\bthreat hunting\b", r"\bedr\b"]),
    "Penetration Testing / Security QA": ("security", [r"\bpenetration testing\b", r"\bpen testing\b", r"\bsecurity testing\b", r"\bsecurity qa\b"]),
    "GRC / Compliance": ("security", [r"\bgrc\b", r"\biso 27001\b", r"\bsoc 2\b", r"\bgdpr\b", r"\bcompliance\b"]),
    "Phishing Simulation": ("security", [r"\bgophish\b", r"\bphishing\b", r"\bsecurity awareness\b"]),
    "Zero Trust / Network Security": ("security", [r"\bzero trust\b", r"\bnetwork security\b", r"\bfirewalls?\b"]),

    # Programming & Development
    "Python": ("programming", [r"\bpython\b"]),
    "C / C++": ("programming", [r"\bc\+\+\b", r"\b\bc\b\s+(?:programming|development|code)"]),
    "Go (Golang)": ("programming", [r"\bgolang\b", r"\b\bgo\b\s+(?:programming|developer|language|code)"]),
    "Rust": ("programming", [r"\brust\b"]),
    "SQL / Relational DBs": ("programming", [r"\bsql\b", r"\bpostgresql\b", r"\bmysql\b", r"\bsqlite\b"]),
    "Bash / Shell": ("programming", [r"\bbash\b", r"\bshell\b", r"\bcli\b"]),
    "REST APIs": ("programming", [r"\brest\b", r"\bapis?\b", r"\brestful\b", r"\bgrpc\b"]),
    "Git": ("programming", [r"\bgit\b", r"\bgithub\b", r"\bgitlab\b"]),

    # AI & Data
    "Machine Learning": ("ai_data", [r"\bmachine learning\b", r"\bml\b", r"\bscikit-learn\b"]),
    "Deep Learning / PyTorch": ("ai_data", [r"\bdeep learning\b", r"\bpytorch\b", r"\btensorflow\b"]),
    "Time-Series Analysis": ("ai_data", [r"\btime-series\b", r"\btime series\b", r"\btemporal data\b"]),
    "Pandas / NumPy": ("ai_data", [r"\bpandas\b", r"\bnumpy\b"]),
    "LLMs / Generative AI": ("ai_data", [r"\bllm\b", r"\bgenerative ai\b", r"\brag\b", r"\blarge language models?\b", r"\bai agents?\b"]),
    "Anomaly Detection": ("ai_data", [r"\banomaly detection\b", r"\boutlier\b"]),
    "MLOps": ("ai_data", [r"\bmlops\b", r"\bmodel deployment\b", r"\bfeature store\b"]),
    "Kafka / Event Streaming": ("ai_data", [r"\bkafka\b", r"\brabbitmq\b", r"\bevent streaming\b"]),

    # Quality & Testing
    "pytest": ("quality_testing", [r"\bpytest\b"]),
    "Test Automation": ("quality_testing", [r"\btest automation\b", r"\bautomated testing\b", r"\bqa automation\b"]),
    "Playwright / Selenium": ("quality_testing", [r"\bplaywright\b", r"\bselenium\b", r"\bcypress\b"]),
    "API Testing": ("quality_testing", [r"\bapi testing\b", r"\bpostman\b", r"\bendpoint testing\b"]),
    "SDET / Test Architecture": ("quality_testing", [r"\bsdet\b", r"\btest framework\b", r"\btest architecture\b"]),
    "Regression Testing": ("quality_testing", [r"\bregression testing\b", r"\bdefect tracking\b"]),
}


def _matches_any_pattern(text: str, patterns: List[str]) -> bool:
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


def extract_skills_for_job(
    job_id: int,
    description: str,
    strengths: Optional[List[str]] = None,
    skill_gaps: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Extracts skills and identifies whether each skill represents a candidate strength or a gap.
    """
    strengths_text = " ".join(strengths or [])
    gaps_text = " ".join(skill_gaps or [])
    desc_text = description or ""

    results = []
    recorded_skills: Set[Tuple[str, int]] = set()

    for skill_name, (category, patterns) in SKILL_TAXONOMY.items():
        is_in_gaps = _matches_any_pattern(gaps_text, patterns)
        is_in_strengths = _matches_any_pattern(strengths_text, patterns)
        is_in_desc = _matches_any_pattern(desc_text, patterns)

        if is_in_gaps:
            if (skill_name, 1) not in recorded_skills:
                results.append({
                    "name": skill_name,
                    "category": category,
                    "is_gap": 1,
                    "context": "Identified in Stage 2 candidate evaluation as a skill gap",
                })
                recorded_skills.add((skill_name, 1))

        if is_in_strengths:
            if (skill_name, 0) not in recorded_skills:
                results.append({
                    "name": skill_name,
                    "category": category,
                    "is_gap": 0,
                    "context": "Identified in Stage 2 evaluation as candidate strength",
                })
                recorded_skills.add((skill_name, 0))

        # If mentioned in description and not recorded yet:
        if is_in_desc and (skill_name, 0) not in recorded_skills and (skill_name, 1) not in recorded_skills:
            results.append({
                "name": skill_name,
                "category": category,
                "is_gap": 0,
                "context": "Required in job description",
            })
            recorded_skills.add((skill_name, 0))

    return results
