
import csv
import json
import re
import sys
import zipfile
from pathlib import Path

from collector.description_extractor import clean_description
from collector.job_filter import is_relevant_title


# Look for specific activities, not isolated technical words.
SIGNALS = {
    "networking": [
        r"(?:troubleshoot|diagnos\w*|monitor\w*|configur\w*|optimiz\w*|automat\w*|deploy\w*|design\w*).{0,110}(?:network|BGP|DNS|routing|firewall|WAN|RAN|5G|wireless|connectivity|DDoS)",
        r"(?:network|BGP|DNS|routing|firewall|WAN|RAN|5G|wireless|connectivity|DDoS).{0,110}(?:troubleshoot|diagnos\w*|monitor\w*|configur\w*|optimiz\w*|automat\w*|deploy\w*|design\w*)",
        r"\b(?:network automation|network monitoring|RAN optimization|IP backbone)\b",
    ],
    "quality_engineering": [
        r"\b(?:test automation|automated testing|regression testing|QA engineer|quality assurance|software testing|test strategy|test framework|test plan)\b",
        r"\b(?:write|develop|create|design|maintain|execute|automate).{0,70}(?:regression|integration|functional|performance|end.to.end) tests?\b",
    ],
    "cybersecurity": [
        r"\b(?:detect|investigat\w*|mitigat\w*|respond|triage|remediat\w*|assess|monitor).{0,110}(?:vulnerabilit\w*|threat|security incident|malware|intrusion|attack)",
        r"\b(?:vulnerabilit\w*|threat|security incident|malware|intrusion|attack).{0,110}(?:detect|investigat\w*|mitigat\w*|respond|triage|remediat\w*|assess|monitor)",
        r"\b(?:vulnerability management|penetration testing|incident response|threat detection|security testing)\b",
    ],
    "applied_ai": [
        r"\b(?:develop|build|design|train|evaluate|deploy|fine.tune|implement|optimiz\w*).{0,100}(?:machine.learning model|ML model|ML pipeline|LLM application|RAG pipeline|AI agent|predictive model)",
        r"\b(?:machine.learning model|ML model|ML pipeline|LLM application|RAG pipeline|AI agent|predictive model).{0,100}(?:develop|build|design|train|evaluate|deploy|fine.tune|implement|optimiz\w*)",
        r"\b(?:MLOps|model training|model deployment|ML pipeline|RAG pipeline)\b",
    ],
    "embedded_iot": [
        r"\b(?:firmware development|embedded system|signal processing|RF design|IoT device)\b",
        r"\b(?:design|develop|debug|test|integrat\w*).{0,100}(?:firmware|microcontroller|embedded device|RF circuit)",
    ],
}

SIGNALS = {
    category: [re.compile(p, re.I) for p in patterns]
    for category, patterns in SIGNALS.items()
}

FOOTER = re.compile(
    r"^(?:benefits(?: and growth)?|compensation|equity|"
    r"equal opportunity|privacy notice)\s*:?$",
    re.I,
)

SENIOR = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|director|"
    r"head of|lead|manager)\b",
    re.I,
)

ROLE_REVIEW = re.compile(
    r"\b(?:sales|account executive|marketing|recruiter|"
    r"product manager|customer engineer|partner engineer)\b",
    re.I,
)


def analyze_description(description):
    lines = clean_description(description or "").splitlines()
    evidence = {}

    for line in lines:
        if FOOTER.match(line.strip()):
            break

        for category, patterns in SIGNALS.items():
            if any(p.search(line) for p in patterns):
                evidence.setdefault(category, [])

                if len(evidence[category]) < 2:
                    if line not in evidence[category]:
                        evidence[category].append(line[:250])

    return evidence


def load_export(path):
    if str(path).endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            return json.loads(archive.read("all_jobs.json"))

    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(path):
    data = load_export(path)
    rows = []

    for source in data["sources"]:
        for job in source["jobs"]:
            evidence = analyze_description(job.get("content"))
            title = job["title"]

            rows.append({
                "company": source["company"],
                "job_id": job["id"],
                "title": title,
                "location": job.get("location", {}).get("name", ""),
                "categories": "; ".join(evidence),
                "evidence": " | ".join(
                    f"{category}: {examples[0]}"
                    for category, examples in evidence.items()
                ),
                "old_title_match": is_relevant_title(title),
                "senior_title_flag": bool(SENIOR.search(title)),
                "role_review_flag": bool(ROLE_REVIEW.search(title)),
                "url": job["absolute_url"],
            })

    output = Path("reports/description_filter_audit.csv")
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)

    matched = [r for r in rows if r["categories"]]
    newly_found = [
        r for r in matched if not r["old_title_match"]
    ]

    print("Total postings:", len(rows))
    print("Description matches:", len(matched))
    print("Missed by original title check:", len(newly_found))
    print("Saved:", output)

    print("\nFirst 20 newly discovered titles:")
    for job in newly_found[:20]:
        print(
            job["company"],
            "|", job["title"],
            "|", job["categories"],
        )


if __name__ == "__main__":
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "reports/full_greenhouse_export.zip"
    )
    main(path)
