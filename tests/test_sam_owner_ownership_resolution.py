import unittest
from unittest.mock import Mock

from modules.sales.sam_owner_ownership_resolution import resolve_owner_work_ownership


def packet(conversation_id="1997", mode="HUMAN"):
    return {
        "work_item_id": f"SAM-OWNER-WORK-{conversation_id}",
        "work_event_id": f"SAM-OWNER-WORK-EVENT-{conversation_id}",
        "account_id": "147387",
        "conversation_id": conversation_id,
        "contact_id": f"contact-{conversation_id}",
        "inbox_id": "96568",
        "observation_hash": f"observation-{conversation_id}",
        "chronology_hash": f"chronology-{conversation_id}",
        "latest_inbound_message_id": f"inbound-{conversation_id}",
        "unanswered_count": 1,
        "review_event_id": f"SAM-LIVE-REVIEW-{conversation_id}",
        "window_evidence_hash": f"window-{conversation_id}",
        "target_mode": mode,
    }


def evidence(request, mode="UNAVAILABLE"):
    observation = {
        **request,
        "work_event_id": f"refreshed-{request['conversation_id']}",
        "ownership_mode": mode,
    }
    return {
        **request,
        "classification": "OWNERSHIP_DECISION_REQUIRED",
        "ownership_mode": mode,
        "lane": "GENERAL",
        "protected_markers": [],
        "specialist_markers": [],
        "observation": observation,
    }


class OwnerOwnershipResolutionTests(unittest.TestCase):
    def test_all_four_production_shapes_support_human_with_zero_send(self):
        for conversation_id in ("1997", "2029", "2031", "2039"):
            with self.subTest(conversation_id=conversation_id):
                request = packet(conversation_id)
                reader = Mock(side_effect=[
                    (evidence(request), 200),
                    (evidence(request, "HUMAN"), 200),
                ])
                recorder = Mock(side_effect=[
                    ({"created": True, "resolution_event_id": "claim"}, 201),
                    ({"created": True, "resolution_event_id": "result"}, 201),
                ])
                writer = Mock(return_value={"success": True})
                refresh = Mock(return_value=({"created": True}, 201))
                result, status = resolve_owner_work_ownership(
                    request, actor_id="owner-admin:server",
                    current_reader=reader, claim_recorder=recorder,
                    result_recorder=recorder, writer=writer,
                    refresh_recorder=refresh,
                )
                self.assertEqual(status, 200)
                self.assertTrue(result["ownership_changed"])
                self.assertFalse(result["sends_customer_message"])
                self.assertFalse(result["calls_telegram"])
                writer.assert_called_once_with(conversation_id, "HUMAN", unittest.mock.ANY)
                self.assertEqual(recorder.call_count, 2)

    def test_stale_chronology_fails_before_claim_or_write(self):
        request = packet()
        current = evidence(request)
        current["chronology_hash"] = "new"
        claim, writer = Mock(), Mock()
        result, status = resolve_owner_work_ownership(
            request, actor_id="owner-admin:server",
            current_reader=lambda *_: (current, 200),
            claim_recorder=claim, writer=writer,
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "ownership_chronology_hash_changed")
        claim.assert_not_called()
        writer.assert_not_called()

    def test_identity_mismatch_fails_closed(self):
        request = packet()
        current = evidence(request)
        current["contact_id"] = "different"
        result, status = resolve_owner_work_ownership(
            request, actor_id="owner-admin:server",
            current_reader=lambda *_: (current, 200),
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "ownership_contact_id_changed")

    def test_unsupported_mode_is_rejected(self):
        result, status = resolve_owner_work_ownership(
            packet(mode="OWNER"), actor_id="owner-admin:server"
        )
        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "ownership_mode_unsupported")

    def test_browser_cannot_supply_missing_server_owner(self):
        result, status = resolve_owner_work_ownership(packet(), actor_id="")
        self.assertEqual(status, 403)
        self.assertEqual(result["status"], "owner_identity_required")

    def test_replay_and_concurrent_claim_are_withheld_without_write(self):
        request = packet()
        writer = Mock()
        result, status = resolve_owner_work_ownership(
            request, actor_id="owner-admin:server",
            current_reader=lambda *_: (evidence(request), 200),
            claim_recorder=lambda _: ({"created": False}, 200),
            writer=writer,
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "ownership_resolution_replay_withheld")
        writer.assert_not_called()

    def test_chatwoot_failure_records_terminal_failure_and_never_retries(self):
        request = packet()
        records = []
        result, status = resolve_owner_work_ownership(
            request, actor_id="owner-admin:server",
            current_reader=lambda *_: (evidence(request), 200),
            claim_recorder=lambda event: (records.append(event) or {"created": True}, 201),
            result_recorder=lambda event: (records.append(event) or {"created": True}, 201),
            writer=Mock(side_effect=TimeoutError()),
        )
        self.assertEqual(status, 502)
        self.assertFalse(result["retry_automatically"])
        self.assertFalse(result["ownership_changed"])
        self.assertEqual([row["outcome"] for row in records], ["claimed", "write_failed"])

    def test_auto_general_requires_current_enabled_policy(self):
        request = packet(mode="AUTO_GENERAL")
        writer = Mock()
        result, status = resolve_owner_work_ownership(
            request, actor_id="owner-admin:server",
            current_reader=lambda *_: (evidence(request), 200),
            writer=writer,
            environ={},
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "ownership_policy_eligibility_unavailable")
        writer.assert_not_called()

    def test_auto_specialist_requires_specialist_current_evidence(self):
        request = packet(mode="AUTO_SPECIALIST")
        current = evidence(request)
        result, status = resolve_owner_work_ownership(
            request, actor_id="owner-admin:server",
            current_reader=lambda *_: (current, 200),
            environ={"SAM_AUTO_SPECIALIST_OWNERSHIP_ENABLED": "true"},
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "ownership_specialist_lane_ineligible")

    def test_protected_evidence_forbids_automatic_modes(self):
        request = packet(mode="AUTO_GENERAL")
        current = evidence(request)
        current["protected_markers"] = ["payment"]
        result, status = resolve_owner_work_ownership(
            request, actor_id="owner-admin:server",
            current_reader=lambda *_: (current, 200),
            environ={"SAM_AUTO_GENERAL_OWNERSHIP_ENABLED": "true"},
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "ownership_protected_policy_forbids_automatic_mode")

