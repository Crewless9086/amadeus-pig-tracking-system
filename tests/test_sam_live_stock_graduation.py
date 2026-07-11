import unittest

from modules.sales.sam_live_stock_graduation import notify_new_graduation_candidates


class SamLiveStockGraduationTests(unittest.TestCase):
    def setUp(self):
        self.environ = {
            "SAM_LIVE_STOCK_GRADUATION_NOTIFICATION_ENABLED": "1",
            "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "test-token",
            "SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID": "123",
        }
        self.scorecard = {
            "success": True,
            "scorecard": {
                "graduation": {
                    "classes": {
                        "collection_timing": {
                            "events": 25,
                            "consecutive_safe_accepted": 21,
                            "unchanged_rate": 0.84,
                            "narrow_auto_send_candidate": True,
                        }
                    }
                }
            },
        }

    def test_candidate_is_recorded_and_notified_without_changing_authority(self):
        recorded = []
        sent = []

        def recorder(event):
            recorded.append(event)
            return {"success": True, "created_count": 1}, 201

        result = notify_new_graduation_candidates(
            scorecard_loader=lambda: (self.scorecard, 200),
            event_recorder=recorder,
            telegram_sender=lambda *args: sent.append(args),
            environ=self.environ,
        )

        self.assertEqual(result["notification_count"], 1)
        self.assertEqual(len(sent), 1)
        self.assertEqual(recorded[0]["captured_facts"]["learning_kind"], "graduation_notification")
        self.assertFalse(result["auto_send_enabled"])
        self.assertFalse(result["sends_customer_message"])

    def test_existing_marker_prevents_duplicate_notification(self):
        sent = []
        result = notify_new_graduation_candidates(
            scorecard_loader=lambda: (self.scorecard, 200),
            event_recorder=lambda event: ({"success": True, "created_count": 0}, 200),
            telegram_sender=lambda *args: sent.append(args),
            environ=self.environ,
        )
        self.assertEqual(result["notification_count"], 0)
        self.assertEqual(sent, [])

    def test_disabled_notification_does_not_load_or_send(self):
        called = []
        result = notify_new_graduation_candidates(
            scorecard_loader=lambda: called.append("loaded"),
            event_recorder=lambda event: called.append("recorded"),
            telegram_sender=lambda *args: called.append("sent"),
            environ={"SAM_LIVE_STOCK_GRADUATION_NOTIFICATION_ENABLED": "0"},
        )
        self.assertEqual(result["status"], "graduation_notification_disabled")
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
