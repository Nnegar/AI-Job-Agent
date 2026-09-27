import yaml


class CVSelector:


    def __init__(self):

        with open("profile/career_profile.yaml") as file:
            self.profile = yaml.safe_load(file)


    def select(self, job_text):

        text = job_text.lower()


        rules = {
            "quality_engineering": [
                "qa",
                "test",
                "automation",
                "sdet",
                "api testing"
            ],

            "cybersecurity": [
                "security",
                "vulnerability",
                "soc",
                "incident"
            ],

            "telecom_ai": [
                "5g",
                "ran",
                "network",
                "telecom"
            ],

            "embedded_iot": [
                "embedded",
                "iot",
                "edge ai"
            ]
        }


        scores = {}


        for category, keywords in rules.items():

            score = 0

            for keyword in keywords:

                if keyword in text:
                    score += 1

            scores[category] = score


        category = max(
            scores,
            key=scores.get
        )


        cv = self.profile["resume_matching"][category]["primary_cv"][0]


        return {
            "category": category,
            "recommended_cv": cv
        }