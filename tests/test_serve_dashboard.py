import json
import os
import unittest
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


if __name__ == "__main__":
    unittest.main()
