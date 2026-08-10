import copy
import hashlib
import json
import unittest
from unittest import mock
import sys
from pathlib import Path

from modules.sales.sam_review_obligation_resolution import (
    CONTRACT_VERSION,
    build_resolution_manifest,
    canonical_sha256,
    resolve_review_obligation,
    resolution_identity,
    record_resolution_event,
    successor_work_item_identity,
)


def review(index=1):
    return {
        "review_event_id": f"SAM-REVIEW-{index:03d}",
        "chatwoot_conversation_id": f"CONV-{index:03d}",
        "chatwoot_message_id": f"IN-{index:03d}",
        "decision_json": {
            "canonical_inventory_snapshot": {
                "selected_pig_ids": ["PIG-2026-1AC2"],
            }
        },
    }


def represented(**overrides):
    packet = {
        "represented_pig_id": "PIG-2026-1AC2",
        "status": "superseded",
        "canonical_same_animal_pig_id": None,
        "alias_evidence_id": None,
        "same_animal_mapping_prohibited": True,
        "governed_disposition_operation_id": "ZIGAY-SUPERSESSION-1",
    }
    packet.update(overrides)
    return packet


def evidence(index=1, **overrides):
    packet = {
        "identity": {
            "review_event_id": f"SAM-REVIEW-{index:03d}",
            "account_id": "147387", "inbox_id": "96568",
            "contact_id": f"CONTACT-{index:03d}",
            "conversation_id": f"CONV-{index:03d}",
            "bound_inbound_message_id": f"IN-{index:03d}",
            "latest_inbound_message_id": f"IN-{index:03d}",
            "latest_public_message_type": "incoming",
        },
        "public_chronology": [{"message_id": f"IN-{index:03d}", "message_type": "incoming",
                               "provider_observed_at": "2026-07-31T12:00:00+00:00"}],
        "chronology_cutoff_at": "2026-07-31T12:00:00+00:00",
        "chronology_sha256": "",
        "delivery": {
            "status": "not_attempted", "evidence_id": "DELIVERY-NONE",
            "evidence_sha256": "b" * 64,
        },
        "content_obligation": {
            "supported_obligation_answered": False,
            "relied_on_superseded_identity": False,
            "evidence_id": "OBLIGATION-1", "evidence_sha256": "c" * 64,
        },
        "protected_decision": {"active": False, "evidence_id": "PROTECTED-NONE", "evidence_sha256": "d" * 64},
        "quarantine": {"active": False, "evidence_id": "QUARANTINE-NONE", "evidence_sha256": "e" * 64},
        "whatsapp_window": {"state": "open", "evidence_id": "WINDOW-OPEN", "evidence_sha256": "f" * 64},
        "source_generation": "fixture-362-v1",
    }
    packet.update(overrides)
    for position, row in enumerate(packet["public_chronology"]):
        row.setdefault(
            "provider_observed_at",
            f"2026-07-31T12:{position:02d}:00+00:00",
        )
    if packet["public_chronology"] and "chronology_cutoff_at" not in overrides:
        packet["chronology_cutoff_at"] = packet["public_chronology"][-1][
            "provider_observed_at"
        ]
    packet["delivery"].setdefault("conversation_id", f"CONV-{index:03d}")
    packet["delivery"].setdefault("inbound_message_id", f"IN-{index:03d}")
    if packet.get("later_public_outgoing"):
        packet["delivery"].setdefault(
            "outgoing_message_id", packet["later_public_outgoing"].get("message_id")
        )
    for key in (
        "delivery", "content_obligation", "protected_decision",
        "quarantine", "whatsapp_window",
    ):
        source = packet[key]
        source["evidence_payload"] = {
            name: value for name, value in source.items()
            if name not in {"evidence_id", "evidence_sha256", "evidence_payload"}
        }
        source["evidence_sha256"] = canonical_sha256(source["evidence_payload"])
    if "chronology_sha256" not in overrides:
        packet["chronology_sha256"] = canonical_sha256(packet["public_chronology"])
    if packet.get("successor_work_item"):
        source = packet["successor_work_item"]
        if source.get("chronology_sha256") == "BOUND_TO_CURRENT_CHRONOLOGY":
            source["chronology_sha256"] = packet["chronology_sha256"]
        source.setdefault("evidence_id", "SUCCESSOR-WORK-EVIDENCE")
        source["evidence_payload"] = {
            name: value for name, value in source.items()
            if name not in {"evidence_id", "evidence_sha256", "evidence_payload"}
        }
        source["evidence_sha256"] = canonical_sha256(source["evidence_payload"])
    return packet


