"""Privacy-safe GateKeeper activation diagnostics.

Production use is read-only. Administrative operations are represented by an
injectable adapter so the full contract can be rehearsed with inert state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Callable, Protocol


STAGES = (
    "n8n_capability_read",
    "owner_projection_preflight",
    "owner_projection_create_response",
    "owner_projection_authoritative_readback",
    "private_chat_projection_preflight",
    "private_chat_projection_create_response",
    "private_chat_projection_authoritative_readback",
    "live_workflow_preread",
    "merge_style_workflow_construction",
    "workflow_validation",
    "workflow_update_request",
    "workflow_authoritative_readback",
    "active_state_single_trigger_verification",
    "render_enablement_preflight",
)

SAFE_STATES = {"started", "completed", "failed", "not_run"}
SAFE_OUTCOMES = {
    "available",
    "absent",
    "accepted",
    "verified",
    "constructed",
    "valid",
    "matched",
    "ready_disabled",
    "rolled_back",
    "mutation_prohibited",
    "conflict",
    "unavailable",
}
SAFE_FAILURES = {
    "",
    "authentication_unavailable",
    "capability_unavailable",
    "projection_conflict",
    "create_response_ambiguous",
    "authoritative_readback_missing",
    "authoritative_readback_conflict",
    "workflow_preread_unavailable",
    "workflow_hash_mismatch",
    "workflow_construction_failed",
    "workflow_validation_failed",
    "workflow_update_rejected",
    "workflow_readback_mismatch",
    "workflow_inactive",
    "telegram_trigger_count_mismatch",
    "render_preflight_mismatch",
    "rollback_unverified",
    "diagnostic_internal_failure",
}
FORBIDDEN_KEYS = {
    "value",
    "token",
    "secret",
    "owner_id",
    "chat_id",
    "file_id",
    "media",
    "workflow",
    "headers",
    "body",
}
BEACON_MEDIA_INTAKE_ENABLED_ENV = "BEACON_TELEGRAM_MEDIA_INTAKE_ENABLED"
OOM_SAKKIE_DIRECT_ENABLED_ENV = "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED"
OOM_SAKKIE_DIRECT_SEND_ENABLED_ENV = "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED"


class AmbiguousTransportError(RuntimeError):
    """The request may have reached the provider but no response was proven."""


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def telegram_shared_flag_authority_contract(environ: dict[str, Any]) -> dict[str, Any]:
    """Classify shared OOM SAKKIE gates separately from BEACON's intake gate."""
    source = environ if isinstance(environ, dict) else {}
    beacon_enabled = _truthy(source.get(BEACON_MEDIA_INTAKE_ENABLED_ENV))
    direct_enabled = _truthy(source.get(OOM_SAKKIE_DIRECT_ENABLED_ENV))
    direct_send_enabled = _truthy(source.get(OOM_SAKKIE_DIRECT_SEND_ENABLED_ENV))
    shared_direct_ready = direct_enabled and direct_send_enabled
    preactivation_ready = not beacon_enabled and shared_direct_ready
    if beacon_enabled:
        status = "beacon_media_intake_already_enabled"
    elif not shared_direct_ready:
        status = "shared_oom_sakkie_direct_contract_unavailable"
    else:
        status = "beacon_media_intake_disabled_shared_routes_preserved"
    return {
        "status": status,
        "preactivation_ready": preactivation_ready,
        "beacon_media_intake": {
            "enabled": beacon_enabled,
            "required_state_before_activation": "disabled",
            "consumer": "beacon_media_intake_only",
        },
        "oom_sakkie_direct": {
            "enabled": direct_enabled,
            "required_shared_state": True,
            "consumers": [
                "direct_webhook_authentication_and_routing",
                "sam_owner_callback_handling",
                "ordinary_owner_text_handling",
            ],
        },
        "oom_sakkie_direct_send": {
            "enabled": direct_send_enabled,
            "required_shared_state": True,
            "consumers": [
                "owner_telegram_replies",
                "telegram_callback_acknowledgements",
                "bounded_beacon_owner_receipt_when_separately_enabled",
            ],
        },
        "beacon_activation_changes_shared_flags": False,
        "customer_messaging_authority": False,
        "publication_authority": False,
        "meta_authority": False,
        "advertising_authority": False,
        "boost_authority": False,
        "spend_authority": False,
    }


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def response_shape(value: Any) -> str:
    if value is None:
        return "empty"
    if isinstance(value, dict):
        return f"object:{len(value)}"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "unsupported"


