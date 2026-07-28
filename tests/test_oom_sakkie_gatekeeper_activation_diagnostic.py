import json
import unittest
import urllib.error

from scripts.oom_sakkie_gatekeeper_activation_diagnostic import (
    STAGES,
    ActivationDiagnostic,
    AmbiguousTransportError,
    InertDiagnosticAdapter,
    StageEvidence,
    administrative_write_stage_evidence,
    deterministic_request_identity,
    inert_rehearsal_report,
    response_shape,
    safe_workflow_rejection_evidence,
    telegram_shared_flag_authority_contract,
)


class GateKeeperActivationDiagnosticTests(unittest.TestCase):
    def test_empty_201_projection_response_requires_and_accepts_verified_readback(self):
        evidence = administrative_write_stage_evidence(
            stage="owner_projection_create_response",
            http_status=201,
            response=None,
            authoritative_readback="verified",
        )
        self.assertEqual(evidence["response_shape"], "empty")
        self.assertEqual(evidence["outcome"], "persisted_verified")
        self.assertTrue(evidence["proceed"])
        self.assertFalse(evidence["raw_response_retained"])

    def test_empty_201_without_projection_readback_is_ambiguous(self):
        evidence = administrative_write_stage_evidence(
            stage="private_chat_projection_create_response",
            http_status=201,
            response=None,
            authoritative_readback="missing",
        )
        self.assertEqual(evidence["outcome"], "ambiguous_unverified")
        self.assertFalse(evidence["proceed"])
        self.assertTrue(evidence["rollback_required"])

    def test_rejected_workflow_update_records_safe_status_and_shape(self):
        evidence = administrative_write_stage_evidence(
            stage="workflow_update_request",
            http_status=400,
            response={"message": "provider detail must not be retained"},
            authoritative_readback="missing",
        )
        self.assertEqual(evidence["http_status"], 400)
        self.assertEqual(evidence["response_shape"], "object:1")
        self.assertEqual(evidence["outcome"], "rejected_not_persisted")
        self.assertNotIn("provider detail", json.dumps(evidence))
        self.assertFalse(evidence["proceed"])

    def test_http_400_records_actionable_safe_n8n_settings_mismatch(self):
        evidence = administrative_write_stage_evidence(
            stage="workflow_update_request",
            http_status=400,
            response={
                "message": "request/body/settings must NOT have additional properties"
            },
            authoritative_readback="missing",
            request_payload={
                "name": "GateKeeper",
                "nodes": [],
                "connections": {},
                "settings": {
                    "binaryMode": "default",
                    "executionOrder": "v1",
                },
            },
        )
        rejection = evidence["rejection_evidence"]
        self.assertEqual(
            rejection["provider_message_code"],
            "n8n_settings_additional_property",
        )
        self.assertEqual(
            rejection["field_contract_mismatch"],
            "settings_contains_unsupported_field",
        )
        self.assertEqual(rejection["response_top_level_keys"], ["message"])
        self.assertEqual(
            rejection["request_top_level_keys"],
            ["connections", "name", "nodes", "settings"],
        )
        self.assertEqual(
            rejection["settings_keys"], ["binaryMode", "executionOrder"]
        )
        self.assertNotIn("GateKeeper", json.dumps(rejection))
        self.assertFalse(rejection["raw_response_retained"])

    def test_unknown_provider_message_is_not_retained(self):
        rejection = safe_workflow_rejection_evidence(
            {
                "message": "secret owner identity and token must never survive",
                "unsafe-provider-key": "private",
            },
            {"name": "private workflow", "nodes": [], "connections": {}, "settings": {}},
        )
        serialized = json.dumps(rejection)
        self.assertEqual(
            rejection["provider_message_code"],
            "provider_rejection_unclassified",
        )
        self.assertEqual(rejection["response_top_level_keys"], ["message"])
        self.assertNotIn("secret owner", serialized)
        self.assertNotIn("private workflow", serialized)
        self.assertNotIn("unsafe-provider-key", serialized)

    def test_accepted_workflow_update_requires_exact_hash_readback(self):
        accepted = administrative_write_stage_evidence(
            stage="workflow_update_request",
            http_status=200,
            response={},
            authoritative_readback="matched",
        )
        ambiguous = administrative_write_stage_evidence(
            stage="workflow_update_request",
            http_status=200,
            response={},
            authoritative_readback="unavailable",
        )
        self.assertTrue(accepted["proceed"])
        self.assertFalse(ambiguous["proceed"])

    def test_rejected_response_with_verified_persistence_requires_rollback(self):
        evidence = administrative_write_stage_evidence(
            stage="owner_projection_create_response",
            http_status=409,
            response={"message": "conflict"},
            authoritative_readback="verified",
        )
        self.assertEqual(
            evidence["outcome"],
            "persisted_after_rejected_or_ambiguous_response",
        )
        self.assertFalse(evidence["proceed"])
        self.assertTrue(evidence["rollback_required"])

    def test_workflow_verified_is_not_exact_hash_match_and_cannot_proceed(self):
        evidence = administrative_write_stage_evidence(
            stage="workflow_update_request",
            http_status=200,
            response={},
            authoritative_readback="verified",
        )
        self.assertEqual(evidence["outcome"], "conflict")
        self.assertFalse(evidence["proceed"])

    def test_projection_matched_is_not_verified_and_cannot_proceed(self):
        evidence = administrative_write_stage_evidence(
            stage="owner_projection_create_response",
            http_status=201,
            response=None,
            authoritative_readback="matched",
        )
        self.assertEqual(evidence["outcome"], "conflict")
        self.assertFalse(evidence["proceed"])

    def test_rejected_http_with_unavailable_readback_remains_ambiguous(self):
        evidence = administrative_write_stage_evidence(
            stage="workflow_update_request",
            http_status=400,
            response={},
            authoritative_readback="unavailable",
        )
        self.assertEqual(evidence["outcome"], "ambiguous_unverified")
        self.assertTrue(evidence["rollback_required"])

    def test_missing_http_with_no_readback_remains_ambiguous(self):
        evidence = administrative_write_stage_evidence(
            stage="private_chat_projection_create_response",
            http_status=None,
            response=None,
            authoritative_readback="not_run",
        )
        self.assertEqual(evidence["outcome"], "ambiguous_unverified")
        self.assertTrue(evidence["rollback_required"])

    def test_shared_direct_flags_are_legitimate_and_beacon_gate_stays_off(self):
        contract = telegram_shared_flag_authority_contract(
            {
                "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "true",
                "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "true",
            }
        )
        self.assertTrue(contract["preactivation_ready"])
        self.assertFalse(contract["beacon_media_intake"]["enabled"])
        self.assertEqual(
            contract["beacon_media_intake"]["required_state_before_activation"],
            "disabled",
        )
        self.assertTrue(contract["oom_sakkie_direct"]["enabled"])
        self.assertIn(
            "sam_owner_callback_handling",
            contract["oom_sakkie_direct"]["consumers"],
        )
        self.assertIn(
            "ordinary_owner_text_handling",
            contract["oom_sakkie_direct"]["consumers"],
        )
        self.assertIn(
            "owner_telegram_replies",
            contract["oom_sakkie_direct_send"]["consumers"],
        )
        self.assertFalse(contract["beacon_activation_changes_shared_flags"])

    def test_absent_beacon_flag_is_fail_closed_disabled_not_misconfiguration(self):
        contract = telegram_shared_flag_authority_contract(
            {
                "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
                "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
            }
        )
        self.assertEqual(
            contract["status"],
            "beacon_media_intake_disabled_shared_routes_preserved",
        )
        self.assertTrue(contract["preactivation_ready"])

    def test_beacon_enabled_before_activation_fails_preflight(self):
        contract = telegram_shared_flag_authority_contract(
            {
                "BEACON_TELEGRAM_MEDIA_INTAKE_ENABLED": "true",
                "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "true",
                "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "true",
            }
        )
        self.assertFalse(contract["preactivation_ready"])
        self.assertEqual(contract["status"], "beacon_media_intake_already_enabled")

    def test_disabling_either_shared_flag_is_not_beacon_containment(self):
        for key in (
            "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED",
            "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED",
        ):
            with self.subTest(key=key):
                source = {
                    "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "true",
                    "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "true",
                }
                source[key] = "false"
                contract = telegram_shared_flag_authority_contract(source)
                self.assertFalse(contract["preactivation_ready"])
                self.assertEqual(
                    contract["status"],
                    "shared_oom_sakkie_direct_contract_unavailable",
                )

    def test_shared_flag_contract_grants_no_new_authority(self):
        contract = telegram_shared_flag_authority_contract(
            {
                "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "true",
                "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "true",
            }
        )
        for key in (
            "customer_messaging_authority",
            "publication_authority",
            "meta_authority",
            "advertising_authority",
            "boost_authority",
            "spend_authority",
        ):
            self.assertFalse(contract[key])

    def test_inert_rehearsal_records_every_stage_in_order(self):
        report = inert_rehearsal_report("PACKET-1")
        completed = [
            event["stage"]
            for event in report["events"]
            if event["state"] == "completed"
        ]
        self.assertEqual(completed, list(STAGES))
        self.assertTrue(report["mutation_attempted"])
        self.assertEqual(report["automatic_retries"], 0)

    def test_read_only_preflight_identifies_all_stages_without_mutation(self):
        report = ActivationDiagnostic(
            packet_identity="PACKET-READ",
            adapter=InertDiagnosticAdapter(),
        ).run_read_only()
        represented = {event["stage"] for event in report["events"]}
        self.assertEqual(represented, set(STAGES))
        self.assertFalse(report["mutation_attempted"])
        not_run = {
            event["stage"]
            for event in report["events"]
            if event["state"] == "not_run"
        }
        self.assertEqual(not_run, {STAGES[2], STAGES[3], STAGES[5], STAGES[6], STAGES[10]})

    def test_request_identity_is_stable_and_packet_bound(self):
        first = deterministic_request_identity("n8n_capability_read", {"packet": "A"})
        self.assertEqual(
            first,
            deterministic_request_identity("n8n_capability_read", {"packet": "A"}),
        )
        self.assertNotEqual(
            first,
            deterministic_request_identity("n8n_capability_read", {"packet": "B"}),
        )

    def test_response_shape_never_contains_values(self):
        shape = response_shape({"data": {"secret": "do-not-show"}, "nextCursor": None})
        self.assertEqual(shape, "object:2")
        self.assertNotIn("do-not-show", shape)

    def test_response_shape_never_contains_provider_controlled_keys(self):
        shape = response_shape(
            {
                "private-owner-identity-123": {},
                "secret-token-material": {},
            }
        )
        self.assertEqual(shape, "object:2")
        self.assertNotIn("owner", shape)
        self.assertNotIn("secret", shape)

    def test_stage_evidence_rejects_unknown_failure_class(self):
        event = StageEvidence(
            1, STAGES[0], "failed", "ID", None, "empty", "unavailable", "raw error"
        )
        with self.assertRaisesRegex(ValueError, "unsafe_failure_class"):
            event.validate()

    def test_report_has_zero_action_authority(self):
        report = inert_rehearsal_report("PACKET-AUTH")
        self.assertTrue(all(value is False for value in report["authority"].values()))
        serialized = json.dumps(report).lower()
        for forbidden in ("bot_token", "owner_id", "chat_id", "file_id"):
            self.assertNotIn(forbidden, serialized)

    def test_unexpected_create_shape_is_classified_without_raw_content(self):
        class ShapeAdapter(InertDiagnosticAdapter):
            def projection_create(self, role):
                result = super().projection_create(role)
                result["response"] = ["unexpected", {"token": "hidden"}]
                return result

        report = ActivationDiagnostic(
            packet_identity="PACKET-SHAPE", adapter=ShapeAdapter()
        ).run_inert_rehearsal()
        creates = [
            event
            for event in report["events"]
            if event["stage"] in {STAGES[2], STAGES[5]} and event["state"] == "completed"
        ]
        self.assertTrue(all(event["response_shape"] == "array" for event in creates))
        self.assertNotIn("hidden", json.dumps(report))

    def test_lost_create_response_is_resolved_by_authoritative_readback(self):
        class LostResponseAdapter(InertDiagnosticAdapter):
            def projection_create(self, role):
                self.created.add(role)
                if role == "owner":
                    raise AmbiguousTransportError("response_lost")
                return super().projection_create(role)

        report = ActivationDiagnostic(
            packet_identity="PACKET-LOST-RESPONSE", adapter=LostResponseAdapter()
        ).run_inert_rehearsal()
        owner_create = [
            event
            for event in report["events"]
            if event["stage"] == STAGES[2] and event["state"] == "failed"
        ]
        owner_readback = [
            event
            for event in report["events"]
            if event["stage"] == STAGES[3] and event["state"] == "completed"
        ]
        self.assertEqual(owner_create[0]["failure_class"], "create_response_ambiguous")
        self.assertEqual(owner_readback[0]["readback_outcome"], "verified")

    def test_partial_projection_failure_rolls_back(self):
        adapter = InertDiagnosticAdapter(failure_stage=STAGES[5])
        diagnostic = ActivationDiagnostic(packet_identity="PACKET-PARTIAL", adapter=adapter)
        with self.assertRaises(RuntimeError):
            diagnostic.run_inert_rehearsal()
        self.assertEqual(adapter.created, set())
        self.assertFalse(adapter.workflow_updated)

    def test_nonexception_unsafe_outcomes_fail_closed(self):
        cases = (
            (STAGES[1], "conflict"),
            (STAGES[3], "unavailable"),
            (STAGES[4], "conflict"),
            (STAGES[6], "unavailable"),
            (STAGES[9], "unavailable"),
            (STAGES[11], "conflict"),
            (STAGES[12], "unavailable"),
            (STAGES[13], "available"),
        )
        for target_stage, unsafe_outcome in cases:
            with self.subTest(stage=target_stage, outcome=unsafe_outcome):
                class OutcomeAdapter(InertDiagnosticAdapter):
                    def _result(self, stage, outcome, response=None):
                        result = super()._result(stage, outcome, response)
                        if stage == target_stage:
                            result["outcome"] = unsafe_outcome
                        return result

                adapter = OutcomeAdapter()
                diagnostic = ActivationDiagnostic(
                    packet_identity=f"PACKET-OUTCOME-{STAGES.index(target_stage)}",
                    adapter=adapter,
                )
                with self.assertRaises(RuntimeError):
                    diagnostic.run_inert_rehearsal()
                failed = [event for event in diagnostic.events if event.state == "failed"]
                self.assertTrue(failed)
                self.assertEqual(failed[-1].stage, target_stage)
                self.assertFalse(adapter.workflow_updated)

    def test_rejected_http_status_fails_and_rolls_back(self):
        class HttpAdapter(InertDiagnosticAdapter):
            def workflow_update(self):
                result = super().workflow_update()
                result["http_status"] = 409
                return result

        adapter = HttpAdapter()
        with self.assertRaisesRegex(RuntimeError, "workflow_update_rejected"):
            ActivationDiagnostic(
                packet_identity="PACKET-HTTP", adapter=adapter
            ).run_inert_rehearsal()
        self.assertFalse(adapter.workflow_updated)

    def test_definitive_create_rejections_do_not_continue_to_readback(self):
        for rejected_status in (401, 403, 409):
            with self.subTest(status=rejected_status):
                class RejectedCreateAdapter(InertDiagnosticAdapter):
                    readback_called = False

                    def projection_create(self, role):
                        return {
                            "http_status": rejected_status,
                            "outcome": "conflict",
                            "response": {"error": "redacted"},
                        }

                    def projection_readback(self, role):
                        self.readback_called = True
                        return super().projection_readback(role)

                adapter = RejectedCreateAdapter()
                with self.assertRaisesRegex(
                    RuntimeError, "create_response_ambiguous"
                ):
                    ActivationDiagnostic(
                        packet_identity=f"PACKET-REJECT-{rejected_status}",
                        adapter=adapter,
                    ).run_inert_rehearsal()
                self.assertFalse(adapter.readback_called)

    def test_raised_http_create_rejections_do_not_continue_to_readback(self):
        for rejected_status in (401, 403, 409):
            with self.subTest(status=rejected_status):
                class RaisedHttpAdapter(InertDiagnosticAdapter):
                    readback_called = False

                    def projection_create(self, role):
                        raise urllib.error.HTTPError(
                            "https://n8n.invalid",
                            rejected_status,
                            "rejected",
                            {},
                            None,
                        )

                    def projection_readback(self, role):
                        self.readback_called = True
                        return super().projection_readback(role)

                adapter = RaisedHttpAdapter()
                with self.assertRaises(urllib.error.HTTPError):
                    ActivationDiagnostic(
                        packet_identity=f"PACKET-HTTP-RAISED-{rejected_status}",
                        adapter=adapter,
                    ).run_inert_rehearsal()
                self.assertFalse(adapter.readback_called)

    def test_nontransport_create_exception_stops_immediately(self):
        class ProgrammerErrorAdapter(InertDiagnosticAdapter):
            readback_called = False

            def projection_create(self, role):
                raise ValueError("programmer_error")

            def projection_readback(self, role):
                self.readback_called = True
                return super().projection_readback(role)

        adapter = ProgrammerErrorAdapter()
        with self.assertRaisesRegex(ValueError, "programmer_error"):
            ActivationDiagnostic(
                packet_identity="PACKET-PROGRAMMER-ERROR", adapter=adapter
            ).run_inert_rehearsal()
        self.assertFalse(adapter.readback_called)

    def test_missing_outcome_never_inherits_expected_success(self):
        representative_stages = (STAGES[0], STAGES[3], STAGES[9], STAGES[11], STAGES[13])
        for target_stage in representative_stages:
            with self.subTest(stage=target_stage):
                class MissingOutcomeAdapter(InertDiagnosticAdapter):
                    def _result(self, stage, outcome, response=None):
                        result = super()._result(stage, outcome, response)
                        if stage == target_stage:
                            result.pop("outcome", None)
                        return result

                with self.assertRaises(RuntimeError):
                    ActivationDiagnostic(
                        packet_identity=f"PACKET-MISSING-{STAGES.index(target_stage)}",
                        adapter=MissingOutcomeAdapter(),
                    ).run_inert_rehearsal()

    def test_ambiguous_create_outcome_requires_verified_readback(self):
        class AmbiguousAdapter(InertDiagnosticAdapter):
            def projection_create(self, role):
                result = super().projection_create(role)
                if role == "owner":
                    result["outcome"] = "unavailable"
                    result["http_status"] = 202
                return result

        report = ActivationDiagnostic(
            packet_identity="PACKET-AMBIGUOUS", adapter=AmbiguousAdapter()
        ).run_inert_rehearsal()
        owner_create = [
            event
            for event in report["events"]
            if event["stage"] == STAGES[2] and event["state"] == "failed"
        ]
        owner_readback = [
            event
            for event in report["events"]
            if event["stage"] == STAGES[3] and event["state"] == "completed"
        ]
        self.assertEqual(owner_create[0]["readback_outcome"], "unavailable")
        self.assertEqual(owner_readback[0]["readback_outcome"], "verified")

    def test_rollback_failure_is_explicit(self):
        adapter = InertDiagnosticAdapter(failure_stage=STAGES[11])
        adapter.rollback_verified = False
        with self.assertRaisesRegex(RuntimeError, "rollback_unverified"):
            ActivationDiagnostic(
                packet_identity="PACKET-ROLLBACK", adapter=adapter
            ).run_inert_rehearsal()

    def test_each_stage_failure_is_sanitized_and_bounded(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                adapter = InertDiagnosticAdapter(failure_stage=stage)
                diagnostic = ActivationDiagnostic(
                    packet_identity=f"PACKET-{STAGES.index(stage)}", adapter=adapter
                )
                with self.assertRaises(RuntimeError):
                    diagnostic.run_inert_rehearsal()
                failed = [event for event in diagnostic.events if event.state == "failed"]
                self.assertEqual(len(failed), 1)
                self.assertIn(failed[0].failure_class, {
                    "capability_unavailable",
                    "projection_conflict",
                    "create_response_ambiguous",
                    "authoritative_readback_missing",
                    "workflow_preread_unavailable",
                    "workflow_construction_failed",
                    "workflow_validation_failed",
                    "workflow_update_rejected",
                    "workflow_readback_mismatch",
                    "telegram_trigger_count_mismatch",
                    "render_preflight_mismatch",
                })

    def test_workflow_hash_mismatch_fails_and_rolls_back(self):
        adapter = InertDiagnosticAdapter(failure_stage=STAGES[11])
        diagnostic = ActivationDiagnostic(packet_identity="PACKET-HASH", adapter=adapter)
        with self.assertRaises(RuntimeError):
            diagnostic.run_inert_rehearsal()
        self.assertFalse(adapter.workflow_updated)

    def test_loss_of_active_state_fails_closed(self):
        adapter = InertDiagnosticAdapter(failure_stage=STAGES[12])
        with self.assertRaises(RuntimeError):
            ActivationDiagnostic(
                packet_identity="PACKET-INACTIVE", adapter=adapter
            ).run_inert_rehearsal()

    def test_extra_trigger_fails_closed(self):
        class TriggerAdapter(InertDiagnosticAdapter):
            def verify_active_trigger(self):
                raise RuntimeError("telegram_trigger_count_mismatch")

        with self.assertRaises(RuntimeError):
            ActivationDiagnostic(
                packet_identity="PACKET-TRIGGER", adapter=TriggerAdapter()
            ).run_inert_rehearsal()

    def test_diagnostic_hash_replays_exactly(self):
        first = inert_rehearsal_report("PACKET-REPLAY")
        second = inert_rehearsal_report("PACKET-REPLAY")
        self.assertEqual(first["diagnostic_sha256"], second["diagnostic_sha256"])


if __name__ == "__main__":
    unittest.main()
