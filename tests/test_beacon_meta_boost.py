import unittest
from datetime import datetime, timedelta, timezone

from modules.sales.beacon_meta_boost import execute_meta_boost, meta_boost_confirmation_phrase


class Provider:
    def __init__(self, result=None, timeout=False):
        self.calls = []
        self.result = result or {"success": True, "provider_reference": "mock-1"}
        self.timeout = timeout
    def create_fixed_lifetime_boost(self, payload):
        self.calls.append(payload)
        if self.timeout:
            raise TimeoutError()
        return self.result


class Store:
    def __init__(self):
        self.claims = set()
        self.results = []
    def claim(self, event):
        if event["idempotency_key"] in self.claims:
            return {"created": False, "success": True, "status": "already_claimed"}
        self.claims.add(event["idempotency_key"])
        return {"created": True}
    def result(self, event):
        self.results.append(event)
        return {"created": True}


class MetaBoostGateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 15, 10, tzinfo=timezone.utc)
        self.env = {"BEACON_META_BOOST_ENABLED": "true", "BEACON_META_BOOST_OWNER_POLICY_APPROVED": "true",
                    "META_AD_ACCOUNT_ID": "act_mock", "META_ADS_ACCESS_TOKEN": "test-only"}
        self.approval = {"approval_id": "A1", "status": "owner_approved", "canonical_post_id": "123_456",
                         "publication_evidence_id": "PUB1", "performance_event_id": "PERF1",
                         "fulfilment_revision": "FUL1", "currency": "ZAR", "total_cap_zar": "300.00",
                         "duration_days": 3, "budget_type": "lifetime_total", "owner_id": "owner",
                         "expires_at": (self.now + timedelta(hours=1)).isoformat()}
        self.publication = {"status": "published", "canonical_post_id": "123_456"}
        self.performance = {"performance_event_id": "PERF1", "canonical_post_id": "123_456",
                            "recommended_action": "light_boost_owner_review",
                            "created_at": (self.now - timedelta(hours=1)).isoformat()}
        self.fulfilment = {"revision": "FUL1", "status": "safe", "residual_capacity": 2,
                           "checked_at": (self.now - timedelta(minutes=2)).isoformat()}

    def run_gate(self, provider=None, store=None, payload=None, env=None):
        provider, store = provider or Provider(), store or Store()
        result = execute_meta_boost(payload or {"approval_id": "A1", "final_confirmation":
            meta_boost_confirmation_phrase("123_456", "300", 3)},
            publication_resolver=lambda _: self.publication, performance_resolver=lambda _: self.performance,
            fulfilment_resolver=lambda _: self.fulfilment, approval_resolver=lambda _: self.approval,
            claim_recorder=store.claim, result_recorder=store.result, provider=provider,
            environ=self.env if env is None else env, now=self.now)
        return result, provider, store

    def test_executes_mock_once_with_fixed_lifetime_cap(self):
        (body, status), provider, store = self.run_gate()
        self.assertEqual(status, 200); self.assertTrue(body["success"])
        self.assertEqual(provider.calls[0]["lifetime_budget_minor"], 30000)
        self.assertEqual(provider.calls[0]["currency"], "ZAR")
        self.assertEqual(store.results[0]["status"], "executed")

    def test_duplicate_retry_does_not_call_provider_twice(self):
        provider, store = Provider(), Store()
        self.run_gate(provider, store); (body, status), _, _ = self.run_gate(provider, store)
        self.assertEqual(status, 200); self.assertEqual(body["status"], "already_claimed")
        self.assertEqual(len(provider.calls), 1)

    def test_policy_credentials_and_confirmation_fail_before_provider(self):
        provider = Provider()
        (body, status), _, _ = self.run_gate(provider=provider, env={})
        self.assertEqual(status, 503); self.assertEqual(body["status"], "meta_boost_disabled")
        (body, status), _, _ = self.run_gate(provider=provider, payload={"approval_id": "A1", "final_confirmation": "yes"})
        self.assertEqual(status, 409); self.assertEqual(body["status"], "exact_final_confirmation_required")
        self.assertEqual(provider.calls, [])

    def test_stale_performance_and_unsafe_fulfilment_block(self):
        provider = Provider()
        self.performance["created_at"] = (self.now - timedelta(days=2)).isoformat()
        (body, _), _, _ = self.run_gate(provider=provider)
        self.assertEqual(body["status"], "boost_performance_evidence_stale")
        self.performance["created_at"] = self.now.isoformat(); self.fulfilment["residual_capacity"] = 0
        (body, _), _, _ = self.run_gate(provider=provider)
        self.assertEqual(body["status"], "fulfilment_not_safe"); self.assertEqual(provider.calls, [])

    def test_non_zar_recurring_or_expired_approval_blocks(self):
        provider = Provider()
        for field, value, expected in (("currency", "USD", "zar_total_cap_required"),
                                       ("budget_type", "daily", "fixed_lifetime_total_cap_only"),
                                       ("expires_at", (self.now - timedelta(seconds=1)).isoformat(), "owner_approval_expired")):
            original = self.approval[field]; self.approval[field] = value
            (body, _), _, _ = self.run_gate(provider=provider)
            self.assertEqual(body["status"], expected); self.approval[field] = original
        self.assertEqual(provider.calls, [])

    def test_timeout_is_uncertain_and_audited_without_retry_authority(self):
        (body, status), provider, store = self.run_gate(provider=Provider(timeout=True))
        self.assertEqual(status, 502); self.assertEqual(body["status"], "provider_acceptance_uncertain")
        self.assertTrue(store.results[0]["uncertain"]); self.assertEqual(len(provider.calls), 1)


if __name__ == "__main__":
    unittest.main()
