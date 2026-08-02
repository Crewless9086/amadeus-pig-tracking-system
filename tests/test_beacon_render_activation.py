from datetime import datetime, timedelta, timezone
import unittest

from scripts.beacon_render_activation import (
    ActivationContainmentError,
    ActivationDeployError,
    RenderActivationCoordinator,
    run_with_deterministic_rollback,
)


REVISION = "a" * 40
BASE_TIME = datetime(2026, 7, 29, 15, 0, tzinfo=timezone.utc)


def row(deploy_id, status, *, revision=REVISION, seconds=0):
    return {
        "id": deploy_id,
        "status": status,
        "commit": {"id": revision},
        "createdAt": (BASE_TIME + timedelta(seconds=seconds)).isoformat(),
    }


class Provider:
    def __init__(self, *, create_result=None, create_error=None, lists=None, states=None):
        self.create_result = create_result
        self.create_error = create_error
        self.lists = list(lists or [[row("baseline", "live", seconds=-100)]])
        self.states = list(states or [])
        self.create_calls = 0
        self.list_calls = 0
        self.get_calls = 0
        self.cancel_calls = 0
        self.sleeps = []

    def list_deploys(self):
        index = min(self.list_calls, len(self.lists) - 1)
        self.list_calls += 1
        return self.lists[index]

    def create_deploy(self, payload):
        self.create_calls += 1
        self.last_payload = payload
        if self.create_error:
            raise self.create_error
        return self.create_result

    def get_deploy(self, _deploy_id):
        index = min(self.get_calls, len(self.states) - 1)
        self.get_calls += 1
        return self.states[index]

    def sleep(self, seconds):
        self.sleeps.append(seconds)

    def cancel_deploy(self, _deploy_id):
        self.cancel_calls += 1
        return 202, {}

    def coordinator(self):
        return RenderActivationCoordinator(
            list_deploys=self.list_deploys,
            create_deploy=self.create_deploy,
            get_deploy=self.get_deploy,
            cancel_deploy=self.cancel_deploy,
            now=lambda: BASE_TIME,
            sleep=self.sleep,
        )


