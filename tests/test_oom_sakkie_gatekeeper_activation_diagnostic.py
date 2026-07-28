import json
import unittest
import urllib.error

from scripts.oom_sakkie_gatekeeper_activation_diagnostic import (
    STAGES,
    ActivationDiagnostic,
    AmbiguousTransportError,
    InertDiagnosticAdapter,
    StageEvidence,
    deterministic_request_identity,
    inert_rehearsal_report,
    response_shape,
)


class GateKeeperActivationDiagnosticTests(unittest.TestCase):
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
