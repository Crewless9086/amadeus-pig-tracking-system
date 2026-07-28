from unittest import TestCase
from unittest.mock import patch

from modules.oom_sakkie.herdmaster_weight_preview import (
    preview_herd_weight_fact,
)
from modules.oom_sakkie.service import (
    DETERMINISTIC_ONLY_TOOLS,
    classify_intent,
    handle_message,
)
from modules.oom_sakkie.tools import herdmaster_weight_preview_handler


SHUPE_MESSAGE = "Shupe weighed 72.2kg on Monday 20th July 2026"
SHUPE = {
    "pig_id": "PIG-2026-34BF",
    "tag_number": "Shupe",
    "status": "Active",
    "on_farm": "Yes",
}


def accepted_preflight(payload):
    return {
        "success": True,
        "accepted_count": 1,
        "accepted_rows": payload["rows"],
        "blocked_rows": [],
        "writes_to_google_sheets": False,
    }, 200


class HerdmasterTelegramWeightPreviewTests(TestCase):
    def test_exact_shupe_fact_is_parsed_without_inventing_time(self):
        result = preview_herd_weight_fact(
            SHUPE_MESSAGE,
            {"success": True, "pigs": [SHUPE]},
            accepted_preflight,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["pig_id"], "PIG-2026-34BF")
        self.assertEqual(result["weight_kg"], 72.2)
        self.assertEqual(result["weight_date"], "2026-07-20")
        self.assertIsNone(result["observation_time"])
        self.assertEqual(result["observation_time_state"], "Unknown")
        self.assertTrue(result["confirmation_required"])
        self.assertFalse(result["writes_performed"])

    def test_preview_identity_is_deterministic(self):
        first = preview_herd_weight_fact(
            SHUPE_MESSAGE, {"success": True, "pigs": [SHUPE]}, accepted_preflight
        )
        replay = preview_herd_weight_fact(
            SHUPE_MESSAGE, {"success": True, "pigs": [SHUPE]}, accepted_preflight
        )
        self.assertEqual(first["preview_id"], replay["preview_id"])

    def test_ambiguous_animal_fails_closed(self):
        duplicate = dict(SHUPE, pig_id="PIG-OTHER")
        result = preview_herd_weight_fact(
            SHUPE_MESSAGE, {"success": True, "pigs": [SHUPE, duplicate]}, accepted_preflight
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "animal_identity_ambiguous")

    def test_missing_animal_fails_closed(self):
        result = preview_herd_weight_fact(
            SHUPE_MESSAGE, {"success": True, "pigs": []}, accepted_preflight
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "animal_identity_not_found")

    def test_inactive_animal_fails_before_preflight(self):
        called = []
        result = preview_herd_weight_fact(
            SHUPE_MESSAGE,
            {"success": True, "pigs": [dict(SHUPE, status="Exited", on_farm="No")]},
            lambda payload: called.append(payload),
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "animal_not_active_on_farm")
        self.assertEqual(called, [])

    def test_canonical_duplicate_or_block_is_returned_without_write(self):
        def blocked(_payload):
            return {
                "success": False,
                "error": "validation_error",
                "accepted_count": 0,
                "blocked_rows": [{"reason": "Already recorded for this date."}],
            }, 400

        result = preview_herd_weight_fact(
            SHUPE_MESSAGE, {"success": True, "pigs": [SHUPE]}, blocked
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "validation_error")
        self.assertIn("canonical weight preflight", result["clarification"])
        self.assertFalse(result["writes_performed"])

    def test_general_weight_fact_routes_to_deterministic_herdmaster_tool(self):
        match = classify_intent(SHUPE_MESSAGE)
        self.assertEqual(match.tool_name, "herdmaster_weight_preview")
        self.assertIn("herdmaster_weight_preview", DETERMINISTIC_ONLY_TOOLS)

    @patch("modules.oom_sakkie.tools.preview_bulk_weight_entries")
    @patch("modules.oom_sakkie.tools.get_pig_allocation_readiness_data")
    @patch("modules.oom_sakkie.tools.owner_session_is_valid", return_value=True)
    def test_owner_handler_returns_confirmation_preview_only(
        self, _owner, readiness, preflight
    ):
        readiness.return_value = {"success": True, "pigs": [SHUPE]}
        preflight.side_effect = accepted_preflight
        result = herdmaster_weight_preview_handler({"user_text": SHUPE_MESSAGE})
        self.assertTrue(result["success"])
        self.assertIn("72.2 kg", result["summary"])
        self.assertIn("2026-07-20", result["summary"])
        self.assertIn("Observation time remains Unknown", result["summary"])
        self.assertIn("No weight was recorded", result["summary"])
        self.assertIn("cannot record it", result["summary"])
        self.assertIn("HERD-WEIGHT-PREVIEW-", result["summary"])
        self.assertNotIn("PIG-2026-34BF", result["summary"])
        self.assertFalse(result["raw"]["writes_performed"])

    @patch("modules.oom_sakkie.tools.get_pig_allocation_readiness_data")
    @patch("modules.oom_sakkie.tools.owner_session_is_valid", return_value=False)
    def test_anonymous_request_is_denied_before_canonical_read(
        self, _owner, readiness
    ):
        result = herdmaster_weight_preview_handler({"user_text": SHUPE_MESSAGE})
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "owner_authentication_required")
        readiness.assert_not_called()

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False})
    @patch("modules.oom_sakkie.tools.preview_bulk_weight_entries")
    @patch("modules.oom_sakkie.tools.get_pig_allocation_readiness_data")
    @patch("modules.oom_sakkie.tools.owner_session_is_valid", return_value=True)
    def test_telegram_read_only_pipeline_returns_actual_preview(
        self, _owner, readiness, preflight, _trace
    ):
        readiness.return_value = {"success": True, "pigs": [SHUPE]}
        preflight.side_effect = accepted_preflight
        result, status = handle_message({
            "text": SHUPE_MESSAGE,
            "channel": "telegram_read_only",
            "session_id": "private-owner-session",
        })
        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "herdmaster_weight_preview")
        self.assertIn("Shupe", result["answer"])
        self.assertIn("72.2 kg", result["answer"])
        self.assertIn("2026-07-20", result["answer"])
        self.assertNotIn("PIG-2026-34BF", result["answer"])
        self.assertEqual(result["pipeline"]["answer_source"], "deterministic")

    def test_weekday_date_conflict_fails_closed(self):
        result = preview_herd_weight_fact(
            "Shupe weighed 72.2kg on Monday 21st July 2026",
            {"success": True, "pigs": [SHUPE]},
            accepted_preflight,
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "weight_date_weekday_conflict")

    def test_incomplete_readiness_envelope_fails_closed(self):
        for readiness in (
            None,
            [],
            {"pigs": [SHUPE]},
            {"success": False, "pigs": [SHUPE]},
            {"success": True, "pigs": [SHUPE, None]},
        ):
            with self.subTest(readiness=readiness):
                result = preview_herd_weight_fact(
                    SHUPE_MESSAGE, readiness, accepted_preflight
                )
                self.assertFalse(result["success"])
                self.assertEqual(
                    result["status"], "canonical_herd_identity_unavailable"
                )

    def test_missing_current_animal_evidence_fails_closed(self):
        for changed in (
            {"on_farm": None},
            {"status": None},
            {"status": "Unknown"},
        ):
            with self.subTest(changed=changed):
                result = preview_herd_weight_fact(
                    SHUPE_MESSAGE,
                    {"success": True, "pigs": [dict(SHUPE, **changed)]},
                    accepted_preflight,
                )
                self.assertFalse(result["success"])
                self.assertEqual(result["status"], "animal_not_active_on_farm")
