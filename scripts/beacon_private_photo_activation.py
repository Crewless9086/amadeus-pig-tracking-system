"""Source-controlled bounded BEACON private-photo activation orchestration.

This module contains no credentials or live identities. Production callers
must inject key-specific Render, canonical n8n, Telegram freshness, and
authoritative verification adapters after acquiring the serialized lane.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from scripts.beacon_render_activation import (
    ActivationContainmentError,
    RenderActivationCoordinator,
    run_with_deterministic_rollback,
)


def verify_pre_enable_invariants(evidence: dict[str, Any]) -> bool:
    return bool(
        evidence.get("telegram_trigger_count") == 1
        and evidence.get("pending_updates") == 0
        and evidence.get("ordinary_oom_route_present") is True
        and evidence.get("sam_callback_present") is True
        and evidence.get("herdmaster_ordinary_route_preserved") is True
        and evidence.get("key_specific_config_readback_verified") is True
        and evidence.get("canonical_workflow_hash_verified") is True
        and evidence.get("stable_revision_bound") is True
    )


def verify_containment_invariants(evidence: dict[str, Any]) -> bool:
    return bool(
        evidence.get("intake_enabled") is False
        and evidence.get("projections_absent") is True
        and evidence.get("exact_config_restored") is True
        and evidence.get("baseline_workflow_hash_verified") is True
        and evidence.get("telegram_trigger_count") == 1
        and evidence.get("pending_updates") == 0
        and evidence.get("ordinary_oom_route_present") is True
        and evidence.get("sam_callback_present") is True
        and evidence.get("herdmaster_ordinary_route_preserved") is True
        and evidence.get("no_transient_deployments") is True
        and evidence.get("latest_stable_revision_bound") is True
    )


@dataclass(frozen=True)
class BeaconActivationCallbacks:
    apply_key_specific_config: Callable[[], dict[str, Any]]
    create_projection_pair: Callable[[], dict[str, Any]]
    put_canonical_workflow: Callable[[], dict[str, Any]]
    verify_pre_enable: Callable[[], bool]
    enable_intake_flag: Callable[[], dict[str, Any]]
    verify_ready: Callable[[dict[str, Any]], bool]
    restore_exact_config: Callable[[], dict[str, Any]]
    restore_canonical_workflow: Callable[[], dict[str, Any]]
    remove_attributable_projections: Callable[[], dict[str, Any]]
    verify_contained: Callable[[dict[str, Any]], bool]


class BoundedBeaconPhotoActivation:
    """Executes each protected mutation at most once per bounded attempt."""

    def __init__(
        self,
        *,
        expected_revision: str,
        render: RenderActivationCoordinator,
        callbacks: BeaconActivationCallbacks,
    ):
        self.expected_revision = expected_revision
        self.render = render
        self.callbacks = callbacks
        self.counts = {
            "config_apply": 0,
            "projection_create": 0,
            "workflow_put": 0,
            "flag_enable": 0,
            "activation_deploy": 0,
            "config_restore": 0,
            "rollback_deploy": 0,
            "workflow_restore": 0,
            "projection_remove": 0,
        }

    def _once(self, key: str, callback: Callable[[], dict[str, Any]]):
        if self.counts[key] != 0:
            raise RuntimeError(f"beacon_activation_stage_reentry:{key}")
        self.counts[key] += 1
        return callback()

    def activate(self) -> dict[str, Any]:
        self._once(
            "config_apply", self.callbacks.apply_key_specific_config
        )
        self._once(
            "projection_create", self.callbacks.create_projection_pair
        )
        self._once(
            "workflow_put", self.callbacks.put_canonical_workflow
        )
        pre_enable = self.callbacks.verify_pre_enable()
        if pre_enable is not True:
            raise RuntimeError("beacon_pre_enable_verification_failed")
        self._once("flag_enable", self.callbacks.enable_intake_flag)
        self.counts["activation_deploy"] += 1
        deployment = self.render.deploy_exact_revision(
            expected_revision=self.expected_revision
        )
        return {
            "deployment_id": deployment["deploy_id"],
            "revision": deployment["revision"],
            "status": deployment["status"],
            "pre_enable_verified": True,
            "raw_callback_content_retained": False,
            "mutation_counts": dict(self.counts),
        }

    def rollback(self) -> dict[str, Any]:
        errors = []
        restored_config = None
        rollback_deployment = None
        restored_workflow = None
        removed_projections = None
        try:
            restored_config = self._once(
                "config_restore", self.callbacks.restore_exact_config
            )
        except Exception as exc:
            errors.append(("config_restore", exc.__class__.__name__))
        if restored_config is not None:
            try:
                self.counts["rollback_deploy"] += 1
                rollback_deployment = self.render.deploy_exact_revision(
                    expected_revision=self.expected_revision
                )
            except Exception as exc:
                errors.append(("rollback_deploy", exc.__class__.__name__))
        try:
            restored_workflow = self._once(
                "workflow_restore", self.callbacks.restore_canonical_workflow
            )
        except Exception as exc:
            errors.append(("workflow_restore", exc.__class__.__name__))
        try:
            removed_projections = self._once(
                "projection_remove", self.callbacks.remove_attributable_projections
            )
        except Exception as exc:
            errors.append(("projection_remove", exc.__class__.__name__))
        if errors:
            raise ActivationContainmentError(
                {
                    "failed_stage_count": len(errors),
                    "failed_stages": [stage for stage, _error in errors],
                    "error_types": [error for _stage, error in errors],
                    "mutation_counts": dict(self.counts),
                    "raw_provider_content_retained": False,
                }
            )
        return {
            "rollback_deployment_id": rollback_deployment["deploy_id"],
            "revision": rollback_deployment["revision"],
            "config_restored": restored_config is not None,
            "workflow_restored": restored_workflow is not None,
            "projections_removed": removed_projections is not None,
            "raw_callback_content_retained": False,
            "mutation_counts": dict(self.counts),
        }

    def execute(self) -> dict[str, Any]:
        result = run_with_deterministic_rollback(
            activate=self.activate,
            verify_activation=self.callbacks.verify_ready,
            rollback=self.rollback,
            verify_containment=self.callbacks.verify_contained,
        )
        return {**result, "mutation_counts": dict(self.counts)}
