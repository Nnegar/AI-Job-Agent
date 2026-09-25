from pathlib import Path

import yaml


PROFILE_PATH = (
    Path(__file__).resolve().parents[1]
    / "profile"
    / "personal_profile.yaml"
)


STORY_RULES = {
    "telecom_ai": {
        "personal_stories": [
            "wireless_curiosity",
            "ai_curiosity",
        ],
        "professional_stories": [
            "huawei",
            "telecom_thesis",
        ],
    },

    "cybersecurity": {
        "personal_stories": [],
        "professional_stories": [
            "current_work",
            "huawei",
        ],
    },

    "quality_engineering": {
        "personal_stories": [],
        "professional_stories": [
            "qa_discovery",
            "current_work",
            "huawei",
        ],
    },

    "embedded_iot": {
        "personal_stories": [
            "wireless_curiosity",
        ],
        "professional_stories": [
            "telecom_thesis",
        ],
    },

    "applied_ai_data": {
        "personal_stories": [
            "ai_curiosity",
        ],
        "professional_stories": [
            "telecom_thesis",
            "independent_ai_project",
        ],
    },
}


def select_personal_context(job_category):
    with PROFILE_PATH.open(encoding="utf-8") as file:
        profile = yaml.safe_load(file)

    if not isinstance(profile, dict):
        raise ValueError("Invalid personal profile")

    rules = STORY_RULES.get(job_category, {
        "personal_stories": [],
        "professional_stories": [
            "huawei",
            "current_work",
        ],
    })

    selected_stories = {}

    for section, story_names in rules.items():

        available_stories = profile.get(section, {})

        if not isinstance(available_stories, dict):
            raise ValueError(
                f"Expected a dictionary in {section}"
            )

        selected_stories[section] = {
            name: available_stories[name]
            for name in story_names
            if name in available_stories
        }

    return {
        "name": profile["identity"]["name"],
        
        "contact": profile["identity"].get("contact", {}),

        "stories": yaml.safe_dump(
            selected_stories,
            allow_unicode=True,
            sort_keys=False,
        ),

        "selected_keys": {
            section: list(stories.keys())
            for section, stories in selected_stories.items()
        },
    }
