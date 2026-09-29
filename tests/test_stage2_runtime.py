import unittest
import time
from analyzer.llm.stage2_runtime import Stage2Runtime


class TestStage2Runtime(unittest.TestCase):
    def setUp(self):
        self.runtime = Stage2Runtime()
        # Use isolated in-memory test state
        self.runtime.state = {
            "date": self.runtime._today(),
            "daily_requests": 0,
            "request_timestamps": [],
            "last_successful_model": None,
            "model_cooldowns": {},
        }

    def test_model_ordering_default(self):
        models = [
            {"name": "openai/gpt-4.1-mini"},
            {"name": "openai/gpt-4.1-nano"},
            {"name": "google/gemini-3.7-flash"},
        ]
        ordered = self.runtime.ordered_models(models)
        self.assertEqual(len(ordered), 3)
        self.assertEqual(ordered[0]["name"], "openai/gpt-4.1-mini")

    def test_model_ordering_with_preferred(self):
        models = [
            {"name": "openai/gpt-4.1-mini"},
            {"name": "openai/gpt-4.1-nano"},
            {"name": "google/gemini-3.7-flash"},
        ]
        self.runtime.state["last_successful_model"] = "google/gemini-3.7-flash"
        ordered = self.runtime.ordered_models(models)
        self.assertEqual(ordered[0]["name"], "google/gemini-3.7-flash")

    def test_cooldown_excludes_model(self):
        models = [
            {"name": "openai/gpt-4.1-mini"},
            {"name": "openai/gpt-4.1-nano"},
        ]
        self.runtime.state["model_cooldowns"]["openai/gpt-4.1-mini"] = time.time() + 60
        ordered = self.runtime.ordered_models(models)
        self.assertEqual(len(ordered), 1)
        self.assertEqual(ordered[0]["name"], "openai/gpt-4.1-nano")

    def test_mark_success_and_failure(self):
        self.runtime.mark_failure("openai/gpt-4.1-mini", RuntimeError("429 rate limit"))
        self.assertIn("openai/gpt-4.1-mini", self.runtime.state["model_cooldowns"])
        
        self.runtime.mark_success("openai/gpt-4.1-mini")
        self.assertNotIn("openai/gpt-4.1-mini", self.runtime.state["model_cooldowns"])
        self.assertEqual(
            self.runtime.state["last_successful_model"], "openai/gpt-4.1-mini"
        )


if __name__ == "__main__":
    unittest.main()
