import json

from analyzer.llm.openrouter_client import OpenRouterClient


SYSTEM_PROMPT = """
You are a job intelligence analyst.

Your task is to analyze a job vacancy itself.

Do NOT evaluate the candidate.
Do NOT consider the candidate profile.

Determine whether this vacancy is relevant for careers in:

- Telecom / Network Engineering
- Network Automation
- Cybersecurity
- Quality Engineering
- Applied AI
- Embedded / IoT

Analyze the actual responsibilities, not only the title.

Return ONLY JSON:

{
    "relevance_score": 0-100,

    "career_tracks": [
        "telecom_ai",
        "cybersecurity"
    ],

    "role_category": "",

    "seniority": "junior|mid|senior|unknown",

    "location_assessment": "",

    "summary": "",

    "why_relevant": [],

    "concerns": [],

    "recommendation":
        "send_to_stage_2|review|ignore"
}

Rules:

- A technical job with some missing skills can still be relevant.
- Do not reject only because of seniority.
- Do not trust marketing/company introduction text.
- Reject obvious non-technical roles.
"""


def analyze_job_intelligence(job):

    client = OpenRouterClient()

    response = client.client.chat.completions.create(
        model="nvidia/nemotron-3-super-120b-a12b:free",

        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "title": job["title"],
                        "company": job["company"],
                        "location": job["location"],
                        "description": job["description"]
                    },
                    ensure_ascii=False
                )
            }
        ],

        temperature=0.2,

        max_tokens=1000
    )


    content = response.choices[0].message.content

    result, _ = json.JSONDecoder().raw_decode(
        content[content.index("{"):]
    )

    return result
