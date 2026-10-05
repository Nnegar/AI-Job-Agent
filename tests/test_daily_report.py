import os
import tempfile
import unittest
from pathlib import Path

from reports.daily_report_generator import generate_daily_reports


class TestDailyReport(unittest.TestCase):
    def setUp(self):
        self.temp_reports_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        if self.temp_reports_dir.exists():
            shutil.rmtree(self.temp_reports_dir)

    def test_report_generation(self):
        results = generate_daily_reports(reports_dir=self.temp_reports_dir)
        self.assertIn("md_path", results)
        self.assertIn("html_path", results)
        self.assertTrue(results["md_path"].exists())
        self.assertTrue(results["html_path"].exists())

        md_text = results["md_path"].read_text(encoding="utf-8")
        html_text = results["html_path"].read_text(encoding="utf-8")

        self.assertIn("Daily Intelligence Report", md_text)
        self.assertIn("Datadog", md_text)
        self.assertIn("Cloudflare", md_text)

        self.assertIn("Daily Intelligence Report", html_text)
        self.assertIn("btn-applied", html_text)
        self.assertIn("updateJobStatus", html_text)


if __name__ == "__main__":
    unittest.main()
