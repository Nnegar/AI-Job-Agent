"""
Stage 3 Decision Engine: Final Application Filter & Priority Shortlisting.

A deterministic, explainable policy engine that combines Stage 1 intelligence,
Stage 2 candidate-to-job matching, and candidate mobility/career constraints
from profile/career_profile.yaml to make final application decisions.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import yaml


CAREER_PROFILE_PATH = (
    Path(__file__).resolve().parents[2] / "profile" / "career_profile.yaml"
)

COUNTRY_ALIASES = {
    "uk": "UK",
    "united kingdom": "UK",
    "great britain": "UK",
    "england": "UK",
    "london": "UK",
    "germany": "Germany",
    "deutschland": "Germany",
    "berlin": "Germany",
    "munich": "Germany",
    "frankfurt": "Germany",
    "netherlands": "Netherlands",
    "holland": "Netherlands",
    "amsterdam": "Netherlands",
    "switzerland": "Switzerland",
    "zurich": "Switzerland",
    "geneva": "Switzerland",
    "sweden": "Sweden",
    "stockholm": "Sweden",
    "denmark": "Denmark",
    "copenhagen": "Denmark",
    "finland": "Finland",
    "helsinki": "Finland",
    "ireland": "Ireland",
    "dublin": "Ireland",
    "canada": "Canada",
    "toronto": "Canada",
    "vancouver": "Canada",
    "italy": "Italy",
    "italia": "Italy",
    "milan": "Italy",
    "rome": "Italy",
    "portugal": "Portugal",
    "lisbon": "Portugal",
    "spain": "Spain",
    "madrid": "Spain",
    "barcelona": "Spain",
    "france": "France",
    "paris": "France",
    "austria": "Austria",
    "vienna": "Austria",
    "belgium": "Belgium",
    "brussels": "Belgium",
    "united states": "USA",
    "usa": "USA",
    "us": "USA",
    "new york": "USA",
    "denver": "USA",
    "austin": "USA",
    "san francisco": "USA",
    "amer": "USA",
}


def load_profile_rules() -> Dict[str, Any]:
    with open(CAREER_PROFILE_PATH, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict):
        raise ValueError("Invalid career profile YAML.")
    return data


def detect_country(location_text: Optional[str]) -> str:
    """
    Detect country name from location string.
    """
    if not location_text:
        return "Unknown"

    text = location_text.lower()

    # Look for known aliases/countries
    for pattern, canonical in COUNTRY_ALIASES.items():
        if re.search(rf"\b{re.escape(pattern)}\b", text):
            return canonical

    return "Other"


def evaluate_stage3_decision(
    job_record: Dict[str, Any],
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluate final application decision, priority, and readiness for a job
    that has completed Stage 2 candidate matching.

    Args:
        job_record: Dictionary containing combined fields from jobs,
                    job_ai_analysis, and candidate_job_analysis.
        profile: Optional pre-loaded career profile dict.

    Returns:
        Dictionary with Stage 3 attributes:
        - job_id
        - decision ('apply', 'manual_review', 'skip')
        - priority ('high', 'medium', 'low', 'none')
        - final_score (float 0-100)
        - application_method ('manual', 'auto_eligible')
        - readiness ('ready', 'needs_preparation')
        - decision_reasons (list of strings)
    """
    if profile is None:
        profile = load_profile_rules()

    job_id = job_record["id"]
    match_score = float(job_record.get("match_score", 0))
    technical_fit = float(job_record.get("technical_fit_score", 0))
    career_growth = float(job_record.get("career_growth_score", 0))
    ai_resilience = float(job_record.get("ai_resilience_score", 0))
    seniority_fit = str(job_record.get("seniority_fit", "stretch")).lower()
    location_fit = str(job_record.get("location_fit", "relocation_required")).lower()
    primary_track = str(job_record.get("primary_track", ""))
    location_str = str(job_record.get("location", ""))

    country_weights = profile.get("country_weights", {})
    detected_country = detect_country(location_str)

    reasons: List[str] = []

    # =========================================================
    # Rule 1: Immediate Disqualifications / Hard Filters
    # =========================================================

    # Location Mismatch (e.g. non-target countries like USA, Asia, Australia)
    if location_fit == "mismatch" or detected_country == "USA":
        reasons.append(
            f"Location mismatch: Position located in {detected_country} ({location_str}), outside relocation targets."
        )
        final_score = round(match_score * 0.35, 1)
        return {
            "job_id": job_id,
            "decision": "skip",
            "priority": "none",
            "final_score": final_score,
            "application_method": "manual",
            "readiness": "ready",
            "decision_reasons": reasons,
        }

    # Seniority Overqualified (e.g. student internships for graduates)
    if seniority_fit == "overqualified":
        reasons.append(
            "Seniority mismatch: Candidate has completed MSc and industry experience; overqualified for student internship."
        )
        final_score = round(match_score * 0.5, 1)
        return {
            "job_id": job_id,
            "decision": "skip",
            "priority": "none",
            "final_score": final_score,
            "application_method": "manual",
            "readiness": "ready",
            "decision_reasons": reasons,
        }

    # =========================================================
    # Rule 2: Country Weight & Location Factor
    # =========================================================

    country_weight = float(country_weights.get(detected_country, 1.00))

    if detected_country in ("Netherlands", "Germany", "Switzerland"):
        reasons.append(
            f"Priority Tier 1 Country: {detected_country} (Weight: {country_weight}x)"
        )
    elif detected_country in ("UK", "Sweden", "Denmark", "Finland", "Ireland", "Canada"):
        reasons.append(
            f"Target Tier 2 Country: {detected_country} (Weight: {country_weight}x)"
        )
    elif detected_country == "Italy":
        # Italy Strategy: apply only if high technical value & meaningful growth
        if technical_fit >= 65 and career_growth >= 65:
            reasons.append(
                "Meets Italy Strategy: Strong company with high technical value and career growth."
            )
        else:
            reasons.append(
                "Italy Strategy Warning: Role offers insufficient technical growth over current Italian position."
            )
            country_weight = 0.80
    else:
        reasons.append(f"European Location: {detected_country} ({location_str})")

    # =========================================================
    # Rule 3: Seniority Multiplier
    # =========================================================

    if seniority_fit == "good_fit":
        seniority_mult = 1.05
        reasons.append("Seniority Alignment: Strong level match for candidate profile.")
    elif seniority_fit == "stretch":
        seniority_mult = 0.90
        reasons.append("Seniority Stretch: Requires senior scope; achievable with strong technical adjacency.")
    elif seniority_fit == "early_career":
        seniority_mult = 0.85
        reasons.append("Seniority Early Career: Below ideal mid-level target.")
    else:
        seniority_mult = 0.80

    # =========================================================
    # Rule 4: Composite Final Score Calculation
    # =========================================================

    # Base match score weighted by country and seniority
    calculated_score = match_score * country_weight * seniority_mult

    # Bonus for Tier 1 track alignment
    if primary_track in ("telecom_ai", "quality_engineering", "cybersecurity"):
        if technical_fit >= 70:
            calculated_score += 2.0
            reasons.append(f"Tier 1 Core Track Bonus: {primary_track} with {technical_fit:.0f} technical fit.")

    # High growth & AI resilience bonus
    if career_growth >= 75 and ai_resilience >= 70:
        calculated_score += 2.0
        reasons.append("High Future Growth & AI Resilience potential.")

    final_score = round(max(0.0, min(100.0, calculated_score)), 1)

    # =========================================================
    # Rule 5: Final Application Decision & Priority
    # =========================================================

    if final_score >= 76.0 and match_score >= 68.0:
        decision = "apply"
        priority = "high" if final_score >= 82.0 else "medium"
        reasons.append(f"Recommended for Application: Composite score {final_score}/100 exceeds threshold.")
    elif final_score >= 64.0:
        decision = "manual_review"
        priority = "medium" if final_score >= 70.0 else "low"
        reasons.append(f"Manual Review Recommended: Score {final_score}/100 indicates viable opportunity requiring human inspection.")
    else:
        decision = "skip"
        priority = "none"
        reasons.append(f"Filtered Out: Final composite score {final_score}/100 is below review threshold.")

    # =========================================================
    # Rule 6: Readiness & Application Method
    # =========================================================

    skill_gaps = job_record.get("skill_gaps", [])
    gaps_str = " ".join(str(g).lower() for g in skill_gaps)

    if any(keyword in gaps_str for keyword in ("framework", "portfolio", "certification", "github", "10+ years")):
        readiness = "needs_preparation"
        reasons.append("Preparation Needed: Cover letter / CV should specifically highlight adjacent project experience.")
    else:
        readiness = "ready"

    # Default to manual per safety policy
    application_method = "manual"
    if decision == "apply" and priority == "high" and seniority_fit == "good_fit":
        reasons.append("Automation Candidate: Highly matched profile eligible for automated flow when enabled.")

    return {
        "job_id": job_id,
        "decision": decision,
        "priority": priority,
        "final_score": final_score,
        "application_method": application_method,
        "readiness": readiness,
        "decision_reasons": reasons,
    }
