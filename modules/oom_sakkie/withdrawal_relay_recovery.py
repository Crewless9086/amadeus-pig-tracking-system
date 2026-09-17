"""Pure coordination contract for one preserved withdrawal relay incident.

This module performs no I/O.  It classifies supplied evidence and produces
only a gated recovery instruction; it cannot read n8n, send Telegram, call the
gateway, or record a farm fact.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import re


PRESERVED_GATEKEEPER_EXECUTION_ID = "61267"
PRESERVED_RELAY_EXECUTION_ID = "61268"
APPROVED_GATEWAY_ORIGIN = (
    "https://amadeus-pig-tracking-system.onrender.com"
)
REVIEWED_BUILD_JS_SHA256 = (
    "7b591a67b0274b015863b1c51e281d1b419b93484dc3e11b869acce5fa64e146"
)
MAX_EVIDENCE_AGE = timedelta(minutes=10)


class IncidentCause(str, Enum):
    HISTORICAL_VALIDATION_FAILURE = "historical_validation_failure"
    VALIDATION_REGRESSION = "validation_regression"
    DEPLOYMENT_CONFIGURATION_MISMATCH = "deployment_configuration_mismatch"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class RelayIncidentEvidence:
    gatekeeper_execution_id: str
    relay_execution_id: str
    normalization_succeeded: bool
    relay_status: str
    relay_reported_transport_validation_error: bool
    current_gateway_origin: str
    current_origin_is_permitted: bool
    live_relay_matches_reviewed_source: bool
    live_relay_has_normalizer: bool
    live_relay_has_safe_diagnostic: bool
    render_gateway_enabled: bool
    render_gateway_token_present: bool
    render_allowed_owner_present: bool
    sam_autonomy_level: str
    sam_level1_live_stock_enabled: bool
    sam_level1_cohort_enabled: bool
    observed_at: datetime
    live_build_js_sha256: str
    reviewed_build_js_sha256: str
    render_commit: str
    reviewed_render_commit: str
    authenticated_owner_identity_sha256: str
    configured_owner_identity_sha256: str


class ReplayGuardState(str, Enum):
    ACQUIRED = "acquired"
    CONSUMED = "consumed"


@dataclass(frozen=True)
class ReplayGuard:
    replay_key: str
    message_sha256: str
    owner_identity_sha256: str
    acquisition_receipt: str
    state: ReplayGuardState


@dataclass(frozen=True)
class RecoveryAuthority:
    serialized_lane_released: bool = False
    exact_executions_preserved: bool = False
    preserved_message_sha256: str = ""
    recovery_message_sha256: str = ""
    reviewed_relay_deployed: bool = False
    exact_gateway_configuration_ready: bool = False
    replay_guard: ReplayGuard | None = None
    required_render_commit: str = ""
    expected_owner_identity_sha256: str = ""


@dataclass(frozen=True)
class RecoveryInstruction:
    ready: bool
    next_action: str
    may_recover_preserved_message: bool
    may_send_one_canonical_preview: bool
    may_record_farm_or_medical_fact: bool
    may_notify_sam: bool
    confirmation_required_after_preview: bool
    replay_key: str


def classify_incident(evidence: RelayIncidentEvidence) -> tuple[IncidentCause, ...]:
    """Label a supplied observation; this function grants no authority."""
    if not _identifies_preserved_incident(evidence):
        return (IncidentCause.INSUFFICIENT_EVIDENCE,)
    if not (
        evidence.normalization_succeeded is True
        and evidence.relay_status == "relay_env_not_ready"
        and evidence.relay_reported_transport_validation_error is True
    ):
        return (IncidentCause.INSUFFICIENT_EVIDENCE,)

    causes: list[IncidentCause] = []
    causes.append(IncidentCause.HISTORICAL_VALIDATION_FAILURE)
    if not (
        evidence.live_relay_matches_reviewed_source is True
        and evidence.live_relay_has_normalizer is True
        and evidence.live_relay_has_safe_diagnostic is True
    ):
        causes.append(IncidentCause.VALIDATION_REGRESSION)
    if not (
        evidence.render_gateway_enabled is True
        and evidence.render_gateway_token_present is True
        and evidence.render_allowed_owner_present is True
    ):
        causes.append(IncidentCause.DEPLOYMENT_CONFIGURATION_MISMATCH)
    return tuple(causes) or (IncidentCause.INSUFFICIENT_EVIDENCE,)


def prepare_recovery_instruction(
    evidence: RelayIncidentEvidence,
    authority: RecoveryAuthority,
    *,
    now: datetime,
) -> RecoveryInstruction:
    """Return a fail-closed, exact-once recovery instruction."""
    replay_key = (
        f"gatekeeper:{evidence.gatekeeper_execution_id}/"
        f"relay:{evidence.relay_execution_id}/withdrawal-preview:v1"
    )
    preserved = _has_preserved_failure_signature(evidence)
    guard = authority.replay_guard
    runtime_ready = (
        _strict_true(authority.serialized_lane_released)
        and _strict_true(authority.exact_executions_preserved)
        and _is_sha256(authority.preserved_message_sha256)
        and authority.preserved_message_sha256
        == authority.recovery_message_sha256
        and _strict_true(authority.reviewed_relay_deployed)
        and _strict_true(authority.exact_gateway_configuration_ready)
        and isinstance(guard, ReplayGuard)
        and guard.replay_key == replay_key
        and guard.message_sha256 == authority.preserved_message_sha256
        and guard.owner_identity_sha256
        == evidence.authenticated_owner_identity_sha256
        and bool(guard.acquisition_receipt)
        and guard.state is ReplayGuardState.ACQUIRED
        and preserved
        and _is_fresh(evidence.observed_at, now)
        and evidence.current_gateway_origin == APPROVED_GATEWAY_ORIGIN
        and _strict_true(evidence.current_origin_is_permitted)
        and _strict_true(evidence.live_relay_matches_reviewed_source)
        and _strict_true(evidence.live_relay_has_normalizer)
        and _strict_true(evidence.live_relay_has_safe_diagnostic)
        and evidence.live_build_js_sha256 == REVIEWED_BUILD_JS_SHA256
        and evidence.reviewed_build_js_sha256 == REVIEWED_BUILD_JS_SHA256
        and _is_git_commit(authority.required_render_commit)
        and evidence.render_commit == authority.required_render_commit
        and evidence.reviewed_render_commit == authority.required_render_commit
        and _strict_true(evidence.render_gateway_enabled)
        and _strict_true(evidence.render_gateway_token_present)
        and _strict_true(evidence.render_allowed_owner_present)
        and _is_sha256(authority.expected_owner_identity_sha256)
        and evidence.authenticated_owner_identity_sha256
        == authority.expected_owner_identity_sha256
        and evidence.configured_owner_identity_sha256
        == authority.expected_owner_identity_sha256
        and guard.owner_identity_sha256
        == authority.expected_owner_identity_sha256
        and evidence.sam_autonomy_level == "0"
        and evidence.sam_level1_live_stock_enabled is False
        and evidence.sam_level1_cohort_enabled is False
    )
    if runtime_ready:
        action = (
            "Recover the preserved normalized input exactly once under the "
            "replay key, then send one canonical withdrawal preview to Charl "
            "for explicit confirmation."
        )
    else:
        action = (
            "Keep executions 61267/61268 and the original message immutable; "
            "perform no replay, Telegram send, or farm/medical recording."
        )
    return RecoveryInstruction(
        ready=runtime_ready,
        next_action=action,
        may_recover_preserved_message=runtime_ready,
        may_send_one_canonical_preview=runtime_ready,
        may_record_farm_or_medical_fact=False,
        may_notify_sam=False,
        confirmation_required_after_preview=True,
        replay_key=replay_key,
    )


def _identifies_preserved_incident(evidence: RelayIncidentEvidence) -> bool:
    return (
        evidence.gatekeeper_execution_id
        == PRESERVED_GATEKEEPER_EXECUTION_ID
        and evidence.relay_execution_id == PRESERVED_RELAY_EXECUTION_ID
    )


def _has_preserved_failure_signature(evidence: RelayIncidentEvidence) -> bool:
    return (
        _identifies_preserved_incident(evidence)
        and evidence.normalization_succeeded is True
        and evidence.relay_status == "relay_env_not_ready"
        and evidence.relay_reported_transport_validation_error is True
    )


def _is_fresh(observed_at: datetime, now: datetime) -> bool:
    if not isinstance(observed_at, datetime) or not isinstance(now, datetime):
        return False
    if observed_at.tzinfo is None or now.tzinfo is None:
        return False
    age = now.astimezone(timezone.utc) - observed_at.astimezone(timezone.utc)
    return timedelta(0) <= age <= MAX_EVIDENCE_AGE


def _strict_true(value: object) -> bool:
    return value is True


def _is_sha256(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "")))


def _is_git_commit(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{40}", str(value or "")))
