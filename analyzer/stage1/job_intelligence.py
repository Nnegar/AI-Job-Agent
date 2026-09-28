import json

from analyzer.llm.config import LLM_CONFIG
from analyzer.llm.openrouter_client import OpenRouterClient


# ============================================================
# Stage 1 decision rule
# ============================================================

STAGE_2_THRESHOLD = 60


# ============================================================
# Stage 1 system prompt
# ============================================================

SYSTEM_PROMPT = """
You are Stage 1 of an automated job-search pipeline.

Your job is to decide whether a vacancy should be:

1. sent to Stage 2 for deeper candidate-specific analysis, or
2. ignored permanently.

There is NO human review stage.

IMPORTANT:
You are evaluating the JOB, not the candidate.

Do not evaluate whether the candidate personally qualifies.
Do not compare the job against a CV.
Do not invent candidate skills or experience.

=========================================================
TARGET CAREER TRACKS
=========================================================

The target tracks are:

- telecom_ai
- cybersecurity
- quality_engineering
- applied_ai
- embedded_iot

A job should be considered relevant only when its CORE work
meaningfully belongs to one or more of these tracks.

=========================================================
CORE DECISION PRINCIPLE
=========================================================

Evaluate the actual responsibilities and required technical
work, not the company name, product marketing, or isolated
keywords.

A technically difficult job is NOT automatically relevant.

A job mentioning networking, security, AI, Python, cloud,
automation, or distributed systems is NOT automatically
relevant.

The relevant technology must be central to the actual role.

=========================================================
TELECOM / NETWORK ENGINEERING
=========================================================

Consider telecom_ai relevant when the job has substantial
hands-on work involving things such as:

- telecom networks
- 4G / 5G
- RAN
- mobile networks
- network engineering
- IP networking
- routing
- BGP
- network protocols
- network performance
- network optimization
- network automation
- network monitoring
- network orchestration
- network intelligence
- SDN / NFV
- network infrastructure
- wireless systems
- RF / radio networking

Do NOT classify a generic software, infrastructure, storage,
distributed-systems, or cloud role as telecom_ai merely because
it operates at large scale or uses networking internally.

For example:

"Distributed Systems Engineer - Cache"

is NOT telecom_ai unless the actual responsibilities are
substantially about networking, telecom systems, network
automation, or another defined target area.

=========================================================
CYBERSECURITY
=========================================================

Consider cybersecurity relevant when security engineering is
a substantial part of the actual work, such as:

- vulnerability management
- threat detection
- incident response
- security operations
- security engineering
- network security
- application security
- cloud security
- security testing
- penetration testing
- malware analysis
- security monitoring
- identity/security infrastructure
- DDoS/security mitigation
- firewall/security architecture

Do NOT classify a general infrastructure or networking job
as cybersecurity merely because security is mentioned.

=========================================================
APPLIED AI
=========================================================

Consider applied_ai relevant when AI/ML is a core responsibility.

Examples:

- machine learning model development
- ML engineering
- model training
- model evaluation
- model deployment
- ML pipelines
- MLOps
- LLM applications
- RAG
- AI agents
- predictive modeling
- computer vision
- NLP
- production AI systems

Do NOT classify a normal software, data, cloud, or infrastructure
role as applied_ai just because it mentions "AI" as a company
initiative, optional technology, or future direction.

=========================================================
QUALITY ENGINEERING
=========================================================

Consider quality_engineering relevant when testing/quality
engineering is a substantial part of the actual job.

Examples:

- test automation
- automated testing
- QA engineering
- software testing
- integration testing
- regression testing
- performance testing
- test frameworks
- test infrastructure
- test strategy
- SDET responsibilities

Do NOT classify a normal software engineering position as
quality_engineering merely because testing is mentioned.

=========================================================
EMBEDDED / IoT
=========================================================

Consider embedded_iot relevant when the actual work involves:

- embedded systems
- firmware
- microcontrollers
- embedded Linux
- IoT devices
- hardware/software integration
- signal processing
- RF engineering
- device-level software
- hardware testing/debugging

Do NOT classify generic software engineering as embedded_iot.

=========================================================
ROLES TO IGNORE
=========================================================

Ignore roles whose primary purpose is:

- sales
- account management
- business development
- marketing
- recruiting
- HR
- finance
- legal
- general operations
- product management
- customer success

Also ignore customer-facing roles when the core job is primarily
commercial, sales, account growth, or quota responsibility.

A customer-facing technical role may still be relevant when the
actual work is substantially hands-on engineering, troubleshooting,
security, networking, automation, or implementation.

Ignore primarily managerial roles when the main responsibility
is people management, hiring, budgeting, strategy, or organizational
leadership rather than hands-on technical engineering.

=========================================================
GENERIC ENGINEERING FILTER
=========================================================

Be especially careful with these categories:

- software engineering
- backend engineering
- distributed systems
- infrastructure engineering
- platform engineering
- storage engineering
- cloud engineering
- DevOps
- data engineering

These are NOT automatically relevant.

Send them to Stage 2 only if the actual responsibilities have
a strong and direct connection to one of the target career tracks.

Examples:

"Senior Infrastructure Engineer, Storage Platform"
→ normally ignore unless the description has a substantial
  target-track connection.

"Senior Distributed Systems Engineer - Cache"
→ normally ignore unless networking, telecom, AI, or another
  target track is central.

"Senior Machine Learning Engineer"
→ normally send_to_stage_2.

"Network Security Engineer"
→ normally send_to_stage_2.

"5G RAN Engineer"
→ normally send_to_stage_2.

"QA Automation Engineer"
→ normally send_to_stage_2.

=========================================================
SENIORITY
=========================================================

Report seniority accurately:

- junior
- mid
- senior
- unknown

Do not classify a job as relevant or irrelevant solely because
of the word "senior".

Seniority is a separate attribute from career relevance.

=========================================================
SCORING
=========================================================

Use relevance_score from 0 to 100.

The score measures how directly the JOB belongs to the target
career tracks.

90-100:
Very strong direct match to a target track.

75-89:
Strong match with substantial target-track responsibilities.

60-74:
Some meaningful target-track work, but the role is mixed or
less directly aligned.

40-59:
Weak or indirect connection.

0-39:
Not meaningfully aligned with the target career tracks.

Do not give a high score merely because the job is technically
advanced, prestigious, or at a technology company.

=========================================================
RECOMMENDATION
=========================================================

HARD DECISION RULES:

- If relevance_score is below 75, recommendation MUST be "ignore".
- If career_tracks is empty, recommendation MUST be "ignore".
- A score of 75 or higher does not automatically mean send_to_stage_2.
- The job must have substantial actual responsibilities in at least
  one target career track.
- Do not send a job to Stage 2 merely because it is technically
  sophisticated.
- Do not send customer engineer, partner engineer, manager, or
  infrastructure roles unless their actual responsibilities contain
  substantial hands-on work in a target career track.
- Do not assign applied_ai unless AI/ML work is a substantial part
  of the actual responsibilities.
- Do not assign telecom_ai unless telecom/network engineering,
  networking, network automation, wireless, 4G/5G, RAN, or similar
  target work is substantial.
- Do not assign cybersecurity merely because the company sells
  security products or because security is mentioned incidentally.

The recommendation must follow this logic:

IF relevance_score < 75:
    recommendation = "ignore"

ELSE IF no genuine target career track:
    recommendation = "ignore"

ELSE:
    recommendation = "send_to_stage_2"

The only valid recommendation values are:

"send_to_stage_2"
"ignore"

Never output "reject".
Never output "review".



=========================================================
OUTPUT
=========================================================

Return ONLY valid JSON:

{
    "relevance_score": 0-100,

    "career_tracks": [
        "telecom_ai",
        "cybersecurity",
        "quality_engineering",
        "applied_ai",
        "embedded_iot"
    ],

    "role_category": "",

    "seniority": "junior|mid|senior|unknown",

    "location_assessment": "",

    "summary": "",

    "why_relevant": [],

    "concerns": [],

    "recommendation": "send_to_stage_2|ignore"
}

Additional rules:

- career_tracks must contain only tracks that are genuinely
  supported by the job description.
- Do not add a track just because the job uses a related word.
- Do not inflate relevance scores.
- Do not use company reputation as evidence of relevance.
- Do not use salary as evidence of relevance.
- Do not use location as evidence of career relevance.
- Do not use seniority as evidence of career relevance.
- Base the decision primarily on actual responsibilities,
  required technical work, and the role's main purpose.
"""

