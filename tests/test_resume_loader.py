import unittest
from pathlib import Path
from analyzer.personalization.resume_loader import (
    load_resume,
    get_available_resumes,
    RESUMES_DIR,
)

class TestResumeLoader(unittest.TestCase):
    def test_get_available_resumes(self):
        available = get_available_resumes()
        self.assertIsInstance(available, list)
        self.assertIn("Telecom_AI_CV", available)
        self.assertIn("Cybersecurity_Engineering_CV", available)
        self.assertIn("Quality_Engineering_CV", available)
        self.assertIn("Embedded_IoT_CV", available)
        self.assertIn("General_Technical_CV", available)

    def test_load_telecom_cv(self):
        content = load_resume("Telecom_AI_CV")
        self.assertIn("Negar Najafi", content)
        self.assertIn("5G", content)
        self.assertTrue(len(content) > 500)

    def test_load_cybersecurity_cv(self):
        content = load_resume("Cybersecurity_Engineering_CV")
        self.assertIn("Negar Najafi", content)
        self.assertTrue("cybersecurity" in content.lower() or "security" in content.lower())
        self.assertTrue(len(content) > 500)

    def test_non_existent_cv_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_resume("NonExistent_CV_Name_12345")

if __name__ == "__main__":
    unittest.main()
