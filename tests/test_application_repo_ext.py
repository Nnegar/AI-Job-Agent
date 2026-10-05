import unittest
import os
from database.application_repository import ApplicationRepository, normalize_status


class TestApplicationRepoExt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = "database/jobs.db"
        if not os.path.exists(cls.db_path):
            raise unittest.SkipTest("database/jobs.db not found")

    def test_pipeline_summary_and_queue(self):
        repo = ApplicationRepository(self.db_path)
        summary = repo.get_pipeline_summary()
        self.assertIn("applied", summary)
        self.assertIn("screening", summary)
        self.assertIn("interview", summary)
        self.assertIn("offered", summary)
        self.assertIn("rejected", summary)
        self.assertIn("prepared", summary)
        self.assertIn("all_active", summary)
        self.assertEqual(
            summary["all_active"],
            summary["applied"] + summary["screening"] + summary["interview"] + summary["offered"]
        )

        # Action queue should return jobs with decision = 'apply' and status = 'prepared'
        action_queue = repo.get_action_queue()
        self.assertIsInstance(action_queue, list)
        self.assertGreater(len(action_queue), 0)
        for job in action_queue:
            self.assertEqual(job["decision"], "apply")
            self.assertEqual(job["app_status"], "prepared")

        # Database jobs pagination
        db_page1 = repo.get_database_jobs(page=1, limit=10)
        self.assertIn("items", db_page1)
        self.assertIn("total", db_page1)
        self.assertEqual(len(db_page1["items"]), 10)
        self.assertGreaterEqual(db_page1["total"], 219)
        self.assertGreaterEqual(db_page1["total_pages"], 22)

        # Filter options
        filters = repo.get_filter_options()
        self.assertIn("companies", filters)
        self.assertIn("tracks", filters)
        self.assertIn("sources", filters)
        self.assertIn("statuses", filters)

        repo.close()

    def test_update_notes(self):
        repo = ApplicationRepository(self.db_path)
        # Job 1 is used in integration tests
        test_notes = '{"recruiter":"Bob","salary":"€120k"}'
        success = repo.update_notes(1, test_notes)
        self.assertTrue(success)
        app = repo.get_by_job_id(1)
        self.assertIsNotNone(app)
        self.assertEqual(app["notes"], test_notes)
        repo.close()

    def test_status_normalization(self):
        self.assertEqual(normalize_status("interviewing"), "interview")
        self.assertEqual(normalize_status("offer"), "offered")
        self.assertEqual(normalize_status("applied"), "applied")


if __name__ == "__main__":
    unittest.main()
