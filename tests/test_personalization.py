import os
import tempfile
import unittest
from pathlib import Path

from analyzer.personalization.cv_selector import CVSelector
from analyzer.personalization.story_selector import select_personal_context
from database.cover_letter_repository import CoverLetterRepository


class TestPersonalization(unittest.TestCase):
    def setUp(self):
        self.selector = CVSelector()

    def test_cv_selector_by_track(self):
        result_telecom = self.selector.select(category="telecom_ai")
        self.assertEqual(result_telecom["recommended_cv"], "Telecom_AI_CV")

        result_cyber = self.selector.select(category="cybersecurity")
        self.assertEqual(result_cyber["recommended_cv"], "Cybersecurity_Engineering_CV")

        result_qa = self.selector.select(category="quality_engineering")
        self.assertEqual(result_qa["recommended_cv"], "Quality_Engineering_CV")

        result_iot = self.selector.select(category="embedded_iot")
        self.assertEqual(result_iot["recommended_cv"], "Embedded_IoT_CV")

        result_applied_ai = self.selector.select(category="applied_ai")
        self.assertEqual(result_applied_ai["recommended_cv"], "Telecom_AI_CV")

    def test_cv_selector_by_keywords(self):
        result = self.selector.select(job_text="Experience with 5G RAN optimization and telecom protocols")
        self.assertEqual(result["recommended_cv"], "Telecom_AI_CV")

        result_sec = self.selector.select(job_text="SOC security analyst with vulnerability assessment and incident response")
        self.assertEqual(result_sec["recommended_cv"], "Cybersecurity_Engineering_CV")

    def test_cv_selector_fallback(self):
        result = self.selector.select(job_text="Completely generic unrelated role")
        self.assertEqual(result["recommended_cv"], "General_Technical_CV")

    def test_story_selector(self):
        context = select_personal_context("telecom_ai")
        self.assertEqual(context["name"], "Negar Najafi")
        self.assertIn("email", context["contact"])
        self.assertIn("huawei", context["selected_keys"]["professional_stories"])
        self.assertTrue(len(context["stories"]) > 100)


class TestCoverLetterRepository(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.repo = CoverLetterRepository(db_path=self.temp_db.name)

        # Create dummy job in temp db for foreign key
        cursor = self.repo.connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY,
                company TEXT,
                title TEXT,
                location TEXT,
                url TEXT
            )
            """
        )
        cursor.execute(
            "INSERT INTO jobs (id, company, title, location, url) VALUES (1, 'Cloudflare', 'Security Engineer', 'London', 'https://example.com/1')"
        )
        self.repo.connection.commit()

    def tearDown(self):
        self.repo.close()
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_save_and_get_draft(self):
        row_id = self.repo.save_draft(
            job_id=1,
            recommended_cv="Cybersecurity_Engineering_CV",
            letter_text="Dear Hiring Manager, I am excited to apply...",
            review_status="draft",
        )
        self.assertTrue(row_id > 0)

        draft = self.repo.get_draft_by_job_id(1)
        self.assertIsNotNone(draft)
        self.assertEqual(draft["job_id"], 1)
        self.assertEqual(draft["recommended_cv"], "Cybersecurity_Engineering_CV")
        self.assertEqual(draft["review_status"], "draft")
        self.assertIn("Dear Hiring Manager", draft["letter_text"])

    def test_update_draft(self):
        self.repo.save_draft(1, "Cybersecurity_Engineering_CV", "Version 1")
        self.repo.save_draft(1, "Cybersecurity_Engineering_CV", "Version 2")
        draft = self.repo.get_draft_by_job_id(1)
        self.assertEqual(draft["letter_text"], "Version 2")
        self.assertEqual(self.repo.get_draft_count(), 1)

    def test_update_status(self):
        self.repo.save_draft(1, "Cybersecurity_Engineering_CV", "Sample text")
        self.repo.update_review_status(1, "approved")
        draft = self.repo.get_draft_by_job_id(1)
        self.assertEqual(draft["review_status"], "approved")

    def test_empty_letter_raises(self):
        with self.assertRaises(ValueError):
            self.repo.save_draft(1, "Cybersecurity_Engineering_CV", "   ")


class TestApplicationRepository(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        from database.application_repository import ApplicationRepository
        self.repo = ApplicationRepository(db_path=self.temp_db.name)

        # Create dummy jobs table and applications table
        cursor = self.repo.connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY,
                company TEXT,
                title TEXT,
                location TEXT,
                url TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL UNIQUE,
                status TEXT DEFAULT 'discovered',
                application_url TEXT,
                applied_date TIMESTAMP,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            )
            """
        )
        cursor.execute(
            "INSERT INTO jobs (id, company, title, location, url) VALUES (1, 'Datadog', 'Network Engineer', 'Dublin', 'https://example.com/1')"
        )
        self.repo.connection.commit()

    def tearDown(self):
        self.repo.close()
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_upsert_and_lifecycle(self):
        # Discovered -> Shortlisted -> Prepared -> Applied
        self.repo.upsert_application(job_id=1, status="shortlisted", notes="Stage 3 approved")
        app = self.repo.get_by_job_id(1)
        self.assertIsNotNone(app)
        self.assertEqual(app["status"], "shortlisted")
        self.assertEqual(app["notes"], "Stage 3 approved")

        # Update to prepared
        self.repo.update_status(job_id=1, status="prepared", notes="Cover letter ready")
        app = self.repo.get_by_job_id(1)
        self.assertEqual(app["status"], "prepared")
        self.assertEqual(app["notes"], "Cover letter ready")

        # Counts
        counts = self.repo.get_status_counts()
        self.assertEqual(counts.get("prepared"), 1)

    def test_invalid_status_raises(self):
        with self.assertRaises(ValueError):
            self.repo.upsert_application(job_id=1, status="flying_to_moon")


if __name__ == "__main__":
    unittest.main()

