import unittest

from modules.sales import sam_live_stock_runtime as runtime


class SamLiveStockCanaryCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            runtime.AUTOREPLY_ENABLED_ENV: "1",
            runtime.AUTOREPLY_CANARY_ENABLED_ENV: "1",
            runtime.AUTOREPLY_CANARY_CONVERSATION_ENV: "1826",
            runtime.AUTOREPLY_CANARY_CONTACT_ENV: "99",
            runtime.AUTOREPLY_CANARY_INBOX_ENV: "77",
            runtime.CHATWOOT_TOKEN_ENV: "SECRET-TOKEN",
        }
        self.inbound = {"conversation_id": "1826", "contact_id": "99", "inbox_id": "77", "content": "Do you have growers?"}
        self.decision = {
            "sales_lane": "live_stock_sales",
            "should_reply": True,
            "suggested_reply_text": "Yes. What quantity do you need?",
            "reply_source": "llm_live_stock_reply_draft",
            "llm_draft": {"used": True, "confidence": 0.99},
            "canonical_composition_authorized": True,
            "facts": {"sales_lane": "live_stock_sales", "lane_confidence": 0.99, "message_intent": "stock_question", "media_review_required": False},
        }
        self.review = {"safe_to_send": True, "escalation_required": False}

    def deliver(self, *, inbound=None, decision=None, review=None, source=None, claim=None, sender=None, evidence=None):
        return runtime.deliver_sam_live_stock_routine_reply_if_enabled(
            inbound or dict(self.inbound), decision or dict(self.decision), review or dict(self.review),
            self.source if source is None else source,
            delivery_claim=claim or (lambda *_: {"success": True, "created": True, "review_event_id": "CLAIM-1"}),
            chatwoot_sender=sender or (lambda *_: {"status_code": 200, "body": {"id": 1, "status": "sent"}}),
            delivery_evidence_recorder=evidence or (lambda _claim, outcome: {"success": True, "created": True, "delivery_state": outcome["delivery_state"]}),
        )

    def test_claim_precedes_send_and_sent_is_accepted_unverified(self):
        calls = []
        result = self.deliver(
            claim=lambda *_: calls.append("claim") or {"success": True, "created": True, "review_event_id": "CLAIM-1"},
            sender=lambda *_: calls.append("send") or {"status_code": 200, "body": {"id": 1, "status": "sent"}},
            evidence=lambda _claim, outcome: calls.append(outcome["delivery_state"]) or {"success": True},
        )
        self.assertEqual(calls, ["claim", "send", "chatwoot_accepted_unverified"])
        self.assertFalse(result["sent"])
        self.assertTrue(result["chatwoot_accepted"])
        self.assertTrue(result["automatic_retry_prohibited"])

    def test_ambiguous_exception_records_unknown_and_replay_never_sends(self):
        state = {"claimed": False, "sends": 0, "outcomes": []}
        def claim(*_):
            created = not state["claimed"]
            state["claimed"] = True
            return {"success": True, "created": created, "review_event_id": "CLAIM-1"}
        def sender(*_):
            state["sends"] += 1
            raise TimeoutError("network timeout")
        def evidence(_claim, outcome):
            state["outcomes"].append(outcome)
            return {"success": True, "created": True}
        first = self.deliver(claim=claim, sender=sender, evidence=evidence)
        replay = self.deliver(claim=claim, sender=sender, evidence=evidence)
        self.assertEqual(first["delivery_evidence"]["success"], True)
        self.assertEqual(state["outcomes"][0]["delivery_state"], "provider_outcome_ambiguous")
        self.assertEqual(replay["status"], "routine_reply_duplicate_withheld")
        self.assertEqual(state["sends"], 1)

    def test_client_exception_is_append_only_ambiguous_evidence(self):
        outcomes = []
        result = self.deliver(
            sender=lambda *_: (_ for _ in ()).throw(RuntimeError("chatwoot_http_422")),
            evidence=lambda _claim, outcome: outcomes.append(outcome) or {"success": True},
        )
        self.assertFalse(result["sent"])
        self.assertEqual(outcomes[0]["delivery_state"], "provider_outcome_ambiguous")

    def test_all_fail_closed_canary_boundaries_send_nothing(self):
        cases = []
        cases.append(({**self.source, runtime.AUTOREPLY_ENABLED_ENV: "0"}, self.inbound, self.decision, self.review))
        cases.append(({**self.source, runtime.AUTOREPLY_CANARY_ENABLED_ENV: "0"}, self.inbound, self.decision, self.review))
        cases.append(({k: v for k, v in self.source.items() if k != runtime.AUTOREPLY_CANARY_CONTACT_ENV}, self.inbound, self.decision, self.review))
        cases.append((self.source, {**self.inbound, "inbox_id": "other"}, self.decision, self.review))
        cases.append((self.source, self.inbound, {**self.decision, "llm_draft": {"used": True, "confidence": 0.95}}, self.review))
        cases.append((self.source, self.inbound, {**self.decision, "facts": {**self.decision["facts"], "lane_confidence": 0.89}}, self.review))
        cases.append((self.source, self.inbound, {**self.decision, "facts": {**self.decision["facts"], "message_intent": "unclear"}}, self.review))
        cases.append((self.source, {**self.inbound, "content": "You are a scam"}, self.decision, self.review))
        cases.append((self.source, self.inbound, {**self.decision, "sales_lane": "meat_sales", "facts": {**self.decision["facts"], "sales_lane": "meat_sales"}}, self.review))
        cases.append((self.source, self.inbound, {**self.decision, "facts": {**self.decision["facts"], "media_review_required": True}}, self.review))
        cases.append((self.source, self.inbound, self.decision, {"safe_to_send": False, "escalation_required": True}))
        cases.append((self.source, self.inbound, {**self.decision, "reply_source": "deterministic_read_only_guard", "llm_draft": {"used": False}}, self.review))
        cases.append((self.source, self.inbound, {**self.decision, "reserves_stock": True}, self.review))
        for source, inbound, decision, review in cases:
            sends = []
            result = self.deliver(source=source, inbound=inbound, decision=decision, review=review, sender=lambda *_: sends.append(True))
            self.assertFalse(result["sent"], result)
            self.assertEqual(sends, [], result)


if __name__ == "__main__":
    unittest.main()
