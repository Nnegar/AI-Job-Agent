import sqlite3
import re
from html.parser import HTMLParser
from html import unescape
from pathlib import Path


DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "jobs.db"
)


class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "li", "br", "h2", "h3"):
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def extract_requirements(description):

    parser = HTMLTextExtractor()
    parser.feed(unescape(description or ""))
    text = unescape("".join(parser.parts))

    pattern = re.compile(
        r"\b(?:experience|required|qualifications|"
        r"\d+\s*(?:-\s*\d+)?\s*\+?\s*years?|"
        r"work authorization)\b",
        re.IGNORECASE,
    )

    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
    ]

    return [
        line for line in lines
        if pattern.search(line)
    ]


def main():
    with sqlite3.connect(DB_PATH) as db:
        jobs = db.execute("""
            SELECT id, title, company, location,
                   description, url
            FROM raw_jobs
            ORDER BY id
        """).fetchall()

    print(f"Jobs to inspect: {len(jobs)}")

    for job in jobs:
        job_id, title, company, location, description, url = job

        print(f"\n{'=' * 60}")
        print(f"ID: {job_id}")
        print(f"Title: {title}")
        print(f"Company: {company}")
        print(f"Location: {location}")
        print(f"URL: {url}")

        requirements = extract_requirements(description)


        years_required = [
            requirement
            for requirement in requirements
            if re.search(
                r"\b\d+\s*\+?\s*years?\b",
                requirement,
                re.IGNORECASE,
            )
        ]

        print("\nEXPLICIT EXPERIENCE REFERENCES:")

        if years_required:
            for item in years_required:
                print("-", item)
        else:
            print("No numeric experience requirement detected.")

        print("\nPotential requirements:")

        if not requirements:
            print("No explicit requirements detected.")

        for requirement in requirements[:12]:
            print(f"- {requirement[:300]}")


if __name__ == "__main__":
    main()
