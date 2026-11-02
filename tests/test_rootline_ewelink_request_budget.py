"""Production request admission with synthetic provider/database boundaries."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import threading
import time

import pytest

from modules.telemetry import rootline_ewelink_request_budget as budget
from modules.telemetry.rootline_ewelink_oauth import OAuthFailure

NOW = datetime(2026, 10, 31, 18, 0, tzinfo=timezone.utc)
ENV = {"EWELINK_CLIENT_ID": "synthetic-application"}


class Backend:
    def __init__(self):
        self.now = NOW
        self.state = None
        self.events = []
        self.lock = threading.Lock()
        self.live = True
        self.terminal_records = []

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


class MemoryBudget(budget.RequestBudget):
    """Replace persistence only; exercise the real admission/probe/send logic."""
    def __init__(self, backend=None, environ=None):
        self.backend = backend or Backend()
        super().__init__(environ or ENV, sleeper=self.backend.advance)

    @contextmanager
    def _locked(self):
        if not self.backend.lock.acquire(blocking=False):
            raise budget.RequestBudgetUnavailable("ewelink_dispatch_busy")
        try:
            yield self.backend
        finally:
            self.backend.lock.release()

    def _now(self, connection):
        if not connection.live:
            raise budget.RequestBudgetUnavailable("database_connection_lost")
        return connection.now

    def _load(self, connection):
        return deepcopy(connection.state or {"version": 1,
            "coverage_start": connection.now.isoformat(), "provider_remaining": "Unknown",
            "prior_provider_usage": "Unknown", "provider_entitlement": "Unknown",
            "external_clients_counted": False, "scopes": {}, "reserves": {},
            "last_finished_at": None, "pending_attempt": None})

    def _counts(self, connection, now, *, scope=None, region=None):
        return (sum(row["units"] for row in connection.events if row["at"] >= now-timedelta(days=31)
            and (scope is None or row["detail"].get("scope") == scope and row["detail"].get("region") == region)),
            sum(row["units"] for row in connection.events if row["at"] >= now-timedelta(minutes=5)))

    def _append(self, state, *, action, attempt_units=0, detail=None):
        self.backend.state = deepcopy(state)
        self.backend.events.append({"action": action, "units": attempt_units,
            "at": self.backend.now, "detail": deepcopy(detail or {})})

    def _terminal_rows(self, connection, identities):
        return deepcopy([row for row in connection.terminal_records
            if row.get("execution_id") in identities])


def snapshot(client, *, device="100204e9bc", region="eu", send=None):
    observed = []
    def success(_timeout):
        observed.append(client.backend.now)
        return {"ok": True}
    with budget.snapshot_group(expected_device=device, environ=client.environ, region=region) as group:
        for endpoint in ("/v2/family", "/v2/device/thing", "/v2/device/thing/status"):
            client.dispatch(region=region, endpoint=endpoint, send=send or success)
        group["normalized_complete"] = True
    return observed


def fail(code=412, http=None):
    def send(_):
        classification = budget.classify_failure(provider_code=code, http_status=http)
        raise OAuthFailure("sanitized", provider_failure=classification)
    return send


def test_expired_never_attempted_claim_conflict_cannot_strand_fresh_read_capacity(monkeypatch):
    monkeypatch.setattr(budget, "LOCAL_ROLLING_LIMIT", 124)
    client = MemoryBudget()
    key = budget.scope_digest(ENV, "eu")
    client.backend.events.extend({"at":NOW-timedelta(hours=1), "units":1,
        "detail":{"scope":key,"region":"eu"}} for _ in range(36))
    live = client.reserve_for_on(execution_id="LIVE", device_id="1002851416", channel=1,
        device_type="borehole_pump_power", region="eu")
    client.begin_on(execution_id="LIVE", permit=live, device_id="1002851416", channel=1)
    stale = client.reserve_for_on(execution_id="CLAIM-CONFLICT", device_id="100204d497", channel=1,
        device_type="fertilizer_injection_valve", region="eu")
    with pytest.raises(budget.RequestBudgetUnavailable, match="rolling_capacity"):
        snapshot(client)
    client.backend.advance(31)
    restarted = MemoryBudget(client.backend)
    assert len(snapshot(restarted)) == 3
    assert "CLAIM-CONFLICT" not in client.backend.state["reserves"]
    assert client.backend.state["reserves"]["LIVE"]["phase"] == "on_attempt"
    with pytest.raises(budget.RequestBudgetUnavailable):
        restarted.begin_on(execution_id="CLAIM-CONFLICT", permit=stale, device_id="100204d497", channel=1)
    assert restarted.reserve_for_on(execution_id="NEW", device_id="100204d497", channel=2,
        device_type="fertilizer_mixer", region="eu")


def canonical_terminal_fixture(kind="fertilizer_mixer", action=None):
    from modules.telemetry import rootline_irrigation_execution_store as execution
    borehole = kind == "borehole_pump_power"
    parent = kind == "irrigation_zone_valve"
    device, channel = (("1002851416",1) if borehole else ("100204e9bc",1) if parent else
        ("100204d497",2 if kind == "fertilizer_mixer" else 1))
    claim_action = "claim_borehole_before_on" if borehole else "claim_before_on" if parent else "claim_auxiliary_before_on"
    action = action or ("record_borehole_completed" if borehole else "record_completed" if parent else "record_auxiliary_completed")
    identity = "CANONICAL-OLD"
    claim = {"execution_id":identity,"device_id":device,"channel":channel,"device_type":kind,
        "provider_capacity_permit":"p"*32,"claimed_at":(NOW-timedelta(seconds=600)).isoformat(),
        "primary_stop_deadline":(NOW-timedelta(seconds=1)).isoformat(),"maximum_duration_seconds":599,
        "state":"claimed","on_attempts":0,"off_attempts":0}
    reserve = {"phase":"on_attempt","permit":"p"*32,"device_id":device,"channel":channel,
        "device_type":kind,"reserved_at":(NOW-timedelta(seconds=599)).isoformat()}
    proof = {"authoritative":True,"state":"OFF","device_id":device,"channel":channel,
        "retrieved_at":NOW.isoformat(),"evidence_id":"a"*64}
    terminal = {**claim,"state":"Completed","shutdown_verified":True,
        "completed_at":NOW.isoformat(),"shutdown_evidence":proof,
        "physical_outcome":"Unmeasured","objective_satisfied":False}
    if borehole:
        terminal.update(operational_proof="provider_app_on_to_off",
            provider_start_evidence={"authoritative":True,"state":"ON"},
            provider_final_off_evidence={**proof,"execution_id":identity},
            canonical_completion_evidence={"execution_id":identity,"final_state":"OFF","evidence_id":"CANONICAL-1"})
    def row(name, body, at):
        event_id = execution._event_id(name, body)
        return {"event_id":event_id,"execution_id":identity,"created_at":at,"copies":1,
            "body":execution._stored_event_body(name, body, event_id)}
    rows = [row(claim_action,claim,NOW-timedelta(seconds=598)),
        row(action,terminal,NOW+timedelta(seconds=1))]
    return identity,reserve,rows


@pytest.mark.parametrize("kind,action", [
    ("irrigation_zone_valve",None),("fertilizer_mixer",None),
    ("fertilizer_injection_valve",None),("borehole_pump_power",None),
    ("fertilizer_injection_valve","record_auxiliary_control_pulse_stopped")])
def test_originally_fresh_terminal_off_only_discharges_its_old_capacity(kind, action):
    identity,reserve,rows = canonical_terminal_fixture(kind,action)
    original = deepcopy(rows)
    assert budget._terminal_off_release(identity,reserve,rows,NOW+timedelta(days=2))
    assert not budget._terminal_off_release("LATER-SAME-OUTPUT",reserve,rows,NOW+timedelta(days=2))
    assert rows == original and rows[-1]["body"]["physical_outcome"] == "Unmeasured"
    assert rows[-1]["body"]["objective_satisfied"] is False


@pytest.mark.parametrize("defect", ["outer_event","forged_matching_identity","changed_proof","outer_execution","duplicate_claim","duplicate_terminal",
    "duplicate_outcome","permit","wrong_device","wrong_channel","boolean_channel","wrong_execution",
    "missing_digest","naive_time","future_time","stale_at_terminal","before_reservation",
    "false_shutdown","boolean_only_terminal","later_active","later_stopping","later_unknown_shutdown"])
def test_terminal_capacity_reconciliation_refuses_unproven_or_contradictory_history(defect):
    from modules.telemetry import rootline_irrigation_execution_store as execution
    identity,reserve,rows = canonical_terminal_fixture()
    terminal=rows[-1]["body"]; proof=terminal["shutdown_evidence"]
    if defect=="outer_event":rows[-1]["event_id"]="OTHER"
    elif defect=="forged_matching_identity":rows[-1]["event_id"]=terminal["event_id"]="ROOTLINE-EXEC-"+"F"*32
    elif defect=="changed_proof":terminal["physical_outcome"]="Verified"
    elif defect=="outer_execution":rows[-1]["execution_id"]="OTHER"
    elif defect=="duplicate_claim":rows[0]["copies"]=2
    elif defect=="duplicate_terminal":rows[-1]["copies"]=2
    elif defect=="permit":terminal["provider_capacity_permit"]="OTHER"
    elif defect=="wrong_device":proof["device_id"]="OTHER"
    elif defect=="wrong_channel":proof["channel"]=1
    elif defect=="boolean_channel":proof["channel"]=True
    elif defect=="wrong_execution":proof["execution_id"]="OTHER"
    elif defect=="missing_digest":proof["evidence_id"]=""
    elif defect=="naive_time":proof["retrieved_at"]=NOW.replace(tzinfo=None).isoformat()
    elif defect=="future_time":proof["retrieved_at"]=(NOW+timedelta(seconds=2)).isoformat()
    elif defect=="stale_at_terminal":proof["retrieved_at"]=(NOW-timedelta(seconds=61)).isoformat()
    elif defect=="before_reservation":proof["retrieved_at"]=(NOW-timedelta(seconds=700)).isoformat()
    elif defect=="false_shutdown":terminal["shutdown_verified"]=False
    elif defect=="boolean_only_terminal":terminal.pop("shutdown_evidence")
    else:
        action = {"duplicate_outcome":"record_auxiliary_on_outcome","later_active":"mark_auxiliary_active",
            "later_stopping":"mark_stopping","later_unknown_shutdown":"contain_auxiliary_device"}[defect]
        body={**rows[0]["body"],"shutdown_verified":False,"on_outcome":{"accepted_unambiguous":True}}
        event_id=execution._event_id(action,body)
        rows.append({"event_id":event_id,"execution_id":identity,"created_at":NOW+timedelta(seconds=2),
            "copies":2 if defect=="duplicate_outcome" else 1,
            "body":execution._stored_event_body(action,body,event_id)})
    assert budget._terminal_off_release(identity,reserve,rows,NOW+timedelta(days=2)) is None


def test_unknown_balance_is_explicit_but_does_not_block_fresh_success():
    client = MemoryBudget()
    times = snapshot(client)
    assert len(times) == 3
    assert all((later-earlier).total_seconds() >= 1 for earlier, later in zip(times, times[1:]))
    assert client._counts(client.backend, client.backend.now) == (3, 3)
    assert client.backend.state["provider_remaining"] == "Unknown"
    assert client.backend.state["prior_provider_usage"] == "Unknown"
    assert client.backend.state["external_clients_counted"] is False
    assert client.backend.state["coverage_start"] == NOW.isoformat()


@pytest.mark.parametrize("provider,http,category", [
    (412, None, "application_call_limit"), (403, None, "authentication_or_permission"),
    (None, 403, "authentication_or_permission"), (None, 429, "rate_limit"),
    (None, 503, "provider_server_error"), (None, 412, "transport_or_response_error"),
    ("412", None, "transport_or_response_error"), (True, None, "transport_or_response_error")])
def test_provider_json_code_is_distinct_from_http_status(provider, http, category):
    result = budget.classify_failure(provider_code=provider, http_status=http)
    assert result["category"] == category
    assert set(result) == {"category", "provider_code", "http_status", "retry_after_seconds"}


@pytest.mark.parametrize("value,expected", [("60", 60), ("-1", 0), ("999999999", 3600),
    ("garbage", 0), ("Sat, 31 Oct 2026 18:05:00 GMT", 300)])
def test_retry_after_is_bounded_and_validated(value, expected):
    assert budget.classify_failure(http_status=429, retry_after=value, now=NOW)["retry_after_seconds"] == expected


def test_quota_hold_is_shared_across_restart_region_and_token_provenance():
    first = MemoryBudget()
    with pytest.raises(OAuthFailure):
        snapshot(first, send=fail())
    for region in ("eu", "us", "as"):
        restarted = MemoryBudget(first.backend)
        with pytest.raises(budget.RequestBudgetUnavailable, match="application_call_limit_hold"):
            snapshot(restarted, region=region)
    assert first._counts(first.backend, first.backend.now) == (1, 1)
    first.backend.advance(3600)
    snapshot(MemoryBudget(first.backend), region="us")
    state = first.backend.state
    assert state["scopes"][budget.scope_digest(ENV, "eu")]["category"] is None
    assert state["provider_remaining"] == "Unknown"
    assert first._counts(first.backend, first.backend.now)[0] == 4


def test_only_complete_snapshot_clears_hold_and_partial_probe_consumes_hour():
    client = MemoryBudget()
    with pytest.raises(OAuthFailure):
        snapshot(client, send=fail())
    client.backend.advance(3600)
    with pytest.raises(ValueError, match="binding_invalid"):
        with budget.snapshot_group(expected_device="100204e9bc", environ=ENV, region="eu"):
            client.dispatch(region="eu", endpoint="/v2/family", send=lambda _: {})
            raise ValueError("binding_invalid")
    with pytest.raises(budget.RequestBudgetUnavailable, match="application_call_limit_hold"):
        snapshot(MemoryBudget(client.backend))
    assert client._counts(client.backend, client.backend.now)[0] == 2


def test_expiry_rotation_is_one_probe_attempt_not_quota_triggered_refresh():
    client = MemoryBudget()
    with pytest.raises(OAuthFailure):
        snapshot(client, send=fail())
    client.backend.advance(3600)
    with budget.snapshot_group(expected_device="100204e9bc", environ=ENV, region="eu") as group:
        client.dispatch(region="eu", endpoint="/v2/user/refresh", send=lambda _: {"at": "synthetic"})
        scope = client.backend.state["scopes"][budget.scope_digest(ENV, "eu")]
        assert scope["category"] == "application_call_limit"
        for endpoint in ("/v2/family", "/v2/device/thing", "/v2/device/thing/status"):
            client.dispatch(region="eu", endpoint=endpoint, send=lambda _: {})
        group["normalized_complete"] = True
    assert client._counts(client.backend, client.backend.now)[0] == 5
    assert client.backend.state["scopes"][budget.scope_digest(ENV, "eu")]["category"] is None


def test_failed_probe_does_not_continue_gets_or_clear_newer_hold():
    client = MemoryBudget()
    with pytest.raises(OAuthFailure):
        snapshot(client, send=fail())
    client.backend.advance(3600)
    with pytest.raises(OAuthFailure):
        with budget.snapshot_group(expected_device="100204e9bc", environ=ENV, region="eu") as group:
            client.dispatch(region="eu", endpoint="/v2/user/refresh", send=fail())
    client.complete_snapshot(group)
    scope = client.backend.state["scopes"][budget.scope_digest(ENV, "eu")]
    assert scope["category"] == "application_call_limit" and scope["generation"] == 2
    assert client._counts(client.backend, client.backend.now)[0] == 2


def test_transient_failures_back_off_one_five_fifteen_sixty_minutes():
    client = MemoryBudget()
    for delay in (60, 300, 900, 3600, 3600):
        with pytest.raises(OAuthFailure):
            snapshot(client, send=fail(code=None, http=503))
        scope = client.backend.state["scopes"][budget.scope_digest(ENV, "eu")]
        due = datetime.fromisoformat(scope["next_probe_at"])
        assert due-client.backend.now == timedelta(seconds=delay)
        client.backend.advance(delay)


def test_optional_requests_cannot_consume_active_rolling_or_short_window_reserves(monkeypatch):
    client = MemoryBudget()
    permit = client.reserve_for_on(execution_id="EXEC-A", device_id="100204d497", channel=1,
        device_type="fertilizer_injection_valve", region="eu")
    client.begin_on(execution_id="EXEC-A", permit=permit, device_id="100204d497", channel=1)
    for limit in ("FIVE_MINUTE_LIMIT", "LOCAL_ROLLING_LIMIT"):
        with monkeypatch.context() as patch:
            patch.setattr(budget, limit, 65)
            snapshot_count = len(client.backend.events)
            with pytest.raises(budget.RequestBudgetUnavailable, match="capacity_exhausted"):
                snapshot(client)
            # At most one optional request can use the last unreserved slot.
            assert sum(row["units"] for row in client.backend.events[snapshot_count:]) <= 1
    before = client.backend.state["reserves"]["EXEC-A"]["remaining"]
    with budget.execution_duty({"execution_id": "EXEC-A"}):
        snapshot(client, device="100204d497")
    assert client.backend.state["reserves"]["EXEC-A"]["remaining"] == before-3
    with budget.execution_duty({"execution_id": "EXEC-A"}):
        with pytest.raises(budget.RequestBudgetUnavailable, match="mismatched"):
            snapshot(client, device="1002851416")


def test_reserve_survives_restart_and_deadline_without_releasing_unresolved_shutdown():
    client = MemoryBudget()
    permit = client.reserve_for_on(execution_id="EXEC-A", device_id="100204d497", channel=2,
        device_type="fertilizer_mixer", region="eu")
    client.begin_on(execution_id="EXEC-A", permit=permit, device_id="100204d497", channel=2)
    client.backend.advance(86400)
    restarted = MemoryBudget(client.backend)
    restarted.reserve_for_on(execution_id="EXEC-B", device_id="1002851416", channel=1,
        device_type="borehole_pump_power", region="eu")
    assert "EXEC-A" in client.backend.state["reserves"]
    restarted.release_after_off("EXEC-A", device_id="100204d497", channel=2,
        evidence={"authoritative": True, "state": "OFF", "device_id": "100204d497",
            "channel": 2, "retrieved_at": client.backend.now.isoformat(), "response_digest": "a"*64})
    assert "EXEC-A" not in client.backend.state["reserves"]


def test_pre_on_expiry_fences_late_sender_without_releasing_attempted_on():
    client = MemoryBudget()
    old = client.reserve_for_on(execution_id="EXEC-A", device_id="100204d497", channel=2,
        device_type="fertilizer_mixer", region="eu")
    client.backend.advance(31)
    new = client.reserve_for_on(execution_id="EXEC-A", device_id="100204d497", channel=2,
        device_type="fertilizer_mixer", region="eu")
    assert old != new
    with pytest.raises(budget.RequestBudgetUnavailable):
        client.begin_on(execution_id="EXEC-A", permit=old, device_id="100204d497", channel=2)
    client.begin_on(execution_id="EXEC-A", permit=new, device_id="100204d497", channel=2)
    with pytest.raises(budget.RequestBudgetUnavailable):
        client.begin_on(execution_id="EXEC-A", permit=new, device_id="100204d497", channel=2)


def test_admission_denied_before_claim_when_all_active_reserves_do_not_fit(monkeypatch):
    client = MemoryBudget()
    monkeypatch.setattr(budget, "FIVE_MINUTE_LIMIT", 70)
    client.reserve_for_on(execution_id="EXEC-A", device_id="100204d497", channel=1,
        device_type="fertilizer_injection_valve", region="eu")
    with pytest.raises(budget.RequestBudgetUnavailable, match="capacity_unavailable"):
        client.reserve_for_on(execution_id="EXEC-B", device_id="1002851416", channel=1,
            device_type="borehole_pump_power", region="eu")


def test_lost_accounting_acknowledgement_counts_possible_attempt_and_sends_nothing():
    client = MemoryBudget()
    append = client._append
    def lost(*args, **kwargs):
        append(*args, **kwargs)
        raise budget.RequestBudgetUnavailable("commit_acknowledgement_lost")
    client._append = lost
    sent = []
    with pytest.raises(budget.RequestBudgetUnavailable):
        client.dispatch(region="eu", endpoint="/v2/family", send=lambda _: sent.append(1))
    assert not sent and client._counts(client.backend, client.backend.now)[0] == 1
    with pytest.raises(budget.RequestBudgetUnavailable, match="prior_attempt_unresolved"):
        snapshot(MemoryBudget(client.backend))


def test_connection_loss_after_intent_is_rechecked_before_actual_send():
    client = MemoryBudget()
    append = client._append
    def lose(*args, **kwargs):
        append(*args, **kwargs)
        client.backend.live = False
    client._append = lose
    sent = []
    with pytest.raises(budget.RequestBudgetUnavailable, match="connection_lost"):
        client.dispatch(region="eu", endpoint="/v2/family", send=lambda _: sent.append(1))
    assert not sent and client._counts(client.backend, client.backend.now)[0] == 1


def test_caller_deadline_does_not_wait_for_slow_provider_or_free_send_fence():
    client = MemoryBudget()
    started, release = threading.Event(), threading.Event()
    def slow(_timeout):
        started.set(); release.wait(2)
        return {}
    try:
        with budget.snapshot_group(expected_device="100204e9bc", environ=ENV, region="eu") as group:
            group["deadline"] = time.monotonic()+.1
            began = time.monotonic()
            with pytest.raises(budget.RequestBudgetUnavailable, match="deadline"):
                client.dispatch(region="eu", endpoint="/v2/family", send=slow)
            assert time.monotonic()-began < .5 and started.is_set()
            with pytest.raises(budget.RequestBudgetUnavailable, match="dispatch_busy"):
                MemoryBudget(client.backend).reserve_for_on(execution_id="EXEC-B",
                    device_id="1002851416", channel=1, device_type="borehole_pump_power", region="eu")
    finally:
        release.set()
        for _ in range(100):
            if not client.backend.lock.locked():
                break
            time.sleep(.005)


def test_deadline_context_is_not_erased_by_nested_execution_transport():
    outer = NOW+timedelta(seconds=1)
    class Transport:
        def read_output_state(self, **_):
            return budget.current_duty()
    wrapped = budget.bind_execution_transport(Transport(), {"execution_id": "X"})
    with budget.execution_duty({"execution_id": "X"}, deadline=outer):
        assert wrapped.read_output_state()["read_deadline"] == outer


def test_slow_on_accounting_cannot_authorize_after_claim_or_primary_deadline():
    for claimed, primary, delay in ((NOW, NOW+timedelta(seconds=120), 31),
            (NOW, NOW+timedelta(seconds=1), 2)):
        client = MemoryBudget()
        permit = client.reserve_for_on(execution_id="EDGE", device_id="100204d497", channel=1,
            device_type="fertilizer_injection_valve", region="eu")
        append = client._append
        def slow(*args, **kwargs):
            append(*args, **kwargs)
            client.backend.advance(delay)
        client._append = slow
        with pytest.raises(budget.RequestBudgetUnavailable, match="deadline"):
            client.begin_on(execution_id="EDGE", permit=permit, device_id="100204d497", channel=1,
                claimed_at=claimed, primary_stop_deadline=primary)
        assert client.backend.state["reserves"]["EDGE"]["phase"] == "on_attempt"


def test_transport_checks_deadline_after_final_accounting_and_off_never_calls_it(monkeypatch):
    from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
    from tests.test_rootline_ifttt_transport import Response
    calls = []
    transport = RootlineIFTTTTransport(token_store=None,
        environ={"ROOTLINE_IFTTT_MAKER_KEY": "synthetic", "ROOTLINE_FERTILIZER_INJECTION_ENABLED": "true"},
        http_open=lambda *a, **kw: (calls.append(kw) or Response()))
    monkeypatch.setattr(budget.RequestBudget, "begin_on", lambda *a, **kw: time.monotonic()-1)
    with budget.execution_duty({"execution_id": "EDGE", "provider_capacity_permit": "permit",
            "claimed_at": NOW.isoformat(), "primary_stop_deadline": (NOW+timedelta(seconds=120)).isoformat()}):
        result = transport.set_state(device_id="100204d497", channel=1, state="ON", idempotency_key="EDGE:ON")
    assert result["provider_command_attempted"] is False and not calls
    monkeypatch.setattr(budget.RequestBudget, "begin_on", lambda *a, **kw: pytest.fail("OFF cannot enter budget"))
    assert transport.set_state(device_id="100204d497", channel=1, state="OFF",
        idempotency_key="EDGE:OFF:1")["accepted_unambiguous"] is True
    assert len(calls) == 1


def test_exhausted_attempted_reserve_gets_bounded_hourly_recovery_without_new_on():
    client = MemoryBudget()
    permit = client.reserve_for_on(execution_id="EXEC-A", device_id="100204d497", channel=1,
        device_type="fertilizer_injection_valve", region="eu")
    client.begin_on(execution_id="EXEC-A", permit=permit, device_id="100204d497", channel=1)
    reserve = client.backend.state["reserves"]["EXEC-A"]
    reserve["remaining"] = 0
    with budget.execution_duty({"execution_id": "EXEC-A"}):
        snapshot(client, device="100204d497")
        assert client.backend.state["reserves"]["EXEC-A"]["remaining"] == 1
        with pytest.raises(budget.RequestBudgetUnavailable, match="recovery_capacity_deferred"):
            snapshot(client, device="100204d497")
    client.backend.advance(3600)
    with budget.execution_duty({"execution_id": "EXEC-A"}):
        snapshot(MemoryBudget(client.backend), device="100204d497")
    with pytest.raises(budget.RequestBudgetUnavailable):
        client.begin_on(execution_id="EXEC-A", permit=permit, device_id="100204d497", channel=1)


def test_normalization_failure_is_sanitized_and_shared_without_refund():
    client = MemoryBudget()
    with pytest.raises(ValueError):
        with budget.snapshot_group(expected_device="100204e9bc", environ=ENV, region="eu"):
            client.dispatch(region="eu", endpoint="/v2/family", send=lambda _: {})
            raise ValueError("synthetic-sensitive-payload")
    assert client._counts(client.backend, client.backend.now)[0] == 1
    assert "synthetic-sensitive-payload" not in repr(client.backend.events)
    with pytest.raises(budget.RequestBudgetUnavailable, match="snapshot_binding_or_normalization_error_hold"):
        snapshot(MemoryBudget(client.backend))


def test_rolling_accounting_is_app_region_scoped_but_pacing_and_recent_count_are_global():
    client = MemoryBudget()
    snapshot(client, region="eu")
    snapshot(client, region="us")
    other = MemoryBudget(client.backend, {"EWELINK_CLIENT_ID": "other-synthetic-app"})
    snapshot(other, region="eu")
    assert client._counts(client.backend, client.backend.now) == (9, 9)
    assert client._counts(client.backend, client.backend.now,
        scope=budget.scope_digest(ENV, "eu"), region="eu") == (3, 9)
    assert client._counts(client.backend, client.backend.now,
        scope=budget.scope_digest(ENV, "us"), region="us") == (3, 9)


def test_readiness_duplicates_are_durably_suppressed_and_next_interval_is_fresh():
    client = MemoryBudget()
    interval=budget.OPTIONAL_OBSERVATION_SECONDS["mixer_readiness"]
    with budget.optional_observation("mixer_readiness"):
        snapshot(client, device="100204d497")
        for _ in range(3):
            with pytest.raises(budget.OptionalObservationDeferred) as deferred:
                snapshot(MemoryBudget(client.backend), device="100204d497")
            assert deferred.value.next_read_at == (NOW+timedelta(seconds=interval)).isoformat()
    assert client._counts(client.backend, client.backend.now)[0] == 3
    assert sum(row["action"] == "optional_observation_suppressed" for row in client.backend.events) == 3
    # Mandatory readers are not suppressed or fed a cached observation.
    assert len(snapshot(client, device="100204d497")) == 3
    client.backend.now = NOW+timedelta(seconds=interval)
    with budget.optional_observation("mixer_readiness"):
        observed = snapshot(MemoryBudget(client.backend), device="100204d497")
    assert observed[0] == NOW+timedelta(seconds=interval)
    assert client._counts(client.backend, client.backend.now)[0] == 9


def test_long_quota_outage_exhausts_original_reserve_then_restarts_recovers_and_releases_off():
    client = MemoryBudget()
    permit = client.reserve_for_on(execution_id="LONG", device_id="100204d497", channel=1,
        device_type="fertilizer_injection_valve", region="eu")
    client.begin_on(execution_id="LONG", permit=permit, device_id="100204d497", channel=1)
    for _ in range(budget.DUTY_CAPACITY["fertilizer_injection_valve"]+5):
        with budget.execution_duty({"execution_id":"LONG"}):
            with pytest.raises(OAuthFailure):
                snapshot(client, device="100204d497", send=fail())
        client.backend.advance(3600)
        client = MemoryBudget(client.backend)
    with budget.execution_duty({"execution_id":"LONG"}):
        snapshot(client, device="100204d497")
    with pytest.raises(budget.RequestBudgetUnavailable):
        client.begin_on(execution_id="LONG", permit=permit, device_id="100204d497", channel=1)
    client.release_after_off("LONG", device_id="100204d497", channel=1, evidence={
        "authoritative":True, "state":"OFF", "device_id":"100204d497", "channel":1,
        "retrieved_at":client.backend.now.isoformat(), "response_digest":"f"*64})
    assert "LONG" not in client.backend.state["reserves"]
    assert client._counts(client.backend,client.backend.now)[0] == budget.DUTY_CAPACITY["fertilizer_injection_valve"]+8


def test_parent_emergency_shutdown_uses_injectors_own_read_reserve():
    from modules.telemetry.rootline_irrigation_coordinator import emergency_off_auxiliary_execution
    active={"execution_id":"INJECTOR", "auxiliary_device_id":"FERTILIZER-INJECTION-CH1",
        "device_id":"100204d497", "channel":1}
    seen=[]
    class Transport:
        def set_state(self, **kwargs):
            seen.append(("command", budget.current_duty()["execution_id"]))
            return {"accepted_unambiguous":True}
        def read_output_state(self, **kwargs):
            seen.append(("read", budget.current_duty()["execution_id"]))
            return {"authoritative":True,"state":"OFF"}
    def store(action,payload):
        if action == "load_active_auxiliary": return active
        if action == "load_auxiliary_off_attempts": return []
        return {"created":True,"success":True}
    result=emergency_off_auxiliary_execution(store=store,
        transport=budget.bind_execution_transport(Transport(),{"execution_id":"PARENT"}),
        expected_device_id="FERTILIZER-INJECTION-CH1")
    assert result["shutdown_verified"] is True
    assert seen == [("command","INJECTOR"),("read","INJECTOR")]


def test_optional_suppression_keeps_its_type_through_real_http_adapter(monkeypatch):
    from modules.telemetry.rootline_ewelink_oauth import _provider_request
    def defer(*a, **kw):
        raise budget.OptionalObservationDeferred("2026-11-01T00:30:00Z")
    monkeypatch.setattr(budget.RequestBudget,"dispatch",defer)
    with pytest.raises(budget.OptionalObservationDeferred):
        _provider_request("GET","https://eu-apia.coolkit.cc/v2/family",mode="bearer",token="synthetic",
            environ={**ENV,"EWELINK_EXPECTED_DEVICE_ID":"100204e9bc"})


class _AcquisitionConnection:
    """Synthetic driver boundary; native worker/transaction setup still runs."""
    def __init__(self, *, setup_delay=0, setup_error=False):
        self.setup_delay = setup_delay
        self.setup_error = setup_error
        self.statements = []
        self.closed = threading.Event()
        self.rolled_back = False

    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): return False

    def execute(self, statement, *_args):
        self.statements.append(statement)
        time.sleep(self.setup_delay)
        if self.setup_error:
            raise RuntimeError("synthetic_setup_failure")
        assert statement in ("set local statement_timeout='3000ms'",
                             "set local lock_timeout='1000ms'")
        return self

    def rollback(self): self.rolled_back = True
    def close(self): self.closed.set()


def test_budget_acquisition_allows_native_setup_over_one_second(monkeypatch):
    import psycopg
    from modules.oom_sakkie import bounded_postgres_read as bounded
    connection = _AcquisitionConnection(setup_delay=.15)
    calls, deadlines = [], []
    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        time.sleep(.85)
        return connection
    native = bounded._connect_with_wall_clock_deadline
    def capture(*args):
        deadlines.append(args[3])
        return native(*args)
    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(bounded, "_connect_with_wall_clock_deadline", capture)
    client = budget.RequestBudget({**ENV, "DATABASE_URL": "postgresql://synthetic"})
    started = time.monotonic()
    acquired = client._connect()
    assert acquired is connection and time.monotonic()-started >= 1.1
    assert deadlines == [bounded.ROOTLINE_CONNECT_DEADLINE_SECONDS] == [5]
    assert len(calls) == 1
    assert calls[0][1] == {"connect_timeout": 3,
        "options": "-c statement_timeout=3000 -c lock_timeout=1000"}
    assert connection.statements == ["set local statement_timeout='3000ms'",
                                     "set local lock_timeout='1000ms'"]
    acquired.close()


@pytest.mark.parametrize("delay_phase", ["driver", "transaction_setup"])
def test_budget_short_group_refuses_and_closes_late_acquisition(monkeypatch, delay_phase):
    import psycopg
    from modules.oom_sakkie import bounded_postgres_read as bounded
    connection = _AcquisitionConnection(setup_delay=.08 if delay_phase == "transaction_setup" else 0)
    calls = []
    def connect(*_args, **_kwargs):
        calls.append(True)
        if delay_phase == "driver": time.sleep(.15)
        return connection
    monkeypatch.setattr(psycopg, "connect", connect)
    with budget.snapshot_group(expected_device="100204e9bc", environ=ENV, region="eu") as group:
        group["deadline"] = time.monotonic()+.03
        started = time.monotonic()
        with pytest.raises(bounded.RootlineConnectionDeadlineExceeded):
            budget.RequestBudget({**ENV, "DATABASE_URL": "postgresql://synthetic"})._connect()
        assert time.monotonic()-started < .12
        assert connection.closed.wait(.8)
    assert calls == [True]


def test_budget_expired_group_opens_no_database(monkeypatch):
    import psycopg
    monkeypatch.setattr(psycopg, "connect", lambda *a, **kw: pytest.fail("expired group cannot connect"))
    with budget.snapshot_group(expected_device="100204e9bc", environ=ENV, region="eu") as group:
        group["deadline"] = time.monotonic()-1
        with pytest.raises(budget.RequestBudgetUnavailable, match="deadline"):
            budget.RequestBudget({**ENV, "DATABASE_URL": "postgresql://synthetic"})._connect()


def test_budget_native_connect_keeps_earlier_nested_duty(monkeypatch):
    import psycopg
    from modules.oom_sakkie import bounded_postgres_read as bounded
    connection = _AcquisitionConnection()
    def connect(*_args, **_kwargs):
        time.sleep(.15)
        return connection
    monkeypatch.setattr(psycopg, "connect", connect)
    earlier = datetime.now(timezone.utc)+timedelta(seconds=.04)
    with budget.execution_duty({"execution_id": "SYNTHETIC"}, deadline=earlier):
        with budget.execution_duty({"execution_id": "SYNTHETIC"}, deadline=earlier+timedelta(seconds=30)):
            with budget.snapshot_group(expected_device="100204e9bc", environ=ENV, region="eu"):
                with pytest.raises(bounded.RootlineConnectionDeadlineExceeded):
                    budget.RequestBudget({**ENV, "DATABASE_URL": "postgresql://synthetic"})._connect()
    assert connection.closed.wait(.8)


def test_budget_setup_failure_rolls_back_without_accounting_retry(monkeypatch):
    import psycopg
    connection = _AcquisitionConnection(setup_error=True)
    calls = []
    monkeypatch.setattr(psycopg, "connect", lambda *a, **kw: calls.append(True) or connection)
    client = budget.RequestBudget({**ENV, "DATABASE_URL": "postgresql://synthetic"})
    monkeypatch.setattr(client, "_append", lambda *a, **kw: pytest.fail("no accounting after setup failure"))
    with pytest.raises(budget.RequestBudgetUnavailable, match="accounting_unavailable"):
        client.dispatch(region="eu", endpoint="/v2/family",
                        send=lambda _: pytest.fail("no provider after setup failure"))
    assert connection.rolled_back and connection.closed.wait(.8) and calls == [True]


def test_budget_acquisition_failure_precedes_coordinator_claim(monkeypatch):
    import psycopg
    from tests.test_rootline_irrigation_coordinator import Store, Transport, run
    connection = _AcquisitionConnection(setup_error=True)
    monkeypatch.setattr(psycopg, "connect", lambda *a, **kw: connection)
    client = budget.RequestBudget({**ENV, "DATABASE_URL": "postgresql://synthetic"})
    class CapacityTransport(Transport):
        def prepare_execution_capacity(self, execution):
            return client.reserve_for_on(execution_id=execution["execution_id"],
                device_id=execution["device_id"], channel=execution["channel"],
                device_type="irrigation_zone_valve", region="eu")
    store, transport, notices = Store(), CapacityTransport(), []
    result = run(store, transport, notices)
    assert result["status"] == "provider_capacity_unavailable"
    assert result["hardware_commands"] == 0 and store.rows == []
    assert transport.calls == [] and notices == []
    assert connection.rolled_back and connection.closed.wait(.8)
