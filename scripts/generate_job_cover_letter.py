
import sys

from analyzer.job_repository import get_job
from analyzer.personal_story_selector import select_personal_context
from analyzer.llm.openrouter_client import OpenRouterClient
from analyzer.cover_letter_repository import save_cover_letter


# Temporary CV excerpt.
# Replace with the actual selected CV in a later step.
TEST_RESUME = """
MSc Telecommunications Engineering,
Politecnico di Milano.

Huawei experience:
- IP networking and troubleshooting
- Mobile network performance analysis
- Python scripting
- Network KPI analysis
"""


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python -m "
            "scripts.generate_job_cover_letter JOB_ID"
        )
        return

    job_id = int(sys.argv[1])
    job = get_job(job_id)

    # This first integration test supports telecom AI jobs.
    # Other categories will be enabled when we add their CVs.
    if job["category"] != "telecom_ai":
        print(
            "This test requires a job categorized "
            "as telecom_ai."
        )
        return

    if not job["description"]:
        print("Job description is missing.")
        return

    cv_id = job["recommended_cv"] or "Telecom_AI_CV"

    if cv_id != "Telecom_AI_CV":
        print("Selected CV does not match our test excerpt.")
        return

    context = select_personal_context(job["category"])

    print("Job:", job["title"])
    print("Company:", job["company"])
    print("Selected CV:", cv_id)
    print("Selected stories:", context["selected_keys"])

    client = OpenRouterClient()

    letter = client.generate_cover_letter(
        job={
            "title": job["title"],
            "company": job["company"],
            "description": job["description"],
        },
        resume=TEST_RESUME,
        personal_story=context["stories"],
        candidate_name=context["name"],
    )

    # Add contact details locally, not through the LLM.
    contact = context.get("contact", {})

    header = "\n".join(
        value
        for value in [
            context["name"],
            contact.get("email"),
            contact.get("phone"),
            contact.get("linkedin"),
        ]
        if value
    )

    complete_letter = f"{header}\n\n{letter}"

    print("\n--- COVER LETTER DRAFT ---\n")
    print(complete_letter)

    print(
        "\nTEST ONLY: This letter uses a temporary "
        "CV excerpt and must be reviewed."
    )

    confirmation = input(
        "\nSave this as a draft? [y/N]: "
    ).strip().lower()

    if confirmation != "y":
        print("Not saved.")
        return

    draft_id = save_cover_letter(
        job_id=job["id"],
        recommended_cv=cv_id,
        letter_text=complete_letter,
    )

    print(f"Draft saved successfully. ID: {draft_id}")


if __name__ == "__main__":
    main()
