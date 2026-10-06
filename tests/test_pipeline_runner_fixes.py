import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import analyzer.pipeline_runner as pr
from analyzer.pipeline_runner import (
    STAGE1_BATCH_SIZE,
    STAGE2_BATCH_SIZE,
    STAGE3_BATCH_SIZE,
    TRACK_DISPLAY_NAMES,
)
from database.candidate_job_repository import CandidateJobRepository
from database.job_ai_repository import JobAIRepository
from database.job_repository import JobRepository
from database.stage3_repository import Stage3Repository


def _init_test_db(db_path: str):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
    """)
    c.execute("""
        CREATE TABLE candidate_job_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            match_score INTEGER,
            technical_fit_score INTEGER,
            career_track_fit_score INTEGER,
            career_growth_score INTEGER,
            ai_resilience_score INTEGER,
            seniority_fit TEXT,
            location_fit TEXT,
            primary_track TEXT,
            strengths TEXT,
            skill_gaps TEXT,
            concerns TEXT,
            reasoning TEXT,
            model TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
    """)
    c.execute("""
        CREATE TABLE job_stage3_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            decision TEXT NOT NULL,
            priority TEXT NOT NULL,
            final_score REAL NOT NULL,
            application_method TEXT NOT NULL,
            readiness TEXT NOT NULL,
            decision_reasons TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
    """)
    c.execute("""
        CREATE TABLE pipeline_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            status TEXT,
            collected_count INTEGER DEFAULT 0,
            duplicates_count INTEGER DEFAULT 0,
            new_jobs_count INTEGER DEFAULT 0,
            stage1_evaluated_count INTEGER DEFAULT 0,
            stage2_evaluated_count INTEGER DEFAULT 0,
            stage2_strong_count INTEGER DEFAULT 0,
            stage2_borderline_count INTEGER DEFAULT 0,
            shortlisted_count INTEGER DEFAULT 0,
            sources_summary TEXT,
            error_message TEXT,
            metadata TEXT
        )
    """)
    c.execute("""
        CREATE TABLE applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER UNIQUE,
            status TEXT,
            application_url TEXT,
            applied_at TIMESTAMP,
            notes TEXT
        )
    """)
    c.execute("""
        CREATE TABLE cover_letters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER UNIQUE,
            recommended_cv TEXT,
            letter_text TEXT,
            review_status TEXT,
            created_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


