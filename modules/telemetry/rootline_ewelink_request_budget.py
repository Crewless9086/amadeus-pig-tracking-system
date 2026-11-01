"""Shared, conservative eWeLink demand control on the existing audit rail.

No provider balance is inferred from this ledger.  It measures this application's
participating requests from coverage_start; other clients and older traffic are
Unknown.  OFF is not an eWeLink API operation and never enters this gate.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from contextvars import ContextVar, copy_context
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from email.utils import parsedate_to_datetime
import json
import os
import time
import threading
import queue
import uuid

EVENT_SOURCE = "rootline_provider_availability"
LEDGER_ID = "ROOTLINE-EWELINK-REQUEST-BUDGET-V1"
GLOBAL_SEND_LOCK = 1874320915
LOCAL_ROLLING_LIMIT = 40000
ROLLING_DAYS = 31
FIVE_MINUTE_LIMIT = 250
MIN_DISPATCH_INTERVAL = 1.0
REQUEST_SECONDS = 15.0
GROUP_SECONDS = 60.0
MAX_PACE_WAIT_SECONDS = 1.1
TRANSIENT_BACKOFF = (60, 300, 900, 3600)
# Whole three-GET snapshots: routine duty plus a finite initial recovery
# allowance. Injector routine duty covers two overlapping minute workers, each
# with the existing outer/inner supervision pass. Longer unresolved recovery
# uses the separately bounded hourly four-attempt replenishment below.
DUTY_SNAPSHOTS = {
    "irrigation_zone_valve": (1 + 2*(1+2) + 1 + 1, 6),
    "fertilizer_mixer": (1 + 1, 5),
    "fertilizer_injection_valve": (1 + 1 + 2*2*2 + 1, 10),
    "borehole_pump_power": (1 + 1, 5)}
DUTY_REFRESH_ALLOWANCE = {"irrigation_zone_valve": 3, "fertilizer_mixer": 3,
    "fertilizer_injection_valve": 1, "borehole_pump_power": 3}
DUTY_CAPACITY = {kind: 3*sum(bounds)+DUTY_REFRESH_ALLOWANCE[kind]
    for kind,bounds in DUTY_SNAPSHOTS.items()}
_duty = ContextVar("rootline_ewelink_duty", default=None)
_group = ContextVar("rootline_ewelink_snapshot", default=None)
_optional_observation = ContextVar("rootline_ewelink_optional_observation", default=None)
OPTIONAL_OBSERVATION_SECONDS = {"mixer_readiness": 1800, "mixer_readiness_delivery": 1800}
_request_workers = threading.BoundedSemaphore(2)
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


class RequestBudgetUnavailable(RuntimeError):
    """Sanitized local refusal; never an authentication failure."""


class OptionalObservationDeferred(RequestBudgetUnavailable):
    """No provider attempt; never evidence that a device or account failed."""
    def __init__(self, next_read_at):
        super().__init__("ewelink_optional_observation_deferred")
        self.next_read_at = next_read_at


@contextmanager
def optional_observation(purpose):
    if purpose not in OPTIONAL_OBSERVATION_SECONDS:
        raise ValueError("unregistered_optional_observation")
    token = _optional_observation.set(purpose)
    try:
        yield
    finally:
        _optional_observation.reset(token)


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
def snapshot_group(*, expected_device, environ, region):
    """Only a complete fresh authenticated device snapshot may heal a hold."""
    old = _group.get()
    if old is not None:
        raise RequestBudgetUnavailable("ewelink_nested_snapshot_rejected")
    deadline = time.monotonic() + GROUP_SECONDS
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
    prepare = getattr(transport, "prepare_execution_capacity", None)
    if prepare is None:
        return True
    try:
        execution["provider_capacity_permit"] = prepare(execution)
        return bool(execution["provider_capacity_permit"])
    except Exception:
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

    def _connect(self):
        if self.connect_factory is not None:
            return self.connect_factory()
        from modules.oom_sakkie.bounded_postgres_read import (
            ROOTLINE_CONNECT_DEADLINE_SECONDS, connect_bounded_rootline_postgres)
        # Acquisition includes the transaction-local settings required by the
        # pooler. Reuse ROOTLINE's bound without extending a shorter read duty.
        return connect_bounded_rootline_postgres(database_url=self.database_url,
            read_only=False, connect_deadline_seconds=min(
                ROOTLINE_CONNECT_DEADLINE_SECONDS, request_timeout()))

    @contextmanager
    def _locked(self):
        try:
            with self._connect() as connection:
                locked = connection.execute("select pg_try_advisory_xact_lock(%s)",
                    (GLOBAL_SEND_LOCK,)).fetchone()[0]
                if not locked:
                    raise RequestBudgetUnavailable("ewelink_dispatch_busy")
                yield connection
        except RequestBudgetUnavailable:
            raise
        except Exception as exc:
            if hasattr(exc, "provider_failure"):
                raise
            raise RequestBudgetUnavailable("ewelink_request_accounting_unavailable") from None

    @staticmethod
    def _now(connection):
        return connection.execute("select clock_timestamp()").fetchone()[0]

    def _load(self, connection):
        row = connection.execute("""select review_json->'ewelink_request_budget'
            from public.sam_live_stock_conversation_review_events
            where chatwoot_conversation_id=%s and event_source=%s
            order by created_at desc,review_event_id desc limit 1""",
            (LEDGER_ID, EVENT_SOURCE)).fetchone()
        if row:
            state = row[0].get("state")
            if not isinstance(state, dict) or state.get("version") != 1:
                raise RequestBudgetUnavailable("ewelink_request_ledger_invalid")
            return state
        now = self._now(connection)
        return {"version": 1, "coverage_start": now.isoformat(),
            "prior_provider_usage": "Unknown", "provider_remaining": "Unknown",
            "provider_entitlement": "Unknown", "external_clients_counted": False,
            "scopes": {}, "reserves": {}, "last_finished_at": None,
            "pending_attempt": None}

    def _counts(self, connection, now, *, scope=None, region=None):
        row = connection.execute("""select
            coalesce(sum(case when cast(%s as text) is null or
                (review_json->'ewelink_request_budget'->'detail'->>'scope'=%s and
                 review_json->'ewelink_request_budget'->'detail'->>'region'=%s)
                then (review_json->'ewelink_request_budget'->>'attempt_units')::int else 0 end),0),
            coalesce(sum(case when created_at >= %s then
                (review_json->'ewelink_request_budget'->>'attempt_units')::int else 0 end),0)
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
        with self._connect() as audit:
            result, status = record_sam_live_stock_review_event(event,
                database_url=self.database_url or "injected-local-connection",
                connect_factory=lambda: nullcontext(audit), created_at=self._now(audit))
            if status >= 400 or result.get("success") is not True:
                raise RequestBudgetUnavailable("ewelink_request_accounting_unavailable")
            actual = audit.execute("""select review_json->'ewelink_request_budget'
                from public.sam_live_stock_conversation_review_events where review_event_id=%s""",
                (identity,)).fetchone()
            if not actual or actual[0] != payload:
                raise RequestBudgetUnavailable("ewelink_request_accounting_unproven")

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
        if group is not None:
            group["failed"] = True
        raise value

    def _dispatch(self, *, region, endpoint, send, deadline):
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
        with self._locked() as connection:
            state = self._load(connection)
            now = self._now(connection)
            self._reconcile_reserves(connection, state, now)
            scope = self._scope(state, key)
            purpose = group.get("optional_purpose") if group else None
            if purpose:
                observations = state.setdefault("optional_observations", {})
                identity = key+":"+purpose
                prior = observations.get(identity, {})
                next_at = _time(prior.get("next_read_at"))
                if prior.get("group_id") != group["id"] and next_at is not None and now < next_at:
                    self._append(state, action="optional_observation_suppressed", detail={
                        "scope": key, "purpose": purpose, "next_read_at": next_at.isoformat(),
                        "provider_attempted": False})
                    raise OptionalObservationDeferred(next_at.isoformat())
                if prior.get("group_id") != group["id"]:
                    observations[identity] = {"group_id": group["id"],
                        "next_read_at": (now+timedelta(seconds=OPTIONAL_OBSERVATION_SECONDS[purpose])).isoformat()}
            self._admit_availability(scope, group, now)
            count, recent = self._counts(connection, now, scope=key, region=region)
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
            if bound and reserve["remaining"] == 0:
                # Do not strand an unresolved device after a prolonged outage.
                # One refresh plus one whole snapshot may be replenished hourly,
                # only within existing capacity. This cannot restore ON authority.
                recovery_at = _time(reserve.get("recovery_due_at"))
                if (reserve.get("phase") != "on_attempt"
                        or (recovery_at is not None and now < recovery_at)
                        or count+scoped_reserved+4 > LOCAL_ROLLING_LIMIT
                        or recent+reserved+4 > FIVE_MINUTE_LIMIT):
                    raise RequestBudgetUnavailable("ewelink_active_recovery_capacity_deferred")
                reserve["remaining"] = 4
                reserve["recovery_due_at"] = (now+timedelta(hours=1)).isoformat()
                reserved += 4
                scoped_reserved += 4
            usable = bound and reserve["remaining"] > 0
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
            state["pending_attempt"] = {"id": attempt, "recorded_at": now.isoformat()}
            self._append(state, action="request_attempt_reserved", attempt_units=1,
                detail={"attempt_id": attempt, "scope": key, "region": region, "endpoint": endpoint,
                    "execution_id": identity if usable else None,
                    "group_id": group["id"] if group else None})
            self._now(connection)
            remaining()
            if group is not None:
                group["budget"] = self
            failure = None
            try:
                result = send(remaining())
                remaining()
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

    def reserve_for_on(self, *, execution_id, device_id, channel, device_type, region):
        key = scope_digest(self.environ, region)
        amount = DUTY_CAPACITY.get(device_type)
        if not amount or not execution_id:
            raise RequestBudgetUnavailable("ewelink_active_duty_binding_invalid")
        with self._locked() as connection:
            state = self._load(connection)
            now = self._now(connection)
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
            count, recent = self._counts(connection, now, scope=key, region=region)
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
                 claimed_at=None, primary_stop_deadline=None):
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
            if claimed_at is not None or primary_stop_deadline is not None:
                claim, primary = _time(claimed_at), _time(primary_stop_deadline)
                if claim is None or primary is None or now < claim:
                    raise RequestBudgetUnavailable("ewelink_final_on_deadline_invalid")
                command_until = min(command_until, claim+timedelta(seconds=30), primary)
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
