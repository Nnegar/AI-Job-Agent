from analyzer.llm.openrouter_client import OpenRouterClient
from analyzer.personal_story_selector import select_personal_context


job = {
    "title": "Network Automation Engineer",
    "company": "Example Telecom Company",
    "description": """
    We are looking for a Network Automation Engineer
    with experience in 5G networks, Python,
    network performance analysis and automation.
    """
}


resume = """
MSc Telecommunications Engineering,
Politecnico di Milano.

Huawei:
- IP networking and troubleshooting
- 5G network performance analysis
- Python scripting
- Network KPI analysis
"""


# Load relevant stories and contact information
context = select_personal_context("telecom_ai")

print("Selected stories:", context["selected_keys"])


# Generate the cover letter
client = OpenRouterClient()

letter = client.generate_cover_letter(
    job=job,
    resume=resume,
    personal_story=context["stories"],
    candidate_name=context["name"],
)


# Add contact information after generation
contact = context["contact"]

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

letter = f"{header}\n\n{letter}"


print("\n--- GENERATED COVER LETTER ---\n")

print(letter)