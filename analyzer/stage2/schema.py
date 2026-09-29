"""
Stage 2 Structured Output Schema and Normalization.

Evaluates Candidate ↔ Job Fit based on the candidate's actual career profile.
"""

from typing import Any, Dict


STAGE2_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "match_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": (
                "Overall candidate-to-job match score from 0 to 100."
            ),
        },
        "technical_fit_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": (
                "Score for technical overlap between candidate skills and job requirements."
            ),
        },
        "career_track_fit_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": (
                "Score for alignment with candidate's target career tracks and role priorities."
            ),
        },
        "career_growth_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": (
                "Score for long-term career growth, skill development, and industry advancement."
            ),
        },
        "ai_resilience_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": (
                "Score for role durability against automation and relevance in AI-driven markets."
            ),
        },
        "seniority_fit": {
            "type": "string",
            "enum": [
                "early_career",
                "good_fit",
                "stretch",
                "overqualified",
            ],
            "description": (
                "Assessment of seniority fit given candidate's actual years of experience."
            ),
        },
        "location_fit": {
            "type": "string",
            "enum": [
                "exact_match",
                "relocation_required",
                "mismatch",
                "remote",
            ],
            "description": (
                "Assessment of geographical fit given candidate's current country and relocation priorities."
            ),
        },
        "primary_track": {
            "type": "string",
            "enum": [
                "telecom_ai",
                "cybersecurity",
                "quality_engineering",
                "applied_ai",
                "embedded_iot",
            ],
            "description": (
                "The primary career track this role best matches for the candidate."
            ),
        },
        "strengths": {
            "type": "array",
            "description": (
                "Up to 3 concrete candidate strengths directly applicable to this vacancy."
            ),
            "items": {
                "type": "string",
            },
        },
        "skill_gaps": {
            "type": "array",
            "description": (
                "Up to 3 concrete skill gaps where the candidate does not yet meet stated requirements."
            ),
            "items": {
                "type": "string",
            },
        },
        "concerns": {
            "type": "array",
            "description": (
                "Up to 2 concerns regarding candidate fit, work culture, or role nature."
            ),
            "items": {
                "type": "string",
            },
        },
        "reasoning": {
            "type": "string",
            "description": (
                "Concise 2-3 sentence synthesis explaining the fit evaluation."
            ),
        },
    },
    "required": [
        "match_score",
        "technical_fit_score",
        "career_track_fit_score",
        "career_growth_score",
        "ai_resilience_score",
        "seniority_fit",
        "location_fit",
        "primary_track",
        "strengths",
        "skill_gaps",
        "concerns",
        "reasoning",
    ],
    "additionalProperties": False,
}


def normalize_stage2_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize Stage 2 analysis results.
    Enforces score ranges and field constraints.
    """
    if not isinstance(result, dict):
        raise ValueError("Stage 2 result must be a dictionary.")

    score_fields = [
        "match_score",
        "technical_fit_score",
        "career_track_fit_score",
        "career_growth_score",
        "ai_resilience_score",
    ]

    for field in score_fields:
        score = result.get(field)
        if (
            isinstance(score, bool)
            or not isinstance(score, int)
            or score < 0
            or score > 100
        ):
            raise ValueError(
                f"Stage 2 field '{field}' must be an integer between 0 and 100, got: {score!r}"
            )

    valid_seniority = {"early_career", "good_fit", "stretch", "overqualified"}
    if result.get("seniority_fit") not in valid_seniority:
        raise ValueError(
            f"Invalid seniority_fit: {result.get('seniority_fit')!r}"
        )

    valid_location = {"exact_match", "relocation_required", "mismatch", "remote"}
    if result.get("location_fit") not in valid_location:
        raise ValueError(
            f"Invalid location_fit: {result.get('location_fit')!r}"
        )

    valid_tracks = {
        "telecom_ai",
        "cybersecurity",
        "quality_engineering",
        "applied_ai",
        "embedded_iot",
    }
    if result.get("primary_track") not in valid_tracks:
        raise ValueError(
            f"Invalid primary_track: {result.get('primary_track')!r}"
        )

    for list_field in ("strengths", "skill_gaps", "concerns"):
        val = result.get(list_field)
        if not isinstance(val, list):
            raise ValueError(f"Stage 2 field '{list_field}' must be a list.")
        # Ensure all items are strings
        result[list_field] = [str(item).strip() for item in val if str(item).strip()]

    result["reasoning"] = str(result.get("reasoning", "")).strip()

    return result
