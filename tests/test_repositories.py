import unittest
import sqlite3
import os
from database.candidate_job_repository import CandidateJobRepository
from database.job_ai_repository import JobAIRepository
from database.job_repository import JobRepository


class TestRepositories(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = "database/jobs.db"
        if not os.path.exists(cls.db_path):
            raise unittest.SkipTest("database/jobs.db not found")

    def test_job_repository_exists_and_reads(self):
        repo = JobRepository(self.db_path)
        job = repo.get_job_by_id(1)
        self.assertIsNotNone(job)
        self.assertEqual(job["id"], 1)
        repo.close()

    def test_job_ai_repository_reads(self):
        repo = JobAIRepository(self.db_path)
        analysis = repo.get_analysis_by_job_id(1)
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis["job_id"], 1)
        repo.close()

    def test_candidate_job_repository_eligible_jobs(self):
        repo = CandidateJobRepository(self.db_path)
        eligible = repo.get_eligible_stage2_jobs()
        
        # Total valid Stage 1 candidates = unanalyzed in Stage 2 + already analyzed in Stage 2
        cursor = repo.connection.cursor()
        cursor.execute("SELECT count(*) FROM candidate_job_analysis")
        already_analyzed = cursor.fetchone()[0]
        self.assertEqual(len(eligible) + already_analyzed, 134)

        # Check every job meets the criteria:
        # score >= 60 and recommendation == 'send_to_stage_2'
        corrupted_legacy_ids = {1, 8, 10, 15, 17, 22, 23, 27, 31, 32, 33}
        for job in eligible:
            self.assertGreaterEqual(job["relevance_score"], 60)
            self.assertEqual(job["recommendation"], "send_to_stage_2")
            self.assertNotIn(job["id"], corrupted_legacy_ids)
            self.assertIsInstance(job["career_tracks"], list)
            self.assertGreater(len(job["career_tracks"]), 0)

        # Test limit parameter
        limited = repo.get_eligible_stage2_jobs(limit=5)
        self.assertEqual(len(limited), min(5, len(eligible)))
        if eligible:
            self.assertEqual(limited[0]["id"], eligible[0]["id"])
        
        repo.close()

    def test_stage3_repository_operations(self):
        from database.stage3_repository import Stage3Repository
        repo = Stage3Repository(self.db_path)
        
        # Test reading Stage 2 jobs for filtering
        jobs = repo.get_stage2_jobs_for_filtering(only_unanalyzed=False)
        self.assertGreaterEqual(len(jobs), 134)
        
        # Test save and retrieve
        test_decision = {
            "job_id": 14,
            "decision": "apply",
            "priority": "high",
            "final_score": 85.5,
            "application_method": "manual",
            "readiness": "ready",
            "decision_reasons": ["Test reason 1", "Test reason 2"],
        }
        repo.save_decision(test_decision)
        saved = repo.get_decision_by_job_id(14)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["job_id"], 14)
        self.assertEqual(saved["decision"], "apply")
        self.assertEqual(saved["priority"], "high")
        self.assertEqual(saved["decision_reasons"], ["Test reason 1", "Test reason 2"])
        
        repo.close()


if __name__ == "__main__":
    unittest.main()
