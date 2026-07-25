import unittest

from modules.sales.sam_meat_readiness_probe import run_sam_meat_readiness_probe


class SamMeatReadinessProbeTests(unittest.TestCase):
    def test_disabled_probe_fails_before_reader(self):
        called = []
        result, status = run_sam_meat_readiness_probe(
            environ={},
            snapshot_loader=lambda *_args, **_kwargs: called.append(True),
        )
        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "sam_meat_readiness_probe_disabled")
        self.assertEqual(called, [])
        self.assertFalse(result["writes_performed"])

    def test_probe_returns_only_sanitized_bounded_metrics(self):
        times = iter((10.0, 10.012))
        result, status = run_sam_meat_readiness_probe(
            environ={
                "SAM_MEAT_READINESS_PROBE_ENABLED": "1",
                "SAM_MEAT_READINESS_PROBE_LEAD_ID": "PRIVATE-LEAD",
            },
            snapshot_loader=lambda *_args, **_kwargs: {
                "pricing": [],
                "availability": {"assembly": {}},
                "fulfilment": {"fulfillment": {}},
                "butcher": {"status": "ready"},
                "query_budget": {"total": 9, "connections": 1},
            },
            deadline_factory=lambda: object(),
            clock=lambda: next(times),
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["elapsed_ms"], 12)
        self.assertEqual(result["connection_count"], 1)
        self.assertEqual(result["statement_count"], 9)
        self.assertLessEqual(result["statement_count"], 10)
        self.assertTrue(result["deadline_enforcement_active"])
        self.assertFalse(result["writes_performed"])
        serialized = str(result)
        self.assertNotIn("PRIVATE-LEAD", serialized)
        for forbidden in ("price_amount", "pig_id", "reservation_id", "provider"):
            self.assertNotIn(forbidden, serialized)

    def test_timeout_and_incomplete_snapshot_fail_closed(self):
        for loader in (
            lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()),
            lambda *_args, **_kwargs: {
                "pricing": [],
                "availability": {"status": "Unavailable"},
                "fulfilment": {},
                "butcher": {},
                "query_budget": {"total": 10, "connections": 1},
            },
        ):
            times = iter((20.0, 24.5))
            result, status = run_sam_meat_readiness_probe(
                environ={
                    "SAM_MEAT_READINESS_PROBE_ENABLED": "1",
                    "SAM_MEAT_READINESS_PROBE_LEAD_ID": "PRIVATE",
                },
                snapshot_loader=loader,
                deadline_factory=lambda: object(),
                clock=lambda: next(times),
            )
            self.assertEqual(status, 503)
            self.assertFalse(result["success"])
            self.assertEqual(result["status"], "Unavailable")
            self.assertFalse(result["writes_performed"])


if __name__ == "__main__":
    unittest.main()
