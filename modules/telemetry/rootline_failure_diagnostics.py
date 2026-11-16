"""Finite diagnostic metadata only: never exception messages or provider payloads."""
from collections.abc import Mapping
import re

_ERROR_TYPES = frozenset({
    "RuntimeError", "ValueError", "TypeError", "KeyError", "AttributeError",
    "TimeoutError", "ConnectionError", "OSError", "OperationalError",
    "InterfaceError", "DatabaseError", "ProgrammingError", "IntegrityError",
    "InternalError", "DataError", "QueryCanceled", "LockNotAvailable",
    "DeadlockDetected", "SerializationFailure", "ConnectionTimeout",
    "UndefinedTable", "UndefinedColumn", "InsufficientPrivilege",
    "InvalidTextRepresentation", "InFailedSqlTransaction", "UniqueViolation",
    "CheckViolation", "NotNullViolation", "ForeignKeyViolation",
    "TooManyConnections", "AdminShutdown", "ConnectionFailure",
    "OAuthFailure", "RequestBudgetUnavailable", "OptionalObservationDeferred",
    "RootlineExecutionStoreUnavailable", "RootlineCycleDeadlineExceeded",
    "RootlineConnectionDeadlineExceeded", "UnknownError"})
# Exact codes from the existing budget/OAuth boundaries; never accept arbitrary text.
# Exact codes from the existing budget/OAuth boundaries; never accept arbitrary text.
_REASONS = frozenset({
    'ewelink_account_binding_changed',
    'ewelink_account_identity_incomplete',
    'ewelink_account_identity_mismatch',
    'ewelink_active_duty_already_reserved',
    'ewelink_active_duty_availability_hold',
    'ewelink_active_duty_binding_invalid',
    'ewelink_active_duty_capacity_unavailable',
    'ewelink_active_duty_exhausted_or_mismatched',
    'ewelink_active_recovery_capacity_deferred',
    'ewelink_active_snapshot_capacity_owned',
    'ewelink_audit_client_unavailable',
    'ewelink_audit_commit_unproven',
    'ewelink_audit_transaction_state_unproven',
    'ewelink_budget_scope_limit',
    'ewelink_budget_scope_unavailable',
    'ewelink_cleanup_isolation_unproven',
    'ewelink_cleanup_pair_reuse_rejected',
    'ewelink_device_account_mismatch',
    'ewelink_device_status_conflict',
    'ewelink_device_status_incomplete',
    'ewelink_dispatch_busy',
    'ewelink_dispatch_clock_reversed',
    'ewelink_dispatch_deadline_reached',
    'ewelink_duty_shutdown_binding_unproven',
    'ewelink_expected_owned_device_not_found',
    'ewelink_final_on_capacity_unavailable',
    'ewelink_final_on_deadline_invalid',
    'ewelink_final_on_deadline_reached',
    'ewelink_local_five_minute_capacity_exhausted',
    'ewelink_local_rolling_capacity_exhausted',
    'ewelink_nested_audit_worker_rejected',
    'ewelink_nested_pair_rejected',
    'ewelink_nested_snapshot_rejected',
    'ewelink_no_send_outputs_not_off',
    'ewelink_no_send_status_not_fresh',
    'ewelink_optional_execution_binding_unproven',
    'ewelink_optional_observation_deferred',
    'ewelink_optional_shutdown_tail_protected',
    'ewelink_optional_snapshot_capacity_unavailable',
    'ewelink_optional_snapshot_group_exhausted',
    'ewelink_pair_admission_unproven',
    'ewelink_pair_binding_rejected',
    'ewelink_pair_capability_missing',
    'ewelink_pair_consumed',
    'ewelink_pair_context_rejected',
    'ewelink_pair_endpoint_rejected',
    'ewelink_pair_facade_rejected',
    'ewelink_pair_fence_unproven',
    'ewelink_pair_incomplete',
    'ewelink_pair_isolation_unproven',
    'ewelink_pair_nested_fence_rejected',
    'ewelink_prepared_client_identity_unproven',
    'ewelink_prepared_clients_not_distinct',
    'ewelink_prepared_clients_unavailable',
    'ewelink_prepared_fence_owner_unproven',
    'ewelink_prepared_metadata_conflict',
    'ewelink_prepared_token_changed',
    'ewelink_prepared_token_expires_before_read',
    'ewelink_prior_attempt_unresolved',
    'ewelink_probe_completion_late',
    'ewelink_provider_application_call_limit',
    'ewelink_provider_application_call_limit_hold',
    'ewelink_provider_auth_mode_rejected',
    'ewelink_provider_authentication_or_permission',
    'ewelink_provider_authentication_or_permission_hold',
    'ewelink_provider_host_rejected',
    'ewelink_provider_operation_rejected',
    'ewelink_provider_provider_response_error',
    'ewelink_provider_provider_response_error_hold',
    'ewelink_provider_provider_server_error',
    'ewelink_provider_provider_server_error_hold',
    'ewelink_provider_rate_limit',
    'ewelink_provider_rate_limit_hold',
    'ewelink_provider_redirect_rejected',
    'ewelink_provider_request_failed',
    'ewelink_provider_snapshot_binding_or_normalization_error',
    'ewelink_provider_snapshot_binding_or_normalization_error_hold',
    'ewelink_provider_transport_or_response_error',
    'ewelink_provider_transport_or_response_error_hold',
    'ewelink_read_deadline_reached',
    'ewelink_readback_device_mismatch',
    'ewelink_readback_disabled',
    'ewelink_readback_token_unavailable',
    'ewelink_refresh_recovery_required',
    'ewelink_refresh_response_incomplete',
    'ewelink_refresh_token_unavailable',
    'ewelink_registered_device_rejected',
    'ewelink_request_accounting_unavailable',
    'ewelink_request_accounting_unproven',
    'ewelink_request_ledger_invalid',
    'ewelink_request_workers_busy',
    'ewelink_snapshot_scope_changed',
    'ewelink_token_ciphertext_invalid',
    'ewelink_token_decryption_failed',
    'ewelink_unresolved_duty_limit',
    'irrigation_control_result_missing',
    'oauth_callback_malformed',
    'oauth_nonce_binding_mismatch',
    'oauth_onboarding_not_ready',
    'oauth_redirect_binding_mismatch',
    'oauth_state_expired',
    'oauth_state_invalid',
    'oauth_state_replayed_or_expired',
    'oauth_token_expiry_incomplete',
    'oauth_token_response_incomplete',
})
_ACTIONS = frozenset({"load_current_water_energy_evidence", "load_canonical_irrigation_history",
    "load_active", "load_job_events", "load_zone_containment", "load_eligibility",
    "load_active_auxiliaries", "load_active_borehole", "record_eligibility", "claim_before_on"})