def deterministic_request_identity(stage: str, safe_identity: dict[str, Any]) -> str:
    return "BEACON-GK-DIAG-" + canonical_sha256(
        {"version": 1, "stage": stage, "identity": safe_identity}
    )[:24].upper()


@dataclass(frozen=True)
class StageEvidence:
    sequence: int
    stage: str
    state: str
    request_identity: str
    http_status: int | None
    response_shape: str
    readback_outcome: str
    failure_class: str

    def validate(self) -> None:
        if self.stage not in STAGES:
            raise ValueError("unknown_stage")
        if self.state not in SAFE_STATES:
            raise ValueError("unsafe_state")
        if self.readback_outcome not in SAFE_OUTCOMES:
            raise ValueError("unsafe_outcome")
        if self.failure_class not in SAFE_FAILURES:
            raise ValueError("unsafe_failure_class")
        if self.http_status is not None and not 100 <= self.http_status <= 599:
            raise ValueError("unsafe_http_status")
        serialized = json.dumps(asdict(self), sort_keys=True).lower()
        if any(f'"{key}":' in serialized for key in FORBIDDEN_KEYS):
            raise ValueError("forbidden_diagnostic_field")


class DiagnosticAdapter(Protocol):
    def capability_read(self) -> dict[str, Any]: ...

    def projection_preflight(self, role: str) -> dict[str, Any]: ...

    def projection_create(self, role: str) -> dict[str, Any]: ...

    def projection_readback(self, role: str) -> dict[str, Any]: ...

    def workflow_preread(self) -> dict[str, Any]: ...

    def construct_workflow(self) -> dict[str, Any]: ...

    def validate_workflow(self) -> dict[str, Any]: ...

    def workflow_update(self) -> dict[str, Any]: ...

    def workflow_readback(self) -> dict[str, Any]: ...

    def verify_active_trigger(self) -> dict[str, Any]: ...

    def render_preflight(self) -> dict[str, Any]: ...

    def rollback(self, attempted: tuple[str, ...]) -> dict[str, Any]: ...


