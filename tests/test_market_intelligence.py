import os
import tempfile
import unittest

from analyzer.market.market_analyzer import MarketAnalyzer
from analyzer.market.skill_extractor import extract_skills_for_job
from database.market_intelligence_repository import MarketIntelligenceRepository


class TestMarketIntelligence(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.repo = MarketIntelligenceRepository(db_path=self.temp_db.name)

        # Create dummy jobs table
        cursor = self.repo.connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY,
                company TEXT,
                title TEXT,
                location TEXT,
                description TEXT
            )
            """
        )
        cursor.execute(
            "INSERT INTO jobs (id, company, title, location, description) VALUES (1, 'Cloudflare', 'Network Security Engineer', 'London', 'Looking for Python, Kubernetes, and SIEM experience')"
        )
        self.repo.connection.commit()

    def tearDown(self):
        self.repo.close()
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_extract_skills(self):
        desc = "Seeking an engineer with strong Python, 5G, and Docker skills. Familiarity with Wireshark and BGP."
        strengths = ["Strong 5G network performance background", "Proficient in Python and Wireshark"]
        gaps = ["No direct Kubernetes container orchestration experience", "Lacks hands-on Splunk SIEM deployment"]

        skills = extract_skills_for_job(1, desc, strengths, gaps)
        names = [s["name"] for s in skills]

        self.assertIn("Python", names)
        self.assertIn("5G", names)
        self.assertIn("Kubernetes", names)
        self.assertIn("SIEM", names)

        # Check gap tagging
        k8s_skill = next(s for s in skills if s["name"] == "Kubernetes")
        self.assertEqual(k8s_skill["is_gap"], 1)

        python_skill = next(s for s in skills if s["name"] == "Python")
        self.assertEqual(python_skill["is_gap"], 0)

    def test_record_and_query_skills(self):
        skills = [
            {"name": "Python", "category": "programming", "is_gap": 0},
            {"name": "Kubernetes", "category": "cloud_devops", "is_gap": 1},
        ]
        inserted = self.repo.record_skills(1, skills)
        self.assertEqual(inserted, 2)
        self.assertTrue(self.repo.has_skills_for_job(1))

        top_skills = self.repo.get_top_market_skills(limit=5)
        self.assertEqual(len(top_skills), 2)

        gaps = self.repo.get_top_candidate_gaps(limit=5)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["skill_name"], "Kubernetes")


if __name__ == "__main__":
    unittest.main()
