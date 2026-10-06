"""
Stage 2 Candidate Analysis Module.

Evaluates fit between the candidate's actual career profile and a job listing.
"""

from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from analyzer.llm.openrouter_client import OpenRouterClient
from analyzer.prompts.stage2_candidate_analysis_prompt import build_stage2_prompt
from analyzer.stage2.schema import STAGE2_ANALYSIS_SCHEMA, normalize_stage2_result


CAREER_PROFILE_PATH = (
    Path(__file__).resolve().parents[2] / "profile" / "career_profile.yaml"
)


def load_career_profile() -> Dict[str, Any]:
    with open(CAREER_PROFILE_PATH, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict):
        raise ValueError("Invalid career profile YAML format.")
    return data


def format_candidate_summary(profile: Dict[str, Any]) -> str:
    """
    Format a factual, concise profile summary from career_profile.yaml.
    Omits personal private stories (which belong only to cover letters).
    """
    candidate = profile.get("candidate", {})
    status = candidate.get("current_status", {})
    mobility = candidate.get("mobility", {})
    priority_countries = mobility.get("priority_countries", {})
    tech = profile.get("technical_profile", {})
    objectives = profile.get("career_objective", {}).get("optimize_for", {})

    return f"""
Candidate: {candidate.get('name', 'Negar Najafi')}
- Education: {status.get('education', {}).get('degree')} from {status.get('education', {}).get('university')}
- Current Status: Employed in {status.get('country')}, working in software QA for cybersecurity products.
- Mobility:
  * Open to relocation: {mobility.get('open_to_relocation', True)}
  * Priority Countries Tier 1: {', '.join(priority_countries.get('tier_1', []))}
  * Priority Countries Tier 2: {', '.join(priority_countries.get('tier_2', []))}
  * Italy Strategy: Apply only if strong company, high technical value, or meaningful growth.

Core Technical Strengths (Demonstrated Experience):
- Strongest: {', '.join(tech.get('strongest', []))}
- Strong: {', '.join(tech.get('strong', []))}
- Developing (Active learning / projects): {', '.join(tech.get('developing', []))}

Target Role Priorities:
- Tier 1: AI Telecom Networks (5G Analytics, Network Intelligence), Quality Engineering Automation (QA Automation, SDET, API Testing), Cybersecurity Engineering (Network Security, Security Operations).
- Tier 2: Embedded IoT, Applied AI & Data Science, 5G/RAN Engineering.
- Roles to de-prioritize: manual-only QA, repetitive regression without automation, generic IT support.

Career Optimization Weights:
- Future Growth: {objectives.get('future_growth', 30)}%
- AI Resilience: {objectives.get('ai_resilience', 30)}%
- Technical Match: {objectives.get('technical_match', 20)}%
- Compensation & Location: {objectives.get('compensation_and_location', 15)}%
- Company Strength: {objectives.get('company_strength', 5)}%
"""


def analyze_candidate_job(
    job: Dict[str, Any],
    stage1_analysis: Optional[Dict[str, Any]] = None,
    career_profile: Optional[Dict[str, Any]] = None,
    client: Optional[OpenRouterClient] = None,
) -> Dict[str, Any]:
    """
    Run Stage 2 candidate-to-job fit analysis.

    Args:
        job: Dictionary containing job fields (id, title, company, location, description).
        stage1_analysis: Dictionary containing Stage 1 analysis fields.
        career_profile: Optional pre-loaded career profile dict.
        client: Optional OpenRouterClient instance.

    Returns:
        Validated dictionary containing Stage 2 fit scores, category assessments,
        strengths, skill gaps, concerns, reasoning, and model metadata.
    """
    # If caller passed (job, career_profile) positionally:
    if stage1_analysis is not None and "relevance_score" not in stage1_analysis and ("professional_summary" in stage1_analysis or "core_skills" in stage1_analysis):
        career_profile = stage1_analysis
        stage1_analysis = job
    elif stage1_analysis is None:
        stage1_analysis = job

    if career_profile is None:
        career_profile = load_career_profile()

    if client is None:
        client = OpenRouterClient()

    candidate_summary = format_candidate_summary(career_profile)

    prompt = build_stage2_prompt(
        job=job,
        stage1_analysis=stage1_analysis,
        career_profile_summary=candidate_summary,
    )

    result, model_name = client.generate_json(
        prompt=prompt,
        schema=STAGE2_ANALYSIS_SCHEMA,
        schema_name="candidate_job_analysis",
        stage="stage2",
    )

    normalized = normalize_stage2_result(result)
    normalized["job_id"] = job["id"]
    normalized["model"] = model_name

    return normalized
