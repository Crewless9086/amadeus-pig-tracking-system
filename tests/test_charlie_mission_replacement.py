import copy
import unittest
from datetime import datetime, timedelta, timezone

from modules.charlie.adaptive_orchestration import build_orchestration_packet, validate_orchestration_binding
from modules.charlie.mission_store import (
    create_replacement_owner_authorization,
    prepare_many_to_one_replacement,
    record_replacement_owner_authorization,
    validate_replacement_owner_authorization,
)


SECRET = "test-owner-authorization-secret-32-bytes-minimum"
S01_PREDECESSORS = (
    "CHARLIE-OUTCOME-23890E45EFE2A2C3",
    "CHARLIE-FOLLOWUP-672D7917CFD7332D",
    "CHARLIE-FOLLOWUP-TELEGRAM-CHANNEL-CONTRACT-20260722",
)


def successor_contract():
    mission = {"title": "Close Oom Sakkie daily control", "raw_text": "Build bounded authenticated Telegram lifecycle software.", "mission_type": "system improvement"}
    packet = build_orchestration_packet(mission)
    workflow = [{"agent": item["agent"], "status": "pending"} for item in packet["selected_agents"]]
    binding = validate_orchestration_binding(packet, workflow)
    return {
        "mission_id": "S01-OOM-DAILY-CONTROL-CLOSURE", "status": "paused", "source": "charlie_reconciliation",
        "raw_text": mission["raw_text"], "title": mission["title"], "urgency": "P1",
        "mission_type": mission["mission_type"], "approval_level": "LEVEL 4",
        "metadata_json": {"orchestration": packet, "agent_workflow": workflow,
                          "orchestration_binding": {**binding, "validated": True, "generation_identity": packet["generation_identity"]}},
    }


def predecessors():
    return [{"mission_id": mission_id, "expected_status": "new", "expected_content_digest": str(n) * 64,
             "expected_metadata_generation": f"generation-{n}", "unfinished_value_reference": f"artifacts/03_preserved_unfinished_value_manifest.json#{mission_id}"}
            for n, mission_id in enumerate(S01_PREDECESSORS, 1)]


class CharlieMissionReplacementContractTests(unittest.TestCase):
    def test_three_to_one_contract_is_deterministic_and_paused(self):
        contract = successor_contract()
        first = prepare_many_to_one_replacement(contract, list(reversed(predecessors())))
        second = prepare_many_to_one_replacement(contract, predecessors())
        self.assertEqual(first, second)
        self.assertEqual(len(first["predecessor_mission_ids"]), 3)
        self.assertEqual(tuple(first["predecessor_mission_ids"]), tuple(sorted(S01_PREDECESSORS)))
        self.assertEqual(contract["status"], "paused")
        self.assertEqual(contract["metadata_json"]["orchestration"]["tier"], "T4")
        self.assertEqual(
            [item["agent"] for item in contract["metadata_json"]["orchestration"]["selected_agents"]],
            [item["agent"] for item in contract["metadata_json"]["agent_workflow"]],
        )
        self.assertTrue(first["replacement_identity"].startswith("CHARLIE-REPLACEMENT-BATCH-"))

    def test_duplicate_predecessor_rejected(self):
        items = predecessors()
        with self.assertRaisesRegex(ValueError, "duplicate_predecessor"):
            prepare_many_to_one_replacement(successor_contract(), [items[0], items[0]])

    def test_runnable_or_successor_active_status_rejected(self):
        contract = successor_contract(); contract["status"] = "approved"
        with self.assertRaisesRegex(ValueError, "status_not_paused"):
            prepare_many_to_one_replacement(contract, predecessors())
        items = predecessors(); items[0]["expected_status"] = "in_progress"
        with self.assertRaisesRegex(ValueError, "status_runnable_or_unsupported"):
            prepare_many_to_one_replacement(successor_contract(), items)

    def test_authorization_binds_exact_contract_allowlist_and_transaction(self):
        prepared = prepare_many_to_one_replacement(successor_contract(), predecessors())
        now = datetime.now(timezone.utc)
        auth = create_replacement_owner_authorization(prepared, owner_principal="owner:charl", secret=SECRET, issued_at=now, expires_at=now+timedelta(minutes=5))
        self.assertEqual(validate_replacement_owner_authorization(prepared, auth, secret=SECRET, now=now), auth)
        forged = copy.deepcopy(auth); forged["transaction_digest"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "binding_invalid"):
            validate_replacement_owner_authorization(prepared, forged, secret=SECRET, now=now)
        with self.assertRaisesRegex(ValueError, "signature_invalid"):
            validate_replacement_owner_authorization(prepared, auth, secret=SECRET + "wrong", now=now)

    def test_stale_authorization_rejected(self):
        prepared = prepare_many_to_one_replacement(successor_contract(), predecessors())
        issued = datetime.now(timezone.utc) - timedelta(minutes=10)
        auth = create_replacement_owner_authorization(prepared, owner_principal="owner:charl", secret=SECRET, issued_at=issued, expires_at=issued+timedelta(minutes=5))
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_replacement_owner_authorization(prepared, auth, secret=SECRET)

    def test_unconfigured_short_secret_rejected(self):
        prepared = prepare_many_to_one_replacement(successor_contract(), predecessors())
        auth = create_replacement_owner_authorization(prepared, owner_principal="owner:charl", secret=SECRET)
        with self.assertRaisesRegex(ValueError, "authority_not_configured"):
            validate_replacement_owner_authorization(prepared, auth, secret="")

    def test_unrecognized_owner_identity_rejected_before_database_access(self):
        prepared = prepare_many_to_one_replacement(successor_contract(), predecessors())
        auth = create_replacement_owner_authorization(prepared, owner_principal="owner:charl", secret=SECRET)
        with self.assertRaisesRegex(ValueError, "owner_identity_not_authorized"):
            record_replacement_owner_authorization(prepared, auth, secret=SECRET, expected_owner_identity_hash="f" * 64)


if __name__ == "__main__":
    unittest.main()
