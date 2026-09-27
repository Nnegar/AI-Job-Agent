import re
from collections import defaultdict


CAREER_TRACKS = {

    "telecom_ai": {
        "keywords": {
            # Very strong matches with your Huawei + thesis background
            "5g": 5,
            "ran": 5,
            "network automation": 5,
            "ip backbone": 5,
            "bgp": 4,
            "routing": 4,
            "network troubleshooting": 4,
            "wireless": 4,
            "telecom": 4,

            # Relevant but more general
            "network": 1,
            "infrastructure": 1,
            "systems engineer": 2,
            "dns": 2,
            "monitoring": 1,
            "observability": 1,
            "performance": 1,
            "traffic": 1,
        }
    },


    "cybersecurity": {
        "keywords": {
            # Strong security engineering indicators
            "vulnerability": 5,
            "threat detection": 5,
            "incident response": 5,
            "penetration testing": 5,
            "firewall": 4,
            "ddos": 4,
            "iam": 4,
            "soc": 3,

            # General security words
            "security": 2,
            "risk": 1,
            "compliance": 1,
        }
    },


    "quality_engineering": {
        "keywords": {
            # Strong QA automation indicators
            "test automation": 5,
            "selenium": 5,
            "playwright": 5,
            "pytest": 5,
            "regression testing": 4,
            "test framework": 4,

            # General QA indicators
            "qa": 3,
            "quality assurance": 3,
            "testing": 2,
            "validation": 1,
        }
    },


    "applied_ai": {
        "keywords": {
            # Strong AI engineering indicators
            "machine learning": 5,
            "mlops": 5,
            "llm": 5,
            "rag": 5,
            "ai agent": 5,
            "model deployment": 5,

            # General AI indicators
            "artificial intelligence": 4,
            "data science": 3,
            "model": 1,
            "ai": 1,
            "automation": 1,
        }
    },


    "embedded_iot": {
        "keywords": {
            # Strong embedded indicators
            "embedded system": 5,
            "firmware": 5,
            "signal processing": 5,
            "rf": 4,
            "iot": 4,

            # General indicators
            "device": 2,
            "hardware": 2,
        }
    },
}


ROLE_PENALTIES = {
        # Usually not your target direction
        "account executive": -10,
        "sales": -8,
        "marketing": -8,
        "recruiter": -8,
        "finance": -8,
        "legal": -8,
        "hr": -8,

        # Technical but less aligned with your current goal
        "solutions architect": -3,
        "partner engineer": -4,
        "developer advocate": -5,
        "customer engineer": -2,

        # Avoid over-selecting management roles
        "manager": -5,
        "director": -7,
        "head of": -7,
    }

def build_job_text(job):

    parts = [
        job.get("title", ""),
        job.get("content", ""),
    ]

    return " ".join(parts).lower()



def score_job(job):

    text = build_job_text(job)

    scores = defaultdict(int)
    matched = defaultdict(list)


    for track, config in CAREER_TRACKS.items():

        for keyword, weight in config["keywords"].items():

            if re.search(
                r"\b" + re.escape(keyword) + r"\b",
                text,
                re.I
            ):

                scores[track] += config["keywords"][keyword]
                matched[track].append(keyword)



    for role, penalty in ROLE_PENALTIES.items():

        if role in text:
            for track in scores:
                scores[track] += penalty



    ranking = sorted(
        scores.items(),
        key=lambda x: x[1],
        reverse=True
    )


    return {
        "scores": dict(scores),
        "ranking": ranking,
        "matched": dict(matched),
    }



def should_send_to_ai(job):

    result = score_job(job)

    if not result["ranking"]:
        return False


    best_score = result["ranking"][0][1]

    return best_score >= 6
