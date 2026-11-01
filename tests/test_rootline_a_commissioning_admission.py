"""A first-use admission: actual normalization, canonical references, no hardware."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

import pytest

from modules.telemetry import rootline_irrigation_execution_store as store
from modules.telemetry.rootline_ifttt_transport import (
    RootlineIFTTTTransport, a_commissioning_final_off_verified,
    validate_a_commissioning_configuration, output_evidence_from_snapshot)
from modules.telemetry.rootline_ewelink_commissioned_baseline import commissioned_controller_baseline
from modules.telemetry.rootline_ewelink_oauth import normalize_device_readback


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def snapshot(*, now=None, states=None):
    now = now or datetime.now(timezone.utc)
    params = {"fwVersion": "3.8.2", "switches": [
        {"outlet": i, "switch": (states or {}).get(i + 1, "OFF").lower()} for i in range(4)],
        "pulses": [{"outlet": i, "pulse": "on", "width": 3599000} for i in range(4)],
        "configure": [{"outlet": i, "startup": "off"} for i in range(4)], "timers": []}
    result = normalize_device_readback(device={"deviceid": "100204e9bc", "online": True,
        "productModel": "4CH Pro R3", "extra": {"uiid": 9}, "params": params},
        status={"params": params}, retrieved_at=now,
        commissioned_baseline=commissioned_controller_baseline())
    result["response_digest"] = digest(result)
    result.update(provider_calls=3, provider_control_calls=0, token_refreshed=False,
        autonomous_control_enabled=False, registered_discovery_only=True)
    return result


class Response:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def getcode(self): return self.status
    def read(self, limit): return b"accepted"


def transport(*, reader=None, sender=None, environ=None):
    calls = []
    def send(request, timeout):
        calls.append({"url": request.full_url, "body": json.loads(request.data), "timeout": timeout})
        if sender: return sender(request, timeout)
        return Response()
    result = RootlineIFTTTTransport(token_store=SimpleNamespace(latest=lambda: {
        "provider_account_digest": "a" * 64, "region": "eu"}),
        environ=environ if environ is not None else {
            **os.environ, "ROOTLINE_IFTTT_MAKER_KEY": "synthetic-test-key", "EWELINK_CLIENT_ID": "synthetic-app"},
        readback=lambda **_: reader() if reader else snapshot(), http_open=send)
    return result, calls


def grant(configuration, *, operation=None, now=None):
    now = now or datetime.now(timezone.utc)
    root = Path(store.__file__).resolve().parents[2]
    return {"contract_version": "rootline_a_operator_grant.v1", "mission_id": "RMQ-20260813-04",
        "operation_id": operation or uuid.uuid4().hex, "zone_id": "A12345", "device_id": "100204e9bc",
        "channel": 4, "provider_account_binding": "ewelink_owner_account",
        "on_event": "irrigation_1_ch4_on", "off_event": "irrigation_1_ch4_off",
        "native_fail_stop_seconds": 3599, "maximum_runtime_seconds": 3599,
        "observation_mode": "native_timeout", "startup_verification_seconds": 30,
        "observation_read_margin_seconds": 60,
        "observation_deadline": (now + timedelta(seconds=3720)).isoformat(),
        "max_on_attempts": 1, "max_off_attempts": 3, "ordinary_a_enabled": False,
        "standing_authority": False, "automatic_on_retry": False,
        "owner_instruction": {"source": "owner_codex_chat", "reference": "SYNTHETIC-OWNER-TEST",
            "artifact_sha256": "b" * 64}, "owner_instruction_received_at": (now - timedelta(minutes=2)).isoformat(),
        "root_review_sha256": "c" * 64, "not_before": (now - timedelta(seconds=1)).isoformat(),
        "on_expires_at": (now + timedelta(seconds=90)).isoformat(),
        "recovery_deadline": (now + timedelta(seconds=3900)).isoformat(),
        "configuration_generation": configuration["configuration"]["configuration_generation"],
        "configuration_baseline_sha256": configuration["configuration"]["commissioned_baseline_sha256"],
        "configuration_sha256": configuration["configuration_sha256"],
        "firmware": "3.8.2", "provider_account_digest": "a" * 64,
        "ifttt_control_path_evidence": {"channels": [1, 2, 3, 4], "device_id": "100204e9bc",
            "configuration_generation": 1, "conflicting_automations": [],
            "reference": "SYNTHETIC-CONFIGURATION-TEST", "artifact_sha256": "d" * 64,
            "source": "canonical_configuration_evidence"},
        "runtime": {"revision": "e" * 40, "service_id": "synthetic-service",
            "hostname": socket.gethostname(),
            "source_pins": {name: sha256((root / name).read_bytes()).hexdigest()
                for name in store._A_COMMISSIONING_SOURCE_PATHS}}}


def journal_rows(value, configuration):
    now = datetime.now(timezone.utc).isoformat()
    def row(phase, details):
        return {"event_id": store._a_id(value["operation_id"], phase),
            "mission_id": value["mission_id"], "operation_id": value["operation_id"],
            "mode": "A_CH4", "version": "rootline_owner_operator_commissioning.v1",
            "state": "operator_commissioning_" + phase.lower(), "source": "owner_codex_operator",
            "recorded_at": now, "owner_instruction": value["owner_instruction"],
            "owner_instruction_received_at": value["owner_instruction_received_at"],
            "source_revision": value["runtime"]["revision"], "deployed_revision": value["runtime"]["revision"],
            "root_review_sha256": value["root_review_sha256"], "details": details}
    return [row("ATTEMPT", {"a_commissioning_grant": value}), row("COMMAND", {
        "a_commissioning_grant_sha256": digest(value), "configuration_snapshot_sha256": digest(configuration)})]


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "e" * 40)
    monkeypatch.setenv("RENDER_SERVICE_ID", "synthetic-service")
    monkeypatch.delenv("ROOTLINE_A_ENABLED", raising=False)
    monkeypatch.delenv("ROOTLINE_BC_COMMISSIONED_BASELINE_REVOKED", raising=False)


def test_production_shaped_configuration_is_observation_and_cannot_enable_ordinary_a(runtime):
    instance, calls = transport()
    observed = instance.read_a_commissioning_configuration()
    value = grant(observed)
    assert validate_a_commissioning_configuration(observed, grant=value, now=datetime.now(timezone.utc))
    assert observed["commissioned"] is False and observed["ordinary_eligibility"] is False
    assert observed["ifttt_automation_configuration"] == "Unknown"
    assert instance.set_state(device_id="100204e9bc", channel=4, state="ON",
        idempotency_key="synthetic:ON")["status"] == "irrigation_output_not_commissioned"
    assert not calls


@pytest.mark.parametrize("change", ["channel", "account", "digest", "generation", "firmware", "native",
    "sibling_on", "target_on", "unknown", "missing_channel", "duplicate_channel", "timer",
    "scene", "interlock", "baseline", "stale", "future", "commissioned", "ifttt_missing",
    "ifttt_wrong_scope", "ifttt_conflict", "provenance"])
def test_configuration_refuses_missing_conflicting_and_cross_channel_facts(runtime, change):
    instance, _ = transport(); observed = instance.read_a_commissioning_configuration(); value = grant(observed)
    altered = deepcopy(observed)
    row = altered["snapshot"]["channels"][3]
    if change == "channel": altered["channel"] = 1
    elif change == "account": altered["provider_account_digest"] = "f" * 64
    elif change == "digest": altered["configuration_sha256"] = "f" * 64
    elif change == "generation": altered["snapshot"]["configuration_generation"] = 2
    elif change == "firmware": altered["snapshot"]["firmware"] = "changed"
    elif change == "native": row["native_auto_off_seconds"] = 60
    elif change == "sibling_on": altered["snapshot"]["channels"][0]["output_state"] = "ON"
    elif change == "target_on": row["output_state"] = "ON"
    elif change == "unknown": row["output_state"] = "Unknown"
    elif change == "missing_channel": altered["snapshot"]["channels"].pop()
    elif change == "duplicate_channel": row["channel"] = 1
    elif change in {"timer", "scene", "interlock"}:
        altered["snapshot"][{"timer": "timers_enabled", "scene": "scenes_enabled", "interlock": "interlock_enabled"}[change]] = True
    elif change == "baseline": altered["snapshot"]["commissioned_baseline_fresh"] = False
    elif change in {"stale", "future"}:
        altered["snapshot"]["retrieved_at"] = (datetime.now(timezone.utc) + timedelta(seconds=-31 if change == "stale" else 60)).isoformat()
    elif change == "commissioned": altered["commissioned"] = True
    elif change == "ifttt_missing": value.pop("ifttt_control_path_evidence")
    elif change == "ifttt_wrong_scope": value["ifttt_control_path_evidence"]["channels"] = [1, 2]
    elif change == "ifttt_conflict": value["ifttt_control_path_evidence"]["conflicting_automations"] = ["unreviewed"]
    elif change == "provenance": altered["snapshot"]["control_path_evidence_source"] = None
    with pytest.raises((ValueError, TypeError)):
        validate_a_commissioning_configuration(altered, grant=value, now=datetime.now(timezone.utc))


def test_exact_canonical_journal_is_required_before_claim(runtime):
    instance, _ = transport(); observed = instance.read_a_commissioning_configuration(); value = grant(observed)
    rows = journal_rows(value, observed)
    actual, command = store._a_grant(rows, value["operation_id"], digest(value), datetime.now(timezone.utc))
    assert actual == value and command == rows[1]
    with pytest.raises(ValueError, match="root_journal_required"):
        store._a_grant([], value["operation_id"], digest(value), datetime.now(timezone.utc))


@pytest.mark.parametrize("change", ["wrong_channel", "wrong_device", "expired", "future", "unbounded",
    "two_on", "four_off", "standing", "retry", "owner", "review", "loaded_revision", "source_pin",
    "command_digest", "command_snapshot", "revoked", "recovery", "ordinary_enabled",
    "native_setting", "unbounded_startup", "unbounded_margin", "no_recovery_room"])
def test_grant_cannot_expand_or_borrow_authority(runtime, monkeypatch, change):
    instance, _ = transport(); observed = instance.read_a_commissioning_configuration(); value = grant(observed)
    if change == "wrong_channel": value["channel"] = 1
    elif change == "wrong_device": value["device_id"] = "100204d497"
    elif change == "expired": value["on_expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    elif change == "future": value["not_before"] = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    elif change == "unbounded": value["recovery_deadline"] = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    elif change == "two_on": value["max_on_attempts"] = 2
    elif change == "four_off": value["max_off_attempts"] = 4
    elif change == "standing": value["standing_authority"] = True
    elif change == "retry": value["automatic_on_retry"] = True
    elif change == "owner": value["owner_instruction"]["source"] = "caller"
    elif change == "review": value["root_review_sha256"] = ""
    elif change == "loaded_revision": value["runtime"]["revision"] = "f" * 40
    elif change == "source_pin": value["runtime"]["source_pins"][store._A_COMMISSIONING_SOURCE_PATHS[0]] = "f" * 64
    elif change == "ordinary_enabled": monkeypatch.setenv("ROOTLINE_A_ENABLED", "true")
    elif change == "native_setting": value["maximum_runtime_seconds"] = 60
    elif change == "unbounded_startup": value["startup_verification_seconds"] = 31
    elif change == "unbounded_margin": value["observation_read_margin_seconds"] = 61
    elif change == "no_recovery_room": value["observation_deadline"] = value["recovery_deadline"]
    rows = journal_rows(value, observed)
    if change == "command_digest": rows[1]["details"]["a_commissioning_grant_sha256"] = "f" * 64
    elif change == "command_snapshot":
        # Exact snapshot binding is checked by the actual claim path, below.
        rows[1]["source"] = "caller"
    elif change in {"revoked", "recovery"}:
        rows.append({"event_id": store._a_id(value["operation_id"], change.upper())})
    with pytest.raises(ValueError): store._a_grant(rows, value["operation_id"], digest(value), datetime.now(timezone.utc))


@pytest.mark.parametrize("state", ["ON", "OFF"])
def test_caller_dict_or_boolean_has_no_uncommissioned_send_path(runtime, state):
    instance, calls = transport(reader=lambda: pytest.fail("unauthorized provider read"))
    outcome = instance.set_a_commissioning_state(operation_claim={"commissioned": True,
        "allow_uncommissioned": True, "execution_id": "forged"}, state=state, idempotency_key="forged:" + state)
    assert outcome["provider_command_attempted"] is False and calls == []
    with pytest.raises(ValueError, match="locked_sender_required"):
        store.authorize_a_commissioning_sender({}, state, "forged")


@pytest.mark.parametrize("change", [None, "wrong_target", "sibling_on", "unknown", "stale", "old_read", "digest"])
def test_final_off_requires_new_exact_full_controller_evidence(change):
    started = datetime.now(timezone.utc) - timedelta(seconds=1)
    observed = snapshot()
    if change == "sibling_on": observed["channels"][0]["output_state"] = "ON"
    elif change == "unknown": observed["channels"][3]["output_state"] = "Unknown"
    elif change in {"stale", "old_read"}:
        observed["retrieved_at"] = (started - timedelta(seconds=60 if change == "stale" else 1)).isoformat()
    output = output_evidence_from_snapshot(observed, device_id="100204e9bc", channel=4)
    if change == "wrong_target": output["channel"] = 1
    elif change == "digest": output["evidence_id"] = "f" * 64
    assert a_commissioning_final_off_verified(output, now=datetime.now(timezone.utc), after=started) is (change is None)


@pytest.mark.parametrize("attack", [None, "db_reversed", "app_reversed", "old_receipt"])
def test_retirement_keeps_canonical_and_provider_clocks_separate(attack):
    app_now = datetime.now(timezone.utc)
    db_now = app_now + timedelta(seconds=10)
    operation = uuid.uuid4().hex
    claimed = {"event_id": store._a_id(operation, "A-CLAIM"), "operation_id": operation,
        "version": store._A_COMMISSIONING_VERSION, "purpose": "operator_commissioning", "phase": "A-CLAIM",
        "zone_id": "A12345", "device_id": "100204e9bc", "channel": 4,
        "execution_id": store._a_id(operation, "A-EXECUTION"), "claimed_at": db_now.isoformat()}
    final = output_evidence_from_snapshot(snapshot(now=app_now), device_id="100204e9bc", channel=4)
    retired = {"event_id": store._a_id(operation, "A-RETIRED"), "operation_id": operation,
        "version": store._A_COMMISSIONING_VERSION, "phase": "A-RETIRED",
        "claim_sha256": digest(claimed), "shutdown_verified": True, "watering_credit_created": False,
        "read_started_at": (app_now-timedelta(seconds=1)).isoformat(),
        "read_completed_at": (app_now+timedelta(seconds=1)).isoformat(),
        "database_read_started_at": (db_now+timedelta(seconds=1)).isoformat(),
        "database_read_completed_at": (db_now+timedelta(seconds=2)).isoformat(),
        "recorded_at": (db_now+timedelta(seconds=3)).isoformat(), "final_off_evidence": final,
        "observation": final, "safe_branch": "never_sent", "reserve_release_verified": True}
    stopped = {"event_id": store._a_id(operation, "A-REVOKED"), "operation_id": operation,
        "version": store._A_COMMISSIONING_VERSION, "phase": "A-REVOKED",
        "claim_sha256": digest(claimed), "recorded_at": db_now.isoformat()}
    if attack == "db_reversed": retired["database_read_started_at"] = (db_now-timedelta(seconds=1)).isoformat()
    elif attack == "app_reversed": retired["read_completed_at"] = (app_now-timedelta(seconds=2)).isoformat()
    elif attack == "old_receipt": retired["read_started_at"] = (app_now+timedelta(seconds=0.5)).isoformat()
    if attack is None:
        assert store._a_projection([claimed, stopped, retired], operation)["retired"]
    else:
        with pytest.raises(ValueError): store._a_projection([claimed, stopped, retired], operation)



def _delivered_start_projection():
    app_now = datetime.now(timezone.utc)
    db_now = app_now+timedelta(seconds=10)
    operation = uuid.uuid4().hex
    claimed = {"event_id": store._a_id(operation, "A-CLAIM"), "operation_id": operation,
        "version": store._A_COMMISSIONING_VERSION, "purpose": "operator_commissioning", "phase": "A-CLAIM",
        "zone_id": "A12345", "device_id": "100204e9bc", "channel": 4,
        "execution_id": store._a_id(operation, "A-EXECUTION"), "claimed_at": db_now.isoformat(),
        "startup_verification_deadline": (db_now+timedelta(seconds=30)).isoformat()}
    def row(phase):
        return {"event_id": store._a_id(operation, phase), "operation_id": operation,
            "version": store._A_COMMISSIONING_VERSION, "phase": phase,
            "claim_sha256": digest(claimed), "recorded_at": db_now.isoformat()}
    on = row("A-ON")
    start = {**row("A-STARTED"), "on_slot_sha256": digest(on), "within_startup_window": True,
        "observation": output_evidence_from_snapshot(snapshot(now=app_now, states={4:"ON"}), device_id="100204e9bc", channel=4),
        "read_started_at": (app_now-timedelta(seconds=1)).isoformat(),
        "read_completed_at": (app_now+timedelta(seconds=1)).isoformat(),
        "database_read_started_at": (db_now+timedelta(seconds=1)).isoformat(),
        "database_read_completed_at": (db_now+timedelta(seconds=2)).isoformat(),
        "recorded_at": (db_now+timedelta(seconds=3)).isoformat()}
    return operation, claimed, on, start


@pytest.mark.parametrize("attack", [None,"wrong_slot","wrong_claim","channel","digest","sibling_on",
    "stale","pre_claim","db_reversed","app_reversed","forged_timely","no_on"])
def test_delivered_start_requires_exact_own_fresh_and_separately_ordered_evidence(attack):
    operation, claimed, on, start = _delivered_start_projection()
    if attack == "wrong_slot": start["on_slot_sha256"] = "f"*64
    elif attack == "wrong_claim": start["claim_sha256"] = "f"*64
    elif attack == "channel": start["observation"]["channel"] = 1
    elif attack == "digest": start["observation"]["evidence_id"] = "f"*64
    elif attack == "sibling_on": start["observation"]["irrigation_output_evidence"]["channels"][0]["output_state"] = "ON"
    elif attack == "stale": start["read_started_at"] = start["read_completed_at"]
    elif attack == "pre_claim": start["database_read_started_at"] = (datetime.fromisoformat(claimed["claimed_at"])-timedelta(seconds=1)).isoformat()
    elif attack == "db_reversed": start["database_read_completed_at"] = claimed["claimed_at"]
    elif attack == "app_reversed": start["read_completed_at"] = start["read_started_at"]
    elif attack == "forged_timely": start["within_startup_window"] = False
    rows = [claimed, start] if attack == "no_on" else [claimed, on, start]
    if attack is None:
        assert store._a_projection(rows, operation)["startup_state"] == "delivered_start"
    else:
        with pytest.raises(ValueError): store._a_projection(rows, operation)


@pytest.mark.parametrize("attack", [None,"wrong_slot","wrong_source","unknown_reason","network_attempted",
    "wrong_provenance","pre_slot","missing_attempt","missing_grant","missing_source_pin","changed_source_pin","duplicate_attempt"])
def test_no_send_receipt_is_bound_to_installed_source_consumed_slot_and_reason(attack):
    operation, claimed, on, _ = _delivered_start_projection()
    expected_source = "a"*64
    attempt = {"event_id":store._a_id(operation,"ATTEMPT"),"details":{"a_commissioning_grant":{
        "runtime":{"source_pins":{"modules/telemetry/rootline_ifttt_transport.py":expected_source}}}}}
    no_send = {"event_id":store._a_id(operation,"A-NO-SEND"),"operation_id":operation,
        "version":store._A_COMMISSIONING_VERSION,"phase":"A-NO-SEND","claim_sha256":digest(claimed),
        "on_slot_sha256":digest(on),"reason":"provider_capacity_not_available","provider_command_attempted":False,
        "provenance":"installed_a_sender_pre_command_refusal.v1","transport_source_sha256":expected_source,
        "recorded_at":on["recorded_at"]}
    if attack == "wrong_slot": no_send["on_slot_sha256"]="f"*64
    elif attack == "wrong_source": no_send["transport_source_sha256"]="f"*64
    elif attack == "unknown_reason": no_send["reason"]="caller_says_no_send"
    elif attack == "network_attempted": no_send["provider_command_attempted"]=True
    elif attack == "wrong_provenance": no_send["provenance"]="caller_boolean"
    elif attack == "pre_slot": no_send["recorded_at"]=(datetime.fromisoformat(on["recorded_at"])-timedelta(seconds=1)).isoformat()
    rows = [attempt,claimed,on,no_send]
    if attack == "missing_attempt": rows.remove(attempt)
    elif attack == "missing_grant": attempt["details"].pop("a_commissioning_grant")
    elif attack == "missing_source_pin": attempt["details"]["a_commissioning_grant"]["runtime"]["source_pins"].clear()
    elif attack == "changed_source_pin":
        attempt["details"]["a_commissioning_grant"]["runtime"]["source_pins"]["modules/telemetry/rootline_ifttt_transport.py"] = "f"*64
    elif attack == "duplicate_attempt": rows.append(deepcopy(attempt))
    if attack is None:
        assert store._a_projection(rows,operation)["startup_state"]=="source_proven_no_send"
    else:
        with pytest.raises(ValueError): store._a_projection(rows,operation)
