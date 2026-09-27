import re
from collections import Counter

from collector.description_filter import analyze_description
from collector.job_filter import is_relevant_title
from collector.job_priority import assess_priority


NON_TARGET_TITLE = re.compile(
    r"\b(?:"
    r"account executive|"
    r"business development|"
    r"marketing|"
    r"recruiter|"
    r"recruitment|"
    r"payroll|"
    r"legal|"
    r"counsel|"
    r"finance|"
    r"accounting|"
    r"revenue operations|"
    r"product manager|"
    r"customer success manager|"
    r"sales"
    r")\b",
    re.IGNORECASE,
)


def get_locations(job):

    locations = job.get("posting_locations") or []

    if locations:
        return locations

    location = job.get("location", "")

    if location and location.lower() not in {
        "hybrid",
        "remote",
        "in-office",
    }:
        return [location]

    return []


def classify_job(job):

    title = job.get("title", "").strip()

    description = job.get("description", "")

    locations = get_locations(job)

    priority = assess_priority(
        {
            **job,
            "posting_locations": locations,
        }
    )

    # Remove clearly irrelevant geographical locations.
    if priority["location_priority"] == "outside":
        return (
            "outside_region",
            {},
            priority,
        )

    # Remove clearly non-target functions.
    if NON_TARGET_TITLE.search(title):
        return (
            "non_target_function",
            {},
            priority,
        )

    title_match = is_relevant_title(title)

    description_evidence = analyze_description(
        description
    )

    description_match = bool(
        description_evidence
    )

    # The Python filter is intentionally broad.
    # Either title OR description evidence is enough.
    if not title_match and not description_match:
        return (
            "weak_match",
            {},
            priority,
        )

    return (
        "ai_queue",
        description_evidence,
        priority,
    )


def filter_jobs_for_ai(jobs):

    candidates = []

    stats = Counter()

    for job in jobs:

        decision, evidence, priority = classify_job(
            job
        )

        stats[decision] += 1

        if decision != "ai_queue":
            continue

        candidate = dict(job)

        # Keep the filter information with the job.
        # Stage 1 AI can use the original job data;
        # these fields are useful for debugging/auditing.
        candidate["filter_categories"] = list(
            evidence.keys()
        )

        candidate["filter_location_priority"] = (
            priority["location_priority"]
        )

        candidate["filter_experience_level"] = (
            priority["experience"]
        )

        candidates.append(candidate)

    return candidates, stats