class ActivationDiagnostic:
    def __init__(self, *, packet_identity: str, adapter: DiagnosticAdapter):
        if not packet_identity or len(packet_identity) > 160:
            raise ValueError("invalid_packet_identity")
        self.packet_identity = packet_identity
        self.adapter = adapter
        self._events: list[StageEvidence] = []
        self._attempted_mutations: list[str] = []

    @property
    def events(self) -> tuple[StageEvidence, ...]:
        return tuple(self._events)

    def _record(
        self,
        stage: str,
        state: str,
        *,
        http_status: int | None = None,
        shape: str = "empty",
        outcome: str = "available",
        failure: str = "",
    ) -> StageEvidence:
        event = StageEvidence(
            sequence=len(self._events) + 1,
            stage=stage,
            state=state,
            request_identity=deterministic_request_identity(
                stage,
                {
                    "packet_identity": self.packet_identity,
                    "sequence": len(self._events) + 1,
                },
            ),
            http_status=http_status,
            response_shape=shape,
            readback_outcome=outcome,
            failure_class=failure,
        )
        event.validate()
        self._events.append(event)
        return event

    def _complete(
        self,
        stage: str,
        operation: Callable[[], dict[str, Any]],
        *,
        expected_outcome: str,
        failure_class: str,
        continue_on_exception: bool = False,
        accepted_http_statuses: frozenset[int] = frozenset({200}),
    ) -> dict[str, Any]:
        self._record(stage, "started")
        try:
            result = operation()
        except Exception as exc:
            self._record(
                stage,
                "failed",
                outcome="unavailable",
                failure=failure_class,
            )
            if continue_on_exception and isinstance(exc, AmbiguousTransportError):
                return {"outcome": "unavailable", "ambiguous": True}
            raise
        status = result.get("http_status")
        payload = result.get("response")
        raw_outcome = result.get("outcome")
        outcome = raw_outcome if isinstance(raw_outcome, str) else "unavailable"
        if not outcome or outcome not in SAFE_OUTCOMES:
            outcome = "unavailable"
        status_valid = isinstance(status, int) and status in accepted_http_statuses
        if outcome != expected_outcome or not status_valid:
            self._record(
                stage,
                "failed",
                http_status=status if isinstance(status, int) else None,
                shape=response_shape(payload),
                outcome=outcome,
                failure=failure_class,
            )
            if continue_on_exception and status_valid:
                return {
                    "outcome": outcome,
                    "ambiguous": True,
                    "http_status": status,
                }
            raise RuntimeError(failure_class)
        self._record(
            stage,
            "completed",
            http_status=status if isinstance(status, int) else None,
            shape=response_shape(payload),
            outcome=outcome,
        )
        return result

    def _not_run(self, stage: str) -> None:
        self._record(
            stage,
            "not_run",
            outcome="mutation_prohibited",
        )

    def run_read_only(self) -> dict[str, Any]:
        """Identify every live stage without administrative mutation."""
        self._complete(
            STAGES[0],
            self.adapter.capability_read,
            expected_outcome="available",
            failure_class="capability_unavailable",
        )
        self._complete(
            STAGES[1],
            lambda: self.adapter.projection_preflight("owner"),
            expected_outcome="absent",
            failure_class="projection_conflict",
        )
        self._not_run(STAGES[2])
        self._not_run(STAGES[3])
        self._complete(
            STAGES[4],
            lambda: self.adapter.projection_preflight("private_chat"),
            expected_outcome="absent",
            failure_class="projection_conflict",
        )
        self._not_run(STAGES[5])
        self._not_run(STAGES[6])
        self._complete(
            STAGES[7],
            self.adapter.workflow_preread,
            expected_outcome="matched",
            failure_class="workflow_preread_unavailable",
        )
        self._complete(
            STAGES[8],
            self.adapter.construct_workflow,
            expected_outcome="constructed",
            failure_class="workflow_construction_failed",
        )
        self._complete(
            STAGES[9],
            self.adapter.validate_workflow,
            expected_outcome="valid",
            failure_class="workflow_validation_failed",
        )
        self._not_run(STAGES[10])
        self._complete(
            STAGES[11],
            self.adapter.workflow_readback,
            expected_outcome="matched",
            failure_class="workflow_readback_mismatch",
        )
        self._complete(
            STAGES[12],
            self.adapter.verify_active_trigger,
            expected_outcome="verified",
            failure_class="telegram_trigger_count_mismatch",
        )
        self._complete(
            STAGES[13],
            self.adapter.render_preflight,
            expected_outcome="ready_disabled",
            failure_class="render_preflight_mismatch",
        )
        return self.report(mode="production_read_only")

    def run_inert_rehearsal(self) -> dict[str, Any]:
        """Exercise administrative stage contracts against an inert adapter."""
        operations = (
            (STAGES[0], self.adapter.capability_read, "available", "capability_unavailable"),
            (STAGES[1], lambda: self.adapter.projection_preflight("owner"), "absent", "projection_conflict"),
            (STAGES[2], lambda: self.adapter.projection_create("owner"), "accepted", "create_response_ambiguous"),
            (STAGES[3], lambda: self.adapter.projection_readback("owner"), "verified", "authoritative_readback_missing"),
            (STAGES[4], lambda: self.adapter.projection_preflight("private_chat"), "absent", "projection_conflict"),
            (STAGES[5], lambda: self.adapter.projection_create("private_chat"), "accepted", "create_response_ambiguous"),
            (STAGES[6], lambda: self.adapter.projection_readback("private_chat"), "verified", "authoritative_readback_missing"),
            (STAGES[7], self.adapter.workflow_preread, "matched", "workflow_preread_unavailable"),
            (STAGES[8], self.adapter.construct_workflow, "constructed", "workflow_construction_failed"),
            (STAGES[9], self.adapter.validate_workflow, "valid", "workflow_validation_failed"),
            (STAGES[10], self.adapter.workflow_update, "accepted", "workflow_update_rejected"),
            (STAGES[11], self.adapter.workflow_readback, "matched", "workflow_readback_mismatch"),
            (STAGES[12], self.adapter.verify_active_trigger, "verified", "telegram_trigger_count_mismatch"),
            (STAGES[13], self.adapter.render_preflight, "ready_disabled", "render_preflight_mismatch"),
        )
        try:
            for stage, operation, outcome, failure in operations:
                if stage in {STAGES[2], STAGES[5], STAGES[10]}:
                    self._attempted_mutations.append(stage)
                self._complete(
                    stage,
                    operation,
                    expected_outcome=outcome,
                    failure_class=failure,
                    continue_on_exception=stage in {STAGES[2], STAGES[5]},
                    accepted_http_statuses=(
                        frozenset({200, 201, 202, 204})
                        if stage in {STAGES[2], STAGES[5], STAGES[10]}
                        else frozenset({200})
                    ),
                )
        except Exception:
            rollback = self.adapter.rollback(tuple(self._attempted_mutations))
            if rollback.get("outcome") != "rolled_back":
                raise RuntimeError("rollback_unverified")
            raise
        return self.report(mode="inert_rehearsal")

    def report(self, *, mode: str) -> dict[str, Any]:
        payload = {
            "contract_version": 1,
            "packet_identity": self.packet_identity,
            "mode": mode,
            "events": [asdict(event) for event in self._events],
            "mutation_attempted": bool(self._attempted_mutations),
            "automatic_retries": 0,
            "secrets_exposed": False,
            "media_exposed": False,
            "authority": {
                "media_intake_enabled": False,
                "photo_requested": False,
                "publication": False,
                "meta": False,
                "customer_messaging": False,
                "advertising": False,
                "boosting": False,
                "spend": False,
            },
        }
        payload["diagnostic_sha256"] = canonical_sha256(payload)
        return payload