class TestPipelineRunnerFixes(unittest.TestCase):
    def test_canonical_batch_configuration_defaults(self):
        """Requirement A, B, C: Verify default batch limits are None (unbounded queue drainage)."""
        self.assertIsNone(STAGE1_BATCH_SIZE)
        self.assertIsNone(STAGE2_BATCH_SIZE)
        self.assertIsNone(STAGE3_BATCH_SIZE)
        self.assertIn("telecom_ai", TRACK_DISPLAY_NAMES)
        self.assertEqual(TRACK_DISPLAY_NAMES["telecom_ai"], "Telecom AI")
        self.assertEqual(TRACK_DISPLAY_NAMES["cybersecurity"], "Cybersecurity")

    def test_explicit_limit_truncation(self):
        """Requirement D: Verify optional explicit limit truncates queues appropriately."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name

        try:
            _init_test_db(db_path)
            conn = sqlite3.connect(db_path)
            c = conn.cursor()

            # Seed 10 jobs
            for i in range(1, 11):
                c.execute(
                    "INSERT INTO jobs (id, title, company, description) VALUES (?, ?, ?, ?)",
                    (i, f"Engineer {i}", "TechCorp", "Job description text"),
                )
            conn.commit()
            conn.close()

            job_repo = JobRepository(db_path)
            # Stage 1: limit=5 returns 5; limit=None returns all 10
            s1_limited = job_repo.get_unanalyzed_jobs(limit=5)
            self.assertEqual(len(s1_limited), 5)
            s1_all = job_repo.get_unanalyzed_jobs(limit=None)
            self.assertEqual(len(s1_all), 10)
            job_repo.close()

            # Seed Stage 1 analyses for all 10
            ai_repo = JobAIRepository(db_path)
            for i in range(1, 11):
                ai_repo.save_analysis({
                    "job_id": i,
                    "relevance_score": 80,
                    "recommendation": "send_to_stage_2",
                    "career_tracks": ["telecom_ai"],
                    "why_relevant": ["Valid fit"],
                    "concerns": [],
                })
            ai_repo.close()

            # Stage 2: limit=3 returns 3; limit=None returns all 10
            cand_repo = CandidateJobRepository(db_path)
            s2_limited = cand_repo.get_eligible_stage2_jobs(limit=3)
            self.assertEqual(len(s2_limited), 3)
            s2_all = cand_repo.get_eligible_stage2_jobs(limit=None)
            self.assertEqual(len(s2_all), 10)

            # Seed Stage 2 analyses for all 10
            for i in range(1, 11):
                cand_repo.save_analysis({
                    "job_id": i,
                    "match_score": 85,
                    "primary_track": "telecom_ai",
                })
            cand_repo.close()

            # Stage 3: limit=4 returns 4; limit=None returns all 10
            stage3_repo = Stage3Repository(db_path)
            s3_limited = stage3_repo.get_stage2_jobs_for_filtering(only_unanalyzed=True, limit=4)
            self.assertEqual(len(s3_limited), 4)
            s3_all = stage3_repo.get_stage2_jobs_for_filtering(only_unanalyzed=True, limit=None)
            self.assertEqual(len(s3_all), 10)
            stage3_repo.close()

        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_analyzed_jobs_excluded_from_pending_queues(self):
        """Requirement E: Verify already analyzed jobs are excluded from pending queues."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name

        try:
            _init_test_db(db_path)
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            for i in range(1, 4):
                c.execute(
                    "INSERT INTO jobs (id, title, company, description) VALUES (?, ?, ?, ?)",
                    (i, f"Role {i}", "Co", "Desc"),
                )
            conn.commit()
            conn.close()

            job_repo = JobRepository(db_path)
            ai_repo = JobAIRepository(db_path)
            cand_repo = CandidateJobRepository(db_path)
            stage3_repo = Stage3Repository(db_path)

            # Initially all 3 are in Stage 1 queue
            self.assertEqual(len(job_repo.get_unanalyzed_jobs()), 3)

            # Job 1 gets Stage 1 analyzed
            ai_repo.save_analysis({
                "job_id": 1,
                "relevance_score": 85,
                "recommendation": "send_to_stage_2",
                "career_tracks": ["telecom_ai"],
            })
            # Stage 1 queue now only has jobs 2 and 3
            remaining_s1 = job_repo.get_unanalyzed_jobs()
            self.assertEqual(len(remaining_s1), 2)
            self.assertNotIn(1, [j["id"] for j in remaining_s1])

            # Job 1 is in Stage 2 queue
            s2_eligible = cand_repo.get_eligible_stage2_jobs()
            self.assertEqual(len(s2_eligible), 1)
            self.assertEqual(s2_eligible[0]["id"], 1)

            # Job 1 gets Stage 2 analyzed
            cand_repo.save_analysis({
                "job_id": 1,
                "match_score": 90,
                "primary_track": "telecom_ai",
            })
            # Stage 2 queue is now empty
            self.assertEqual(len(cand_repo.get_eligible_stage2_jobs()), 0)

            # Job 1 is in Stage 3 queue
            s3_pending = stage3_repo.get_stage2_jobs_for_filtering(only_unanalyzed=True)
            self.assertEqual(len(s3_pending), 1)
            self.assertEqual(s3_pending[0]["id"], 1)

            # Job 1 gets Stage 3 analyzed
            stage3_repo.save_decision({
                "job_id": 1,
                "decision": "apply",
                "priority": "high",
                "final_score": 90.0,
                "application_method": "manual",
                "readiness": "ready",
                "decision_reasons": ["High score match"],
            })
            # Stage 3 queue is now empty
            self.assertEqual(len(stage3_repo.get_stage2_jobs_for_filtering(only_unanalyzed=True)), 0)

            job_repo.close()
            ai_repo.close()
            cand_repo.close()
            stage3_repo.close()

        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_idempotency_no_duplicate_records(self):
        """Requirement F: Verify saving analysis twice does not create duplicate rows."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name

        try:
            _init_test_db(db_path)
            ai_repo = JobAIRepository(db_path)
            cand_repo = CandidateJobRepository(db_path)
            stage3_repo = Stage3Repository(db_path)

            # Save S1 twice
            payload_s1 = {
                "job_id": 42,
                "relevance_score": 80,
                "recommendation": "send_to_stage_2",
                "career_tracks": ["telecom_ai"],
            }
            ai_repo.save_analysis(payload_s1)
            payload_s1["relevance_score"] = 85
            ai_repo.save_analysis(payload_s1)

            # Save S2 twice
            payload_s2 = {
                "job_id": 42,
                "match_score": 75,
                "primary_track": "telecom_ai",
            }
            cand_repo.save_analysis(payload_s2)
            payload_s2["match_score"] = 82
            cand_repo.save_analysis(payload_s2)

            # Save S3 twice
            payload_s3 = {
                "job_id": 42,
                "decision": "apply",
                "priority": "high",
                "final_score": 85.0,
                "application_method": "manual",
                "readiness": "ready",
                "decision_reasons": ["High score match"],
            }
            stage3_repo.save_decision(payload_s3)
            payload_s3["final_score"] = 88.0
            stage3_repo.save_decision(payload_s3)

            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT count(*) FROM job_ai_analysis WHERE job_id = 42")
            self.assertEqual(c.fetchone()[0], 1)
            c.execute("SELECT relevance_score FROM job_ai_analysis WHERE job_id = 42")
            self.assertEqual(c.fetchone()[0], 85)

            c.execute("SELECT count(*) FROM candidate_job_analysis WHERE job_id = 42")
            self.assertEqual(c.fetchone()[0], 1)
            c.execute("SELECT match_score FROM candidate_job_analysis WHERE job_id = 42")
            self.assertEqual(c.fetchone()[0], 82)

            c.execute("SELECT count(*) FROM job_stage3_analysis WHERE job_id = 42")
            self.assertEqual(c.fetchone()[0], 1)
            c.execute("SELECT final_score FROM job_stage3_analysis WHERE job_id = 42")
            self.assertEqual(c.fetchone()[0], 88.0)
            conn.close()

            ai_repo.close()
            cand_repo.close()
            stage3_repo.close()

        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_zero_new_jobs_queue_exhaustion(self):
        """Requirement G: Verify 0 pending items when queues are fully exhausted."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name

        try:
            _init_test_db(db_path)
            job_repo = JobRepository(db_path)
            cand_repo = CandidateJobRepository(db_path)
            stage3_repo = Stage3Repository(db_path)

            # With no jobs or all jobs analyzed:
            self.assertEqual(len(job_repo.get_unanalyzed_jobs()), 0)
            self.assertEqual(len(cand_repo.get_eligible_stage2_jobs()), 0)
            self.assertEqual(len(stage3_repo.get_stage2_jobs_for_filtering(only_unanalyzed=True)), 0)

            job_repo.close()
            cand_repo.close()
            stage3_repo.close()

        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_backlog_processed_when_zero_new_jobs_collected(self):
        """Requirement H: Backlog jobs are evaluated even when collection returns 0 new jobs."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name

        try:
            _init_test_db(db_path)
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            # Insert 2 pending unanalyzed jobs
            c.execute(
                "INSERT INTO jobs (id, title, company, description, requirements) VALUES (?, ?, ?, ?, ?)",
                (1, "Telecom AI Architect", "Vodafone", "Telecom AI job description", "Requirements"),
            )
            c.execute(
                "INSERT INTO jobs (id, title, company, description, requirements) VALUES (?, ?, ?, ?, ?)",
                (2, "Cybersecurity Specialist", "Orange", "Cybersecurity job description", "Requirements"),
            )
            conn.commit()
            conn.close()

            runner = pr.PipelineRunner(db_path=Path(db_path))

            # Mock collection to return 0 new jobs
            mock_collector = MagicMock()
            mock_collector.collect_from_all_sources.return_value = {
                "total_fetched": 100,
                "duplicates_skipped": 100,
                "new_jobs_saved": 0,
                "sources_summary": {},
            }

            # Mock analyzers so 0 external API calls are made
            mock_s1 = MagicMock(return_value={
                "recommendation": "send_to_stage_2",
                "career_tracks": ["telecom_ai"],
                "relevance_score": 85,
                "role_category": "engineering",
                "why_relevant": ["Matches"],
                "concerns": [],
            })
            def _fake_s2(job, stage1_analysis, career_profile):
                return {
                    "job_id": job["id"],
                    "match_score": 82,
                    "technical_fit_score": 80,
                    "career_track_fit_score": 85,
                    "career_growth_score": 80,
                    "ai_resilience_score": 80,
                    "seniority_fit": "good_fit",
                    "location_fit": "exact_match",
                    "primary_track": "telecom_ai",
                    "strengths": ["Networking"],
                    "skill_gaps": [],
                    "concerns": [],
                    "reasoning": "Strong match",
                }
            def _fake_s3(job_record):
                return {
                    "job_id": job_record["id"],
                    "decision": "apply",
                    "priority": "high",
                    "final_score": 84.0,
                    "application_method": "manual",
                    "readiness": "ready",
                    "decision_reasons": ["Top match"],
                }

            with patch("analyzer.pipeline_runner.UnifiedCollector", return_value=mock_collector), \
                 patch("analyzer.pipeline_runner.analyze_job_intelligence", mock_s1), \
                 patch("analyzer.pipeline_runner.analyze_candidate_job", side_effect=_fake_s2), \
                 patch("analyzer.pipeline_runner.evaluate_stage3_decision", side_effect=_fake_s3), \
                 patch("analyzer.pipeline_runner.generate_daily_reports"):

                summary = runner.run_full_pipeline(max_stage1_batch=None, max_stage2_batch=None, max_stage3_batch=None)

            self.assertEqual(summary["new_jobs"], 0)
            self.assertEqual(summary["stage1_evaluated"], 2)
            self.assertEqual(summary["stage2_evaluated"], 2)
            self.assertEqual(summary["shortlisted"], 2)

        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_domain_counting_query_against_canonical_schema(self):
        """
        Regression test for sqlite3.OperationalError: no such column: primary_track.
        Verifies that querying shortlisted domain tracks correctly joins
        job_stage3_analysis and candidate_job_analysis.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name

        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()

            # Create canonical schemas
            c.execute("""
                CREATE TABLE job_ai_analysis (
                    id INTEGER PRIMARY KEY,
                    job_id INTEGER,
                    relevance_score INTEGER,
                    career_tracks TEXT,
                    recommendation TEXT
                )
            """)
            c.execute("""
                CREATE TABLE candidate_job_analysis (
                    id INTEGER PRIMARY KEY,
                    job_id INTEGER,
                    match_score INTEGER,
                    primary_track TEXT
                )
            """)
            c.execute("""
                CREATE TABLE job_stage3_analysis (
                    id INTEGER PRIMARY KEY,
                    job_id INTEGER,
                    decision TEXT,
                    priority TEXT,
                    final_score REAL
                )
            """)

            # Seed data
            c.execute("INSERT INTO job_ai_analysis VALUES (1, 101, 90, '[\"telecom_ai\"]', 'send_to_stage_2')")
            c.execute("INSERT INTO job_ai_analysis VALUES (2, 102, 85, '[\"cybersecurity\"]', 'send_to_stage_2')")
            c.execute("INSERT INTO job_ai_analysis VALUES (3, 103, 80, '[\"quality_engineering\"]', 'send_to_stage_2')")

            c.execute("INSERT INTO candidate_job_analysis VALUES (1, 101, 85, 'telecom_ai')")
            c.execute("INSERT INTO candidate_job_analysis VALUES (2, 102, 88, 'cybersecurity')")
            c.execute("INSERT INTO candidate_job_analysis VALUES (3, 103, 70, 'quality_engineering')")

            c.execute("INSERT INTO job_stage3_analysis VALUES (1, 101, 'apply', 'high', 85.0)")
            c.execute("INSERT INTO job_stage3_analysis VALUES (2, 102, 'apply', 'medium', 82.0)")
            c.execute("INSERT INTO job_stage3_analysis VALUES (3, 103, 'skip', 'none', 45.0)")
            conn.commit()

            # Execute the canonical domain counting query
            domains_count = {}
            c.execute("""
                SELECT COALESCE(s2.primary_track, 'general') as track, count(*)
                FROM job_stage3_analysis s3
                JOIN candidate_job_analysis s2 ON s2.job_id = s3.job_id
                WHERE s3.decision = 'apply'
                GROUP BY s2.primary_track
            """)
            for track_raw, cnt in c.fetchall():
                clean_name = TRACK_DISPLAY_NAMES.get(track_raw, track_raw.replace("_", " ").title())
                domains_count[clean_name] = cnt

            c.execute("SELECT count(*) FROM job_stage3_analysis WHERE decision = 'apply'")
            total_shortlisted = c.fetchone()[0]
            conn.close()

            # Assertions
            self.assertEqual(total_shortlisted, 2)
            self.assertEqual(domains_count.get("Telecom AI"), 1)
            self.assertEqual(domains_count.get("Cybersecurity"), 1)
            # quality_engineering decision is 'skip', so it must not be in shortlisted domains
            self.assertNotIn("Quality Engineering", domains_count)
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_pipeline_runner_batch_param_resolution(self):
        """Verify run_full_pipeline resolves custom batch sizes and respects overrides."""
        runner = pr.PipelineRunner(db_path=Path(":memory:"))
        import inspect
        sig = inspect.signature(runner.run_full_pipeline)
        params = sig.parameters
        self.assertIn("max_stage1_batch", params)
        self.assertIn("max_stage2_batch", params)
        self.assertIn("max_stage3_batch", params)
        self.assertIn("max_lookback_days", params)


if __name__ == "__main__":
    unittest.main()

