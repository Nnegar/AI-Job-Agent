import unittest
from analyzer.market.gap_classifier import classify_skill_gap, classify_gaps


class TestGapClassifier(unittest.TestCase):
    def test_missing_classification(self):
        res1 = classify_skill_gap("Limited direct experience with kernel-level troubleshooting technologies like eBPF")
        self.assertEqual(res1["tier"], "MISSING")
        self.assertIn("eBPF", res1["skill"])
        self.assertEqual(res1["badge_class"], "tier-missing")

        res2 = classify_skill_gap("No demonstrated experience in Go (Golang) backend microservices")
        self.assertEqual(res2["tier"], "MISSING")
        self.assertIn("Go", res2["skill"])

        res3 = classify_skill_gap("Lack of Kubernetes cluster management and Helm chart deployment")
        self.assertEqual(res3["tier"], "MISSING")
        self.assertIn("Kubernetes", res3["skill"])

    def test_partial_classification(self):
        res1 = classify_skill_gap("Limited direct experience with network automation tools like Ansible or Netmiko")
        self.assertEqual(res1["tier"], "PARTIAL")
        self.assertIn("Network Automation", res1["skill"])
        self.assertEqual(res1["badge_class"], "tier-partial")

        res2 = classify_skill_gap("No demonstrated evidence with SIEM and Splunk log correlation")
        self.assertEqual(res2["tier"], "PARTIAL")
        self.assertIn("SIEM", res2["skill"])

        res3 = classify_skill_gap("Lack of Playwright automated test frameworks")
        self.assertEqual(res3["tier"], "PARTIAL")
        self.assertIn("QA / Test Automation", res3["skill"])

    def test_strategic_classification(self):
        res1 = classify_skill_gap("Familiarity with Zero Trust architecture and micro-segmentation is a plus")
        self.assertEqual(res1["tier"], "STRATEGIC")
        self.assertIn("Zero Trust", res1["skill"])
        self.assertEqual(res1["badge_class"], "tier-strategic")

        res2 = classify_skill_gap("Experience with Prometheus and Grafana telemetry dashboards")
        self.assertEqual(res2["tier"], "STRATEGIC")
        self.assertIn("Prometheus", res2["skill"])

    def test_classify_gaps_list(self):
        raw_list = [
            "Limited direct experience with kernel-level troubleshooting technologies like eBPF",
            "Lack of network automation scripts using Python or Ansible",
            "Bonus: understanding of Zero Trust architecture",
        ]
        classified = classify_gaps(raw_list)
        self.assertEqual(len(classified), 3)
        tiers = [c["tier"] for c in classified]
        self.assertIn("MISSING", tiers)
        self.assertIn("PARTIAL", tiers)
        self.assertIn("STRATEGIC", tiers)


if __name__ == "__main__":
    unittest.main()
