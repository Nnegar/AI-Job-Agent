"""
3-Tier Skill Gap Classifier.
Categorizes candidate skill gaps into three distinct strategic tiers:
1. MISSING (Red/Coral): Genuinely lacking evidence or foundational experience in profile (e.g. eBPF, Go, Rust, Kubernetes cluster admin, malware reverse engineering).
2. PARTIAL / WEAK (Amber/Gold): Candidate possesses related foundational experience, but lacks production evidence or framework depth (e.g. Network automation, SIEM, CI/CD, Playwright/Selenium, cloud networking).
3. STRATEGIC / LEARN (Blue/Purple): Forward-looking technologies that are high-ROI additions to the candidate's profile (e.g. Zero Trust, Prometheus/Grafana, LLM telemetry, OpenTelemetry, Service Mesh).
"""

import re
from typing import Any, Dict, List, Optional, Tuple

# Pre-defined taxonomy rules matching Negar Najafi's background (MSc Telecom Eng, Polimi)
# Proven: Python, Linux, 5G/Cellular, Wireshark, TCP/IP, RF/Wireless
TAXONOMY_RULES = [
    # 1. MISSING (Genuinely lacking evidence / core pivot required)
    (
        r"\b(ebpf|xdp|kernel|bpf)\b",
        "eBPF / Kernel",
        "MISSING",
        "No direct kernel-level or eBPF tracing experience in profile.",
    ),
    (
        r"\b(go|golang)\b",
        "Go (Golang)",
        "MISSING",
        "Systems programming language required; profile centered on Python.",
    ),
    (
        r"\b(rust)\b",
        "Rust",
        "MISSING",
        "Systems language with strict memory-safety required; absent from profile.",
    ),
    (
        r"\b(c\+\+|embedded c|c/c\+\+)\b",
        "C / C++ Systems",
        "MISSING",
        "Production-grade C/C++ systems engineering required.",
    ),
    (
        r"\b(kubernetes|k8s|helm|istio)\b",
        "Kubernetes",
        "MISSING",
        "Production container orchestration administration lacks evidence.",
    ),
    (
        r"\b(reverse engineering|malware|ghidra|ida pro|yara|exploit|threat actor)\b",
        "Malware / Reverse Engineering",
        "MISSING",
        "Offensive security and binary analysis require specialized background.",
    ),
    (
        r"\b(deepspeed|megatron|distributed training|pretraining|phd)\b",
        "Distributed ML Training",
        "MISSING",
        "High-scale distributed model pretraining outside current scope.",
    ),

    # 2. STRATEGIC (High-ROI market additions, forward-looking strategic value)
    (
        r"\b(zero trust|ztna|beyondcorp)\b",
        "Zero Trust Architecture",
        "STRATEGIC",
        "High-ROI security architecture paradigm; enhances network security roles.",
    ),
    (
        r"\b(prometheus|grafana|opentelemetry|telemetry|datadog)\b",
        "Prometheus / Grafana",
        "STRATEGIC",
        "Cloud-native observability stack that directly bridges networking and SRE.",
    ),
    (
        r"\b(llm telemetry|agent telemetry|eval-driven|ai agent|agentic)\b",
        "LLM & Agent Telemetry",
        "STRATEGIC",
        "Emerging GenAI operational tooling; valuable for Telecom AI roles.",
    ),
    (
        r"\b(service mesh|envoy|cilium)\b",
        "Service Mesh / Envoy",
        "STRATEGIC",
        "Modern cloud networking infrastructure; high synergy with 5G core.",
    ),
    (
        r"\b(kafka|rabbitmq|event streaming)\b",
        "Event Streaming (Kafka)",
        "STRATEGIC",
        "Asynchronous messaging architecture for telemetry and streaming data.",
    ),

    # 3. PARTIAL / WEAK (Related foundation exists, needs production evidence)
    (
        r"\b(network automation|netmiko|paramiko|ansible|nornir|scapy)\b",
        "Network Automation",
        "PARTIAL",
        "Strong Python & networking foundation exists; needs automated config evidence.",
    ),
    (
        r"\b(siem|splunk|suricata|zeek|snort|soc|incident response|threat hunting)\b",
        "SIEM / Threat Detection",
        "PARTIAL",
        "Solid TCP/IP and packet analysis foundation; lacks enterprise SIEM tooling evidence.",
    ),
    (
        r"\b(ci/cd|github actions|gitlab ci|jenkins|pipeline)\b",
        "CI/CD Automation",
        "PARTIAL",
        "Git foundation exists; needs formal automated build and test pipeline experience.",
    ),
    (
        r"\b(playwright|selenium|cypress|automated testing|qa automation)\b",
        "QA / Test Automation",
        "PARTIAL",
        "Python scripting skills transferable; lacks browser/E2E test framework artifacts.",
    ),
    (
        r"\b(docker|containerization|containers)\b",
        "Docker / Containerization",
        "PARTIAL",
        "Linux CLI experience established; needs published Dockerfiles and image workflows.",
    ),
    (
        r"\b(terraform|iac|cloudformation)\b",
        "Infrastructure as Code",
        "PARTIAL",
        "Cloud foundation exists; needs declarative infrastructure provisioning samples.",
    ),
    (
        r"\b(aws|azure|gcp|cloud networking|vpc)\b",
        "Cloud Networking (AWS/Azure)",
        "PARTIAL",
        "Network fundamentals (VPC/routing) established; needs vendor cloud certification/demo.",
    ),
    (
        r"\b(rest api|fastapi|flask|graphql|api design)\b",
        "API Integration",
        "PARTIAL",
        "Python backend capabilities established; needs production API contracts.",
    ),
]


