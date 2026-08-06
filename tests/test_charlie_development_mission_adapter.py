import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from modules.charlie.development_mission_adapter import (
    create_development_authorization,
    create_development_dispatch_grant,
    prepare_development_mission,
    validate_development_authorization,
    validate_development_dispatch_grant,
)
from modules.charlie.development_mission_store_adapter import _verify_repository_lineage


SECRET = "development-adapter-owner-secret-at-least-32-bytes"


def frozen_proposal():
    path = Path("docs/06-operations/contracts/CORE_T1_POST_P0_HANDOVER_CORRECTION_PROPOSAL.json")
    return json.loads(path.read_text(encoding="utf-8"))


class CharlieDevelopmentMissionAdapterTests(unittest.TestCase):
    def test_frozen_t1_contract_is_exact_one_builder(self):
        prepared = prepare_development_mission(frozen_proposal())
        self.assertEqual(prepared["plan"]["score_total"], 12)
        self.assertEqual(prepared["plan"]["tier"], "T1")
        self.assertEqual(prepared["plan"]["agents"], ["builder"])
        self.assertEqual(prepared["selected_worker"], "builder")

    def test_unsigned_wrong_owner_forged_stale_and_wrong_action_fail(self):
        prepared = prepare_development_mission(frozen_proposal())
        with self.assertRaisesRegex(ValueError, "authorization_(binding|signature)_invalid"):
            validate_development_authorization(prepared, {}, action="authorize_insert", secret=SECRET)
        with self.assertRaisesRegex(ValueError, "owner_authority_required"):
            create_development_authorization(prepared, action="authorize_insert", owner_principal="oom_sakkie", secret=SECRET)
        auth = create_development_authorization(prepared, action="authorize_insert", owner_principal="charlie", secret=SECRET)
        forged = {**auth, "signature": "0" * 64}
        with self.assertRaisesRegex(ValueError, "signature_invalid"):
            validate_development_authorization(prepared, forged, action="authorize_insert", secret=SECRET)
        with self.assertRaisesRegex(ValueError, "binding_invalid"):
            validate_development_authorization(prepared, auth, action="release", secret=SECRET)
        old = datetime.now(timezone.utc) - timedelta(minutes=10)
        stale = create_development_authorization(prepared, action="authorize_insert", owner_principal="charl", secret=SECRET,
                                                 issued_at=old, expires_at=old + timedelta(minutes=5))
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_development_authorization(prepared, stale, action="authorize_insert", secret=SECRET)

    def test_score_tier_scope_worker_and_operational_routing_tamper_fail(self):
        for mutate in (
            lambda p: p["planning_proof"].update(score_total=13),
            lambda p: p["planning_proof"].update(tier="T2"),
            lambda p: p["planning_proof"].update(agents=["tester"]),
            lambda p: p["mission"].update(expected_files=["docs/other.md"]),
            lambda p: p["mission"]["agentic_architecture_packet"].update(ordinary_farm_routing=True),
        ):
            proposal = copy.deepcopy(frozen_proposal())
            mutate(proposal)
            with self.assertRaises(ValueError):
                prepare_development_mission(proposal)

    def test_expired_pickup_grant_remains_valid_only_as_durable_session_identity(self):
        prepared = prepare_development_mission(frozen_proposal())
        issued = datetime.now(timezone.utc) - timedelta(minutes=20)
        grant = create_development_dispatch_grant(
            prepared, worker_id="builder-1", worker_role="builder", dispatch_id="D-1",
            secret=SECRET, issued_at=issued, expires_at=issued + timedelta(minutes=15),
        )
        with self.assertRaisesRegex(ValueError, "grant_stale"):
            validate_development_dispatch_grant(prepared, grant, secret=SECRET)
        validated = validate_development_dispatch_grant(
            prepared, grant, secret=SECRET, allow_expired=True,
        )
        self.assertEqual(validated["dispatch_grant_digest"], grant["dispatch_grant_digest"])

    @patch("modules.charlie.development_mission_store_adapter.subprocess.run")
    def test_repository_lineage_requires_exact_ancestry_and_file_set(self, run):
        mission = prepare_development_mission(frozen_proposal())["mission"]
        expected = mission["expected_files"]
        run.side_effect = [
            type("Result", (), {"returncode": 0, "stdout": ""})(),
            type("Result", (), {"returncode": 0, "stdout": "\n".join(expected) + "\n"})(),
        ]
        proof = _verify_repository_lineage(mission, {
            "base_revision": mission["source_base_revision"],
            "candidate_revision": "a" * 40,
            "changed_files": expected,
        })
        self.assertEqual(proof["changed_files"], expected)
        self.assertEqual(len(proof["proof_digest"]), 64)

        with self.assertRaisesRegex(ValueError, "lineage_invalid"):
            _verify_repository_lineage(mission, {
                "base_revision": mission["source_base_revision"],
                "candidate_revision": "a" * 40,
                "changed_files": ["docs/unexpected.md"],
            })


if __name__ == "__main__":
    unittest.main()