_RECORDER_STATUSES = frozenset({"database_url_not_configured", "psycopg_dependency_missing",
    "sam_live_stock_review_event_write_failed"})


def sanitize_failure(value):
    """Revalidate even typed metadata at the durable boundary; drop unknown fields."""
    if not isinstance(value, Mapping):
        return {}
    result = {}
    for key in ("error_type", "cause_type"):
        if key in value:
            result[key] = value[key] if isinstance(value[key], str) and value[key] in _ERROR_TYPES else "UnknownError"
    for key, allowed in (("reason", _REASONS), ("store_action", _ACTIONS),
            ("accounting_stage", {"locked", "append"}), ("recorder_status", _RECORDER_STATUSES)):
        if isinstance(value.get(key), str) and value[key] in allowed:
            result[key] = value[key]
    sqlstate = value.get("sqlstate")
    if isinstance(sqlstate, str) and re.fullmatch(r"[0-9A-Z]{5}", sqlstate):
        result["sqlstate"] = sqlstate
    status = value.get("recorder_http_status")
    if type(status) is int and 100 <= status <= 599:
        result["recorder_http_status"] = status
    return result


def exception_failure(exc):
    result = sanitize_failure(getattr(exc, "failure_diagnostics", None))
    result.update(sanitize_failure({"error_type": type(exc).__name__,
        "store_action": getattr(exc, "action", None)}))
    # Only exact registered codes may leave an exception. No free text is copied.
    if len(exc.args) == 1 and isinstance(exc.args[0], str) and exc.args[0] in _REASONS:
        result["reason"] = exc.args[0]
    return result