def classify_skill_gap(gap_text: str) -> Dict[str, Any]:
    """
    Classifies a raw skill gap string into MISSING, PARTIAL, or STRATEGIC.
    Returns a standardized dictionary.
    """
    if not gap_text or not isinstance(gap_text, str):
        return {
            "raw_text": "",
            "skill": "Technical Competency",
            "tier": "PARTIAL",
            "badge_class": "tier-partial",
            "description": "General domain knowledge development recommended.",
        }

    text_lower = gap_text.lower()

    # Match against taxonomy
    for pattern, skill_name, tier, description in TAXONOMY_RULES:
        if re.search(pattern, text_lower):
            badge_class = f"tier-{tier.lower()}"
            return {
                "raw_text": gap_text.strip(),
                "skill": skill_name,
                "tier": tier,
                "badge_class": badge_class,
                "description": description,
            }

    # Heuristics based on linguistic cues in stage 2 reasoning
    if any(k in text_lower for k in ["no direct", "no experience", "lack of", "lacks", "zero evidence", "missing", "phd"]):
        # Check if it sounds like a missing tool/language
        tier = "MISSING"
        badge_class = "tier-missing"
        description = "Core requirement without direct evidence in current resume."
    elif any(k in text_lower for k in ["limited", "partial", "weak", "needs more", "could strengthen", "relies on"]):
        tier = "PARTIAL"
        badge_class = "tier-partial"
        description = "Related foundation exists; needs focused production demonstration."
    elif any(k in text_lower for k in ["nice to have", "plus", "beneficial", "valuable", "strategic"]):
        tier = "STRATEGIC"
        badge_class = "tier-strategic"
        description = "Strategically valuable domain addition that elevates candidate standing."
    else:
        tier = "PARTIAL"
        badge_class = "tier-partial"
        description = "Domain experience to showcase in candidate interview prep."

    # Extract concise name from raw text
    skill_name = _extract_compact_name(gap_text)

    return {
        "raw_text": gap_text.strip(),
        "skill": skill_name,
        "tier": tier,
        "badge_class": badge_class,
        "description": description,
    }


def _extract_compact_name(raw_text: str) -> str:
    # Remove leading common prefixes
    cleaned = re.sub(
        r"^(lack of|no direct experience with|limited direct experience with|no demonstrated experience in|no demonstrated experience with|limited experience with|limited exposure to|lacks)\s+",
        "",
        raw_text,
        flags=re.IGNORECASE,
    ).strip()

    # Truncate to reasonable length if it's a long sentence
    if len(cleaned) > 36:
        # Check for colon or commas
        parts = re.split(r"[,;:\(]", cleaned)
        cleaned = parts[0].strip()
    return cleaned[:36].title()


def classify_gaps(gaps: List[str]) -> List[Dict[str, Any]]:
    """
    Classifies a list of raw gap strings.
    """
    results = []
    seen_skills = set()

    for g in gaps:
        if not g or not isinstance(g, str):
            continue
        classified = classify_skill_gap(g)
        key = classified["skill"].lower()
        if key not in seen_skills:
            seen_skills.add(key)
            results.append(classified)

    return results
