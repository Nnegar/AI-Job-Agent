import re


PRIORITY_COUNTRIES = {
    "Netherlands",
    "Germany",
    "Switzerland",
}

SECONDARY_COUNTRIES = {
    "Austria",
    "Sweden",
    "Denmark",
    "Finland",
    "United Kingdom",
    "UK",
    "Ireland",
    "Canada",
}

OTHER_EU_COUNTRIES = {
    "Belgium",
    "Italy",
    "France",
    "Spain",
    "Portugal",
}

OTHER_COUNTRIES = {
    "United States",
    "USA",
    "US",
    "Japan",
    "Singapore",
    "India",
    "Australia",
}

SENIOR_TITLE_PATTERN = re.compile(
    r"\b(senior|sr\.?|staff|principal|"
    r"director|head of)\b",
    re.IGNORECASE,
)


def classify_location(locations):
    if not locations:
        return "unknown"

    results = []

    for location in locations:
        found = False

        groups = [
            ("priority", PRIORITY_COUNTRIES),
            ("secondary", SECONDARY_COUNTRIES),
            ("other_eu", OTHER_EU_COUNTRIES),
            ("outside", OTHER_COUNTRIES),
        ]

        for group, countries in groups:
            for country in countries:
                if re.search(
                    rf"\b{re.escape(country)}\b",
                    location,
                    re.IGNORECASE,
                ):
                    results.append(group)
                    found = True
                    break

            if found:
                break

        if not found:
            results.append("unknown")

    # A job may offer several possible countries.
    for priority in [
        "priority",
        "secondary",
        "other_eu",
        "unknown",
        "outside",
    ]:
        if priority in results:
            return priority

    return "unknown"


def classify_experience(title):
    if SENIOR_TITLE_PATTERN.search(title):
        return "senior"

    if re.search(
        r"\b(intern|internship|graduate|junior|"
        r"entry.level|associate)\b",
        title,
        re.IGNORECASE,
    ):
        return "early_career"

    return "unspecified"


def assess_priority(job):
    return {
        "location_priority": classify_location(
            job.get("posting_locations", [])
        ),
        "experience": classify_experience(
            job["title"]
        ),
    }
