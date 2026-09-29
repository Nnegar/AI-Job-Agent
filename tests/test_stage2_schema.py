import unittest
from analyzer.stage2.schema import normalize_stage2_result, STAGE2_ANALYSIS_SCHEMA


class TestStage2Schema(unittest.TestCase):
    def setUp(self):
        self.valid_sample = {
            "match_score": 82,
            "technical_fit_score": 80,
            "career_track_fit_score": 90,
            "career_growth_score": 85,
            "ai_resilience_score": 80,
            "seniority_fit": "good_fit",
            "location_fit": "relocation_required",
            "primary_track": "quality_engineering",
            "strengths": ["Strong QA testing experience", "Python familiarity"],
            "skill_gaps": ["Requires 3 years Playwright automation in production"],
            "concerns": ["Relocation required to Germany"],
            "reasoning": "Strong match for QA automation with adjacent experience.",
        }

    def test_valid_result_passes(self):
        normalized = normalize_stage2_result(dict(self.valid_sample))
        self.assertEqual(normalized["match_score"], 82)
        self.assertEqual(normalized["seniority_fit"], "good_fit")
        self.assertEqual(normalized["primary_track"], "quality_engineering")

    def test_invalid_score_bounds(self):
        sample = dict(self.valid_sample)
        sample["match_score"] = 105
        with self.assertRaises(ValueError):
            normalize_stage2_result(sample)

        sample["match_score"] = -5
        with self.assertRaises(ValueError):
            normalize_stage2_result(sample)

    def test_invalid_seniority_fit(self):
        sample = dict(self.valid_sample)
        sample["seniority_fit"] = "unknown_level"
        with self.assertRaises(ValueError):
            normalize_stage2_result(sample)

    def test_invalid_location_fit(self):
        sample = dict(self.valid_sample)
        sample["location_fit"] = "mars"
        with self.assertRaises(ValueError):
            normalize_stage2_result(sample)

    def test_invalid_primary_track(self):
        sample = dict(self.valid_sample)
        sample["primary_track"] = "finance"
        with self.assertRaises(ValueError):
            normalize_stage2_result(sample)

    def test_schema_required_fields(self):
        required = STAGE2_ANALYSIS_SCHEMA["required"]
        for field in (
            "match_score",
            "technical_fit_score",
            "career_track_fit_score",
            "career_growth_score",
            "ai_resilience_score",
            "seniority_fit",
            "location_fit",
            "primary_track",
            "strengths",
            "skill_gaps",
            "concerns",
            "reasoning",
        ):
            self.assertIn(field, required)


if __name__ == "__main__":
    unittest.main()
