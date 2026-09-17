import unittest
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

from modules.oom_sakkie.withdrawal_relay_recovery import (
    APPROVED_GATEWAY_ORIGIN,
    IncidentCause,
    REVIEWED_BUILD_JS_SHA256,
    RecoveryAuthority,
    ReplayGuard,
    ReplayGuardState,
    RelayIncidentEvidence,
    classify_incident,
    prepare_recovery_instruction,
)


def incident(**overrides):
    now = datetime(2026, 7, 30, 14, 0, tzinfo=timezone.utc)
    values = {
        "gatekeeper_execution_id": "61267",
        "relay_execution_id": "61268",
        "normalization_succeeded": True,
        "relay_status": "relay_env_not_ready",
        "relay_reported_transport_validation_error": True,
        "current_gateway_origin": APPROVED_GATEWAY_ORIGIN,
        "current_origin_is_permitted": True,
        "live_relay_matches_reviewed_source": False,
        "live_relay_has_normalizer": False,
        "live_relay_has_safe_diagnostic": False,
        "render_gateway_enabled": False,
        "render_gateway_token_present": False,
        "render_allowed_owner_present": False,
        "sam_autonomy_level": "0",
        "sam_level1_live_stock_enabled": False,
        "sam_level1_cohort_enabled": False,
        "observed_at": now,
        "live_build_js_sha256": "old",
        "reviewed_build_js_sha256": REVIEWED_BUILD_JS_SHA256,
        "render_commit": "d" * 40,
        "reviewed_render_commit": "d" * 40,
        "authenticated_owner_identity_sha256": "b" * 64,
        "configured_owner_identity_sha256": "b" * 64,
    }
    values.update(overrides)
    return RelayIncidentEvidence(**values)