# ============================================================
# Structured output schema
# ============================================================

JOB_INTELLIGENCE_SCHEMA = {

    "type": "object",

    "properties": {

        "relevance_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": (
                "Job-only relevance score. "
                "0-59 means reject; "
                "60-100 means potentially send to Stage 2."
            ),
        },

        "career_tracks": {
            "type": "array",
            "description": (
                "Target career tracks supported by the "
                "actual job responsibilities."
            ),
            "items": {
                "type": "string",
                "enum": [
                    "telecom_ai",
                    "cybersecurity",
                    "quality_engineering",
                    "applied_ai",
                    "embedded_iot",
                ],
            },
        },

        "role_category": {
            "type": "string",
            "description": (
                "Concise category describing the actual job role."
            ),
        },

        "seniority": {
            "type": "string",
            "enum": [
                "junior",
                "mid",
                "senior",
                "unknown",
            ],
        },

        "location_assessment": {
            "type": "string",
            "description": (
                "Only the job's explicitly stated location "
                "and work arrangement. Do not evaluate "
                "candidate suitability."
            ),
        },

        "summary": {
            "type": "string",
            "description": (
                "One concise sentence describing the job."
            ),
        },

        "why_relevant": {
            "type": "array",
            "description": (
                "Up to 3 concrete job-level reasons "
                "for relevance."
            ),
            "items": {
                "type": "string",
            },
        },

        "concerns": {
            "type": "array",
            "description": (
                "Up to 2 job-level concerns. "
                "Do not mention candidate fit."
            ),
            "items": {
                "type": "string",
            },
        },

        "recommendation": {
            "type": "string",
            "enum": [
                "send_to_stage_2",
                "reject",
            ],
            "description": (
                "Must be consistent with relevance_score: "
                "60-100 = send_to_stage_2; "
                "0-59 = reject."
            ),
        },
    },

    "required": [
        "relevance_score",
        "career_tracks",
        "role_category",
        "seniority",
        "location_assessment",
        "summary",
        "why_relevant",
        "concerns",
        "recommendation",
    ],

    "additionalProperties": False,
}


