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
        self.assertIn('md_path', results)
        self.assertIn('html_path', results)
        self.assertTrue(results['md_path'].exists())
        self.assertTrue(results['html_path'].exists())

        md_text = results['md_path'].read_text(encoding='utf-8')
        html_text = results['html_path'].read_text(encoding='utf-8')

        self.assertIn('Daily Intelligence Report', md_text)
        self.assertIn('Datadog', md_text)
        self.assertIn('Cloudflare', md_text)

        # Tab navigation buttons
        self.assertIn('tab-btn-applications', html_text)
        self.assertIn('tab-btn-pipeline', html_text)
        self.assertIn('tab-btn-database', html_text)
        self.assertIn('tab-btn-market', html_text)

        # Pipeline table and interactive elements
        self.assertIn('tab-pipeline', html_text)
        self.assertIn('pipe-table-body', html_text)
        self.assertIn('pipeline-stage-boxes', html_text)
        self.assertIn('app-modal', html_text)
        self.assertIn('saveModalNotes', html_text)
        self.assertIn('updateJobStatus', html_text)

        # Header runner button and pipeline run screen
        self.assertIn('btn-run-pipeline', html_text)
        self.assertIn('pipeline-run-modal', html_text)
        self.assertIn('header-last-run', html_text)
        self.assertIn('openPipelineRunModal', html_text)
        self.assertIn('pipe-run-complete-view', html_text)
        self.assertNotIn('Pipeline Healthy & Up to Date', html_text)


if __name__ == '__main__':
    unittest.main()
