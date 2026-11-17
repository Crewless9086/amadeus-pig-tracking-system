"""Shared, conservative eWeLink demand control on the existing audit rail.

No provider balance is inferred from this ledger.  It measures this application's
participating requests from coverage_start; other clients and older traffic are
Unknown.  OFF is not an eWeLink API operation and never enters this gate.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from contextvars import ContextVar, copy_context
from copy import deepcopy
from types import MappingProxyType
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from email.utils import parsedate_to_datetime
import json
import math
import os
import time
import threading
import queue
import uuid

EVENT_SOURCE = "rootline_provider_availability"
LEDGER_ID = "ROOTLINE-EWELINK-REQUEST-BUDGET-V1"
GLOBAL_SEND_LOCK = 1874320915
LOCAL_ROLLING_LIMIT = 50000
ROLLING_DAYS = 31
FIVE_MINUTE_LIMIT = 250
MIN_DISPATCH_INTERVAL = 1.0
REQUEST_SECONDS = 15.0
GROUP_SECONDS = 60.0
MAX_PACE_WAIT_SECONDS = 1.1
TRANSIENT_BACKOFF = (60, 300, 900, 3600)
# Whole three-GET snapshots: routine duty plus a finite initial recovery
# allowance. Injector routine duty covers an immediate second worker after ON
# plus two minute workers with all three existing supervision passes. Longer unresolved recovery
# uses the separately bounded hourly four-attempt replenishment below.
DUTY_SNAPSHOTS = {
    "irrigation_zone_valve": (1 + 4*(1+2) + 1 + 1 + 7, 6),
    "fertilizer_mixer": (1 + 1, 5),
    "fertilizer_injection_valve": (1 + 1 + 1 + 3*2*2 + 1, 10),
    "borehole_pump_power": (1 + 1 + 7, 5)}
DUTY_REFRESH_ALLOWANCE = {"irrigation_zone_valve": 3, "fertilizer_mixer": 3,
    "fertilizer_injection_valve": 1, "borehole_pump_power": 3}
DUTY_CAPACITY = {kind: 3*sum(bounds)+DUTY_REFRESH_ALLOWANCE[kind]
    for kind,bounds in DUTY_SNAPSHOTS.items()}
_duty = ContextVar("rootline_ewelink_duty", default=None)
_group = ContextVar("rootline_ewelink_snapshot", default=None)
_optional_observation = ContextVar("rootline_ewelink_optional_observation", default=None)
OPTIONAL_OBSERVATION_SECONDS = {"mixer_readiness": 1800, "mixer_readiness_delivery": 1800,
    "irrigation_routine": 900, "borehole_routine": 1800,
    "pulse_preparation": 300, "final_flush": 300}
_request_workers = threading.BoundedSemaphore(2)
_dispatch_audit = ContextVar("rootline_ewelink_dispatch_audit", default=None)
_private_pair = ContextVar("rootline_ewelink_private_no_send_pair", default=None)
_CLAIM_ACTIONS = {"claim_before_on", "claim_auxiliary_before_on", "claim_borehole_before_on"}
_OUTCOME_ACTIONS = {"record_on_outcome", "record_auxiliary_on_outcome", "record_borehole_on_outcome"}
_ACTIVE_ACTIONS = {"mark_active", "mark_auxiliary_active", "mark_borehole_active", "mark_stopping"}
_OFF_ACTIONS = {"claim_off_attempt", "claim_auxiliary_off_attempt", "claim_borehole_off_attempt"}
_TERMINAL_ACTIONS = {"record_completed", "record_auxiliary_completed",
    "record_auxiliary_control_pulse_stopped", "record_borehole_completed", "record_borehole_aborted",
    "record_execution_not_dispatched", "contain_zone", "record_ambiguous_shutdown",
    "record_claim_recovery", "contain_auxiliary_device", "contain_borehole"}
_RECONCILE_ACTIONS = _CLAIM_ACTIONS | _OUTCOME_ACTIONS | _ACTIVE_ACTIONS | _OFF_ACTIONS | _TERMINAL_ACTIONS
MAX_RECONCILE_ROWS = 512


@contextmanager
def _accounting_operation(operation):
    """Attach only an allowlisted location; preserve the original exception."""
    try:
        yield
    except Exception as exc:
        from modules.telemetry.rootline_failure_diagnostics import sanitize_failure
        details = sanitize_failure(getattr(exc, "failure_diagnostics", None))
        if "accounting_operation" not in details:
            details.update(sanitize_failure({"accounting_operation": operation}))
        exc.failure_diagnostics = details
        raise


class RequestBudgetUnavailable(RuntimeError):
    """Sanitized local refusal; never an authentication failure."""

    def __init__(self, message, *, failure_diagnostics=None):
        super().__init__(message)
        from modules.telemetry.rootline_failure_diagnostics import sanitize_failure
        self.failure_diagnostics = sanitize_failure(failure_diagnostics)


class FullSnapshotRequired(RequestBudgetUnavailable):
    """Pre-send signal: the same snapshot must perform full recovery discovery."""


class OptionalObservationDeferred(RequestBudgetUnavailable):
    """No provider attempt; never evidence that a device or account failed."""
    def __init__(self, next_read_at):
        super().__init__("ewelink_optional_observation_deferred")
        self.next_read_at = next_read_at


@contextmanager
def optional_observation(purpose, *, binding=None, first_read_at=None,
                         interval_seconds=None, last_read_at=None, admission_token=None):
    if purpose not in OPTIONAL_OBSERVATION_SECONDS:
        raise ValueError("unregistered_optional_observation")
    token = _optional_observation.set({"purpose": purpose,
        "binding": dict(binding or {}), "first_read_at": first_read_at,
        "interval_seconds": interval_seconds or OPTIONAL_OBSERVATION_SECONDS[purpose],
        "last_read_at": last_read_at, "admission_token": admission_token})
    try:
        yield
    finally:
        _optional_observation.reset(token)


@contextmanager
def routine_execution_observation(execution):
    """Durable due slots affect routine observation only, never a stop duty."""
    borehole = execution.get("device_type") == "borehole_pump_power"
    purpose = "borehole_routine" if borehole else "irrigation_routine"
    interval = (max(1800, math.ceil(int(execution.get("planned_runtime_seconds") or
        execution.get("requested_seconds") or execution.get("maximum_duration_seconds") or 0)/480)*60) if borehole else 900)
    from modules.telemetry.rootline_borehole_conditions import continuous_borehole
    if continuous_borehole(execution):
        interval = OPTIONAL_OBSERVATION_SECONDS["borehole_routine"]
    start = execution.get("provider_start_evidence" if borehole else "start_evidence") or {}
    started = _time(start.get("retrieved_at") or start.get("observed_at"))
    if started is None and continuous_borehole(execution):
        # This anchors a read slot, never a claimed provider ON or water start.
        started = _time(execution.get("claimed_at"))
    if started is None or not execution.get("execution_id"):
        raise RequestBudgetUnavailable("ewelink_optional_execution_binding_unproven")
    with optional_observation(purpose, binding={"execution_id": execution["execution_id"],
            "provider_account_binding": "ewelink_owner_account",
            "device_id": execution.get("device_id"), "channel": execution.get("channel")},
            first_read_at=(started+timedelta(seconds=interval)).isoformat(),
            interval_seconds=interval, last_read_at=execution.get("primary_stop_deadline")):
        yield


def classify_failure(*, provider_code=None, http_status=None, retry_after=None, now=None):
    """Keep provider JSON codes distinct from HTTP status, without raw payloads."""
    now = now or datetime.now(timezone.utc)
    code = provider_code if type(provider_code) is int else None
    status = http_status if type(http_status) is int else None
    if code == 412:
        category = "application_call_limit"
    elif status == 429 or code == 429:
        category = "rate_limit"
    elif status in {401, 403} or code in {401, 402, 403, 406, 407}:
        category = "authentication_or_permission"
    elif status is not None and 500 <= status <= 599:
        category = "provider_server_error"
    elif code is not None:
        category = "provider_response_error"
    else:
        category = "transport_or_response_error"
    seconds = 0
    if isinstance(retry_after, str) and len(retry_after) <= 128:
        try:
            seconds = int(retry_after.strip())
        except ValueError:
            try:
                when = parsedate_to_datetime(retry_after)
                if when.tzinfo is not None:
                    seconds = int((when - now).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
    return {"category": category, "provider_code": code, "http_status": status,
            "retry_after_seconds": max(0, min(3600, seconds))}


def scope_digest(environ, region):
    app = str(environ.get("EWELINK_CLIENT_ID") or "")
    if not app or region not in {"as", "eu", "us", "cn"}:
        raise RequestBudgetUnavailable("ewelink_budget_scope_unavailable")
    # Availability is application-wide: moving token/region provenance cannot
    # erase an observed hold while the actual entitlement remains Unknown.
    return sha256(app.encode()).hexdigest()


@contextmanager
def execution_duty(execution, *, deadline=None):
    """Attribute safety reads to one execution; callers cannot borrow a sibling."""
    item = dict(execution or {})
    existing = _duty.get() or {}
    if existing.get("execution_id") == item.get("execution_id") and existing.get("read_deadline"):
        earlier = _time(existing["read_deadline"])
        supplied = _time(deadline)
        if earlier is not None and (supplied is None or earlier < supplied):
            deadline = earlier
    if deadline is not None:
        item["read_deadline"] = deadline
    token = _duty.set(item)
    try:
        yield
    finally:
        _duty.reset(token)


@contextmanager
def snapshot_group(*, expected_device, environ, region, deadline=None):
    """Only a complete fresh authenticated device snapshot may heal a hold."""
    old = _group.get()
    if old is not None:
        raise RequestBudgetUnavailable("ewelink_nested_snapshot_rejected")
    from modules.telemetry.rootline_cycle_budget import remaining_seconds
    original = time.monotonic() + remaining_seconds(GROUP_SECONDS)
    deadline = min(original, deadline) if deadline is not None else original
    duty = _duty.get() or {}
    bound = _time(duty.get("read_deadline"))
    if bound is not None:
        deadline = min(deadline, time.monotonic() +
            max(0, (bound - datetime.now(timezone.utc)).total_seconds()))
    group = {"id": uuid.uuid4().hex, "expected_device": str(expected_device),
        "scope": scope_digest(environ, region), "region": region,
        "deadline": deadline, "budget": None, "successful_endpoints": [],
        "optional_purpose": _optional_observation.get(),
        "normalized_complete": False, "failed": False}
    token = _group.set(group)
    try:
        yield group
    except Exception:
        if group["budget"] is not None and not group["failed"]:
            # Binding/normalization failures happen after HTTP succeeds. They
            # also need shared backoff; never preserve raw payload or exception.
            group["failed"] = True
            group["budget"].fail_snapshot(group)
        raise
    else:
        if group["budget"] is not None and group["normalized_complete"] and not group["failed"]:
            group["budget"].complete_snapshot(group)
    finally:
        try:
            if group["budget"] is not None and group.get("optional_purpose"):
                group["budget"].finish_optional_group(group)
        finally:
            _group.reset(token)


def request_timeout():
    group = _group.get()
    if group is None:
        return REQUEST_SECONDS
    remaining = group["deadline"] - time.monotonic()
    if remaining <= 0:
        raise RequestBudgetUnavailable("ewelink_read_deadline_reached")
    return min(REQUEST_SECONDS, remaining)


def current_duty():
    return dict(_duty.get() or {})


def prepare_execution_capacity(transport, execution):
    """Admit before durable hardware claim; injected transports own their rails."""
    execution.pop("_provider_capacity_failure", None)
    prepare = getattr(transport, "prepare_execution_capacity", None)
    if prepare is None:
        return True
    try:
        execution["provider_capacity_permit"] = prepare(execution)
        return bool(execution["provider_capacity_permit"])
    except Exception as exc:
        from modules.telemetry.rootline_failure_diagnostics import exception_failure
        from modules.telemetry.rootline_cycle_budget import work_deadline
        failure = exception_failure(exc)
        deadline = work_deadline()
        if deadline is not None:
            failure["cycle_remaining_ms"] = max(0, min(86400000,
                int((deadline-time.monotonic())*1000)))
        execution["_provider_capacity_failure"] = failure
        return False


def bind_execution_transport(transport, execution, *, read_deadline=None):
    while isinstance(transport, _ExecutionTransport):
        transport = transport.transport
    return _ExecutionTransport(transport, execution, read_deadline=read_deadline)


class _ExecutionTransport:
    def __init__(self, transport, execution, *, read_deadline=None):
        self.transport = transport
        self.execution = dict(execution)
        self.read_deadline = read_deadline

    def read_output_state(self, **kwargs):
        with execution_duty(self.execution, deadline=self.read_deadline):
            return self.transport.read_output_state(**kwargs)

    def read_safety_configuration(self, **kwargs):
        with execution_duty(self.execution, deadline=self.read_deadline):
            return self.transport.read_safety_configuration(**kwargs)

    def set_state(self, **kwargs):
        with execution_duty(self.execution):
            return self.transport.set_state(**kwargs)

    def __getattr__(self, name):
        return getattr(self.transport, name)


class RequestBudget:
    """One global send fence, durable reservations, and scoped availability.

    Lock order: hardware 1874320911 -> 1874320912, token-binding row (if
    rotating), global request 1874320915.  This module never acquires either
    hardware or token locks.  The send transaction retains its backend across
    HTTP; separately committed audit rows survive its rollback or process death.
    No session lock or transaction-pooler session affinity is assumed.
    """
    def __init__(self, environ=None, *, connect_factory=None, sleeper=time.sleep):
        self.environ = environ if environ is not None else os.environ
        self.database_url = str(self.environ.get("DATABASE_URL") or "").strip()
        self.connect_factory = connect_factory
        self.sleep = sleeper

    @_accounting_operation("connection_acquire")
    def _connect(self):
        if self.connect_factory is not None:
            return self.connect_factory()
        from modules.oom_sakkie.bounded_postgres_read import (
            ROOTLINE_CONNECT_DEADLINE_SECONDS, connect_bounded_rootline_postgres)
        # Acquisition includes the transaction-local settings required by the
        # pooler. Reuse ROOTLINE's bound without extending a shorter read duty.
        pair = _private_pair.get()
        private = pair is not None and pair.owner is self
        return connect_bounded_rootline_postgres(database_url=self.database_url,
            read_only=False, reuse_local_settings=private, read_committed=private,
            native_begin_read_committed=private,
            connect_deadline_seconds=min(ROOTLINE_CONNECT_DEADLINE_SECONDS, request_timeout()))

    @contextmanager
    def _locked(self, *, read_committed=False, prepared=None):
        operation = "fence_setup"
        try:
            pair = _private_pair.get()
            if prepared is not None:
                if pair is None or pair.owner is not self:
                    raise RequestBudgetUnavailable("ewelink_prepared_fence_owner_unproven")
                _PreparedNoSendClients._verify_idle(prepared)
                from modules.telemetry.rootline_cycle_budget import remaining_seconds
                from modules.oom_sakkie.bounded_postgres_read import STATEMENT_TIMEOUT_MS, LOCK_TIMEOUT_MS
                remaining = min(request_timeout(), remaining_seconds())
                statement = max(1, min(STATEMENT_TIMEOUT_MS, int(remaining * 1000)))
                with _accounting_operation("fence_setup"):
                    prepared.configure_transaction_timeouts(statement,
                        min(LOCK_TIMEOUT_MS, statement), read_committed=True)
            operation = "fence_enter"
            with prepared if prepared is not None else self._connect() as connection:
                if read_committed:
                    # Only post-pair canonical cleanup opts in. The ordinary
                    # acquisition has applied SET LOCAL but no data snapshot.
                    # An injected incompatible snapshot makes SET fail closed.
                    if pair is not None:
                        raise RequestBudgetUnavailable("ewelink_cleanup_pair_reuse_rejected")
                    with _accounting_operation("fence_setup"):
                        connection.execute("set transaction isolation level read committed")
                    with _accounting_operation("fence_acquire"):
                        row = connection.execute("select pg_try_advisory_xact_lock(%s),"
                        "current_setting('transaction_isolation')", (GLOBAL_SEND_LOCK,)).fetchone()
                    if not row or row[1] != "read committed":
                        raise RequestBudgetUnavailable("ewelink_cleanup_isolation_unproven")
                    locked = row[0]
                elif pair is not None and pair.owner is self:
                    if pair.fence is not None:
                        raise RequestBudgetUnavailable("ewelink_pair_nested_fence_rejected")
                    with _accounting_operation("fence_acquire"):
                        row = connection.execute("select pg_try_advisory_xact_lock(%s),"
                        "current_setting('transaction_isolation'),pg_backend_pid()",
                            (GLOBAL_SEND_LOCK,)).fetchone()
                    if not row or row[1] != "read committed":
                        raise RequestBudgetUnavailable("ewelink_pair_isolation_unproven")
                    locked = row[0]
                    pair.fence, pair.backend = connection, row[2]
                else:
                    with _accounting_operation("fence_acquire"):
                        locked = connection.execute("select pg_try_advisory_xact_lock(%s)",
                            (GLOBAL_SEND_LOCK,)).fetchone()[0]
                if not locked:
                    raise RequestBudgetUnavailable("ewelink_dispatch_busy")
                operation = "fenced_body"
                yield connection
                operation = "fence_close"
        except RequestBudgetUnavailable:
            raise
        except Exception as exc:
            if hasattr(exc, "provider_failure"):
                raise
            raise RequestBudgetUnavailable("ewelink_request_accounting_unavailable",
                failure_diagnostics={**getattr(exc, "failure_diagnostics", {}),
                    "accounting_stage": "locked", "cause_type": type(exc).__name__,
                    "sqlstate": getattr(exc, "sqlstate", None),
                    "accounting_operation": getattr(exc, "failure_diagnostics", {}).get("accounting_operation", operation)}) from None

    @staticmethod
    def _now(connection):
        pair = _private_pair.get()
        if pair is not None and connection is pair.fence:
            with _accounting_operation("fence_clock"):
                row = connection.execute("select clock_timestamp(),pg_backend_pid(),"
                "exists(select 1 from pg_locks where pid=pg_backend_pid() and locktype='advisory' "
                "and classid=0 and objid=%s and objsubid=1 and granted)", (GLOBAL_SEND_LOCK,)).fetchone()
            if not row or row[1] != pair.backend or row[2] is not True:
                raise RequestBudgetUnavailable("ewelink_pair_fence_unproven")
            return row[0]
        with _accounting_operation("clock_read"):
            return connection.execute("select clock_timestamp()").fetchone()[0]

    def _load(self, connection):
        with _accounting_operation("ledger_load"):
            row = connection.execute("""select review_json->'ewelink_request_budget'
            from public.sam_live_stock_conversation_review_events
            where chatwoot_conversation_id=%s and event_source=%s
            order by created_at desc,review_event_id desc limit 1""",
                (LEDGER_ID, EVENT_SOURCE)).fetchone()
        if row and row[0] is None:
            raise RequestBudgetUnavailable("ewelink_request_ledger_invalid")
        return self._ledger_state(row[0] if row else None, self._now(connection) if not row else None)

    @staticmethod
    def _ledger_state(payload, now):
        if payload is not None:
            state = payload.get("state") if isinstance(payload, dict) else None
            if not isinstance(state, dict) or state.get("version") != 1:
                raise RequestBudgetUnavailable("ewelink_request_ledger_invalid")
            return state
        return {"version": 1, "coverage_start": now.isoformat(),
            "prior_provider_usage": "Unknown", "provider_remaining": "Unknown",
            "provider_entitlement": "Unknown", "external_clients_counted": False,
            "scopes": {}, "reserves": {}, "last_finished_at": None,
            "pending_attempt": None}

    def _admission_preimage(self, connection, *, scope, region):
        # Each endpoint takes a NEW READ COMMITTED snapshot. Reconciliation
        # remains a separate fresh canonical query and appends zero attempt units.
        with _accounting_operation("admission_preimage"):
            row = connection.execute("""with stamp as materialized (select clock_timestamp() as at),
            latest as (select review_json->'ewelink_request_budget' as body
                from public.sam_live_stock_conversation_review_events
                where chatwoot_conversation_id=%s and event_source=%s
                order by created_at desc,review_event_id desc limit 1),
            counts as (select
                coalesce(sum(case when cast(%s as text) is null or
                    (review_json #>> '{ewelink_request_budget,detail,scope}'=%s and
                     review_json #>> '{ewelink_request_budget,detail,region}'=%s)
                    then (review_json #>> '{ewelink_request_budget,attempt_units}')::int else 0 end),0) as rolling,
                coalesce(sum(case when created_at >= stamp.at-interval '5 minutes' then
                    (review_json #>> '{ewelink_request_budget,attempt_units}')::int else 0 end),0) as recent
                from public.sam_live_stock_conversation_review_events cross join stamp
                where chatwoot_conversation_id=%s and event_source=%s
                    and created_at >= stamp.at-(%s * interval '1 day')
                    and (review_json #>> '{ewelink_request_budget,attempt_units}') collate "C" is distinct from '0')
            select latest.body,stamp.at,counts.rolling,counts.recent,exists(select 1 from latest)
            from stamp cross join counts left join latest on true""",
                (LEDGER_ID, EVENT_SOURCE, scope, scope, region, LEDGER_ID, EVENT_SOURCE, ROLLING_DAYS)).fetchone()
        if not row or len(row) != 5 or (row[4] and row[0] is None):
            raise RequestBudgetUnavailable("ewelink_request_ledger_invalid")
        return self._ledger_state(row[0], row[1]), row[1], (int(row[2]), int(row[3]))

    @staticmethod
    def _utc_preimage_counts(now):
        # Ordinary admission historically used Python wall-time cutoffs. Across
        # DST transitions these can differ from PostgreSQL interval arithmetic.
        # Reuse the single-read counts only for a provably fixed UTC session;
        # other sessions retain the original post-reconciliation count query.
        from zoneinfo import ZoneInfo
        zone = now.tzinfo
        return zone is timezone.utc or (isinstance(zone, ZoneInfo) and zone.key in {"UTC", "Etc/UTC"})

    def _counts(self, connection, now, *, scope=None, region=None):
        with _accounting_operation("counts_fallback"):
            row = connection.execute("""select
            coalesce(sum(case when cast(%s as text) is null or
                (review_json #>> '{ewelink_request_budget,detail,scope}'=%s and
                 review_json #>> '{ewelink_request_budget,detail,region}'=%s)
                then (review_json #>> '{ewelink_request_budget,attempt_units}')::int else 0 end),0),
            coalesce(sum(case when created_at >= %s then
                (review_json #>> '{ewelink_request_budget,attempt_units}')::int else 0 end),0)
            from public.sam_live_stock_conversation_review_events
            where chatwoot_conversation_id=%s and event_source=%s and created_at >= %s""",
                (scope, scope, region, now-timedelta(minutes=5), LEDGER_ID, EVENT_SOURCE,
                 now-timedelta(days=ROLLING_DAYS))).fetchone()
        return int(row[0]), int(row[1])

    def _append(self, state, *, action, attempt_units=0, detail=None):
        from modules.sales.sam_live_stock_launch_control import (
            build_sam_live_stock_review_event, record_sam_live_stock_review_event)
        identity = "ROOTLINE-EWELINK-BUDGET-" + uuid.uuid4().hex.upper()
        payload = {"action": action, "attempt_units": attempt_units,
            "detail": detail or {}, "state": state}
        event = build_sam_live_stock_review_event({"conversation_id": LEDGER_ID}, {}, {},
            {"score": 0, "safe_to_send": False, "recommended_action": action},
            event_source=EVENT_SOURCE)
        event.update(review_event_id=identity, chatwoot_conversation_id=LEDGER_ID,
            review_json={"ewelink_request_budget": payload}, facts_json={},
            decision_json={}, customer_message_excerpt="", sam_reply_excerpt="")
        # The outer transaction owns only the advisory fence.  This independent
        # transaction durably counts a possible attempt before any network send.
        with self._audit_transaction(action) as audit:
            result, status = record_sam_live_stock_review_event(event,
                database_url=self.database_url or "injected-local-connection",
                connect_factory=lambda: nullcontext(audit),
                durable_receipt=True)
            if status >= 400 or result.get("success") is not True:
                raise RequestBudgetUnavailable("ewelink_request_accounting_unavailable",
                    failure_diagnostics={"accounting_stage": "append",
                        "accounting_operation": result.get("accounting_operation", "audit_record"),
                        "sqlstate": result.get("sqlstate"),
                        "cause_type": result.get("error_type"), "recorder_status": result.get("status"),
                        "recorder_http_status": status})
            receipt = result.get("persisted_receipt") or {}
            if receipt.get("review_event_id") != identity or receipt.get("review_json") != event["review_json"]:
                raise RequestBudgetUnavailable("ewelink_request_accounting_unproven")

    @contextmanager
    def _audit_transaction(self, action):
        """One worker may reuse only its idle audit client, never its send fence."""
        with _accounting_operation("audit_transaction"):
            session = _dispatch_audit.get()
            if (action not in {"request_attempt_reserved", "request_completed"}
                    or session is None or session["owner"] is not self
                    or session["thread"] != threading.get_ident()):
                with self._connect() as connection:
                    yield connection
                return
            from psycopg.pq import TransactionStatus
            from modules.oom_sakkie.bounded_postgres_read import STATEMENT_TIMEOUT_MS, LOCK_TIMEOUT_MS
            from modules.telemetry.rootline_cycle_budget import remaining_seconds
            connection = session["connection"]
            fresh = connection is None
            try:
                if session["poisoned"]:
                    raise RequestBudgetUnavailable("ewelink_audit_client_unavailable")
                if fresh:
                    connection = self._connect()
                    session["connection"] = connection
                # Internal identity checks do not hand the raw client to a caller.
                raw = getattr(connection, "_connection", None)
                if raw is None:
                    raw = getattr(connection, "connection", connection)
                fence = session.get("fence")
                fence_raw = getattr(fence, "_connection", None)
                if fence_raw is None:
                    fence_raw = getattr(fence, "connection", fence)
                if (connection is fence or raw is fence_raw
                        or connection.closed
                        or raw.info.transaction_status not in
                            ({TransactionStatus.IDLE, TransactionStatus.INTRANS} if fresh else
                             {TransactionStatus.IDLE})):
                    raise RequestBudgetUnavailable("ewelink_audit_transaction_state_unproven")
                # The first connection's transaction contains only bounded setup.
                # A reused client MUST be idle before beginning this distinct append.
                remaining = min(request_timeout(), remaining_seconds())
                statement = max(1, min(STATEMENT_TIMEOUT_MS, int(remaining*1000)))
                lock = max(1, min(LOCK_TIMEOUT_MS, statement))
                pair = _private_pair.get()
                configure = getattr(connection, "configure_transaction_timeouts", None)
                if pair is not None and pair.owner is self and callable(configure):
                    with _accounting_operation("audit_setup"):
                        configure(statement, lock, read_committed=True)
                else:
                    with _accounting_operation("audit_setup"):
                        connection.execute("select set_config('statement_timeout',%s,true),"
                    "set_config('lock_timeout',%s,true)", (str(statement), str(lock)))
                yield connection
                request_timeout()
                remaining_seconds()
                with _accounting_operation("audit_commit"):
                    connection.commit()
                if connection.closed or raw.info.transaction_status != TransactionStatus.IDLE:
                    raise RequestBudgetUnavailable("ewelink_audit_commit_unproven")
                # Unknown/late acknowledgement cannot admit a send or expose output.
                request_timeout()
                remaining_seconds()
            except BaseException:
                session["poisoned"] = True
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass
                session["connection"] = None
                raise

    def _scope(self, state, key):
        scopes = state["scopes"]
        if key not in scopes:
            if len(scopes) >= 8:
                raise RequestBudgetUnavailable("ewelink_budget_scope_limit")
            scopes[key] = {"category": None, "generation": 0, "failures": 0,
                "next_probe_at": None, "probe_group": None, "probe_until": None}
        return scopes[key]

    def _terminal_rows(self, connection, identities):
        from modules.telemetry.rootline_irrigation_execution_store import EVENT_SOURCE as execution_source
        # One bounded set read; no hardware/token locks. Keep cardinality while
        # projecting repeated history, and retain each bounded OFF barrier.
        with _accounting_operation("reserve_terminal_read"):
            rows = connection.execute("""with ranked as (
            select review_event_id,chatwoot_conversation_id,created_at,
                review_json->'rootline_execution' as body,
                count(*) over duty as copies, row_number() over duty as ordinal
            from public.sam_live_stock_conversation_review_events
            where event_source=%s
              and review_json->'rootline_execution'->>'execution_id'=any(%s)
              and review_json->'rootline_execution'->>'action'=any(%s)
            window duty as (partition by
                review_json->'rootline_execution'->>'execution_id',
                review_json->'rootline_execution'->>'action',
                case when review_json->'rootline_execution'->>'action'=any(%s)
                    then review_json->'rootline_execution'->>'attempt' else '' end
                order by created_at desc,review_event_id desc
                rows between unbounded preceding and unbounded following))
            select review_event_id,chatwoot_conversation_id,created_at,body,copies
            from ranked where ordinal=1 limit %s""",
                (execution_source, identities, sorted(_RECONCILE_ACTIONS), sorted(_OFF_ACTIONS),
                 MAX_RECONCILE_ROWS+1)).fetchall()
        if len(rows) > MAX_RECONCILE_ROWS:
            return []  # Incomplete proof cannot refund an attempted duty.
        return [{"event_id": row[0], "execution_id": row[1], "created_at": row[2],
            "body": row[3], "copies": row[4]} for row in rows]

    def _reconcile_reserves(self, connection, state, now):
        expired = [identity for identity, row in state["reserves"].items()
            if row.get("phase") == "pre_on" and (_time(row.get("admit_until")) or now) <= now]
        for identity in expired:
            del state["reserves"][identity]
        attempted = {identity: row for identity, row in state["reserves"].items()
            if row.get("phase") == "on_attempt"}
        if len(attempted) > 16:
            raise RequestBudgetUnavailable("ewelink_unresolved_duty_limit")
        rows = self._terminal_rows(connection, list(attempted)) if attempted else []
        released = []
        for identity, reserve in attempted.items():
            proof = _terminal_off_release(identity, reserve, rows, now)
            if proof is not None:
                del state["reserves"][identity]
                released.append({"execution_id": identity, **proof})
        if expired or released:
            # Persist before any later availability/capacity refusal. This is
            # accounting only: canonical lifecycle and device evidence stay put.
            self._append(state, action="active_duty_accounting_reconciled", detail={
                "expired_never_attempted": expired, "canonical_off_releases": released})

    def _admit_availability(self, scope, group, now):
        if not scope["category"]:
            return
        if (group is not None and scope["probe_group"] == group["id"]
                and (_time(scope["probe_until"]) or now) > now):
            return
        due = _time(scope["next_probe_at"])
        if group is None or due is None or now < due:
            raise RequestBudgetUnavailable("ewelink_provider_" + scope["category"] + "_hold")
        scope["probe_group"] = group["id"]
        scope["probe_until"] = (now + timedelta(seconds=GROUP_SECONDS)).isoformat()
        # Consume the probe slot before its first attempt; crash cannot free it.
        delay = 3600 if scope["category"] == "application_call_limit" else TRANSIENT_BACKOFF[
            min(max(scope["failures"]-1, 0), len(TRANSIENT_BACKOFF)-1)]
        scope["next_probe_at"] = (now + timedelta(seconds=delay)).isoformat()

    def dispatch(self, *, region, endpoint, send):
        """Bound caller waiting, including DNS and slow response bodies.

        A timed-out HTTP worker retains its transaction fence until it returns;
        it cannot hold the caller's hardware locks.  Only reads/expiry rotation
        run here, never an equipment command.  A delayed worker rechecks its
        monotonic deadline and live database transaction immediately before send.
        This is a local participant fence, not externally fenced provider egress.
        """
        pair = _private_pair.get()
        if pair is not None:
            # A mismatched facade must fail within the pair, never start a new
            # worker or borrow another group's accounting/fence connection.
            return pair.dispatch(self, region=region, endpoint=endpoint, send=send)
        if (_group.get() or {}).get("_private_pair") is not None:
            raise RequestBudgetUnavailable("ewelink_pair_capability_missing")
        if not _request_workers.acquire(blocking=False):
            raise RequestBudgetUnavailable("ewelink_request_workers_busy")
        result = queue.Queue(maxsize=1)
        context = copy_context()
        group = _group.get()
        deadline = min(time.monotonic() + REQUEST_SECONDS + 5,
            group["deadline"] if group else float("inf"))
        def work():
            try:
                value = context.run(self._dispatch, region=region, endpoint=endpoint,
                    send=send, deadline=deadline)
                result.put((True, value))
            except BaseException as exc:
                result.put((False, exc))
            finally:
                _request_workers.release()
        worker = threading.Thread(target=work, name="rootline-bounded-ewelink-read", daemon=True)
        try:
            worker.start()
        except BaseException:
            _request_workers.release()
            raise
        try:
            success, value = result.get(timeout=max(0, deadline-time.monotonic()))
        except queue.Empty:
            if group is not None:
                group["failed"] = True
            raise RequestBudgetUnavailable("ewelink_read_deadline_reached") from None
        if success:
            return value
        if group is not None and not isinstance(value, FullSnapshotRequired):
            group["failed"] = True
        raise value

    def _dispatch(self, *, region, endpoint, send, deadline):
        with self._worker_audit():
            return self._dispatch_with_fence(region=region, endpoint=endpoint,
                send=send, deadline=deadline)

    @contextmanager
    def _worker_audit(self):
        # Created INSIDE one worker; never shared with siblings or later calls.
        if _dispatch_audit.get() is not None:
            raise RequestBudgetUnavailable("ewelink_nested_audit_worker_rejected")
        session = {"owner": self, "thread": threading.get_ident(), "connection": None,
            "poisoned": False, "fence": None}
        token = _dispatch_audit.set(session)
        try:
            yield session
        finally:
            try:
                connection = session["connection"]
                if connection is not None:
                    try:
                        connection.close()
                    finally:
                        session["connection"] = None
            finally:
                _dispatch_audit.reset(token)

    def _dispatch_with_fence(self, *, region, endpoint, send, deadline):
        with self._locked() as connection:
            return self._dispatch_fenced(connection, region=region, endpoint=endpoint,
                send=send, deadline=deadline)

    def _dispatch_fenced(self, connection, *, region, endpoint, send, deadline, pair=None):
        def remaining():
            value = min(request_timeout(), deadline-time.monotonic())
            if value <= 0:
                raise RequestBudgetUnavailable("ewelink_read_deadline_reached")
            return value
        remaining()
        key = scope_digest(self.environ, region)
        group = _group.get()
        if group is not None and (group["scope"] != key or group["region"] != region):
            raise RequestBudgetUnavailable("ewelink_snapshot_scope_changed")
        _dispatch_audit.get()["fence"] = connection
        # Sample original deadlines immediately before admission; never reset them.
        from modules.telemetry.rootline_cycle_budget import on_deadline, work_deadline
        sampled_at = time.monotonic()
        cycle = on_deadline() if on_deadline() is not None else work_deadline()
        samples = {name: int(max(0, bound-sampled_at)*1000)
            for name, bound in (("dispatch_remaining_ms", deadline),
                ("group_remaining_ms", group.get("deadline") if group else None),
                ("cycle_remaining_ms", cycle))
            if isinstance(bound, (int, float)) and math.isfinite(bound)}
        try:
            state, now, counts = self._admission_preimage(connection, scope=key, region=region)
        except Exception as exc:
            from modules.telemetry.rootline_failure_diagnostics import sanitize_failure
            exc.failure_diagnostics = sanitize_failure({
                **getattr(exc, "failure_diagnostics", {}), **samples})
            raise
        if pair is None and not self._utc_preimage_counts(now):
            counts = None
        scope = state.get("scopes", {}).get(key)
        if group and group.get("routine_read") and scope and scope["category"]:
            own_probe = (scope.get("probe_group") == group["id"]
                and (_time(scope.get("probe_until")) or now) > now)
            due = _time(scope.get("next_probe_at"))
            if own_probe or (due is not None and now >= due):
                # Refresh can already own this probe. It remains charged once;
                # only the next GET changes to full family/thing/status.
                if endpoint != "/v2/user/refresh":
                    raise FullSnapshotRequired("ewelink_full_recovery_snapshot_required")
        self._reconcile_reserves(connection, state, now)
        scope = self._scope(state, key)
        optional = group.get("optional_purpose") if group else None
        purpose = optional["purpose"] if optional else None
        if optional:
            observations = state.setdefault("optional_observations", {})
            # Execution-bound keys expire only after their final eligible
            # window and any already admitted snapshot have elapsed. The two
            # account-wide manager keys remain, as do unknown legacy records.
            for old_key, old in tuple(observations.items()):
                expires = _time(old.get("expires_at"))
                if expires is not None and now > expires:
                    del observations[old_key]
            binding = optional["binding"]
            identity = key+":"+purpose+(":"+sha256(json.dumps(binding,
                sort_keys=True, separators=(",", ":")).encode()).hexdigest() if binding else "")
            prior = observations.get(identity, {})
            next_at = _time(prior.get("next_read_at")) or _time(optional.get("first_read_at"))
            last_at = _time(optional.get("last_read_at"))
            same_attempt = (optional.get("admission_token") is not None
                and prior.get("admission_token") == optional["admission_token"])
            if ((last_at is not None and now > last_at and prior.get("group_id") != group["id"]) or
                    (not same_attempt and prior.get("group_id") != group["id"]
                        and next_at is not None and now < next_at)):
                next_at = next_at or last_at
                self._append(state, action="optional_observation_suppressed", detail={
                    "scope": key, "purpose": purpose, "next_read_at": next_at.isoformat(),
                    "provider_attempted": False})
                raise OptionalObservationDeferred(next_at.isoformat())
            if not same_attempt and prior.get("group_id") != group["id"]:
                retry_at = now+timedelta(seconds=optional["interval_seconds"])
                if last_at is not None and now < last_at:
                    retry_at = min(retry_at, last_at)
                observations[identity] = {"group_id": group["id"],
                    "admission_token": optional.get("admission_token"),
                    "next_read_at": retry_at.isoformat(),
                    "expires_at": (last_at+timedelta(seconds=GROUP_SECONDS)).isoformat() if last_at else None}
            elif same_attempt:
                prior["group_id"] = group["id"]
        self._admit_availability(scope, group, now)
        count, recent = counts if counts is not None else self._counts(connection, now, scope=key, region=region)
        duty = _duty.get() or {}
        identity = str(duty.get("execution_id") or "")
        reserve = state["reserves"].get(identity)
        expected = group["expected_device"] if group else None
        bound = (reserve is not None and reserve["scope"] == key
            and reserve.get("region") == region and expected in reserve["read_devices"])
        if reserve is not None and not bound:
            raise RequestBudgetUnavailable("ewelink_active_duty_exhausted_or_mismatched")
        reserved = sum(row["remaining"] for row in state["reserves"].values())
        scoped_reserved = sum(row["remaining"] for row in state["reserves"].values()
            if row["scope"] == key and row.get("region") == region)
        from modules.telemetry.rootline_borehole_conditions import continuous_borehole
        continuous_optional = bool(bound and optional and continuous_borehole(duty))
        if bound and reserve["remaining"] == 0 and not continuous_optional:
            # Do not strand an unresolved device after a prolonged outage.
            # One refresh plus one whole snapshot may be replenished hourly,
            # only within existing capacity. This cannot restore ON authority.
            recovery_at = _time(reserve.get("recovery_due_at"))
            if (optional or reserve.get("phase") != "on_attempt"
                    or (recovery_at is not None and now < recovery_at)
                    or count+scoped_reserved+4 > LOCAL_ROLLING_LIMIT
                    or recent+reserved+4 > FIVE_MINUTE_LIMIT):
                raise RequestBudgetUnavailable("ewelink_active_recovery_capacity_deferred")
            reserve["remaining"] = 4
            reserve["recovery_due_at"] = (now+timedelta(hours=1)).isoformat()
            reserved += 4
            scoped_reserved += 4
        usable = bound and reserve["remaining"] > 0 and not continuous_optional
        if optional and group.get("optional_attempts", 0) >= 4:
            raise RequestBudgetUnavailable("ewelink_optional_snapshot_group_exhausted")
        if bound and not continuous_optional:
            # An admission only earmarks existing capacity. Per-send charging
            # remains authoritative; no old or failed attempt is refunded.
            groups = reserve.setdefault("optional_groups", {})
            groups = reserve["optional_groups"] = {identifier: item for identifier, item in groups.items()
                if (_time(item.get("until")) or now) > now}
            admitted = groups.get(group["id"]) if group else None
            held = sum(item["remaining"] for item in groups.values())
            if optional and admitted is None:
                if reserve["remaining"]-held < 8:
                    raise RequestBudgetUnavailable("ewelink_optional_shutdown_tail_protected")
                admitted = groups[group["id"]] = {"remaining": 4,
                    "until": (now+timedelta(seconds=GROUP_SECONDS)).isoformat()}
            elif admitted is not None:
                if admitted["remaining"] <= 0:
                    raise RequestBudgetUnavailable("ewelink_optional_snapshot_group_exhausted")
            elif reserve["remaining"]-held <= 0:
                raise RequestBudgetUnavailable("ewelink_active_snapshot_capacity_owned")
        else:
            admitted = None
            if optional and group.get("optional_admitted") is not True:
                if (count+scoped_reserved+4 > LOCAL_ROLLING_LIMIT
                        or recent+reserved+4 > FIVE_MINUTE_LIMIT):
                    raise RequestBudgetUnavailable("ewelink_optional_snapshot_capacity_unavailable")
        if count >= LOCAL_ROLLING_LIMIT or (not usable and count + scoped_reserved >= LOCAL_ROLLING_LIMIT):
            raise RequestBudgetUnavailable("ewelink_local_rolling_capacity_exhausted")
        if recent >= FIVE_MINUTE_LIMIT or (not usable and recent+reserved >= FIVE_MINUTE_LIMIT):
            raise RequestBudgetUnavailable("ewelink_local_five_minute_capacity_exhausted")
        pending = state.get("pending_attempt")
        if pending:
            # A committed intent with no completion is ambiguous.  Preserve
            # its charge and back off, never infer that the request failed.
            lost_at = _time(pending.get("recorded_at"))
            if lost_at is None or now < lost_at or now-lost_at < timedelta(seconds=GROUP_SECONDS):
                raise RequestBudgetUnavailable("ewelink_prior_attempt_unresolved")
        finished = _time(state.get("last_finished_at"))
        if finished is not None:
            elapsed = (now-finished).total_seconds()
            if elapsed < 0:
                raise RequestBudgetUnavailable("ewelink_dispatch_clock_reversed")
            delay = max(0, MIN_DISPATCH_INTERVAL-elapsed)
            if delay > MAX_PACE_WAIT_SECONDS or remaining() <= delay:
                raise RequestBudgetUnavailable("ewelink_dispatch_deadline_reached")
            if delay:
                self.sleep(delay)
        remaining()
        # Keep the transaction alive and prove its backend still owns the
        # fence immediately before committing intent and again before send.
        now = self._now(connection)
        attempt = uuid.uuid4().hex
        if usable:
            reserve["remaining"] -= 1
            if admitted is not None:
                admitted["remaining"] -= 1
        state["pending_attempt"] = {"id": attempt, "recorded_at": now.isoformat()}
        self._append(state, action="request_attempt_reserved", attempt_units=1,
            detail={"attempt_id": attempt, "scope": key, "region": region, "endpoint": endpoint,
                "execution_id": identity if usable or continuous_optional else None,
                "group_id": group["id"] if group else None})
        self._now(connection)
        remaining()
        if group is not None:
            group["budget"] = self
            if optional:
                group["optional_admitted"] = True
                group["optional_attempts"] = group.get("optional_attempts", 0)+1
        failure = None
        try:
            timeout = remaining()
            if pair is not None:
                timeout = pair.admit(endpoint, timeout)
            result = send(timeout)
            remaining()
            if pair is not None:
                pair.check_active()
        except Exception as exc:
            failure = getattr(exc, "provider_failure", None) or classify_failure()
            result = None
            caught = exc
        finished_at = self._now(connection)
        state["pending_attempt"] = None
        state["last_finished_at"] = finished_at.isoformat()
        if failure is not None:
            scope["failures"] += 1
            scope["generation"] += 1
            scope["category"] = failure["category"]
            delay = (3600 if failure["category"] == "application_call_limit"
                else max(failure["retry_after_seconds"], TRANSIENT_BACKOFF[
                    min(scope["failures"]-1, len(TRANSIENT_BACKOFF)-1)]))
            scope["next_probe_at"] = (finished_at+timedelta(seconds=delay)).isoformat()
            scope["probe_group"] = None
            scope["probe_until"] = None
        self._append(state, action="request_completed", detail={"attempt_id": attempt,
            "scope": key, "failure": failure, "outcome": "failed" if failure else "http_succeeded"})
        if failure is not None:
            raise caught
        if group is not None:
            group["successful_endpoints"].append(endpoint)
        return result

    def fail_snapshot(self, group):
        with self._locked() as connection:
            state = self._load(connection)
            scope = self._scope(state, group["scope"])
            if scope["category"] and scope.get("probe_group") != group["id"]:
                return  # Preserve a newer failure from another group.
            now = self._now(connection)
            category = scope["category"] or "snapshot_binding_or_normalization_error"
            scope["failures"] += 1
            scope["generation"] += 1
            delay = (3600 if category == "application_call_limit" else
                TRANSIENT_BACKOFF[min(scope["failures"]-1, len(TRANSIENT_BACKOFF)-1)])
            scope.update(category=category, probe_group=None, probe_until=None,
                next_probe_at=(now+timedelta(seconds=delay)).isoformat())
            self._append(state, action="snapshot_validation_failed", detail={
                "scope": group["scope"], "group_id": group["id"], "category": category})

    def complete_snapshot(self, group):
        if (group.get("failed") or group.get("normalized_complete") is not True
                or group.get("successful_endpoints", [])[-3:] != [
                    "/v2/family", "/v2/device/thing", "/v2/device/thing/status"]):
            return
        with self._locked() as connection:
            state = self._load(connection)
            scope = self._scope(state, group["scope"])
            now = self._now(connection)
            if scope["category"] and scope["probe_group"] == group["id"]:
                if ((_time(scope["probe_until"]) or now) <= now
                        or time.monotonic() >= group["deadline"]):
                    raise RequestBudgetUnavailable("ewelink_probe_completion_late")
                scope.update(category=None, failures=0, probe_group=None,
                    probe_until=None, next_probe_at=None)
                self._append(state, action="complete_snapshot_restored_availability",
                    detail={"scope": group["scope"], "group_id": group["id"],
                        "provider_remaining": "Unknown"})

    def finish_optional_group(self, group):
        """Release unused admission headroom, never charged request units."""
        duty = _duty.get() or {}
        identity = str(duty.get("execution_id") or "")
        if not identity:
            return
        with self._locked() as connection:
            state = self._load(connection)
            reserve = state["reserves"].get(identity)
            groups = reserve.get("optional_groups", {}) if reserve else {}
            if groups.pop(group["id"], None) is not None:
                self._append(state, action="optional_snapshot_finished", detail={
                    "execution_id": identity, "group_id": group["id"], "attempt_units_refunded": 0})

    def reserve_for_on(self, *, execution_id, device_id, channel, device_type, region):
        key = scope_digest(self.environ, region)
        amount = DUTY_CAPACITY.get(device_type)
        if not amount or not execution_id:
            raise RequestBudgetUnavailable("ewelink_active_duty_binding_invalid")
        with self._locked() as connection:
            state, now, counts = self._admission_preimage(connection, scope=key, region=region)
            # Only a never-authorized sender can age out.  begin_on durably
            # changes phase before network I/O; active/ambiguous reserves never
            # expire and require exact fresh OFF proof.
            self._reconcile_reserves(connection, state, now)
            if self._scope(state, key)["category"]:
                raise RequestBudgetUnavailable("ewelink_active_duty_availability_hold")
            binding = {"scope": key, "region": region, "device_id": str(device_id), "channel": int(channel),
                "device_type": device_type}
            existing = state["reserves"].get(execution_id)
            if existing:
                raise RequestBudgetUnavailable("ewelink_active_duty_already_reserved")
            count, recent = (counts if self._utc_preimage_counts(now)
                else self._counts(connection, now, scope=key, region=region))
            reserved = sum(row["remaining"] for row in state["reserves"].values())
            scoped_reserved = sum(row["remaining"] for row in state["reserves"].values()
                if row["scope"] == key and row.get("region") == region)
            if count+scoped_reserved+amount > LOCAL_ROLLING_LIMIT or recent+reserved+amount > FIVE_MINUTE_LIMIT:
                raise RequestBudgetUnavailable("ewelink_active_duty_capacity_unavailable")
            if len(state["reserves"]) >= 16:
                raise RequestBudgetUnavailable("ewelink_unresolved_duty_limit")
            devices = [str(device_id)]
            if device_type == "fertilizer_injection_valve":
                from modules.telemetry.rootline_device_registry import get_device_contract
                devices.append(get_device_contract("B12345")["device_id"])
            state["reserves"][execution_id] = {**binding, "remaining": amount,
                "reserved_at": now.isoformat(), "read_devices": sorted(set(devices)),
                "phase": "pre_on", "permit": uuid.uuid4().hex,
                "admit_until": (now+timedelta(seconds=30)).isoformat()}
            self._append(state, action="active_duty_reserved", detail={"execution_id": execution_id})
            return state["reserves"][execution_id]["permit"]

    def begin_on(self, *, execution_id, permit, device_id, channel,
                 claimed_at=None, primary_stop_deadline=None, continuous=False):
        """No pacing/probe wait at the command edge; a refusal proves no send."""
        with self._locked() as connection:
            state = self._load(connection)
            now = self._now(connection)
            reserve = state["reserves"].get(execution_id)
            if (not reserve or not permit or reserve.get("permit") != permit
                    or reserve["device_id"] != device_id or reserve["channel"] != channel
                    or reserve.get("phase") != "pre_on" or reserve["remaining"] < 6
                    or (_time(reserve.get("admit_until")) or now) <= now
                    or self._scope(state, reserve["scope"])["category"]):
                raise RequestBudgetUnavailable("ewelink_final_on_capacity_unavailable")
            command_until = _time(reserve["admit_until"])
            if continuous and (claimed_at is None or device_id != "1002851416" or channel != 1
                    or reserve.get("device_type") != "borehole_pump_power"):
                raise RequestBudgetUnavailable("ewelink_continuous_binding_invalid")
            if claimed_at is not None or primary_stop_deadline is not None:
                claim, primary = _time(claimed_at), _time(primary_stop_deadline)
                if claim is None or now < claim or (primary is None and not continuous):
                    raise RequestBudgetUnavailable("ewelink_final_on_deadline_invalid")
                if continuous and (device_id != "1002851416" or channel != 1 or primary is not None):
                    raise RequestBudgetUnavailable("ewelink_continuous_binding_invalid")
                command_until = min(command_until, claim+timedelta(seconds=30))
                if primary is not None:
                    command_until = min(command_until, primary)
            # Carry an independent monotonic bound over the accounting commit;
            # the returned deadline is checked immediately beside the HTTP call.
            edge_deadline = time.monotonic() + (command_until-now).total_seconds()
            if edge_deadline <= time.monotonic():
                raise RequestBudgetUnavailable("ewelink_final_on_deadline_reached")
            reserve["phase"] = "on_attempt"
            self._append(state, action="active_duty_on_attempt_reserved",
                detail={"execution_id": execution_id})
            if self._now(connection) >= command_until or time.monotonic() >= edge_deadline:
                raise RequestBudgetUnavailable("ewelink_final_on_deadline_reached")
            return edge_deadline

    def release_after_canonical_terminal(self, execution_id):
        """Revalidate one no-send duty after unlock on the existing terminal rail."""
        with self._locked(read_committed=True) as connection:
            state = self._load(connection)
            reserve = state["reserves"].get(execution_id)
            if reserve is None:
                return True
            now = self._now(connection)
            rows = self._terminal_rows(connection, [execution_id])
            proof = _terminal_off_release(execution_id, reserve, rows, now)
            if proof is None:
                return False
            del state["reserves"][execution_id]
            self._append(state, action="active_duty_accounting_reconciled", detail={
                "expired_never_attempted": [],
                "canonical_off_releases": [{"execution_id": execution_id, **proof}]})
            return True

    def release_after_off(self, execution_id, *, device_id, channel, evidence):
        if (not isinstance(evidence, dict) or evidence.get("authoritative") is not True
                or evidence.get("state") != "OFF" or evidence.get("device_id") != device_id
                or evidence.get("channel") != channel or not evidence.get("response_digest")):
            return
        with self._locked() as connection:
            state = self._load(connection)
            reserve = state["reserves"].get(execution_id)
            if reserve is None:
                return
            observed = _time(evidence.get("retrieved_at"))
            now = self._now(connection)
            if (reserve["device_id"] != device_id or reserve["channel"] != channel
                    or observed is None or not timedelta(0) <= now-observed <= timedelta(seconds=60)
                    or observed < _time(reserve["reserved_at"])):
                raise RequestBudgetUnavailable("ewelink_duty_shutdown_binding_unproven")
            del state["reserves"][execution_id]
            self._append(state, action="active_duty_off_verified", detail={
                "execution_id": execution_id, "response_digest": evidence["response_digest"]})


class _PreparedNoSendClients:
    """Two invocation-private idle frontends; no fence or snapshot is prepared."""
    def __init__(self, source, binding):
        from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
        self.source, self.binding = deepcopy(dict(source)), deepcopy(dict(binding))
        self._gate = threading.Lock()
        self._clients = []
        self._spent = False
        try:
            for _ in range(2):
                request_timeout()
                connection = connect_bounded_rootline_postgres(
                    database_url=self.source.get("DATABASE_URL"), read_only=False,
                    reuse_local_settings=True, read_committed=True,
                    native_begin_read_committed=True,
                    connect_deadline_seconds=min(5.0, request_timeout()))
                self._clients.append(connection)
                connection.rollback()
                self._verify_idle(connection)
            if self._clients[0]._connection is self._clients[1]._connection:
                raise RequestBudgetUnavailable("ewelink_prepared_clients_not_distinct")
            request_timeout()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _verify_idle(connection):
        from modules.oom_sakkie.bounded_postgres_read import (
            _CycleBudgetConnection, _require_native_begin_state)
        if (type(connection) is not _CycleBudgetConnection
                or connection._connection is not connection._native_begin_connection
                or connection._reuse_disabled):
            raise RequestBudgetUnavailable("ewelink_prepared_client_identity_unproven")
        _require_native_begin_state(connection._connection, idle=True)

    def take(self, source, binding):
        with self._gate:
            if (self._spent or len(self._clients) != 2
                    or dict(source) != self.source or dict(binding) != self.binding):
                raise RequestBudgetUnavailable("ewelink_prepared_clients_unavailable")
            for connection in self._clients:
                self._verify_idle(connection)
            clients, self._clients = self._clients, []
            self._spent = True
            return clients

    def close(self):
        with self._gate:
            clients, self._clients = self._clients, []
            self._spent = True
        # Transferred clients belong exclusively to the worker, including late drain.
        for connection in clients:
            try:
                connection.close()
            except Exception:
                pass


class _NoSendPair:
    """Single-use capability for one prepared, locked two-GET invocation.

    The parent owns hardware locks; this worker owns a separate global-fence
    transaction and one private audit frontend client. Abandonment serializes
    admission, not the socket: an already-admitted read can drain after unlock.
    """
    _ENDPOINTS = ("/v2/device/thing", "/v2/device/thing/status")

    def __init__(self, *, source, binding, token_identity, group, prepared_clients=None):
        if (_private_pair.get() is not None or _group.get() is not group
                or group.get("_private_pair") is not None):
            raise RequestBudgetUnavailable("ewelink_pair_context_rejected")
        self.prepared_clients = prepared_clients
        self.source = MappingProxyType(deepcopy(dict(source)))
        self.binding = MappingProxyType(deepcopy(dict(binding)))
        self.token_identity = tuple(token_identity)
        self.group, self.duty = group, deepcopy(_duty.get())
        self.group_identity = tuple(group.get(key) for key in
            ("id", "scope", "region", "expected_device", "deadline"))
        self.deadline = group["deadline"]
        if (not self.token_identity or not self.binding.get("execution_id") or
                not self.duty or self.duty.get("execution_id") != self.binding["execution_id"] or
                group["expected_device"] != self.binding.get("device_id")):
            raise RequestBudgetUnavailable("ewelink_pair_binding_rejected")
        self.gate = threading.Lock()
        self.started = self.abandoned = self.failed = False
        self.phase = 0
        self.inflight = False
        self.owner = self.thread = self.fence = self.backend = None
        group["_private_pair"] = self

    def abandon(self, *, failed=True):
        # The caller runs this before returning to its hardware-lock owner.
        with self.gate:
            self.abandoned = True
            if failed:
                self.failed = True

    def _check_locked(self):
        if (self.abandoned or self.failed or time.monotonic() >= self.deadline
                or _private_pair.get() is not self or threading.get_ident() != self.thread
                or _group.get() is not self.group or self.group.get("_private_pair") is not self
                or _duty.get() != self.duty
                or tuple(self.group.get(key) for key in
                    ("id", "scope", "region", "expected_device", "deadline")) != self.group_identity):
            self.failed = self.group["failed"] = True
            raise RequestBudgetUnavailable("ewelink_pair_context_rejected")

    def check_active(self):
        with self.gate:
            self._check_locked()

    def admit(self, endpoint, timeout):
        with self.gate:
            self._check_locked()
            if self.phase >= len(self._ENDPOINTS) or endpoint != self._ENDPOINTS[self.phase] or self.inflight:
                self.failed = self.group["failed"] = True
                raise RequestBudgetUnavailable("ewelink_pair_endpoint_rejected")
            # This is the linearization point versus caller abandonment. No I/O
            # occurs under the gate; an admitted socket may begin/finish later.
            self.inflight = True
            return min(timeout, self.deadline-time.monotonic())

    def dispatch(self, facade, *, region, endpoint, send):
        with self.gate:
            self._check_locked()
            expected = dict(self.source)
            if endpoint == "/v2/device/thing/status":
                expected["EWELINK_EXPECTED_DEVICE_ID"] = self.binding["device_id"]
            if (self.phase >= len(self._ENDPOINTS) or self.inflight or endpoint != self._ENDPOINTS[self.phase]
                    or region != self.group["region"] or dict(facade.environ) != expected
                    or facade.database_url != self.owner.database_url
                    or facade.connect_factory is not self.owner.connect_factory):
                self.failed = self.group["failed"] = True
                raise RequestBudgetUnavailable("ewelink_pair_facade_rejected")
        try:
            value = self.owner._dispatch_fenced(self.fence, region=region,
                endpoint=endpoint, send=send, deadline=self.deadline, pair=self)
            with self.gate:
                self._check_locked()
                if not self.inflight:
                    raise RequestBudgetUnavailable("ewelink_pair_admission_unproven")
                self.inflight = False
                self.phase += 1
            return value
        except BaseException:
            self.group["failed"] = True  # HTTP/accounting failure already owns its hold.
            self.abandon()
            raise

    def _work(self, read):
        if _private_pair.get() is not None:
            raise RequestBudgetUnavailable("ewelink_nested_pair_rejected")
        self.thread = threading.get_ident()
        self.owner = RequestBudget(self.source)
        token = _private_pair.set(self)
        try:
            self.check_active()
            clients = (self.prepared_clients.take(self.source, self.binding)
                       if self.prepared_clients is not None else None)
            try:
                with self.owner._worker_audit() as session:
                    if clients is not None:
                        session["connection"] = clients[1]
                    with self.owner._locked(prepared=clients[0] if clients else None) as connection:
                        session["fence"] = connection
                        value = read()
                        self.check_active()
                        if self.phase != len(self._ENDPOINTS):
                            raise RequestBudgetUnavailable("ewelink_pair_incomplete")
            finally:
                close_error = None
                for connection in clients or []:
                    try:
                        connection.close()
                    except Exception as exc:
                        close_error = exc
                if close_error is not None:
                    raise close_error
            # Output is published only after successful audit/fence cleanup.
            self.check_active()
            return value
        finally:
            _private_pair.reset(token)

    def run(self, read):
        with self.gate:
            if self.started or self.abandoned or self.failed:
                raise RequestBudgetUnavailable("ewelink_pair_consumed")
            self.started = True
        if not _request_workers.acquire(blocking=False):
            self.abandon()
            raise RequestBudgetUnavailable("ewelink_request_workers_busy")
        result = queue.Queue(maxsize=1)
        context = copy_context()
        def work():
            try:
                outcome = (True, context.run(self._work, read))
            except BaseException as exc:
                outcome = (False, exc)
            finally:
                _request_workers.release()
            result.put(outcome)
        worker = threading.Thread(target=work, name="rootline-bounded-ewelink-read", daemon=True)
        success = False
        try:
            try:
                worker.start()
            except BaseException:
                _request_workers.release()
                raise
            try:
                success, value = result.get(timeout=max(0, self.deadline-time.monotonic()))
            except queue.Empty:
                self.group["failed"] = True
                raise RequestBudgetUnavailable("ewelink_read_deadline_reached") from None
            if time.monotonic() >= self.deadline:
                success = False
                raise RequestBudgetUnavailable("ewelink_read_deadline_reached")
            if not success:
                raise value
            return value
        finally:
            self.abandon(failed=not success)


def _ordinary_terminal_identity(record, records, execution):
    """Recover only the two fields overwritten by the existing event writer."""
    terminal = record["body"]
    action = terminal["action"]
    pairs = {(None, None), (action, None)}
    for predecessor in records:
        body = predecessor["body"]
        if (body.get("action") in _CLAIM_ACTIONS | _ACTIVE_ACTIONS | _OUTCOME_ACTIONS
                and body.get("execution_id") == terminal["execution_id"]
                and _time(predecessor["created_at"]) <= _time(record["created_at"])):
            pairs.add((body["action"], predecessor["event_id"]))
            pairs.add((action, predecessor["event_id"]))
    material = {key: value for key, value in terminal.items() if key not in {"action", "event_id"}}
    for prior_action, prior_id in pairs:
        original = dict(material)
        if prior_action is not None:
            original["action"] = prior_action
        if prior_id is not None:
            original["event_id"] = prior_id
        if execution._event_id(action, original) == record["event_id"]:
            return True
    return False


def _terminal_off_release(identity, reserve, records, now):
    """Discharge an old read duty from originally fresh canonical terminal OFF.

    This proof never authorizes a command, refreshes present device truth or
    changes the terminal's physical/business result. Another execution, even on
    the same output, cannot inherit it.
    """
    from modules.telemetry import rootline_irrigation_execution_store as execution
    rows = [row for row in records if isinstance(row.get("body"), dict)
        and row["body"].get("execution_id") == identity]
    if not rows or reserve.get("phase") != "on_attempt":
        return None
    if any(row.get("execution_id") != identity or row.get("event_id") != row["body"].get("event_id")
            or not row.get("event_id") or _time(row.get("created_at")) is None
            or _time(row["created_at"]) > now or type(row.get("copies")) is not int
            or row["copies"] < 1 for row in rows):
        return None
    bodies = [row["body"] for row in rows]
    claims = [row for row in rows if row["body"].get("action") in _CLAIM_ACTIONS]
    if len(claims) != 1 or claims[0]["copies"] != 1:
        return None
    if any(row["copies"] != 1 for row in rows if row["body"].get("action") in _OUTCOME_ACTIONS):
        return None
    claim = claims[0]["body"]
    kind = reserve.get("device_type")
    borehole = kind == "borehole_pump_power"
    auxiliary = kind in {"fertilizer_mixer", "fertilizer_injection_valve"}
    claim_action = ("claim_borehole_before_on" if borehole else
        "claim_auxiliary_before_on" if auxiliary else "claim_before_on")
    device = claim.get("device_id") or ("1002851416" if claim.get("device_key") ==
        "ewelink:ewelink_owner_account:1002851416:1" else None)
    channel = claim.get("channel") or (1 if borehole and device else None)
    reserved, claimed, claim_recorded = map(_time, (
        reserve.get("reserved_at"), claim.get("claimed_at"), claims[0]["created_at"]))
    if (kind not in DUTY_CAPACITY or claim.get("action") != claim_action
            or claim.get("event_id") != execution._event_id(claim_action, claim)
            or not reserve.get("permit") or claim.get("provider_capacity_permit") != reserve["permit"]
            or device != reserve.get("device_id") or type(channel) is not int
            or channel != reserve.get("channel")
            or (auxiliary and claim.get("device_type") != kind)
            or None in (reserved, claimed, claim_recorded)
            or not claimed <= claim_recorded or not reserved <= claim_recorded):
        return None
    for record in sorted(rows, key=lambda row: _time(row["created_at"]), reverse=True):
        terminal = record["body"]
        action = terminal.get("action")
        if action not in _TERMINAL_ACTIONS or record["copies"] != 1:
            continue
        if terminal.get("shutdown_verified") is not True or not execution._managed_claim_matches(
                bodies, terminal, {"claim": claim_action}):
            continue
        if action == "record_execution_not_dispatched":
            terminal_valid = execution._verified_not_dispatched(terminal, bodies)
        elif borehole:
            terminal_valid = (execution._verified_borehole_completion(terminal)
                or execution._verified_borehole_abort(terminal, bodies))
        else:
            terminal_valid = execution._terminal_closes_active(terminal, auxiliary=auxiliary)
        if not terminal_valid:
            continue
        if action not in {"record_execution_not_dispatched", "record_borehole_aborted"} \
                and not _ordinary_terminal_identity(record, rows, execution):
            continue
        recorded = _time(record["created_at"])
        if any(_time(later["created_at"]) >= recorded and later is not record
                and (later["body"].get("action") in _ACTIVE_ACTIONS
                    or later["body"].get("shutdown_verified") is False
                    or (later["body"].get("action") in _OUTCOME_ACTIONS and
                        (later["body"].get("on_outcome") or {}).get("provider_command_attempted") is not False))
                for later in rows):
            continue
        evidence = terminal.get("provider_final_off_evidence" if borehole and
            action != "record_execution_not_dispatched" else "shutdown_evidence")
        if not isinstance(evidence, dict):
            continue
        observed = _time(evidence.get("retrieved_at"))
        digest = evidence.get("evidence_id") or evidence.get("response_digest")
        finished_key = ("retired_at" if action == "record_execution_not_dispatched" else
            "aborted_at" if action == "record_borehole_aborted" else "completed_at")
        finished = _time(terminal.get(finished_key)) if finished_key in terminal else recorded
        locked_terminal = action in {"record_execution_not_dispatched", "record_borehole_aborted"}
        if locked_terminal:
            # PostgreSQL now()/created_at is this protected transaction's start,
            # before its fresh read. The existing family verifier binds the
            # store-owned read/finish clocks to the actual canonical preimages.
            started = _time(terminal.get("read_started_at" if action ==
                "record_execution_not_dispatched" else "abort_read_started_at"))
            chronology = (observed is not None and finished is not None and started is not None
                and max(reserved, claimed, claim_recorded) <= recorded <= started <= observed <= finished <= now
                and finished-observed <= timedelta(seconds=60)
                and finished-started <= timedelta(seconds=GROUP_SECONDS+5)
                and finished-recorded <= timedelta(seconds=GROUP_SECONDS+10))
        else:
            chronology = (observed is not None and finished is not None
                and max(reserved, claimed, claim_recorded) <= observed <= finished <= recorded <= now
                and recorded-observed <= timedelta(seconds=60))
        if (evidence.get("authoritative") is not True or evidence.get("state") != "OFF"
                or evidence.get("device_id") != device or type(evidence.get("channel")) is not int
                or evidence["channel"] != channel
                or evidence.get("execution_id", identity) != identity
                or not execution._sha256_text(digest) or not chronology
                or ("observed_at" in evidence and _time(evidence["observed_at"]) != observed)):
            continue
        return {"terminal_event_id": record["event_id"], "response_digest": digest}
    return None


def _time(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


class _NoSendStatus(_NoSendPair):
    """One fresh output GET after invocation-local metadata preparation."""
    _ENDPOINTS = ("/v2/device/thing/status",)