# ============================================================
# Deterministic Stage 1 normalization
# ============================================================

def _normalize_result(result):
    """
    Enforce the Stage 1 decision rule.

    The LLM provides the analysis and score.

    The application, not the LLM, makes the final binary
    recommendation:

        score >= 60 AND at least one target track
            -> send_to_stage_2

        otherwise
            -> reject

    This prevents contradictions such as:

        relevance_score = 0
        recommendation = send_to_stage_2
    """

    if not isinstance(result, dict):
        raise ValueError(
            "Stage 1 result must be a JSON object."
        )

    score = result.get(
        "relevance_score"
    )

    if (
        isinstance(score, bool)
        or not isinstance(score, int)
        or score < 0
        or score > 100
    ):
        raise ValueError(
            "Stage 1 relevance_score must be "
            "an integer between 0 and 100."
        )

    career_tracks = result.get(
        "career_tracks"
    )

    if not isinstance(
        career_tracks,
        list,
    ):
        raise ValueError(
            "Stage 1 career_tracks must be a list."
        )

    # --------------------------------------------------------
    # Final deterministic decision.
    #
    # We intentionally do NOT trust the model's recommendation
    # when it conflicts with the score/track evidence.
    # --------------------------------------------------------

    if (
        score >= STAGE_2_THRESHOLD
        and len(career_tracks) > 0
    ):
        result["recommendation"] = (
            "send_to_stage_2"
        )

    else:
        result["recommendation"] = (
            "reject"
        )

    return result


# ============================================================
# Job input
# ============================================================

def _build_job_prompt(job):
    """
    Build the job-only input.

    No candidate information is passed to Stage 1.
    """

    return json.dumps(
        {
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "description": job.get("description"),
        },
        ensure_ascii=False,
        indent=2,
    )


# ============================================================
# Main Stage 1 analysis
# ============================================================

def analyze_job_intelligence(job):

    client = OpenRouterClient()

    prompt = (
        SYSTEM_PROMPT
        + "\n\nJOB VACANCY:\n"
        + _build_job_prompt(job)
    )

    result, model = client.generate_json(

        prompt=prompt,

        schema=JOB_INTELLIGENCE_SCHEMA,

        stage="stage1",

        max_requests=LLM_CONFIG[
            "stage1_max_requests_per_job"
        ],
    )

    # --------------------------------------------------------
    # Enforce the binary Stage 1 decision.
    # --------------------------------------------------------

    result = _normalize_result(
        result
    )

    result["job_id"] = job["id"]

    result["model"] = model

    return result