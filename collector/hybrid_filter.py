
import re
from collections import Counter

from collector.job_filter import is_relevant_title
from collector.job_priority import classify_location
from scripts.audit_description_filter import analyze_description


TECH_TITLE = re.compile(
    r"\b(?:engineer(?:ing)?|developer|scientist|researcher|"
    r"architect|analyst|specialist|administrator|technician|"
    r"SRE|technical support)\b",
    re.I,
)

TECH_DEPARTMENT = re.compile(
    r"\b(?:engineering|infrastructure|security|"
    r"information technology|dev eng|platform|"
    r"technical post sales|support engineering|"
    r"professional services|data science|"
    r"observability|operations)\b",
    re.I,
)

NON_TARGET = re.compile(
    r"\b(?:account executive|business development representative|"
    r"deal desk|marketing|recruiter|recruitment|payroll|"
    r"legal|counsel|finance|accounting|revenue operations|"
    r"product manager|customer success manager|chief of staff)\b",
    re.I,
)

STRETCH = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|director|"
    r"head of|vice president|vp|lead|manager)\b",
    re.I,
)


def get_locations(job):
    # Cloudflare uses special posting-location metadata.
    for item in job.get("metadata") or []:
        if item.get("name") == "Job Posting Location":
            value = item.get("value")

            if value:
                return value if isinstance(value, list) else [value]

    # Datadog and Elastic generally expose usable locations here.
    location = (job.get("location") or {}).get("name", "")

    if location and location.lower() not in {
        "hybrid", "remote", "in-office"
    }:
        return [location]

    return [
        office.get("location") or office.get("name")
        for office in job.get("offices") or []
        if office.get("location") or office.get("name")
    ]


def classify_job(job):
    title = job.get("title", "").strip()

    department = " ".join(
        item.get("name", "")
        for item in job.get("departments") or []
    )

    locations = get_locations(job)

    if classify_location(locations) == "outside":
        # An explicitly broad regional listing needs human review.
        broad = any(
            re.search(r"\b(?:EMEA|Europe|global|anywhere)\b", loc, re.I)
            for loc in locations
        )
        if not broad:
            return "outside_region", {}, locations

    if NON_TARGET.search(title):
        if not re.search(r"\bengineer\b", title, re.I):
            return "non_target_function", {}, locations

    title_match = is_relevant_title(title)

    description_evidence = analyze_description(
        job.get("content") or ""
    )

    technical_context = bool(
        TECH_TITLE.search(title)
        or TECH_DEPARTMENT.search(department)
    )

    # The key hybrid rule.
    relevant = (
        title_match
        or (bool(description_evidence) and technical_context)
    )

    if not relevant:
        return "weak_match", description_evidence, locations

    if STRETCH.search(title):
        return "stretch_review", description_evidence, locations

    return "ai_queue", description_evidence, locations


def filter_export(data):
    queues = {
        "ai_queue": {},
        "stretch_review": {},
    }

    stats = Counter()

    for source in data["sources"]:
        company = source["company"]

        for job in source["jobs"]:
            decision, evidence, locations = classify_job(job)
            stats[decision] += 1

            if decision not in queues:
                continue

            # Deduplicate multi-country versions of the same role.
            key = (
                company,
                job.get("internal_job_id") or job["id"],
                job["title"].strip().lower(),
            )

            existing = queues[decision].get(key)

            if existing:
                existing["locations"] = sorted(
                    set(existing["locations"] + locations)
                )
                existing["posting_ids"].append(job["id"])
            else:
                queues[decision][key] = {
                    "company": company,
                    "job": job,
                    "locations": locations,
                    "posting_ids": [job["id"]],
                    "categories": list(evidence),
                }

    return (
        list(queues["ai_queue"].values()),
        list(queues["stretch_review"].values()),
        stats,
    )
