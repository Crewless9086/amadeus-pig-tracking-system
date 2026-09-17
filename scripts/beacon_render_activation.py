"""Bounded, replay-safe Render deployment coordination for BEACON activation.

Environment keys are updated separately through key-specific calls. This module
then requests exactly one explicit deployment and reconciles an ambiguous POST
by provider chronology instead of retrying the mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


TRANSIENT_STATES = frozenset(
    {"created", "queued", "build_in_progress", "update_in_progress"}
)
FAILURE_STATES = frozenset(
    {"build_failed", "update_failed", "canceled", "deactivated"}
)


class ActivationDeployError(RuntimeError):
    def __init__(self, status: str, evidence: dict[str, Any]):
        super().__init__(status)
        self.status = status
        self.evidence = evidence


class ActivationContainmentError(RuntimeError):
    def __init__(self, evidence: dict[str, Any]):
        super().__init__("beacon_activation_containment_unverified")
        self.evidence = evidence


@dataclass(frozen=True)
class DeployBinding:
    deploy_id: str
    revision: str
    source: str
    request_started_at: str


def deploy_row(wrapper: dict[str, Any]) -> dict[str, Any]:
    return wrapper.get("deploy") or wrapper


def deploy_revision(row: dict[str, Any]) -> str:
    return str((row.get("commit") or {}).get("id") or "")


def parse_provider_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def reconcile_deploy_acceptance(
    rows: list[dict[str, Any]],
    *,
    expected_revision: str,
    baseline_ids: set[str],
    request_started_at: datetime,
    clock_skew_tolerance_seconds: int = 10,
) -> DeployBinding | None:
    candidates = []
    for wrapper in rows:
        row = deploy_row(wrapper)
        deploy_id = str(row.get("id") or "")
        created_at = parse_provider_time(
            row.get("createdAt") or row.get("created_at") or row.get("startedAt")
        )
        if (
            deploy_id
            and deploy_id not in baseline_ids
            and deploy_revision(row) == expected_revision
            and created_at is not None
            and created_at
            >= request_started_at - timedelta(seconds=clock_skew_tolerance_seconds)
        ):
            candidates.append(row)
    if len(candidates) > 1:
        raise ActivationDeployError(
            "render_deploy_acceptance_ambiguous",
            {
                "candidate_count": len(candidates),
                "mutation_retried": False,
                "terminal_barrier_verified": False,
                "ambiguous_create_unsettled": True,
                "raw_provider_content_retained": False,
            },
        )
    if not candidates:
        return None
    return DeployBinding(
        deploy_id=str(candidates[0]["id"]),
        revision=expected_revision,
        source="provider_chronology_reconciliation",
        request_started_at=request_started_at.isoformat(),
    )


class RenderActivationCoordinator:
    """Coordinates one explicit deploy request without ambiguous mutation retry."""

    def __init__(
        self,
        *,
        list_deploys: Callable[[], list[dict[str, Any]]],
        create_deploy: Callable[[dict[str, str]], tuple[int, dict[str, Any]]],
        get_deploy: Callable[[str], dict[str, Any]],
        cancel_deploy: Callable[[str], tuple[int, dict[str, Any]]],
        now: Callable[[], datetime],
        sleep: Callable[[float], None],
    ):
        self.list_deploys = list_deploys
        self.create_deploy = create_deploy
        self.get_deploy = get_deploy
        self.cancel_deploy = cancel_deploy
        self.now = now
        self.sleep = sleep

    def request_once(
        self,
        *,
        expected_revision: str,
        acceptance_polls: int = 6,
        poll_seconds: float = 2,
        clock_skew_tolerance_seconds: int = 10,
    ) -> DeployBinding:
        before = [deploy_row(row) for row in self.list_deploys()]
        baseline_ids = {str(row.get("id") or "") for row in before}
        request_started_at = self.now().astimezone(timezone.utc)
        response_status = None
        response_body: dict[str, Any] = {}
        response_ambiguous = False
        try:
            response_status, response_body = self.create_deploy(
                {
                    "clearCache": "do_not_clear",
                    "commitId": expected_revision,
                }
            )
        except (TimeoutError, ConnectionError, OSError):
            response_ambiguous = True

        response_row = deploy_row(response_body)
        deploy_id = str(response_row.get("id") or "")
        if response_status in {201, 202} and deploy_id:
            if deploy_id in baseline_ids:
                raise ActivationDeployError(
                    "render_deploy_response_identity_stale",
                    {
                        "mutation_retried": False,
                        "terminal_barrier_verified": False,
                        "raw_provider_content_retained": False,
                    },
                )
            authoritative = deploy_row(self.get_deploy(deploy_id))
            created_at = parse_provider_time(
                authoritative.get("createdAt")
                or authoritative.get("created_at")
                or authoritative.get("startedAt")
            )
            if (
                str(authoritative.get("id") or "") != deploy_id
                or deploy_revision(authoritative) != expected_revision
                or created_at is None
                or created_at
                < request_started_at
                - timedelta(seconds=clock_skew_tolerance_seconds)
            ):
                raise ActivationDeployError(
                    "render_deploy_response_identity_unverified",
                    {
                        "mutation_retried": False,
                        "terminal_barrier_verified": False,
                        "raw_provider_content_retained": False,
                    },
                )
            return DeployBinding(
                deploy_id=deploy_id,
                revision=expected_revision,
                source="create_response_authoritative_readback",
                request_started_at=request_started_at.isoformat(),
            )
        response_status_ambiguous = (
            response_status in {408, 409, 425, 429}
            or (response_status is not None and response_status >= 500)
        )
        if (
            response_status is not None
            and response_status not in {201, 202}
            and not response_status_ambiguous
        ):
            raise ActivationDeployError(
                "render_deploy_request_rejected",
                {
                    "http_status": response_status,
                    "mutation_retried": False,
                    "raw_provider_content_retained": False,
                },
            )
        response_ambiguous = response_ambiguous or response_status_ambiguous

        for poll in range(acceptance_polls):
            binding = reconcile_deploy_acceptance(
                self.list_deploys(),
                expected_revision=expected_revision,
                baseline_ids=baseline_ids,
                request_started_at=request_started_at,
                clock_skew_tolerance_seconds=clock_skew_tolerance_seconds,
            )
            if binding is not None:
                return binding
            if poll + 1 < acceptance_polls:
                self.sleep(poll_seconds)
        raise ActivationDeployError(
            "render_deploy_acceptance_unresolved",
            {
                "create_response_ambiguous": response_ambiguous,
                "mutation_retried": False,
                "candidate_count": 0,
                "terminal_barrier_verified": False,
                "ambiguous_create_unsettled": True,
                "raw_provider_content_retained": False,
            },
        )

    def wait_until_live(
        self,
        binding: DeployBinding,
        *,
        expected_revision: str,
        completion_polls: int = 60,
        poll_seconds: float = 5,
        terminalization_polls: int = 12,
    ) -> dict[str, Any]:
        last_state = ""
        for poll in range(completion_polls):
            try:
                row = deploy_row(self.get_deploy(binding.deploy_id))
            except (TimeoutError, ConnectionError, OSError) as exc:
                settled_state = self._terminalize_timed_out_deploy(
                    binding,
                    polls=terminalization_polls,
                    poll_seconds=poll_seconds,
                )
                raise ActivationDeployError(
                    "render_deployment_read_failed",
                    {
                        "deploy_id": binding.deploy_id,
                        "read_error_type": exc.__class__.__name__,
                        "terminal_barrier_state": settled_state,
                        "terminal_barrier_verified": True,
                    },
                ) from exc
            last_state = str(row.get("status") or "")
            observed_revision = deploy_revision(row)
            if observed_revision and observed_revision != expected_revision:
                settled_state = self._terminalize_timed_out_deploy(
                    binding,
                    polls=terminalization_polls,
                    poll_seconds=poll_seconds,
                )
                raise ActivationDeployError(
                    "render_deployed_revision_mismatch",
                    {
                        "deploy_id": binding.deploy_id,
                        "expected_revision": expected_revision,
                        "observed_revision": observed_revision,
                        "terminal_barrier_state": settled_state,
                        "terminal_barrier_verified": True,
                    },
                )
            if last_state == "live":
                return {
                    "deploy_id": binding.deploy_id,
                    "revision": expected_revision,
                    "status": "live",
                    "acceptance_source": binding.source,
                    "mutation_attempts": 1,
                }
            if last_state in FAILURE_STATES:
                raise ActivationDeployError(
                    "render_deployment_failed",
                    {
                        "deploy_id": binding.deploy_id,
                        "provider_status": last_state,
                        "mutation_attempts": 1,
                    },
                )
            if last_state not in TRANSIENT_STATES:
                raise ActivationDeployError(
                    "render_deployment_state_unknown",
                    {
                        "deploy_id": binding.deploy_id,
                        "provider_status": last_state,
                        "mutation_attempts": 1,
                        "terminal_barrier_verified": False,
                    },
                )
            if poll + 1 < completion_polls:
                self.sleep(poll_seconds)
        settled_state = self._terminalize_timed_out_deploy(
            binding,
            polls=terminalization_polls,
            poll_seconds=poll_seconds,
        )
        raise ActivationDeployError(
            "render_deployment_completion_timeout",
            {
                "deploy_id": binding.deploy_id,
                "provider_status": last_state,
                "terminal_barrier_state": settled_state,
                "terminal_barrier_verified": True,
                "mutation_attempts": 1,
                "cancel_attempts": 1,
            },
        )

    def _terminalize_timed_out_deploy(
        self,
        binding: DeployBinding,
        *,
        polls: int,
        poll_seconds: float,
    ) -> str:
        try:
            self.cancel_deploy(binding.deploy_id)
        except (TimeoutError, ConnectionError, OSError):
            pass
        terminal = FAILURE_STATES | {"live"}
        last_state = ""
        for poll in range(polls):
            row = deploy_row(self.get_deploy(binding.deploy_id))
            last_state = str(row.get("status") or "")
            if deploy_revision(row) not in {"", binding.revision}:
                raise ActivationDeployError(
                    "render_timed_out_deploy_revision_mismatch",
                    {
                        "deploy_id": binding.deploy_id,
                        "terminal_barrier_verified": False,
                    },
                )
            if last_state in terminal:
                return last_state
            if last_state not in TRANSIENT_STATES:
                break
            if poll + 1 < polls:
                self.sleep(poll_seconds)
        raise ActivationDeployError(
            "render_timed_out_deploy_unsettled",
            {
                "deploy_id": binding.deploy_id,
                "provider_status": last_state,
                "terminal_barrier_verified": False,
                "cancel_attempts": 1,
            },
        )

    def deploy_exact_revision(
        self,
        *,
        expected_revision: str,
        acceptance_polls: int = 6,
        completion_polls: int = 60,
        acceptance_poll_seconds: float = 2,
        completion_poll_seconds: float = 5,
        clock_skew_tolerance_seconds: int = 10,
    ) -> dict[str, Any]:
        binding = self.request_once(
            expected_revision=expected_revision,
            acceptance_polls=acceptance_polls,
            poll_seconds=acceptance_poll_seconds,
            clock_skew_tolerance_seconds=clock_skew_tolerance_seconds,
        )
        return self.wait_until_live(
            binding,
            expected_revision=expected_revision,
            completion_polls=completion_polls,
            poll_seconds=completion_poll_seconds,
        )


def run_with_deterministic_rollback(
    *,
    activate: Callable[[], dict[str, Any]],
    verify_activation: Callable[[dict[str, Any]], bool],
    rollback: Callable[[], dict[str, Any]],
    verify_containment: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    """Run one activation and prove rollback before returning any failure.

    Callers provide exact workflow/config/projection operations. This wrapper
    guarantees that an activation exception or verification mismatch cannot
    bypass one rollback attempt and authoritative containment verification.
    """

    try:
        activated = activate()
        if not verify_activation(activated):
            raise ActivationDeployError(
                "beacon_activation_verification_mismatch",
                {"activation_mutation_attempts": 1},
            )
        return {
            "status": "beacon_activation_verified",
            "activation": activated,
            "rollback_performed": False,
        }
    except Exception as activation_error:
        if (
            isinstance(activation_error, ActivationDeployError)
            and activation_error.evidence.get("terminal_barrier_verified") is False
        ):
            raise ActivationContainmentError(
                {
                    "activation_error_type": activation_error.__class__.__name__,
                    "activation_status": activation_error.status,
                    "rollback_attempts": 0,
                    "containment_verified": False,
                    "unsafe_transient_deploy_unsettled": True,
                }
            ) from activation_error
        rollback_result = None
        rollback_error = None
        containment_error = None
        try:
            rollback_result = rollback()
        except Exception as exc:
            rollback_error = exc
        contained = False
        if rollback_error is None and rollback_result is not None:
            try:
                contained = bool(verify_containment(rollback_result))
            except Exception as exc:
                containment_error = exc
        if not contained:
            raise ActivationContainmentError(
                {
                    "activation_error_type": activation_error.__class__.__name__,
                    "rollback_error_type": (
                        rollback_error.__class__.__name__ if rollback_error else ""
                    ),
                    "containment_error_type": (
                        containment_error.__class__.__name__
                        if containment_error
                        else ""
                    ),
                    "rollback_attempts": 1,
                    "containment_verified": False,
                }
            ) from activation_error
        activation_status = (
            activation_error.status
            if isinstance(activation_error, ActivationDeployError)
            else activation_error.__class__.__name__
        )
        activation_evidence = (
            activation_error.evidence
            if isinstance(activation_error, ActivationDeployError)
            else {}
        )
        return {
            "status": "beacon_activation_failed_contained",
            "activation_error_type": activation_error.__class__.__name__,
            "activation_status": activation_status,
            "activation_evidence": activation_evidence,
            "rollback": rollback_result,
            "rollback_performed": True,
            "containment_verified": True,
        }
