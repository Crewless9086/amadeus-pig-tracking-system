from datetime import datetime, timezone
import unittest

from scripts.beacon_private_photo_activation import (
    BeaconActivationCallbacks,
    BoundedBeaconPhotoActivation,
    verify_containment_invariants,
    verify_pre_enable_invariants,
)
from scripts.beacon_render_activation import RenderActivationCoordinator


REVISION = "c" * 40
NOW = datetime(2026, 7, 29, 15, 0, tzinfo=timezone.utc)


class RenderProvider:
    def __init__(self, deploy_states):
        self.deploy_states = {
            deploy_id: list(states) for deploy_id, states in deploy_states.items()
        }
        self.created = []
        self.canceled = []
        self.sequence = list(deploy_states)
        self.current = ""

    def list_deploys(self):
        rows = [{
            "id": "baseline",
            "status": "live",
            "commit": {"id": REVISION},
            "createdAt": "2026-07-29T14:00:00+00:00",
        }]
        rows.extend({
            "id": deploy_id,
            "status": states[min(0, len(states) - 1)]["status"],
            "commit": {"id": REVISION},
            "createdAt": "2026-07-29T15:00:01+00:00",
        } for deploy_id, states in self.deploy_states.items() if deploy_id in self.created)
        return rows

    def create_deploy(self, _payload):
        deploy_id = self.sequence[len(self.created)]
        self.created.append(deploy_id)
        self.current = deploy_id
        return 201, {"id": deploy_id}

    def get_deploy(self, deploy_id):
        states = self.deploy_states[deploy_id]
        row = states.pop(0) if len(states) > 1 else states[0]
        return {
            "id": deploy_id,
            "commit": {"id": REVISION},
            "createdAt": "2026-07-29T15:00:01+00:00",
            **row,
        }

    def cancel_deploy(self, deploy_id):
        self.canceled.append(deploy_id)
        return 202, {}

    def coordinator(self):
        return RenderActivationCoordinator(
            list_deploys=self.list_deploys,
            create_deploy=self.create_deploy,
            get_deploy=self.get_deploy,
            cancel_deploy=self.cancel_deploy,
            now=lambda: NOW,
            sleep=lambda _seconds: None,
        )


class Mutations:
    def __init__(self, *, ready=True):
        self.calls = {}
        self.ready = ready

    def call(self, name, result):
        def callback(*_args):
            self.calls[name] = self.calls.get(name, 0) + 1
            return result
        return callback

    def callbacks(self):
        topology = {
            "telegram_trigger_count": 1,
            "ordinary_oom_route_present": True,
            "sam_callback_present": True,
            "herdmaster_ordinary_route_preserved": True,
        }
        pre_enable_evidence = {
            **topology,
            "pending_updates": 0,
            "key_specific_config_readback_verified": True,
            "canonical_workflow_hash_verified": True,
            "stable_revision_bound": True,
        }
        containment_evidence = {
            **topology,
            "intake_enabled": False,
            "projections_absent": True,
            "exact_config_restored": True,
            "baseline_workflow_hash_verified": True,
            "pending_updates": 0,
            "no_transient_deployments": True,
            "latest_stable_revision_bound": True,
        }
        return BeaconActivationCallbacks(
            apply_key_specific_config=self.call(
                "config_apply", {"changed_keys": 2, "unrelated_drift": False}
            ),
            create_projection_pair=self.call(
                "projection_create", {"pair_verified": True, "created_count": 2}
            ),
            put_canonical_workflow=self.call(
                "workflow_put", {**topology, "put_safe": True}
            ),
            verify_pre_enable=self.call(
                "pre_enable", verify_pre_enable_invariants(pre_enable_evidence)
            ),
            enable_intake_flag=self.call(
                "flag_enable", {"changed_key": "BEACON_TELEGRAM_MEDIA_INTAKE_ENABLED"}
            ),
            verify_ready=self.call("verify_ready", self.ready),
            restore_exact_config=self.call(
                "config_restore", {"exact_prior_values": True}
            ),
            restore_canonical_workflow=self.call(
                "workflow_restore", {**topology, "baseline_hash_verified": True}
            ),
            remove_attributable_projections=self.call(
                "projection_remove", {"projections_absent": True}
            ),
            verify_contained=self.call(
                "verify_contained",
                verify_containment_invariants(containment_evidence),
            ),
        )


