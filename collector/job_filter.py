import re
from collector.job_priority import assess_priority


TITLE_KEYWORDS = [
    # Telecommunications
    "network engineer",
    "network automation",
    "network intelligence",
    "telecom",
    "wireless",
    "5g",
    "ran engineer",

    # Cybersecurity
    "cybersecurity",
    "security engineer",
    "security analyst",

    # Quality engineering
    "qa engineer",
    "quality engineer",
    "test engineer",
    "test automation",
    "sdet",

    # AI and data
    "machine learning",
    "ai engineer",
    "data engineer",
    "data scientist",

    # Embedded and IoT
    "embedded engineer",
    "iot engineer",
]


def is_relevant_title(title):
    title = title.lower()

    return any(
        re.search(
            rf"\b{re.escape(keyword)}\b",
            title
        )
        for keyword in TITLE_KEYWORDS
    )


def filter_jobs(jobs):
    return [
        job for job in jobs
        if is_relevant_title(job["title"])
    ]


def filter_candidates(jobs):
    relevant = filter_jobs(jobs)

    candidates = []

    for job in relevant:
        assessment = assess_priority(job)

        # Exclude locations outside our search area.
        if assessment["location_priority"] == "outside":
            continue

        # Deprioritize explicitly senior positions.
        if assessment["experience"] == "senior":
            continue

        job["location_priority"] = assessment["location_priority"]
        job["experience_level"] = assessment["experience"]

        candidates.append(job)

    return candidates