class InertDiagnosticAdapter:
    """Deterministic production-shaped state used only for local rehearsal."""

    def __init__(self, failure_stage: str = ""):
        self.failure_stage = failure_stage
        self.created: set[str] = set()
        self.workflow_updated = False
        self.rollback_verified = True

    def _result(self, stage: str, outcome: str, response: Any = None):
        if self.failure_stage == stage:
            raise RuntimeError(stage)
        return {"http_status": 200, "outcome": outcome, "response": response or {}}

    def capability_read(self):
        return self._result(STAGES[0], "available", {"data": [], "nextCursor": None})

    def projection_preflight(self, role):
        stage = STAGES[1] if role == "owner" else STAGES[4]
        return self._result(stage, "absent", {"data": []})

    def projection_create(self, role):
        stage = STAGES[2] if role == "owner" else STAGES[5]
        result = self._result(stage, "accepted", {"data": {"id": "redacted"}})
        self.created.add(role)
        return result

    def projection_readback(self, role):
        stage = STAGES[3] if role == "owner" else STAGES[6]
        if role not in self.created:
            raise RuntimeError("authoritative_readback_missing")
        return self._result(stage, "verified", {"data": [{"id": "redacted"}]})

    def workflow_preread(self):
        return self._result(STAGES[7], "matched", {"hash": "redacted"})

    def construct_workflow(self):
        return self._result(STAGES[8], "constructed", {"hash": "redacted"})

    def validate_workflow(self):
        return self._result(STAGES[9], "valid", {"valid": True})

    def workflow_update(self):
        result = self._result(STAGES[10], "accepted", {"data": {}})
        self.workflow_updated = True
        return result

    def workflow_readback(self):
        return self._result(STAGES[11], "matched", {"hash": "redacted"})

    def verify_active_trigger(self):
        return self._result(STAGES[12], "verified", {"active": True, "triggers": 1})

    def render_preflight(self):
        return self._result(STAGES[13], "ready_disabled", {"enabled": False})

    def rollback(self, attempted):
        self.created.clear()
        self.workflow_updated = False
        return {
            "outcome": "rolled_back" if self.rollback_verified else "unavailable",
            "attempted_count": len(attempted),
        }


def inert_rehearsal_report(packet_identity: str) -> dict[str, Any]:
    return ActivationDiagnostic(
        packet_identity=packet_identity,
        adapter=InertDiagnosticAdapter(),
    ).run_inert_rehearsal()


if __name__ == "__main__":
    print(
        json.dumps(
            inert_rehearsal_report("BEACON-GATEKEEPER-DIAGNOSTIC-REHEARSAL-1"),
            sort_keys=True,
        )
    )
