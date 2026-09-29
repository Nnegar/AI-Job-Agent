import unittest
from analyzer.stage3.decision_engine import (
    detect_country,
    evaluate_stage3_decision,
)


class TestStage3Engine(unittest.TestCase):
    def test_country_detection(self):
        self.assertEqual(detect_country("Lisbon, Portugal"), "Portugal")
        self.assertEqual(detect_country("London, UK"), "UK")
        self.assertEqual(detect_country("Munich, Germany"), "Germany")
        self.assertEqual(detect_country("Zurich, Switzerland"), "Switzerland")
        self.assertEqual(detect_country("Amsterdam, Netherlands"), "Netherlands")
        self.assertEqual(detect_country("Milan, Italy"), "Italy")
        self.assertEqual(detect_country("New York, United States"), "USA")
        self.assertEqual(detect_country("Denver"), "USA")
        self.assertEqual(detect_country(""), "Unknown")

    def test_disqualify_location_mismatch(self):
        job = {
            "id": 999,
            "match_score": 85,
            "technical_fit_score": 80,
            "seniority_fit": "good_fit",
            "location_fit": "mismatch",
            "location": "New York, USA",
        }
        decision = evaluate_stage3_decision(job)
        self.assertEqual(decision["decision"], "skip")
        self.assertEqual(decision["priority"], "none")
        self.assertLess(decision["final_score"], 40.0)

    def test_disqualify_overqualified_seniority(self):
        job = {
            "id": 998,
            "match_score": 75,
            "technical_fit_score": 70,
            "seniority_fit": "overqualified",
            "location_fit": "relocation_required",
            "location": "Paris, France",
        }
        decision = evaluate_stage3_decision(job)
        self.assertEqual(decision["decision"], "skip")
        self.assertEqual(decision["priority"], "none")

    def test_apply_decision_high_priority(self):
        job = {
            "id": 997,
            "match_score": 82,
            "technical_fit_score": 80,
            "career_growth_score": 80,
            "ai_resilience_score": 75,
            "seniority_fit": "good_fit",
            "location_fit": "relocation_required",
            "location": "Munich, Germany",
            "primary_track": "telecom_ai",
            "skill_gaps": [],
        }
        decision = evaluate_stage3_decision(job)
        self.assertEqual(decision["decision"], "apply")
        self.assertEqual(decision["priority"], "high")
        self.assertGreaterEqual(decision["final_score"], 80.0)
        self.assertEqual(decision["readiness"], "ready")

    def test_manual_review_for_moderate_match(self):
        job = {
            "id": 996,
            "match_score": 68,
            "technical_fit_score": 60,
            "career_growth_score": 70,
            "ai_resilience_score": 65,
            "seniority_fit": "stretch",
            "location_fit": "relocation_required",
            "location": "London, UK",
            "primary_track": "cybersecurity",
            "skill_gaps": ["Requires testing framework portfolio"],
        }
        decision = evaluate_stage3_decision(job)
        self.assertIn(decision["decision"], ("manual_review", "apply"))
        self.assertEqual(decision["readiness"], "needs_preparation")


if __name__ == "__main__":
    unittest.main()