class SamReviewObligationResolutionTests(unittest.TestCase):
    def test_production_rpc_search_path_includes_protected_pgcrypto_schema(self):
        sql = (Path(__file__).resolve().parents[1] / "supabase" / "migrations" /
               "202608100004_fix_sam_resolution_rpc_pgcrypto_path.sql").read_text(
                   encoding="utf-8"
               ).lower()
        self.assertIn("alter function public.record_sam_review_obligation_resolution(jsonb)", sql)
        self.assertIn("set search_path = pg_catalog, extensions, public", sql)
        self.assertNotIn("grant", sql)

    def test_recorder_enters_service_role_before_governed_rpc(self):
        packet = resolve_review_obligation(
            review=review(), evidence=evidence(), represented_identity=represented()
        )
        calls = []

        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params=None):
                calls.append((sql, params))
                return self
            def fetchone(self): return [True]

        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def cursor(self): return Cursor()

        fake_psycopg = mock.Mock()
        fake_psycopg.connect.return_value = Connection()
        with mock.patch.dict(sys.modules, {"psycopg": fake_psycopg}):
            result, status = record_resolution_event(packet, database_url="postgres://fixture")
        self.assertEqual(status, 201)
        self.assertTrue(result["created"])
        self.assertEqual(calls[0], ("set local role service_role", None))
        self.assertIn("record_sam_review_obligation_resolution", calls[1][0])

    def test_later_review_supersedes_history_without_manufacturing_successor_work(self):
        proof = evidence(content_obligation={
            "supported_obligation_answered": False,
            "relied_on_superseded_identity": False,
            "review_is_latest_for_conversation": False,
        })
        result = resolve_review_obligation(
            review=review(), evidence=proof, represented_identity=represented()
        )
        self.assertEqual(result["customer_obligation_status"], "superseded_by_later_review")
        self.assertEqual(result["resolution_action"], "historical")
        self.assertIsNone(result["successor_work_item_id"])

    def test_superseded_review_does_not_hide_protected_or_quarantined_state(self):
        base = {
            "supported_obligation_answered": False,
            "relied_on_superseded_identity": False,
            "review_is_latest_for_conversation": False,
        }
        protected = resolve_review_obligation(
            review=review(), evidence=evidence(
                content_obligation=base,
                protected_decision={"active": True},
            ), represented_identity=represented(),
        )
        self.assertEqual(protected["resolution_action"], "protected")
        quarantined = resolve_review_obligation(
            review=review(), evidence=evidence(
                content_obligation=base,
                quarantine={"active": True},
            ), represented_identity=represented(),
        )
        self.assertEqual(quarantined["resolution_action"], "quarantined")

    def test_active_unanswered_is_replanned_without_alias(self):
        result = resolve_review_obligation(
            review=review(), evidence=evidence(), represented_identity=represented()
        )
        self.assertEqual(result["customer_obligation_status"], "active_replan_required")
        self.assertEqual(result["resolution_action"], "active")
        self.assertIsNone(result["canonical_same_animal_pig_id"])
        self.assertEqual(result["resolution_event_id"], resolution_identity(result))

    def test_transport_delivery_never_proves_substantive_completion(self):
        proof = evidence(delivery={
            "status": "provider_delivered", "evidence_id": "DELIVERED-1",
            "evidence_sha256": "d" * 64,
            "outgoing_message_id": "OUT-DELIVERY-EVIDENCE",
        })
        result = resolve_review_obligation(
            review=review(), evidence=proof, represented_identity=represented()
        )
        self.assertEqual(
            result["customer_obligation_status"],
            "delivered_attempt_requires_content_resolution",
        )
        self.assertEqual(result["resolution_action"], "indeterminate")

    def test_exact_attributed_delivery_without_content_review_remains_unresolved(self):
        proof = evidence(
            delivery={
                "status": "provider_delivered",
                "outgoing_message_id": "OUT-BOUND",
            },
            content_obligation={
                "supported_obligation_answered": False,
                "relied_on_superseded_identity": False,
            },
            later_public_outgoing={
                "message_id": "OUT-BOUND",
                "bound_reply_to_inbound_id": "IN-001",
                "content_sha256": "9" * 64,
                "response_class_evidence_id": "CONTENT-REVIEW-REQUIRED",
            },
            public_chronology=[
                {"message_id": "IN-001", "message_type": "incoming"},
                {"message_id": "OUT-BOUND", "message_type": "outgoing"},
            ],
        )
        result = resolve_review_obligation(
            review=review(), evidence=proof, represented_identity=represented()
        )
        self.assertEqual(
            result["customer_obligation_status"],
            "delivered_attempt_requires_content_resolution",
        )
        self.assertEqual(result["resolution_action"], "indeterminate")

    def test_attributable_content_with_nonterminal_or_failed_transport_never_completes(self):
        for status in ("not_attempted", "attempt_claimed", "provider_failed"):
            proof = evidence(
                delivery={"status": status, "evidence_id": f"D-{status}"},
                later_public_outgoing={
                    "message_id": "OUT-NONTERMINAL",
                    "bound_reply_to_inbound_id": "IN-001",
                    "content_sha256": "1" * 64,
                    "response_class_evidence_id": "CLASS-NONTERMINAL",
                },
                content_obligation={
                    "supported_obligation_answered": True,
                    "relied_on_superseded_identity": False,
                    "evidence_id": "O-NONTERMINAL",
                },
                public_chronology=[
                    {"message_id": "IN-001", "message_type": "incoming"},
                    {"message_id": "OUT-NONTERMINAL", "message_type": "outgoing"},
                ],
            )
            result = resolve_review_obligation(review=review(), evidence=proof, represented_identity=represented())
            self.assertEqual(result["resolution_action"], "indeterminate")
            self.assertNotEqual(result["customer_obligation_status"], "completed_by_attributable_supported_reply")

    def test_protected_and_quarantined_collision_keeps_owner_work_visible(self):
        proof = evidence(
            delivery={"status": "provider_outcome_ambiguous", "evidence_id": "D-AMB"},
            protected_decision={"active": True, "evidence_id": "P-ACTIVE"},
            quarantine={"active": True, "evidence_id": "Q-ACTIVE"},
        )
        result = resolve_review_obligation(review=review(), evidence=proof, represented_identity=represented())
        self.assertEqual(result["resolution_action"], "protected")
        self.assertEqual(result["customer_obligation_status"], "protected_owner_action_required")
        self.assertEqual(result["communication_delivery_status"], "provider_outcome_ambiguous")

    def test_one_bit_chronology_and_evidence_tamper_fail_closed(self):
        proof = evidence()
        proof["public_chronology"][0]["message_type"] = "outgoing"
        result = resolve_review_obligation(review=review(), evidence=proof, represented_identity=represented())
        self.assertIn("canonical_public_chronology_digest_mismatch", result["resolution_errors"])
        proof = evidence()
        proof["delivery"]["evidence_payload"]["status"] = "changed"
        result = resolve_review_obligation(review=review(), evidence=proof, represented_identity=represented())
        self.assertIn("delivery_evidence_sha256_mismatch", result["resolution_errors"])
        proof = evidence(
            delivery={"status": "provider_delivered", "evidence_id": "D-COMPLETE"},
            later_public_outgoing={"message_id": "OUT-COMPLETE", "bound_reply_to_inbound_id": "IN-001", "content_sha256": "4" * 64, "response_class_evidence_id": "CLASS-COMPLETE"},
            content_obligation={"supported_obligation_answered": False, "relied_on_superseded_identity": False, "evidence_id": "O-COMPLETE"},
            public_chronology=[{"message_id": "IN-001", "message_type": "incoming"}, {"message_id": "OUT-COMPLETE", "message_type": "outgoing"}],
        )
        proof["content_obligation"]["supported_obligation_answered"] = True
        result = resolve_review_obligation(review=review(), evidence=proof, represented_identity=represented())
        self.assertIn("obligation_evidence_payload_semantic_mismatch", result["resolution_errors"])
        self.assertEqual(result["resolution_action"], "indeterminate")
        reviewed = review()
        reviewed["decision_json_text"] = json.dumps(reviewed["decision_json"], sort_keys=True)
        reviewed["decision_json_sha256"] = hashlib.sha256(
            reviewed["decision_json_text"].encode()
        ).hexdigest()
        reviewed["decision_json"]["tampered"] = True
        result = resolve_review_obligation(review=reviewed, evidence=evidence(), represented_identity=represented())
        self.assertIn("review_decision_text_semantic_mismatch", result["resolution_errors"])

    def test_unattributable_or_unrelated_outgoing_never_completes(self):
        for bound, chronology in (
            ("OTHER-INBOUND", [{"message_id": "IN-001", "message_type": "incoming"}, {"message_id": "OUT-X", "message_type": "outgoing"}]),
            ("IN-001", [{"message_id": "IN-001", "message_type": "incoming"}]),
        ):
            proof = evidence(
                delivery={"status": "provider_delivered", "evidence_id": "DX", "evidence_sha256": "1" * 64},
                later_public_outgoing={"message_id": "OUT-X", "bound_reply_to_inbound_id": bound, "content_sha256": "2" * 64, "response_class_evidence_id": "CLASS-X"},
                content_obligation={"supported_obligation_answered": True, "relied_on_superseded_identity": False, "evidence_id": "OX", "evidence_sha256": "3" * 64},
                public_chronology=chronology,
            )
            result = resolve_review_obligation(review=review(), evidence=proof, represented_identity=represented())
            self.assertNotEqual(result["resolution_action"], "completed")

    def test_attributable_supported_reply_can_complete_without_superseded_stock(self):
        proof = evidence(
            delivery={"status": "provider_delivered", "evidence_id": "D1", "evidence_sha256": "d" * 64},
            later_public_outgoing={
                "message_id": "OUT-1", "bound_reply_to_inbound_id": "IN-001",
                "content_sha256": "e" * 64, "response_class_evidence_id": "CLASS-1",
            },
            content_obligation={
                "supported_obligation_answered": True,
                "relied_on_superseded_identity": False,
                "evidence_id": "O1", "evidence_sha256": "f" * 64,
            },
            public_chronology=[
                {"message_id": "IN-001", "message_type": "incoming"},
                {"message_id": "OUT-1", "message_type": "outgoing"},
            ],
        )
        result = resolve_review_obligation(
            review=review(), evidence=proof, represented_identity=represented()
        )
        self.assertEqual(
            result["customer_obligation_status"],
            "completed_by_attributable_supported_reply",
        )
        self.assertEqual(result["resolution_action"], "completed")

    def test_delivered_reply_using_superseded_stock_creates_corrective_replan(self):
        proof = evidence(
            delivery={"status": "provider_read", "evidence_id": "D2", "evidence_sha256": "d" * 64},
            later_public_outgoing={
                "message_id": "OUT-2", "bound_reply_to_inbound_id": "IN-001",
                "content_sha256": "e" * 64, "response_class_evidence_id": "CLASS-2",
            },
            content_obligation={
                "supported_obligation_answered": True,
                "relied_on_superseded_identity": True,
                "evidence_id": "O2", "evidence_sha256": "f" * 64,
            },
            public_chronology=[
                {"message_id": "IN-001", "message_type": "incoming"},
                {"message_id": "OUT-2", "message_type": "outgoing"},
            ],
        )
        result = resolve_review_obligation(
            review=review(), evidence=proof, represented_identity=represented()
        )
        self.assertEqual(
            result["customer_obligation_status"],
            "corrective_replan_required_after_reply",
        )
        self.assertEqual(result["resolution_action"], "corrective_replanning")

    def test_quarantine_protected_closed_and_successor_states_remain_visible(self):
        cases = (
            (
                evidence(quarantine={"active": True, "evidence_id": "Q1", "evidence_sha256": "1" * 64}),
                "quarantined_no_retry", "quarantined",
            ),
            (
                evidence(protected_decision={"active": True, "evidence_id": "P1", "evidence_sha256": "2" * 64}),
                "protected_owner_action_required", "protected",
            ),
            (
                evidence(whatsapp_window={"state": "closed", "evidence_id": "W1", "evidence_sha256": "3" * 64}),
                "closed_window_reengagement_required", "active",
            ),
            (
                evidence(
                    later_inbound_message_id="IN-NEW",
                    successor_work_item={
                        "work_item_id": successor_work_item_identity(
                            account_id="147387", inbox_id="96568", contact_id="CONTACT-001",
                            conversation_id="CONV-001", inbound_message_id="IN-NEW",
                        ),
                        "contact_id": "CONTACT-001",
                        "conversation_id": "CONV-001",
                        "inbound_message_id": "IN-NEW",
                        "current_actionable": True,
                        "chronology_sha256": "BOUND_TO_CURRENT_CHRONOLOGY",
                    },
                    public_chronology=[
                        {"message_id": "IN-001", "message_type": "incoming"},
                        {"message_id": "IN-NEW", "message_type": "incoming"},
                    ],
                ),
                "superseded_by_later_inbound", "historical",
            ),
        )
        for proof, status, action in cases:
            with self.subTest(status=status):
                result = resolve_review_obligation(
                    review=review(), evidence=proof, represented_identity=represented()
                )
                self.assertEqual(result["customer_obligation_status"], status)
                self.assertEqual(result["resolution_action"], action)

    def test_changed_identity_chronology_or_missing_successor_fails_closed(self):
        proofs = []
        changed = evidence()
        changed["identity"]["bound_inbound_message_id"] = "OTHER"
        proofs.append(changed)
        proofs.append(evidence(public_chronology=[]))
        proofs.append(evidence(later_inbound_message_id="IN-NEW"))
        proofs.append(evidence(
            later_inbound_message_id="IN-NEW",
            successor_work_item={
                "work_item_id": "FABRICATED", "contact_id": "OTHER",
                "conversation_id": "CONV-001", "inbound_message_id": "IN-NEW",
                "current_actionable": True,
                "chronology_sha256": "BOUND_TO_CURRENT_CHRONOLOGY",
            },
            public_chronology=[
                {"message_id": "IN-001", "message_type": "incoming"},
                {"message_id": "IN-NEW", "message_type": "incoming"},
            ],
        ))
        for proof in proofs:
            with self.subTest(proof=proof):
                result = resolve_review_obligation(
                    review=review(), evidence=proof, represented_identity=represented()
                )
                self.assertEqual(result["customer_obligation_status"], "unknown_fail_closed")
                self.assertEqual(result["resolution_action"], "indeterminate")
                self.assertTrue(result["resolution_errors"])

    def test_zigay_child_mapping_is_prohibited(self):
        result = resolve_review_obligation(
            review=review(), evidence=evidence(),
            represented_identity=represented(
                canonical_same_animal_pig_id="PIG-B1A8-CHILD-1",
                alias_evidence_id="FORGED-ALIAS",
            ),
        )
        self.assertIn("cohort_child_same_animal_mapping_prohibited", result["resolution_errors"])

    def test_chronology_cutoff_must_equal_authoritative_tail(self):
        proof = evidence(chronology_cutoff_at="2026-07-31T12:05:00+00:00")
        result = resolve_review_obligation(
            review=review(), evidence=proof, represented_identity=represented()
        )
        self.assertIn("chronology_cutoff_tail_mismatch", result["resolution_errors"])
        self.assertEqual(result["resolution_action"], "indeterminate")
        self.assertEqual(result["resolution_action"], "indeterminate")

    def test_conflicting_or_unknown_identity_is_indeterminate(self):
        for status in ("conflicting", "unknown"):
            result = resolve_review_obligation(
                review=review(), evidence=evidence(),
                represented_identity=represented(status=status),
            )
            self.assertEqual(result["resolution_action"], "indeterminate")
            self.assertIn("represented_identity_not_authoritative", result["resolution_errors"])

    def test_complete_362_row_manifest_is_deterministic_and_replay_stable(self):
        reviews = [review(index) for index in range(1, 363)]
        evidence_rows = {row["review_event_id"]: evidence(index) for index, row in enumerate(reviews, 1)}
        first = build_resolution_manifest(
            reviews=reviews, evidence_by_review=evidence_rows,
            represented_identity=represented(),
        )
        replay = build_resolution_manifest(
            reviews=list(reversed(copy.deepcopy(reviews))),
            evidence_by_review=copy.deepcopy(evidence_rows),
            represented_identity=represented(),
        )
        self.assertEqual(first, replay)
        self.assertEqual(first["contract_version"], CONTRACT_VERSION)
        self.assertEqual(first["row_count"], 362)
        self.assertEqual(len(set(first["resolution_event_ids"])), 362)
        self.assertTrue(all(row["review_decision_sha256"] for row in first["rows"]))


if __name__ == "__main__":
    unittest.main()
