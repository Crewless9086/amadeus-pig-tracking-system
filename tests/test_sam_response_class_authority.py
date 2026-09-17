import json
from pathlib import Path
import unittest
from datetime import datetime, timedelta, timezone

from modules.sales.sam_response_class_authority import (
    append_authority_decision,
    authority_visibility_report,
    build_authority_event,
    evaluate_and_persist_candidates,
    evidence_window_identity,
    pair_canonical_evidence,
    resolve_runtime_authority,
)


NOW = datetime(2026, 7, 26, 12, tzinfo=timezone.utc)
ENABLED = {
    "SAM_RESPONSE_CLASS_AUTHORITY_CONTROLLER_ENABLED": "true",
    "SAM_RESPONSE_CLASS_AUTHORITY_GLOBAL_ENABLED": "true",
    "SAM_RESPONSE_CLASS_GREETING_ENABLED": "true",
}


def qualifying(response_class="greeting", count=30):
    return [
        {
            "response_class": response_class,
            "observed_at": (NOW - timedelta(hours=1)).isoformat(),
            "owner_approved": True,
            "provider_confirmed": True,
        }
        for _ in range(count)
    ]


class SamResponseClassAuthorityTests(unittest.TestCase):
    def test_event_is_json_safe_sanitized_and_stable(self):
        evaluation = {
            "evidence": {"sample_count": 30, "owner_approval_rate": 1.0},
            "gates": {"sample_count": True},
        }
        kwargs = dict(
            actor_type="owner",
            actor_id="owner-session",
            reason="bounded canary approved",
            authorized_envelope={"response_classes": ["greeting"]},
            environ=ENABLED,
            now=NOW,
        )
        first = build_authority_event("greeting", "promoted", evaluation, **kwargs)
        second = build_authority_event("greeting", "promoted", evaluation, **kwargs)
        self.assertEqual(first["authority_event_id"], second["authority_event_id"])
        self.assertFalse(first["contains_customer_content"])
        self.assertFalse(first["sends_customer_message"])
        json.dumps(first)

    def test_charlie_can_pause_but_cannot_promote(self):
        evaluation = {"evidence": {}, "gates": {}}
        paused = build_authority_event(
            "greeting", "paused", evaluation,
            actor_type="charlie", actor_id="charlie", reason="delivery drift",
            now=NOW,
        )
        self.assertEqual(paused["decision"], "paused")
        with self.assertRaisesRegex(ValueError, "charlie_may_only_pause"):
            build_authority_event(
                "greeting", "promoted", evaluation,
                actor_type="charlie", actor_id="charlie", reason="not allowed",
                authorized_envelope={"response_classes": ["greeting"]},
                now=NOW,
            )

    def test_owner_may_build_each_governed_decision_without_side_effects(self):
        evaluation = {"evidence": {"sample_count": 30}, "gates": {}}
        for decision in (
            "candidate", "canary_authorized", "promoted",
            "paused", "regressed", "retired",
        ):
            event = build_authority_event(
                "greeting", decision, evaluation,
                actor_type="owner", actor_id="owner", reason="governed decision",
                authorized_envelope=(
                    {"response_classes": ["greeting"]}
                    if decision in {"canary_authorized", "promoted"} else {}
                ),
                now=NOW,
            )
            self.assertFalse(event["sends_customer_message"])
            self.assertFalse(event["mutates_business_state"])

    def test_server_persists_candidate_but_never_promotes(self):
        recorded = []
        result = evaluate_and_persist_candidates(
            qualifying(),
            now=NOW,
            recorder=lambda event, **_kwargs: (
                recorded.append(event) or {
                    "success": True,
                    "status": "authority_event_recorded",
                    "authority_event_id": event["authority_event_id"],
                },
                201,
            ),
            database_url="unused",
        )
        self.assertEqual([row["decision"] for row in recorded], ["candidate"])
        self.assertFalse(result["runtime_authority_changed"])

    def test_runtime_requires_persistent_promoted_fresh_exact_class_and_switches(self):
        evaluation = {
            "evidence": {"sample_count": 30},
            "gates": {"sample_count": True},
        }
        event = build_authority_event(
            "greeting", "promoted", evaluation,
            actor_type="owner", actor_id="owner", reason="canary passed",
            authorized_envelope={"response_classes": ["greeting"]},
            environ=ENABLED, now=NOW,
        )
        allowed = resolve_runtime_authority(
            "greeting", current_message_class="greeting",
            delivery_rail_available=True, latest_event=event,
            environ=ENABLED, now=NOW,
        )
        self.assertTrue(allowed["allowed"])
        blocked = resolve_runtime_authority(
            "greeting", current_message_class="thanks",
            delivery_rail_available=True, latest_event=event,
            environ=ENABLED, now=NOW,
        )
        self.assertFalse(blocked["allowed"])
        self.assertIn("current_message_class_mismatch", blocked["blockers"])

    def test_missing_database_configuration_and_kill_switches_fail_closed(self):
        result = resolve_runtime_authority(
            "greeting", current_message_class="greeting",
            delivery_rail_available=True, environ={},
        )
        self.assertFalse(result["allowed"])
        self.assertIn("persistent_authority_unavailable", result["blockers"])
        self.assertIn("global_kill_switch_not_clear", result["blockers"])

    def test_regression_is_independent_by_class(self):
        rows = qualifying("greeting") + qualifying("thanks")
        rows[-1]["owner_rejected"] = True
        report = authority_visibility_report(rows, now=NOW)
        self.assertEqual(report["classes"]["greeting"]["qualification"], "candidate")
        self.assertEqual(report["classes"]["thanks"]["qualification"], "regressed")
        self.assertFalse(report["charlie"]["may_promote"])

    def test_evidence_hash_is_class_bound(self):
        evidence = {"sample_count": 30}
        self.assertNotEqual(
            evidence_window_identity("greeting", evidence),
            evidence_window_identity("thanks", evidence),
        )

    def test_migration_is_append_only_and_has_conflict_index(self):
        sql = Path(
            "supabase/migrations/202607260001_create_sam_response_class_authority_events.sql"
        ).read_text(encoding="utf-8").lower()
        self.assertIn("before update", sql)
        self.assertIn("before delete", sql)
        self.assertIn("uq_sam_response_class_authority_prior_transition", sql)
        self.assertIn("from public, anon, authenticated", sql)
        self.assertIn("revoke select, insert, update, delete, truncate", sql)
        self.assertIn("revoke execute", sql)
        self.assertIn("grant select, insert", sql)
        self.assertIn("must not own a sequence", sql)

    def test_production_shaped_learning_delivery_linkage_is_exact_and_idempotent(self):
        fixture = json.loads(Path(
            "tests/fixtures/sam_response_class_authority_linkage.json"
        ).read_text(encoding="utf-8"))
        first = pair_canonical_evidence(
            fixture["learning_rows"], fixture["delivery_rows"]
        )
        second = pair_canonical_evidence(
            fixture["learning_rows"], fixture["delivery_rows"] * 2
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["response_class"], "greeting")
        self.assertTrue(first[0]["owner_approved"])
        self.assertTrue(first[0]["provider_confirmed"])
        self.assertTrue(first[0]["delivery_linkage_available"])
        self.assertFalse(first[0]["contains_customer_content"])

    def test_learning_linkage_never_crosses_conversation_or_class(self):
        fixture = json.loads(Path(
            "tests/fixtures/sam_response_class_authority_linkage.json"
        ).read_text(encoding="utf-8"))
        for key, value in (
            ("conversation_id", "OTHER-CONVERSATION"),
            ("response_class", "thanks"),
        ):
            rows = json.loads(json.dumps(fixture["delivery_rows"]))
            for row in rows:
                if key == "conversation_id":
                    row["conversation_id"] = value
                    row["review_json"]["conversation_id"] = value
                else:
                    row["review_json"][key] = value
            result = pair_canonical_evidence(fixture["learning_rows"], rows)
            self.assertFalse(result[0]["provider_confirmed"])
            self.assertFalse(result[0]["delivery_linkage_available"])

    def test_historical_missing_linkage_remains_unavailable(self):
        result = pair_canonical_evidence(
            [{
                "learning_event_id": "HISTORICAL-1",
                "conversation_id": "C-1",
                "created_at": "2026-07-01T00:00:00+00:00",
                "captured_facts": {
                    "reply_class": "greeting",
                    "owner_reply_classification": "approved_verbatim",
                },
            }],
            [],
        )
        self.assertTrue(result[0]["owner_approved"])
        self.assertFalse(result[0]["provider_confirmed"])
        self.assertFalse(result[0]["delivery_linkage_available"])


if __name__ == "__main__":
    unittest.main()
