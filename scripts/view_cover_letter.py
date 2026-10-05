import argparse
import sys
from pathlib import Path

from database.cover_letter_repository import CoverLetterRepository

def main():
    parser = argparse.ArgumentParser(description="View generated cover letter drafts.")
    parser.add_argument("--job-id", type=int, help="Job ID to view")
    parser.add_argument("--latest", action="store_true", help="View all recent drafts")
    args = parser.parse_args()

    repo = CoverLetterRepository()
    
    if args.job_id:
        draft = repo.get_draft_by_job_id(args.job_id)
        if not draft:
            print(f"No cover letter draft found for Job ID {args.job_id}")
            return
        print(f"=== COVER LETTER DRAFT FOR JOB #{args.job_id} ===")
        print(f"Recommended CV: {draft['recommended_cv']}")
        print(f"Review Status:  {draft['review_status']}")
        print(f"Updated At:     {draft['updated_at']}")
        print("--------------------------------------------------")
        print(draft["letter_text"])
        print("--------------------------------------------------")
    else:
        drafts = repo.get_all_drafts()
        print(f"Total drafts found: {len(drafts)}")
        for d in drafts:
            print(f"\n=== Job #{d['job_id']}: {d.get('company')} - {d.get('title')} ({d.get('location')}) ===")
            print(f"CV: {d['recommended_cv']} | Status: {d['review_status']} | Date: {d['updated_at']}")
            print("--------------------------------------------------")
            print(d["letter_text"][:400] + "...\n")

if __name__ == "__main__":
    main()
