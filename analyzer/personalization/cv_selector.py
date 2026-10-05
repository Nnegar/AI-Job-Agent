from pathlib import Path
from typing import Dict, Any, Optional
import yaml

PROFILE_PATH = (
    Path(__file__).resolve().parents[2]
    / "profile"
    / "career_profile.yaml"
)

TRACK_ALIASES = {
    "telecom": "telecom_ai",
    "telecom_ai": "telecom_ai",
    "applied_ai": "applied_ai_data",
    "applied_ai_data": "applied_ai_data",
    "ai_telecom": "telecom_ai",
    "cybersecurity": "cybersecurity",
    "security": "cybersecurity",
    "quality_engineering": "quality_engineering",
    "qa": "quality_engineering",
    "embedded_iot": "embedded_iot",
    "iot": "embedded_iot",
    "embedded": "embedded_iot",
}


class CVSelector:
    def __init__(self, profile_path: Optional[Path] = None):
        target_path = profile_path or PROFILE_PATH
        with open(target_path, "r", encoding="utf-8") as file:
            self.profile = yaml.safe_load(file)
        self.resume_matching = self.profile.get("resume_matching", {})

    def select(self, job_text: Optional[str] = None, category: Optional[str] = None) -> Dict[str, Any]:
        """
        Select the best CV for a given category (primary track) or job text.
        If category is provided, matches directly against career_profile rules.
        Otherwise falls back to keyword analysis of job_text.
        """
        # 1. Direct category matching if provided
        if category:
            norm_cat = TRACK_ALIASES.get(category.strip().lower(), category.strip().lower())
            if norm_cat in self.resume_matching:
                cfg = self.resume_matching[norm_cat]
                primary = cfg.get("primary_cv", ["General_Technical_CV"])[0]
                alt = cfg.get("alternative_cv", [None])[0] if cfg.get("alternative_cv") else None
                return {
                    "category": norm_cat,
                    "recommended_cv": primary,
                    "alternative_cv": alt,
                }

        # 2. Text keyword matching fallback
        text = (job_text or "").lower()
        rules = {
            "quality_engineering": [
                "qa",
                "test",
                "automation",
                "sdet",
                "api testing",
            ],
            "cybersecurity": [
                "security",
                "vulnerability",
                "soc",
                "incident",
            ],
            "telecom_ai": [
                "5g",
                "ran",
                "network",
                "telecom",
            ],
            "embedded_iot": [
                "embedded",
                "iot",
                "edge ai",
            ],
        }

        scores = {}
        for cat, keywords in rules.items():
            score = sum(1 for kw in keywords if kw in text)
            scores[cat] = score

        best_score = max(scores.values()) if scores else 0
        if best_score > 0:
            category = max(scores, key=scores.get)
            cfg = self.resume_matching.get(category, {})
            primary = cfg.get("primary_cv", ["General_Technical_CV"])[0]
            alt = cfg.get("alternative_cv", [None])[0] if cfg.get("alternative_cv") else None
            return {
                "category": category,
                "recommended_cv": primary,
                "alternative_cv": alt,
            }

        # 3. Default fallback
        unclear_cfg = self.resume_matching.get("unclear_technical_role", {})
        fallback_cv = unclear_cfg.get("primary_cv", ["General_Technical_CV"])[0]
        return {
            "category": "unclear_technical_role",
            "recommended_cv": fallback_cv,
            "alternative_cv": None,
        }