"""
Generate Shortlist Cover Letters Script.

Processes the Stage 3 shortlisted jobs (decision = 'apply'):
1. Selects the most appropriate CV variant using CVSelector & Stage 2 primary track.
2. Loads the full resume content using ResumeLoader.
3. Selects relevant personal & professional stories using StorySelector.
4. Generates a tailored, factually grounded cover letter using OpenRouter.
5. Saves the draft to cover_letter_drafts.
6. Updates the application status in applications table to 'prepared'.
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analyzer.llm.openrouter_client import OpenRouterClient
from analyzer.personalization.cv_selector import CVSelector
from analyzer.personalization.resume_loader import load_resume, get_available_resumes
from analyzer.personalization.story_selector import select_personal_context
from database.application_repository import ApplicationRepository
from database.cover_letter_repository import CoverLetterRepository

DB_PATH = PROJECT_ROOT / "database" / "jobs.db"



def fetch_shortlisted_jobs(
    db_path: Path = DB_PATH, job_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if job_id is not None:
        query = """
            SELECT
                j.id,
                j.company,
                j.title,
                j.location,
                j.url,
                j.description,
                s3.decision,
                s3.priority,
                s3.final_score,
                s2.primary_track,
                s2.match_score
            FROM jobs j
            JOIN job_stage3_analysis s3 ON j.id = s3.job_id
            JOIN candidate_job_analysis s2 ON j.id = s2.job_id
            WHERE j.id = ?
        """
        cursor.execute(query, (job_id,))
    else:
        query = """
            SELECT
                j.id,
                j.company,
                j.title,
                j.location,
                j.url,
                j.description,
                s3.decision,
                s3.priority,
                s3.final_score,
                s2.primary_track,
                s2.match_score
            FROM jobs j
            JOIN job_stage3_analysis s3 ON j.id = s3.job_id
            JOIN candidate_job_analysis s2 ON j.id = s2.job_id
            WHERE s3.decision = 'apply'
            ORDER BY
                CASE s3.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                s3.final_score DESC
        """
        cursor.execute(query)

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def build_candidate_header(context: Dict[str, Any]) -> str:
    contact = context.get("contact", {})
    parts = [
        context.get("name", "Negar Najafi"),
        contact.get("email"),
        contact.get("phone"),
        contact.get("linkedin"),
    ]
    return "\n".join(str(p) for p in parts if p)


def main():
    parser = argparse.ArgumentParser(
        description="Generate personalized cover letters for shortlisted jobs."
    )
    parser.add_argument("--job-id", type=int, help="Target specific job ID")
    parser.add_argument(
        "--limit", type=int, default=None, help="Maximum number of letters to generate"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate run without invoking LLM or writing drafts",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-generate cover letters even if drafts already exist",
    )
    args = parser.parse_args()

    print("==================================================")
    print("SHORTLIST PERSONALIZATION & COVER LETTER GENERATOR")
    print("==================================================")

    available_cvs = get_available_resumes()
    print(f"Available resumes: {available_cvs}")

    jobs = fetch_shortlisted_jobs(job_id=args.job_id)
    if not jobs:
        print("No eligible shortlisted jobs found.")
        return

    if args.limit:
        jobs = jobs[: args.limit]

    print(f"Total jobs to process: {len(jobs)}")
    print("--------------------------------------------------")

    cv_selector = CVSelector()
    cover_repo = CoverLetterRepository()
    app_repo = ApplicationRepository()
    llm_client = None if args.dry_run else OpenRouterClient()

    success_count = 0
    skip_count = 0

    for idx, job in enumerate(jobs, start=1):
        job_id = job["id"]
        company = job["company"]
        title = job["title"]
        location = job["location"]
        priority = job["priority"]
        final_score = job["final_score"]
        track = job.get("primary_track") or "general"

        print(f"\n[{idx}/{len(jobs)}] Job #{job_id}: {company} - {title} ({location})")
        print(f"       Priority: {priority.upper()} | Score: {final_score:.1f} | Track: {track}")

        # Check existing draft
        existing_draft = cover_repo.get_draft_by_job_id(job_id)
        if existing_draft and not args.force:
            print(f"       -> Draft already exists (Status: {existing_draft['review_status']}). Use --force to regenerate.")
            skip_count += 1
            continue

        # 1. CV Selection
        cv_match = cv_selector.select(job_text=job.get("description", ""), category=track)
        recommended_cv = cv_match["recommended_cv"]
        category = cv_match["category"]
        print(f"       -> Recommended CV: {recommended_cv} (Category: {category})")

        # 2. Load Resume Text
        try:
            resume_text = load_resume(recommended_cv)
            print(f"       -> Loaded CV text: {len(resume_text)} characters")
        except FileNotFoundError as err:
            print(f"       [ERROR] Could not load CV: {err}")
            continue

        # 3. Select Personal Context & Stories
        context = select_personal_context(category)
        selected_stories = context.get("selected_keys", {})
        print(f"       -> Selected Stories: {selected_stories}")

        if args.dry_run:
            print("       [DRY RUN] Skipped LLM generation.")
            success_count += 1
            continue

        # 4. Generate Cover Letter via LLM
        job_data = {
            "title": title,
            "company": company,
            "description": job.get("description", ""),
        }

        print("       -> Generating cover letter with OpenRouter...")
        try:
            raw_letter = llm_client.generate_cover_letter(
                job=job_data,
                resume=resume_text,
                personal_story=context["stories"],
                candidate_name=context["name"],
            )

            # 5. Format and Save
            header = build_candidate_header(context)
            final_letter = f"{header}\n\n{raw_letter.strip()}"

            cover_repo.save_draft(
                job_id=job_id,
                recommended_cv=recommended_cv,
                letter_text=final_letter,
                review_status="draft",
            )

            # 6. Update Application State
            notes = (
                f"CV: {recommended_cv} | Track: {category} | "
                f"Priority: {priority.upper()} | Score: {final_score:.1f}"
            )
            app_repo.upsert_application(
                job_id=job_id,
                status="prepared",
                application_url=job.get("url"),
                notes=notes,
            )

            print(f"       [SUCCESS] Saved draft ({len(final_letter)} chars). Application marked as 'prepared'.")
            success_count += 1

        except Exception as err:
            print(f"       [ERROR] Generation failed: {err}")

    print("\n==================================================")
    print("SUMMARY")
    print(f"Processed: {len(jobs)} | Generated: {success_count} | Skipped: {skip_count}")
    print(f"Total drafts in database: {cover_repo.get_draft_count()}")
    print("Application statuses:", app_repo.get_status_counts())
    print("==================================================")

    cover_repo.close()
    app_repo.close()


if __name__ == "__main__":
    main()
