import datetime
import os
import tempfile
import unittest

from database.sync_repository import SyncRepository


class TestSyncRepository(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.repo = SyncRepository(db_path=self.temp_db.name)

    def tearDown(self):
        self.repo.close()
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_first_run_returns_7_days_ago(self):
        now = datetime.datetime(2026, 9, 15, 12, 0, tzinfo=datetime.timezone.utc)
        since = self.repo.get_since_date("greenhouse", "cloudflare", max_lookback_days=7, current_time=now)
        expected = datetime.datetime(2026, 9, 8, 12, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(since, expected)

    def test_gap_greater_than_one_week_is_capped_at_7_days(self):
        # Last pull was Sep 4, now is Sep 15 (gap = 11 days)
        last_pull = datetime.datetime(2026, 9, 4, 10, 0, tzinfo=datetime.timezone.utc)
        self.repo.update_sync_state("greenhouse", "cloudflare", jobs_collected=50, sync_time=last_pull)

        now = datetime.datetime(2026, 9, 15, 10, 0, tzinfo=datetime.timezone.utc)
        since = self.repo.get_since_date("greenhouse", "cloudflare", max_lookback_days=7, current_time=now)
        # Should be capped at 7 days ago (Sep 8), not Sep 4
        expected = datetime.datetime(2026, 9, 8, 10, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(since, expected)

    def test_gap_less_than_one_week_uses_last_pull_timestamp(self):
        # Last pull was Sep 13, now is Sep 15 (gap = 2 days)
        last_pull = datetime.datetime(2026, 9, 13, 10, 0, tzinfo=datetime.timezone.utc)
        self.repo.update_sync_state("lever", "spotify", jobs_collected=20, sync_time=last_pull)

        now = datetime.datetime(2026, 9, 15, 10, 0, tzinfo=datetime.timezone.utc)
        since = self.repo.get_since_date("lever", "spotify", max_lookback_days=7, current_time=now)
        self.assertEqual(since, last_pull)


if __name__ == "__main__":
    unittest.main()
