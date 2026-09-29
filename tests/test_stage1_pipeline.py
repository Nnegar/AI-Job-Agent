import unittest
from analyzer.stage1.job_intelligence import _normalize_result, STAGE_2_THRESHOLD


class TestStage1Normalization(unittest.TestCase):
    def test_threshold_value(self):
        self.assertEqual(STAGE_2_THRESHOLD, 60)

    def test_normalize_valid_send_to_stage_2(self):
        input_data = {
            "relevance_score": 75,
            "career_tracks": ["telecom_ai"],
            "role_category": "Network Automation",
            "seniority": "mid",
            "location_assessment": "Italy",
            "summary": "Great match",
            "why_relevant": ["5G automation"],
            "concerns": [],
            "recommendation": "reject",  # LLM mistakenly output reject
        }
        normalized = _normalize_result(input_data)
        # Should be corrected to send_to_stage_2
        self.assertEqual(normalized["recommendation"], "send_to_stage_2")

    def test_normalize_low_score_rejected(self):
        input_data = {
            "relevance_score": 45,
            "career_tracks": ["telecom_ai"],
            "recommendation": "send_to_stage_2",  # LLM mistakenly said send
        }
        normalized = _normalize_result(input_data)
        self.assertEqual(normalized["recommendation"], "reject")

    def test_normalize_empty_tracks_rejected(self):
        input_data = {
            "relevance_score": 85,
            "career_tracks": [],  # Empty tracks
            "recommendation": "send_to_stage_2",
        }
        normalized = _normalize_result(input_data)
        self.assertEqual(normalized["recommendation"], "reject")


if __name__ == "__main__":
    unittest.main()
