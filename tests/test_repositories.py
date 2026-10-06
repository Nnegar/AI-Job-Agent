import unittest
import sqlite3
import os
import json
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
        import tempfile
        import json
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            temp_db_path = f.name

        try:
            conn = sqlite3.connect(temp_db_path)
            c = conn.cursor()
            c.execute("""
                CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY,
                    source TEXT,
                    source_job_id TEXT,
                    company TEXT,
                    title TEXT,
                    location TEXT,
                    url TEXT,
                    description TEXT,
                    requirements TEXT,
                    posted_at TIMESTAMP,
                    created_at TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE job_ai_analysis (
                    id INTEGER PRIMARY KEY,
                    job_id INTEGER,
                    relevance_score INTEGER,
                    career_tracks TEXT,
                    role_category TEXT,
                    seniority TEXT,
                    location_assessment TEXT,
                    summary TEXT,
                    why_relevant TEXT,
                    concerns TEXT,
                    recommendation TEXT,
                    model TEXT,
                    analyzed_at TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE candidate_job_analysis (
                    id INTEGER PRIMARY KEY,
                    job_id INTEGER,
                    match_score INTEGER
                )
            """)

            # Seed deterministic fixture jobs:
            # 1. Job 1: Eligible (recommendation='send_to_stage_2', score=85, no Stage 2 analysis)
            c.execute("INSERT INTO jobs (id, company, title) VALUES (1, 'Acme', 'AI Engineer')")
            c.execute(
                "INSERT INTO job_ai_analysis (job_id, relevance_score, recommendation, career_tracks, concerns) VALUES (?, ?, ?, ?, ?)",
                (1, 85, 'send_to_stage_2', json.dumps(['telecom_ai']), json.dumps([]))
            )

            # 2. Job 2: Eligible (recommendation='send_to_stage_2', score=70, no Stage 2 analysis)
            c.execute("INSERT INTO jobs (id, company, title) VALUES (2, 'Beta', 'Security Engineer')")
            c.execute(
                "INSERT INTO job_ai_analysis (job_id, relevance_score, recommendation, career_tracks, concerns) VALUES (?, ?, ?, ?, ?)",
                (2, 70, 'send_to_stage_2', json.dumps(['cybersecurity']), json.dumps([]))
            )

            # 3. Job 3: NOT eligible (recommendation='reject')
            c.execute("INSERT INTO jobs (id, company, title) VALUES (3, 'Gamma', 'Sales Manager')")
            c.execute(
                "INSERT INTO job_ai_analysis (job_id, relevance_score, recommendation, career_tracks, concerns) VALUES (?, ?, ?, ?, ?)",
                (3, 30, 'reject', json.dumps([]), json.dumps(['Not technical']))
            )

            # 4. Job 4: NOT eligible (score=55 < 60 threshold)
            c.execute("INSERT INTO jobs (id, company, title) VALUES (4, 'Delta', 'Junior IT')")
            c.execute(
                "INSERT INTO job_ai_analysis (job_id, relevance_score, recommendation, career_tracks, concerns) VALUES (?, ?, ?, ?, ?)",
                (4, 55, 'send_to_stage_2', json.dumps(['general']), json.dumps([]))
            )

            # 5. Job 5: NOT eligible (already analyzed in Stage 2)
            c.execute("INSERT INTO jobs (id, company, title) VALUES (5, 'Epsilon', 'Senior Cloud')")
            c.execute(
                "INSERT INTO job_ai_analysis (job_id, relevance_score, recommendation, career_tracks, concerns) VALUES (?, ?, ?, ?, ?)",
                (5, 90, 'send_to_stage_2', json.dumps(['sre_cloud']), json.dumps([]))
            )
            c.execute("INSERT INTO candidate_job_analysis (job_id, match_score) VALUES (5, 88)")

            conn.commit()
            conn.close()

            repo = CandidateJobRepository(temp_db_path)
            eligible = repo.get_eligible_stage2_jobs()

            # Should return exactly 2 eligible jobs: Job 1 (score 85) and Job 2 (score 70)
            self.assertEqual(len(eligible), 2)
            self.assertEqual(eligible[0]["id"], 1)
            self.assertEqual(eligible[0]["relevance_score"], 85)
            self.assertEqual(eligible[0]["career_tracks"], ["telecom_ai"])
            self.assertEqual(eligible[1]["id"], 2)
            self.assertEqual(eligible[1]["relevance_score"], 70)

            # Test limit parameter
            limited = repo.get_eligible_stage2_jobs(limit=1)
            self.assertEqual(len(limited), 1)
            self.assertEqual(limited[0]["id"], 1)

            repo.close()
        finally:
            if os.path.exists(temp_db_path):
                os.remove(temp_db_path)

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

    def test_pipeline_run_repository_operations(self):
        import tempfile
        from database.pipeline_run_repository import PipelineRunRepository

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            temp_db_path = f.name

        try:
            repo = PipelineRunRepository(temp_db_path)
            
            # Test starting a run
            run_id = repo.start_run()
            self.assertGreater(run_id, 0)

            # Test failing a run
            partial = {"stage1_evaluated": 10, "stage2_evaluated": 5}
            res = repo.fail_run(run_id, "Test error occurred", partial_summary=partial)
            self.assertTrue(res)

            # Verify recorded status
            cursor = repo.connection.cursor()
            cursor.execute("SELECT status, summary_json, completed_at FROM pipeline_execution_runs WHERE id = ?", (run_id,))
            row = cursor.fetchone()
            self.assertEqual(row["status"], "failed")
            self.assertIsNotNone(row["completed_at"])
            summary = json.loads(row["summary_json"])
            self.assertEqual(summary["error"], "Test error occurred")
            self.assertEqual(summary["stage1_evaluated"], 10)

            # Test cannot fail an already failed or completed run
            res_repeat = repo.fail_run(run_id, "Another error")
            self.assertFalse(res_repeat)

            # Test starting and cancelling a run
            run2_id = repo.start_run()
            res_cancel = repo.cancel_run(run2_id, partial_summary={"stage1_evaluated": 2})
            self.assertTrue(res_cancel)
            cursor.execute("SELECT status, summary_json FROM pipeline_execution_runs WHERE id = ?", (run2_id,))
            row2 = cursor.fetchone()
            self.assertEqual(row2["status"], "cancelled")

            # Test starting and completing a run
            run3_id = repo.start_run()
            res_complete = repo.complete_run(run3_id, {"new_jobs": 5, "collected": 20})
            self.assertTrue(res_complete)
            cursor.execute("SELECT status FROM pipeline_execution_runs WHERE id = ?", (run3_id,))
            self.assertEqual(cursor.fetchone()["status"], "completed")

            repo.close()
        finally:
            if os.path.exists(temp_db_path):
                os.remove(temp_db_path)


if __name__ == "__main__":
    unittest.main()
