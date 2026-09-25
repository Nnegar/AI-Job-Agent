from pathlib import Path
import yaml

profile_path = Path("profile/personal_profile.yaml")

with profile_path.open(encoding="utf-8") as file:
    profile = yaml.safe_load(file)

sections = [
    "personal_stories",
    "professional_stories",
    "work_style",
    "career_motivation",
    "cover_letter_preferences",
]

for section in sections:
    print(f"\n{section}:")

    data = profile.get(section)

    if isinstance(data, dict):
        print(list(data.keys()))
    elif isinstance(data, list):
        print(f"List with {len(data)} items")
    else:
        print(f"Type: {type(data).__name__}")