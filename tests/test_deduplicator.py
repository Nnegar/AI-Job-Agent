import os
import tempfile
import unittest

from collector.deduplicator import (
    JobDeduplicator,
    generate_job_signature,
    normalize_company,
    normalize_title,
    normalize_url,
)


class TestJobDeduplicator(unittest.TestCase):
    def test_normalize_url(self):
        url1 = "https://boards.greenhouse.io/cloudflare/jobs/12345?gh_jid=12345&utm_source=linkedin#apply"
        url2 = "https://boards.greenhouse.io/cloudflare/jobs/12345/"
        self.assertEqual(normalize_url(url1), "https://boards.greenhouse.io/cloudflare/jobs/12345")
        self.assertEqual(normalize_url(url2), "https://boards.greenhouse.io/cloudflare/jobs/12345")

    def test_normalize_company(self):
        self.assertEqual(normalize_company("Cloudflare, Inc."), "cloudflare")
        self.assertEqual(normalize_company("Spotify AB"), "spotify")
        self.assertEqual(normalize_company("DeepL GmbH"), "deepl")
        self.assertEqual(normalize_company("Vodafone Group"), "vodafone")

    def test_normalize_title(self):
        title1 = "Network Security Engineer (m/w/d) - London"
        title2 = "Network Security Engineer [Hybrid]"
        self.assertEqual(normalize_title(title1), "network security engineer")
        self.assertEqual(normalize_title(title2), "network security engineer")

    def test_semantic_signature(self):
        sig1 = generate_job_signature("Spotify Technology S.A.", "Senior QA Engineer (f/m/d) - Europe")
        sig2 = generate_job_signature("Spotify", "Senior QA Engineer [Remote]")
        self.assertEqual(sig1, sig2)

    def test_in_memory_duplicate_detection(self):
        dedup = JobDeduplicator(db_path=None)

        job1 = {
            "source": "lever",
            "source_job_id": "abc-123",
            "company": "DeepL GmbH",
            "title": "Software Engineer, Cloud Infrastructure",
            "url": "https://jobs.lever.co/deepl/abc-123?utm_source=glassdoor",
        }

        # First time: not duplicate
        is_dup, reason = dedup.is_duplicate(job1)
        self.assertFalse(is_dup)

        # Register it
        dedup.register_job(job1)

        # Second job from LinkedIn with slightly different URL and title tags
        job2 = {
            "source": "linkedin",
            "source_job_id": "999888",
            "company": "DeepL",
            "title": "Software Engineer, Cloud Infrastructure (m/f/d)",
            "url": "https://www.linkedin.com/jobs/view/999888",
        }

        is_dup, reason = dedup.is_duplicate(job2)
        self.assertTrue(is_dup)
        self.assertEqual(reason, "duplicate_semantic_signature")


if __name__ == "__main__":
    unittest.main()
