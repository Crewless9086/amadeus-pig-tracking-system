import tempfile
import unittest
from pathlib import Path

from scripts import trust_log


class TrustLogTests(unittest.TestCase):
    def test_new_skill_starts_watch(self):
        self.assertEqual(trust_log.compute_tier(0, 0, 0), "watch")
        self.assertEqual(trust_log.compute_tier(1, 1, 0), "watch")

    def test_pass_increments_runs_and_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trust.tsv"

            entry = trust_log.log_result("sam_reply", "pass", path=path, tested_at="2026-07-11T00:00:00+00:00")

            self.assertEqual(entry.runs, 1)
            self.assertEqual(entry.passes, 1)
            self.assertEqual(entry.failures, 0)
            self.assertEqual(entry.tier, "watch")

    def test_fail_increments_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trust.tsv"

            entry = trust_log.log_result("sam_reply", "fail", reason="bad draft", path=path)

            self.assertEqual(entry.runs, 1)
            self.assertEqual(entry.failures, 1)
            self.assertEqual(entry.last_failure_reason, "bad draft")

    def test_twenty_runs_and_95_percent_becomes_auto(self):
        self.assertEqual(trust_log.compute_tier(20, 19, 1), "auto")

    def test_below_90_percent_becomes_watch(self):
        self.assertEqual(trust_log.compute_tier(20, 17, 3), "watch")

    def test_red_zone_violation_sets_watch(self):
        self.assertEqual(trust_log.compute_tier(40, 40, 0, red_zone_violation=True), "watch")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trust.tsv"
            for _ in range(20):
                trust_log.log_result("orders", "pass", path=path)

            entry = trust_log.log_result(
                "orders",
                "fail",
                reason="reservation attempted",
                red_zone_violation=True,
                path=path,
            )

            self.assertEqual(entry.tier, "watch")
            self.assertEqual(entry.last_result, "red_zone_violation")

    def test_render_output_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trust.tsv"
            trust_log.log_result("builder", "pass", path=path, tested_at="2026-07-11T00:00:00+00:00")

            summary = trust_log.render_summary(path)

            self.assertIn("skill | tier | runs | pass_rate", summary)
            self.assertIn("builder | watch | 1 | 100% | pass | none", summary)


if __name__ == "__main__":
    unittest.main()

