import json


COVER_LETTER_PROMPT = """
You are a professional cover letter writer.

Write a personalized cover letter using the
information provided below.

CANDIDATE NAME:
{candidate_name}

JOB DESCRIPTION:
{job}


CANDIDATE RESUME:
{resume}


RELEVANT PERSONAL STORY:
{personal_story}


REQUIREMENTS:

1. Write in natural, professional English.

2. Connect the candidate's actual experience
   to the job requirements.

3. Use the personal story naturally when relevant.

4. Do not repeat the entire resume.

5. Do not invent skills, experience, achievements,
   or company-specific information.

6. Distinguish existing skills from skills
   the candidate is still developing.

7. Keep the letter concise: 250-350 words.

8. Avoid generic phrases and exaggerated enthusiasm.

9. Do not mention every personal story.

10. Do not include placeholders or invented
    names of hiring managers.


Return only the cover letter text.

FACTUAL ACCURACY RULES:

- Treat the supplied job, resume, and personal story
  as the only sources of candidate information.

- Do not invent numbers, percentages, time savings,
  business impact, achievements, responsibilities,
  tools, certifications, or years of experience.

- Do not turn a general activity into a specific
  achievement unless the input supports it.

- Do not claim experience with a technology merely
  because it appears in the job description.

- Distinguish what the candidate has done from what
  the candidate wants to learn.

- If a detail is missing, omit it rather than
  guessing.

- Before returning the letter, check every factual
  claim against the supplied information. Remove
  or rewrite unsupported claims.
"""


def build_cover_letter_prompt(
    job,
    resume,
    personal_story,
    candidate_name,
):
    return COVER_LETTER_PROMPT.format(
        job=json.dumps(job, ensure_ascii=False),
        resume=resume,
        personal_story=personal_story,
        candidate_name=candidate_name,
    )