class BeaconPrivatePhotoActivationTests(unittest.TestCase):
    def test_success_invokes_each_mutation_once_and_preserves_routes(self):
        provider = RenderProvider({"activation": [{"status": "live"}]})
        mutations = Mutations(ready=True)
        runner = BoundedBeaconPhotoActivation(
            expected_revision=REVISION,
            render=provider.coordinator(),
            callbacks=mutations.callbacks(),
        )
        result = runner.execute()
        self.assertEqual(result["status"], "beacon_activation_verified")
        self.assertEqual(provider.created, ["activation"])
        self.assertEqual(result["mutation_counts"]["workflow_put"], 1)
        self.assertEqual(result["mutation_counts"]["projection_create"], 1)
        self.assertEqual(result["mutation_counts"]["flag_enable"], 1)
        self.assertNotIn("config_restore", mutations.calls)

    def test_verification_mismatch_rolls_back_in_exact_order_once(self):
        provider = RenderProvider({
            "activation": [{"status": "live"}],
            "rollback": [{"status": "live"}],
        })
        mutations = Mutations(ready=False)
        runner = BoundedBeaconPhotoActivation(
            expected_revision=REVISION,
            render=provider.coordinator(),
            callbacks=mutations.callbacks(),
        )
        result = runner.execute()
        self.assertEqual(result["status"], "beacon_activation_failed_contained")
        self.assertEqual(provider.created, ["activation", "rollback"])
        for name in (
            "config_apply", "projection_create", "workflow_put", "flag_enable",
            "config_restore", "workflow_restore", "projection_remove",
        ):
            self.assertEqual(mutations.calls[name], 1, name)
        self.assertEqual(mutations.calls["verify_contained"], 1)
        self.assertEqual(result["mutation_counts"]["rollback_deploy"], 1)

    def test_delayed_activation_success_does_not_duplicate_protected_mutations(self):
        provider = RenderProvider({
            "activation": [
                {"status": "queued"},
                {"status": "build_in_progress"},
                {"status": "live"},
            ]
        })
        mutations = Mutations(ready=True)
        result = BoundedBeaconPhotoActivation(
            expected_revision=REVISION,
            render=provider.coordinator(),
            callbacks=mutations.callbacks(),
        ).execute()
        self.assertEqual(result["status"], "beacon_activation_verified")
        self.assertEqual(provider.created, ["activation"])
        self.assertEqual(mutations.calls["projection_create"], 1)
        self.assertEqual(mutations.calls["workflow_put"], 1)

    def test_false_pre_enable_invariant_blocks_flag_and_deploy_then_contains(self):
        provider = RenderProvider({"rollback": [{"status": "live"}]})
        mutations = Mutations(ready=True)
        callbacks = mutations.callbacks()
        callbacks = BeaconActivationCallbacks(
            **{
                **callbacks.__dict__,
                "verify_pre_enable": mutations.call("pre_enable_failed", False),
            }
        )
        result = BoundedBeaconPhotoActivation(
            expected_revision=REVISION,
            render=provider.coordinator(),
            callbacks=callbacks,
        ).execute()
        self.assertEqual(result["status"], "beacon_activation_failed_contained")
        self.assertNotIn("flag_enable", mutations.calls)
        self.assertEqual(provider.created, ["rollback"])
        self.assertEqual(mutations.calls["workflow_restore"], 1)
        self.assertEqual(mutations.calls["projection_remove"], 1)

    def test_pre_enable_exception_blocks_flag_and_deploy_then_contains(self):
        provider = RenderProvider({"rollback": [{"status": "live"}]})
        mutations = Mutations(ready=True)
        callbacks = mutations.callbacks()

        def fail_pre_enable():
            raise ConnectionError()

        callbacks = BeaconActivationCallbacks(
            **{**callbacks.__dict__, "verify_pre_enable": fail_pre_enable}
        )
        result = BoundedBeaconPhotoActivation(
            expected_revision=REVISION,
            render=provider.coordinator(),
            callbacks=callbacks,
        ).execute()
        self.assertEqual(result["status"], "beacon_activation_failed_contained")
        self.assertNotIn("flag_enable", mutations.calls)
        self.assertEqual(provider.created, ["rollback"])

    def test_invariant_verifiers_reject_route_and_containment_drift(self):
        self.assertFalse(verify_pre_enable_invariants({
            "telegram_trigger_count": 2,
            "pending_updates": 0,
            "ordinary_oom_route_present": True,
            "sam_callback_present": True,
            "herdmaster_ordinary_route_preserved": True,
            "key_specific_config_readback_verified": True,
            "canonical_workflow_hash_verified": True,
            "stable_revision_bound": True,
        }))
        self.assertFalse(verify_containment_invariants({
            "intake_enabled": False,
            "projections_absent": True,
            "exact_config_restored": True,
            "baseline_workflow_hash_verified": True,
            "telegram_trigger_count": 1,
            "pending_updates": 0,
            "ordinary_oom_route_present": False,
            "sam_callback_present": True,
            "herdmaster_ordinary_route_preserved": True,
            "no_transient_deployments": True,
            "latest_stable_revision_bound": True,
        }))


if __name__ == "__main__":
    unittest.main()
