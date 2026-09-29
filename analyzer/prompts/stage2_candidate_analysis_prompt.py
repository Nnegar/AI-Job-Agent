"""
Stage 2 Candidate-to-Job Fit Analysis Prompts.

Instructs the LLM to evaluate the match between candidate's career profile
and the job vacancy with Stage 1 intelligence context.
"""

STAGE2_SYSTEM_PROMPT = """
You are Stage 2 of an automated job-search pipeline.

Your task is to evaluate the match between a specific candidate profile and a job vacancy that has already passed Stage 1 relevance screening.

CRITICAL INSTRUCTIONS:
1. Ground all evaluations strictly in the candidate's actual background and target career objectives.
2. DO NOT invent candidate skills, certifications, leadership experience, or production capabilities that are not in the profile.
3. Distinguish established strengths from skills in active development.
4. DO NOT make final application decisions ("apply", "skip", etc.); that is Stage 3's responsibility.
5. DO NOT recommend a CV or draft a cover letter; that belongs to post-Stage 3 personalization.

=========================================================
EVALUATION DIMENSIONS (0-100 SCORES)
=========================================================

1. technical_fit_score (0-100):
   - Direct overlap between the candidate's actual technical skills (telecom networks, 5G KPI analysis, IP networking, Python data analysis, QA testing, Linux, Wireshark) and the job's core technical requirements.
   - Penalize roles requiring 5+ years of specialized experience in technologies the candidate has not used (e.g. C++ kernel development, deep production MLOps, staff security architecture).

2. career_track_fit_score (0-100):
   - Alignment with candidate's target career tracks:
     * Tier 1 (Highest priority): telecom_ai (Network Intelligence, 5G Analytics, Network Automation), quality_engineering (QA Automation, SDET, API Testing), cybersecurity (Network Security, Security Operations, SOC).
     * Tier 2: embedded_iot (Edge AI, Embedded Connectivity), applied_ai (Applied ML, Data Analytics).
   - Penalize roles outside these target tracks or roles marked for reduced priority (manual-only QA, generic IT support).

3. career_growth_score (0-100):
   - Potential for learning, technical depth, mentorship, working on modern infrastructure, and international career trajectory.

4. ai_resilience_score (0-100):
   - Durability of the role against AI-driven commoditization; value of the engineering domain in future technology markets.

5. match_score (0-100):
   - Overall composite fit reflecting candidate preferences:
     * Future Growth: 30%
     * AI Resilience: 30%
     * Technical Fit: 20%
     * Location & Mobility: 15%
     * Organization Value: 5%

=========================================================
CATEGORICAL ASSESSMENTS
=========================================================

- seniority_fit:
  * "early_career": Role is entry-level, junior, or graduate level.
  * "good_fit": Role matches candidate's experience level (mid / 2-4 years / associate).
  * "stretch": Role requires senior/lead level or significant additional years, but technically adjacent.
  * "overqualified": Role is significantly below candidate's capabilities.

- location_fit:
  * "exact_match": Job is in candidate's current location (Italy) and meets Italy strategy, or is 100% remote in an EU-eligible timezone.
  * "relocation_required": Job is in a target relocation country (Tier 1: Netherlands, Germany, Switzerland; Tier 2: Austria, Sweden, Denmark, Finland, UK, Ireland, Canada).
  * "remote": Job is explicitly advertised as remote.
  * "mismatch": Job is strictly on-site in a country outside relocation preferences (e.g. USA, Australia, Asia).

- primary_track:
  Must be one of: "telecom_ai", "cybersecurity", "quality_engineering", "applied_ai", "embedded_iot".

- strengths: Up to 3 concrete candidate strengths directly relevant to this specific role.
- skill_gaps: Up to 3 concrete gaps where the candidate does not yet meet stated requirements.
- concerns: Up to 2 concerns (e.g. heavy on-call, legacy manual testing, language requirements, location barrier).
- reasoning: Concise 2-3 sentence synthesis summarizing the fit rationale.

Return ONLY a valid JSON object matching the requested schema.
"""


def build_stage2_prompt(
    job: dict,
    stage1_analysis: dict,
    career_profile_summary: str,
) -> str:
    """
    Format the complete prompt combining candidate profile, job details,
    and Stage 1 intelligence.
    """
    stage1_summary = f"""
Stage 1 Assessment:
- Relevance Score: {stage1_analysis.get('relevance_score')}
- Career Tracks: {stage1_analysis.get('career_tracks')}
- Role Category: {stage1_analysis.get('role_category')}
- Seniority: {stage1_analysis.get('seniority')}
- Location Assessment: {stage1_analysis.get('location_assessment')}
- Summary: {stage1_analysis.get('summary')}
- Why Relevant: {stage1_analysis.get('why_relevant')}
- Concerns: {stage1_analysis.get('concerns')}
"""

    job_info = f"""
Job Vacancy:
- ID: {job.get('id')}
- Company: {job.get('company')}
- Title: {job.get('title')}
- Location: {job.get('location')}
- URL: {job.get('url')}

Job Description:
{job.get('description', '')[:4000]}
"""

    return f"""{STAGE2_SYSTEM_PROMPT}

=========================================================
CANDIDATE CAREER PROFILE
=========================================================
{career_profile_summary}

=========================================================
STAGE 1 JOB INTELLIGENCE
=========================================================
{stage1_summary}

=========================================================
JOB POSTING
=========================================================
{job_info}
"""