class WithdrawalRelayRecoveryContractTests(unittest.TestCase):
    def test_classifies_historical_value_live_regression_and_runtime_mismatch(self):
        self.assertEqual(
            classify_incident(incident()),
            (
                IncidentCause.HISTORICAL_VALIDATION_FAILURE,
                IncidentCause.VALIDATION_REGRESSION,
                IncidentCause.DEPLOYMENT_CONFIGURATION_MISMATCH,
            ),
        )

    def test_wrong_execution_or_unsupported_failure_fails_closed(self):
        self.assertEqual(
            classify_incident(incident(relay_execution_id="61269")),
            (IncidentCause.INSUFFICIENT_EVIDENCE,),
        )
        self.assertEqual(
            classify_incident(
                incident(relay_reported_transport_validation_error=False)
            ),
            (IncidentCause.INSUFFICIENT_EVIDENCE,),
        )

    def test_no_authority_means_no_replay_send_recording_or_sam_notice(self):
        evidence = incident()
        instruction = prepare_recovery_instruction(
            evidence, RecoveryAuthority(), now=evidence.observed_at
        )
        self.assertFalse(instruction.ready)
        self.assertFalse(instruction.may_recover_preserved_message)
        self.assertFalse(instruction.may_send_one_canonical_preview)
        self.assertFalse(instruction.may_record_farm_or_medical_fact)
        self.assertFalse(instruction.may_notify_sam)
        self.assertTrue(instruction.confirmation_required_after_preview)
        self.assertIn("61267", instruction.replay_key)
        self.assertIn("61268", instruction.replay_key)

    def test_each_release_and_readiness_gate_is_required(self):
        ready_evidence = incident(
            live_relay_matches_reviewed_source=True,
            live_relay_has_normalizer=True,
            live_relay_has_safe_diagnostic=True,
            render_gateway_enabled=True,
            render_gateway_token_present=True,
            render_allowed_owner_present=True,
            live_build_js_sha256=REVIEWED_BUILD_JS_SHA256,
        )
        replay_key = "gatekeeper:61267/relay:61268/withdrawal-preview:v1"
        guard = ReplayGuard(
            replay_key=replay_key,
            message_sha256="a" * 64,
            owner_identity_sha256="b" * 64,
            acquisition_receipt="receipt-1",
            state=ReplayGuardState.ACQUIRED,
        )
        flags = {
            "serialized_lane_released": True,
            "exact_executions_preserved": True,
            "preserved_message_sha256": "a" * 64,
            "recovery_message_sha256": "a" * 64,
            "reviewed_relay_deployed": True,
            "exact_gateway_configuration_ready": True,
            "replay_guard": guard,
            "required_render_commit": "d" * 40,
            "expected_owner_identity_sha256": "b" * 64,
        }
        for missing in flags:
            replacement = (
                None
                if missing == "replay_guard"
                else ""
                if missing.endswith("sha256")
                else False
            )
            authority = RecoveryAuthority(
                **{**flags, missing: replacement}
            )
            self.assertFalse(
                prepare_recovery_instruction(
                    ready_evidence,
                    authority,
                    now=ready_evidence.observed_at,
                ).ready,
                missing,
            )

    def test_ready_state_allows_one_preview_but_never_fact_recording(self):
        evidence = incident(
            live_relay_matches_reviewed_source=True,
            live_relay_has_normalizer=True,
            live_relay_has_safe_diagnostic=True,
            render_gateway_enabled=True,
            render_gateway_token_present=True,
            render_allowed_owner_present=True,
            live_build_js_sha256=REVIEWED_BUILD_JS_SHA256,
        )
        authority = RecoveryAuthority(
            serialized_lane_released=True,
            exact_executions_preserved=True,
            preserved_message_sha256="a" * 64,
            recovery_message_sha256="a" * 64,
            reviewed_relay_deployed=True,
            exact_gateway_configuration_ready=True,
            replay_guard=ReplayGuard(
                replay_key=(
                    "gatekeeper:61267/relay:61268/withdrawal-preview:v1"
                ),
                message_sha256="a" * 64,
                owner_identity_sha256="b" * 64,
                acquisition_receipt="receipt-1",
                state=ReplayGuardState.ACQUIRED,
            ),
            required_render_commit="d" * 40,
            expected_owner_identity_sha256="b" * 64,
        )
        instruction = prepare_recovery_instruction(
            evidence, authority, now=evidence.observed_at
        )
        self.assertTrue(instruction.ready)
        self.assertTrue(instruction.may_recover_preserved_message)
        self.assertTrue(instruction.may_send_one_canonical_preview)
        self.assertFalse(instruction.may_record_farm_or_medical_fact)
        self.assertFalse(instruction.may_notify_sam)

        consumed_guard = ReplayGuard(
            **{
                **authority.replay_guard.__dict__,
                "state": ReplayGuardState.CONSUMED,
            }
        )
        consumed = RecoveryAuthority(
            **{**authority.__dict__, "replay_guard": consumed_guard}
        )
        self.assertFalse(
            prepare_recovery_instruction(
                evidence, consumed, now=evidence.observed_at
            ).ready
        )

    def test_sam_must_remain_contained(self):
        evidence = incident(
            live_relay_matches_reviewed_source=True,
            live_relay_has_normalizer=True,
            live_relay_has_safe_diagnostic=True,
            render_gateway_enabled=True,
            render_gateway_token_present=True,
            render_allowed_owner_present=True,
            live_build_js_sha256=REVIEWED_BUILD_JS_SHA256,
            sam_autonomy_level="1",
        )
        authority = RecoveryAuthority(
            serialized_lane_released=True,
            exact_executions_preserved=True,
            preserved_message_sha256="a" * 64,
            recovery_message_sha256="a" * 64,
            reviewed_relay_deployed=True,
            exact_gateway_configuration_ready=True,
            replay_guard=ReplayGuard(
                replay_key=(
                    "gatekeeper:61267/relay:61268/withdrawal-preview:v1"
                ),
                message_sha256="a" * 64,
                owner_identity_sha256="b" * 64,
                acquisition_receipt="receipt-1",
                state=ReplayGuardState.ACQUIRED,
            ),
            required_render_commit="d" * 40,
            expected_owner_identity_sha256="b" * 64,
        )
        self.assertFalse(
            prepare_recovery_instruction(
                evidence, authority, now=evidence.observed_at
            ).ready
        )

    def test_wrong_guard_binding_stale_evidence_and_failure_shape_block(self):
        evidence = incident(
            live_relay_matches_reviewed_source=True,
            live_relay_has_normalizer=True,
            live_relay_has_safe_diagnostic=True,
            live_build_js_sha256=REVIEWED_BUILD_JS_SHA256,
            render_gateway_enabled=True,
            render_gateway_token_present=True,
            render_allowed_owner_present=True,
        )
        good = ReplayGuard(
            replay_key="gatekeeper:61267/relay:61268/withdrawal-preview:v1",
            message_sha256="a" * 64,
            owner_identity_sha256="b" * 64,
            acquisition_receipt="receipt-1",
            state=ReplayGuardState.ACQUIRED,
        )
        base = {
            "serialized_lane_released": True,
            "exact_executions_preserved": True,
            "preserved_message_sha256": "a" * 64,
            "recovery_message_sha256": "a" * 64,
            "reviewed_relay_deployed": True,
            "exact_gateway_configuration_ready": True,
            "replay_guard": good,
            "required_render_commit": "d" * 40,
            "expected_owner_identity_sha256": "b" * 64,
        }
        cases = [
            (incident(**{**evidence.__dict__, "normalization_succeeded": False}), RecoveryAuthority(**base)),
            (incident(**{**evidence.__dict__, "relay_status": "other"}), RecoveryAuthority(**base)),
            (incident(**{**evidence.__dict__, "relay_reported_transport_validation_error": False}), RecoveryAuthority(**base)),
            (incident(**{**evidence.__dict__, "observed_at": evidence.observed_at - timedelta(minutes=11)}), RecoveryAuthority(**base)),
            (evidence, RecoveryAuthority(**{**base, "replay_guard": ReplayGuard(**{**good.__dict__, "replay_key": "wrong"})})),
            (evidence, RecoveryAuthority(**{**base, "replay_guard": ReplayGuard(**{**good.__dict__, "message_sha256": "c" * 64})})),
            (evidence, RecoveryAuthority(**{**base, "replay_guard": ReplayGuard(**{**good.__dict__, "owner_identity_sha256": "c" * 64})})),
            (incident(**{**evidence.__dict__, "render_gateway_enabled": "false"}), RecoveryAuthority(**base)),
            (incident(**{**evidence.__dict__, "render_commit": "e" * 40, "reviewed_render_commit": "e" * 40}), RecoveryAuthority(**base)),
            (incident(**{**evidence.__dict__, "authenticated_owner_identity_sha256": "c" * 64, "configured_owner_identity_sha256": "c" * 64}), RecoveryAuthority(**base)),
        ]
        for candidate, authority in cases:
            self.assertFalse(
                prepare_recovery_instruction(
                    candidate, authority, now=evidence.observed_at
                ).ready
            )

    def test_contract_has_no_io_imports(self):
        source = (
            Path(__file__).parents[1]
            / "modules/oom_sakkie/withdrawal_relay_recovery.py"
        )
        tree = ast.parse(source.read_text(encoding="utf-8"))
        roots = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        roots.update(
            (node.module or "").split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        self.assertTrue(
            roots.isdisjoint(
                {
                    "requests",
                    "urllib",
                    "http",
                    "socket",
                    "os",
                    "subprocess",
                    "psycopg",
                    "sqlalchemy",
                    "modules",
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