class BeaconRenderActivationTests(unittest.TestCase):
    def test_success_before_timeout_uses_returned_deploy_identity_once(self):
        provider = Provider(
            create_result=(201, {"id": "new"}),
            states=[row("new", "live")],
        )
        result = provider.coordinator().deploy_exact_revision(
            expected_revision=REVISION,
            completion_polls=2,
        )
        self.assertEqual(result["status"], "live")
        self.assertEqual(result["mutation_attempts"], 1)
        self.assertEqual(provider.create_calls, 1)
        self.assertEqual(provider.last_payload["commitId"], REVISION)

    def test_delayed_success_polls_one_known_deploy_without_recreating(self):
        provider = Provider(
            create_result=(202, {"id": "new"}),
            states=[
                row("new", "queued"),
                row("new", "build_in_progress"),
                row("new", "live"),
            ],
        )
        result = provider.coordinator().deploy_exact_revision(
            expected_revision=REVISION,
            completion_polls=4,
            completion_poll_seconds=3,
        )
        self.assertEqual(result["deploy_id"], "new")
        self.assertEqual(provider.create_calls, 1)
        self.assertEqual(provider.sleeps, [3])

    def test_genuine_completion_timeout_is_bounded_and_not_retried(self):
        provider = Provider(
            create_result=(201, {"id": "new"}),
            states=[
                row("new", "build_in_progress"),
                row("new", "build_in_progress"),
                row("new", "build_in_progress"),
                row("new", "build_in_progress"),
                row("new", "canceled"),
            ],
        )
        with self.assertRaises(ActivationDeployError) as caught:
            provider.coordinator().deploy_exact_revision(
                expected_revision=REVISION,
                completion_polls=3,
                completion_poll_seconds=1,
            )
        self.assertEqual(caught.exception.status, "render_deployment_completion_timeout")
        self.assertEqual(provider.create_calls, 1)
        self.assertTrue(caught.exception.evidence["terminal_barrier_verified"])
        self.assertEqual(caught.exception.evidence["terminal_barrier_state"], "canceled")
        self.assertEqual(provider.cancel_calls, 1)

    def test_ambiguous_post_completion_is_reconciled_without_duplicate_create(self):
        provider = Provider(
            create_error=TimeoutError(),
            lists=[
                [row("baseline", "live", seconds=-100)],
                [row("new", "queued", seconds=1), row("baseline", "live", seconds=-100)],
            ],
            states=[row("new", "live", seconds=1)],
        )
        result = provider.coordinator().deploy_exact_revision(
            expected_revision=REVISION,
            acceptance_polls=2,
        )
        self.assertEqual(result["acceptance_source"], "provider_chronology_reconciliation")
        self.assertEqual(provider.create_calls, 1)

    def test_ambiguous_http_gateway_timeout_is_reconciled_without_retry(self):
        provider = Provider(
            create_result=(504, {}),
            lists=[
                [row("baseline", "live", seconds=-100)],
                [row("new", "queued", seconds=1), row("baseline", "live", seconds=-100)],
            ],
            states=[row("new", "live", seconds=1)],
        )
        result = provider.coordinator().deploy_exact_revision(
            expected_revision=REVISION,
            acceptance_polls=2,
        )
        self.assertEqual(result["acceptance_source"], "provider_chronology_reconciliation")
        self.assertEqual(provider.create_calls, 1)

    def test_wrapped_success_response_adopts_identity_without_reconciliation(self):
        provider = Provider(
            create_result=(201, {"deploy": {"id": "new"}}),
            states=[row("new", "live")],
        )
        result = provider.coordinator().deploy_exact_revision(
            expected_revision=REVISION
        )
        self.assertEqual(result["deploy_id"], "new")
        self.assertEqual(
            result["acceptance_source"], "create_response_authoritative_readback"
        )

    def test_provider_clock_precision_tolerance_accepts_new_nonbaseline_deploy(self):
        provider = Provider(
            create_error=TimeoutError(),
            lists=[
                [row("baseline", "live", seconds=-100)],
                [row("new", "queued", seconds=-2), row("baseline", "live", seconds=-100)],
            ],
            states=[row("new", "live", seconds=-2)],
        )
        result = provider.coordinator().deploy_exact_revision(
            expected_revision=REVISION,
            acceptance_polls=2,
            clock_skew_tolerance_seconds=5,
        )
        self.assertEqual(result["deploy_id"], "new")

    def test_stale_baseline_id_in_success_response_is_rejected(self):
        provider = Provider(
            create_result=(201, {"id": "baseline"}),
            states=[row("baseline", "live", seconds=-100)],
        )
        with self.assertRaises(ActivationDeployError) as caught:
            provider.coordinator().request_once(expected_revision=REVISION)
        self.assertEqual(caught.exception.status, "render_deploy_response_identity_stale")

    def test_late_live_activation_is_terminally_barriered_before_rollback(self):
        provider = Provider(
            create_result=(201, {"id": "new"}),
            states=[
                row("new", "build_in_progress"),
                row("new", "build_in_progress"),
                row("new", "live"),
            ],
        )
        with self.assertRaises(ActivationDeployError) as caught:
            provider.coordinator().deploy_exact_revision(
                expected_revision=REVISION,
                completion_polls=1,
                completion_poll_seconds=1,
            )
        self.assertEqual(caught.exception.status, "render_deployment_completion_timeout")
        self.assertEqual(caught.exception.evidence["terminal_barrier_state"], "live")
        self.assertTrue(caught.exception.evidence["terminal_barrier_verified"])

    def test_unsettled_activation_deploy_blocks_containment_claim(self):
        provider = Provider(
            create_result=(201, {"id": "new"}),
            states=[row("new", "build_in_progress")],
        )
        with self.assertRaises(ActivationDeployError) as caught:
            provider.coordinator().wait_until_live(
                provider.coordinator().request_once(expected_revision=REVISION),
                expected_revision=REVISION,
                completion_polls=1,
                terminalization_polls=2,
                poll_seconds=1,
            )
        self.assertEqual(caught.exception.status, "render_timed_out_deploy_unsettled")
        self.assertFalse(caught.exception.evidence["terminal_barrier_verified"])

    def test_ambiguous_post_with_no_provider_candidate_fails_without_retry(self):
        provider = Provider(
            create_error=ConnectionError(),
            lists=[[row("baseline", "live", seconds=-100)]],
        )
        with self.assertRaises(ActivationDeployError) as caught:
            provider.coordinator().request_once(
                expected_revision=REVISION,
                acceptance_polls=3,
                poll_seconds=1,
            )
        self.assertEqual(caught.exception.status, "render_deploy_acceptance_unresolved")
        self.assertFalse(caught.exception.evidence["mutation_retried"])
        self.assertEqual(provider.create_calls, 1)

    def test_multiple_provider_candidates_fail_closed_as_ambiguous(self):
        provider = Provider(
            create_error=TimeoutError(),
            lists=[
                [row("baseline", "live", seconds=-100)],
                [
                    row("new-2", "queued", seconds=2),
                    row("new-1", "queued", seconds=1),
                    row("baseline", "live", seconds=-100),
                ],
            ],
        )
        with self.assertRaises(ActivationDeployError) as caught:
            provider.coordinator().request_once(expected_revision=REVISION)
        self.assertEqual(caught.exception.status, "render_deploy_acceptance_ambiguous")
        self.assertEqual(provider.create_calls, 1)

    def test_provider_failure_is_distinct_from_timeout(self):
        provider = Provider(
            create_result=(201, {"id": "new"}),
            states=[row("new", "build_failed")],
        )
        with self.assertRaises(ActivationDeployError) as caught:
            provider.coordinator().deploy_exact_revision(expected_revision=REVISION)
        self.assertEqual(caught.exception.status, "render_deployment_failed")
        self.assertEqual(caught.exception.evidence["provider_status"], "build_failed")

    def test_revision_mismatch_blocks_even_if_provider_reports_live(self):
        provider = Provider(
            create_result=(201, {"id": "new"}),
            states=[row("new", "live", revision="b" * 40)],
        )
        with self.assertRaises(ActivationDeployError) as caught:
            provider.coordinator().deploy_exact_revision(expected_revision=REVISION)
        self.assertEqual(
            caught.exception.status, "render_deploy_response_identity_unverified"
        )

    def test_same_coordinator_is_reusable_for_deterministic_rollback_deploy(self):
        provider = Provider(
            create_result=(201, {"id": "rollback"}),
            states=[row("rollback", "live")],
        )
        result = provider.coordinator().deploy_exact_revision(expected_revision=REVISION)
        self.assertEqual(result["deploy_id"], "rollback")
        self.assertEqual(provider.create_calls, 1)

    def test_activation_failure_rolls_back_once_and_proves_containment(self):
        calls = {"rollback": 0}

        def fail_activation():
            raise TimeoutError()

        def rollback():
            calls["rollback"] += 1
            return {"flag": False, "projections_absent": True}

        result = run_with_deterministic_rollback(
            activate=fail_activation,
            verify_activation=lambda _result: False,
            rollback=rollback,
            verify_containment=lambda state: (
                state["flag"] is False and state["projections_absent"] is True
            ),
        )
        self.assertEqual(result["status"], "beacon_activation_failed_contained")
        self.assertTrue(result["containment_verified"])
        self.assertEqual(calls["rollback"], 1)

    def test_activation_verification_mismatch_is_preserved_and_contained(self):
        result = run_with_deterministic_rollback(
            activate=lambda: {"enabled": False},
            verify_activation=lambda state: state["enabled"],
            rollback=lambda: {"contained": True},
            verify_containment=lambda state: state["contained"],
        )
        self.assertEqual(
            result["activation_status"], "beacon_activation_verification_mismatch"
        )
        self.assertEqual(result["activation_evidence"]["activation_mutation_attempts"], 1)

    def test_containment_verification_exception_is_wrapped_fail_closed(self):
        with self.assertRaises(ActivationContainmentError) as caught:
            run_with_deterministic_rollback(
                activate=lambda: (_ for _ in ()).throw(TimeoutError()),
                verify_activation=lambda _state: False,
                rollback=lambda: {"contained": True},
                verify_containment=lambda _state: (_ for _ in ()).throw(
                    ConnectionError()
                ),
            )
        self.assertEqual(
            caught.exception.evidence["containment_error_type"], "ConnectionError"
        )

    def test_ambiguous_rollback_completion_never_claims_containment(self):
        calls = {"rollback": 0}

        def rollback():
            calls["rollback"] += 1
            raise ActivationDeployError(
                "render_deploy_acceptance_unresolved",
                {"mutation_retried": False},
            )

        with self.assertRaises(ActivationContainmentError) as caught:
            run_with_deterministic_rollback(
                activate=lambda: (_ for _ in ()).throw(TimeoutError()),
                verify_activation=lambda _result: False,
                rollback=rollback,
                verify_containment=lambda _state: False,
            )
        self.assertFalse(caught.exception.evidence["containment_verified"])
        self.assertEqual(caught.exception.evidence["rollback_attempts"], 1)
        self.assertEqual(calls["rollback"], 1)

    def test_unsettled_activation_deploy_blocks_rollback_race(self):
        calls = {"rollback": 0}

        def activate():
            raise ActivationDeployError(
                "render_timed_out_deploy_unsettled",
                {"terminal_barrier_verified": False},
            )

        def rollback():
            calls["rollback"] += 1
            return {}

        with self.assertRaises(ActivationContainmentError) as caught:
            run_with_deterministic_rollback(
                activate=activate,
                verify_activation=lambda _state: False,
                rollback=rollback,
                verify_containment=lambda _state: False,
            )
        self.assertTrue(
            caught.exception.evidence["unsafe_transient_deploy_unsettled"]
        )
        self.assertEqual(caught.exception.evidence["rollback_attempts"], 0)
        self.assertEqual(calls["rollback"], 0)

    def test_unresolved_ambiguous_create_blocks_rollback_race(self):
        calls = {"rollback": 0}

        def activate():
            raise ActivationDeployError(
                "render_deploy_acceptance_unresolved",
                {
                    "terminal_barrier_verified": False,
                    "ambiguous_create_unsettled": True,
                },
            )

        def rollback():
            calls["rollback"] += 1
            return {}

        with self.assertRaises(ActivationContainmentError) as caught:
            run_with_deterministic_rollback(
                activate=activate,
                verify_activation=lambda _state: False,
                rollback=rollback,
                verify_containment=lambda _state: False,
            )
        self.assertEqual(
            caught.exception.evidence["activation_status"],
            "render_deploy_acceptance_unresolved",
        )
        self.assertEqual(caught.exception.evidence["rollback_attempts"], 0)
        self.assertEqual(calls["rollback"], 0)

    def test_successful_activation_does_not_call_rollback(self):
        calls = {"rollback": 0}

        result = run_with_deterministic_rollback(
            activate=lambda: {"enabled": True},
            verify_activation=lambda state: state["enabled"],
            rollback=lambda: calls.__setitem__("rollback", 1),
            verify_containment=lambda _state: False,
        )
        self.assertEqual(result["status"], "beacon_activation_verified")
        self.assertFalse(result["rollback_performed"])
        self.assertEqual(calls["rollback"], 0)


if __name__ == "__main__":
    unittest.main()
