import json
import os
import unittest
from unittest.mock import patch
import analyzer.pipeline_runner
from http.server import HTTPServer
import threading
import urllib.request
import urllib.parse
from scripts.serve_dashboard import DashboardHandler, find_free_port


class TestServeDashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = find_free_port(9090)
        cls.server = HTTPServer(("127.0.0.1", cls.port), DashboardHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_get_applications_api(self):
        req = urllib.request.Request(f"{self.base_url}/api/applications")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("applications", data)

    def test_get_pipeline_api(self):
        req = urllib.request.Request(f"{self.base_url}/api/pipeline")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("summary", data)
            self.assertIn("jobs", data)
            self.assertIn("applied", data["summary"])
            self.assertIn("all_active", data["summary"])

    def test_get_database_jobs_paginated_api(self):
        req = urllib.request.Request(f"{self.base_url}/api/database/jobs?page=1&limit=10&search=engineering")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("items", data)
            self.assertIn("total", data)
            self.assertIn("filters", data)
            self.assertLessEqual(len(data["items"]), 10)

    def test_post_status_transition_api(self):
        payload = json.dumps({"status": "applied", "notes": "Automated test applied"}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/applications/1/status",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("status"), "applied")
            self.assertIn("summary", data)

    def test_post_notes_only_api(self):
        notes_content = json.dumps({"recruiter": "Alice Johnson", "target_comp": "€110,000"})
        payload = json.dumps({"notes": notes_content}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/applications/1/status",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("summary", data)

    @patch("analyzer.pipeline_runner.PipelineRunner")
    def test_post_pipeline_run_api(self, mock_runner_cls):
        mock_instance = mock_runner_cls.return_value
        mock_instance.run_full_pipeline.return_value = {
            "collected": 50,
            "duplicates": 10,
            "new_jobs": 40,
            "stage1_evaluated": 20,
            "stage2_evaluated": 15,
            "shortlisted": 8,
            "domains": {"Cybersecurity": 5, "Telecom AI": 3},
            "queue_before": 20,
            "queue_after": 25,
        }
        mock_instance.run_repo.get_last_run_display.return_value = "Today, 14:00"

        req = urllib.request.Request(
            f"{self.base_url}/api/pipeline/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("summary", data)
            self.assertEqual(data["summary"]["collected"], 50)
            self.assertEqual(data["summary"]["new_jobs"], 40)
            self.assertEqual(data["last_run"], "Today, 14:00")

    @patch("analyzer.pipeline_runner.PipelineRunner")
    def test_get_pipeline_run_stream_api(self, mock_runner_cls):
        def fake_run(event_callback=None, **kwargs):
            if event_callback:
                event_callback({"stage": "init", "percent": 5, "callout": "Connecting..."})
                event_callback({"stage": "complete", "percent": 100, "callout": "Done", "summary": {}})
            return {}

        mock_instance = mock_runner_cls.return_value
        mock_instance.run_full_pipeline.side_effect = fake_run

        req = urllib.request.Request(f"{self.base_url}/api/pipeline/run-stream")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/event-stream", resp.headers.get("Content-Type", ""))
            # Read first chunk
            chunk = resp.readline().decode("utf-8")
            self.assertTrue(chunk.startswith("data:"))
            first_event = json.loads(chunk[len("data:"):].strip())
            self.assertEqual(first_event.get("stage"), "init")

    def test_serve_html_dashboard(self):
        req = urllib.request.Request(f"{self.base_url}/")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read().decode("utf-8")
            self.assertIn("AI Job Agent", content)
            self.assertIn("tab-btn-applications", content)
            self.assertIn("tab-btn-pipeline", content)
            self.assertIn("tab-btn-database", content)
            self.assertIn("tab-btn-market", content)
            self.assertIn("pipe-table-body", content)
            self.assertIn("app-modal", content)
            self.assertIn("btn-run-pipeline", content)
            self.assertIn("header-last-run", content)
            self.assertIn("pipeline-run-modal", content)
            self.assertNotIn("Pipeline Healthy & Up to Date", content)


if __name__ == "__main__":
    unittest.main()
