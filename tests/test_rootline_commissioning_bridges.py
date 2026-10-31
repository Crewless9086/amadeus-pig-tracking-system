from tests.test_rootline_ifttt_transport import irrigation_output
"""Actual canonical loader -> normalized readback -> safety/eligibility contracts.

All records/transports below are synthetic; the SQL-shaped adapter is read-only.
No credential, network, real database or physical-device capability is used.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from modules.telemetry.rootline_device_spine import load_device_record, validate_device
from modules.telemetry.rootline_ewelink_commissioned_baseline import (
    commissioned_registered_device_baseline,
)
from modules.telemetry.rootline_ewelink_oauth import normalize_device_readback
from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
from modules.telemetry.rootline_auxiliary_management import (
    build_auxiliary_eligibility, revalidate_auxiliary_execution_edge,
)

NOW = datetime(2026, 10, 29, 10, tzinfo=timezone.utc)
INJECTOR = "ifttt_ewelink:ewelink_owner_account:100204d497:1"
PUMP = "ewelink:ewelink_owner_account:1002851416:1"
STAGES = ("provider_discovered", "readback_proven", "bounded_actuation_ready",
    "physical_identity_proven", "fail_stop_proven", "replay_proven",
    "operational_dependencies_proven", "supervised")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def reference(name, value=None):
    return {"evidence_id": "synthetic:" + name, "source": "canonical",
        "observed_at": (NOW - timedelta(minutes=1)).isoformat(),
        "sha256": digest(value if value is not None else {"synthetic": name})}


def record_for(key, kind, native):
    provider, account, device, channel = key.split(":")
    return {"provider": provider, "provider_account_binding": account,
        "device_id": device, "channel": int(channel), "physical_name": "Synthetic fixture",
        "device_type": kind, "adapter_profile": "ewelink_relay", "safe_state": "OFF",
        "maximum_runtime_seconds": native, "native_fail_stop_seconds": native,
        "readback": "provider_state", "physical_effect": "synthetic configured output",
        "dependencies": ["canonical"], "manual_isolation": "synthetic labelled isolator",
        "commissioning_stage": "standing_active", "standing_authority": True,
        "registry_generation": 1, "independent_physical_identity_proven": True,
        "independent_fail_stop_proven": True,
        "commissioning_evidence": {s: reference(s) for s in STAGES},
        "authority_envelope": {"standing_authority_id": "synthetic:authority", "version": "1",
            "issuer": "owner_policy", "policy_sha256": "a" * 64, "revoked": False}}


class CanonicalDatabase:
    """Execute production query selection, evidence identity and digest checks."""
    def __init__(self, key, record):
        self.key, self.record = key, record
        self.invalidated = set()
        self.authority_active = True
        self.missing = False
        self.queries = []
        self.bad_digest = False

    def __call__(self):
        owner = self
        class Session:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def cursor(self): return self
            def execute(self, sql, params):
                assert sql.strip().lower().startswith("select ")
                owner.queries.append((sql, params))
                self.row = None
                r = owner.record
                if "from app_private.rootline_device_registry where" in sql:
                    if params == (owner.key,) and not owner.missing:
                        h = digest(r)
                        self.row = ("rootline_device_spine.v1", deepcopy(r),
                            "0" * 64 if owner.bad_digest else h, r["registry_generation"], h)
                elif "rootline_device_commissioning_evidence e" in sql:
                    refs = list(r.get("commissioning_evidence", {}).values())
                    profile = r.get("authority_envelope", {}).get("controller_configuration", {})
                    if profile.get("reference"): refs.append(profile["reference"])
                    for ref in refs:
                        if params == (ref["evidence_id"], ref["source"], ref["observed_at"]):
                            self.row = (ref["evidence_id"], ref["sha256"],
                                ref["evidence_id"] not in owner.invalidated)
                elif "rootline_standing_authorities a" in sql:
                    a = r["authority_envelope"]
                    if params == (a["standing_authority_id"], a["version"], a["issuer"]):
                        self.row = (a["standing_authority_id"], a["version"],
                            a["policy_sha256"], owner.authority_active)
                else:
                    raise AssertionError("unapproved query")
            def fetchone(self): return self.row
        return Session()


def fertilizer_snapshot(**params):
    raw = {"fwVersion": "3.8.2", "switches": [{"outlet": i, "switch": "off"} for i in range(4)],
        "pulses": [{"outlet": 0, "pulse": "on", "width": 120000},
                   {"outlet": 1, "pulse": "on", "width": 1800000},
                   *[{"outlet": i, "pulse": "off", "width": 1000} for i in (2, 3)]],
        "configure": [{"outlet": i, "startup": "off"} for i in range(4)], "timers": []}
    raw.update(params)
    value = normalize_device_readback(device={"deviceid": "100204d497", "online": True,
        "params": raw}, status={"params": {}}, retrieved_at=NOW,
        commissioned_baseline=commissioned_registered_device_baseline("100204d497"))
    return {**value, "response_digest": digest(value), "provider_control_calls": 0}


def injector_database(snapshot):
    row = record_for(INJECTOR, "flow_dependent_injection_valve", 120)
    profile = {"version": "rootline_fertilizer_channel_configuration.v1", "device_key": INJECTOR,
        "channel": 1, "controller_baseline_sha256": snapshot["commissioned_baseline_sha256"],
        "firmware": snapshot["firmware"], "native_fail_stop_seconds": 120, "power_restoration_state": "OFF"}
    row["authority_envelope"]["controller_configuration"] = {**profile, "reference": reference("injector-config", profile)}
    return CanonicalDatabase(INJECTOR, row)


def context():
    return {"plan_generation": "P", "batch_generation": "B", "fertilizer_needed": True,
        "premix_verified": True, "job_id": "ROOTLINE-IRRIGATION-JOB-" + "A" * 24,
        "fertilizer_history_complete_through": NOW.isoformat(),
        "job_sha256": "a" * 64, "segment_identity": "ROOTLINE-JOB-SEGMENT-" + "B" * 24,
        "active_zone_ids": ["B12345"], "zone_execution_id": "Z", "completed_pulses": 0,
        "zone_device_id": "100204e9bc", "zone_channel": 1,
        "zone_start_evidence": {"evidence_id": "START", "zone_execution_id": "Z",
            "observed_at": (NOW-timedelta(seconds=600)).isoformat()},
        "zone_output_evidence": {**irrigation_output(NOW), "zone_execution_id": "Z",
            "observed_at": NOW.isoformat(), "state": "ON"},
        "irrigation_stop_deadline": (NOW+timedelta(seconds=1800)).isoformat(),
        "mixer_active": False, "prior_shutdown_unverified": False}


def transport(snapshot, db):
    return RootlineIFTTTTransport(token_store=object(), environ={},
        readback=lambda **_: snapshot, commissioning_connect_factory=db,
        http_open=lambda *_a, **_k: pytest.fail("no provider write allowed"))


def eligibility(snapshot, db, *, now=NOW, flag=True):
    safety = transport(snapshot, db).read_safety_configuration(device_id="100204d497", channel=1)
    artifact = build_auxiliary_eligibility(task={"auxiliary_device_id": "FERTILIZER-INJECTION-CH1"},
        safety=safety, context=context(), flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED": flag}, now=now)
    return safety, artifact


def test_real_normalizer_canonical_loader_transport_and_injector_eligibility():
    snap = fertilizer_snapshot(); db = injector_database(snap)
    assert snap["commissioned_supervised_channels"] == [2]
    safety, artifact = eligibility(snap, db)
    assert artifact["eligible"] and safety["commissioned"]
    assert safety["physical_commissioning_generation"].endswith(digest(db.record))
    assert artifact["physical_commissioning_generation"] == safety["physical_commissioning_generation"]
    assert revalidate_auxiliary_execution_edge(artifact, current_context=context(), current_safety=safety, now=NOW)
    assert db.queries and not eligibility(snap, db, flag=False)[1]["eligible"]
    mixer = transport(snap, db).read_safety_configuration(device_id="100204d497", channel=2)
    assert mixer["commissioned"] and mixer["physical_commissioning_generation"] == snap["commissioned_baseline_id"]


@pytest.mark.parametrize("change", ["missing", "wrong_device", "wrong_channel", "no_authority",
    "revoked", "invalidated", "configuration_invalidated", "wrong_firmware", "wrong_baseline",
    "bad_digest", "future_proof", "no_profile", "wrong_native"])
def test_invalid_canonical_injector_evidence_never_opens_eligibility(change):
    snap = fertilizer_snapshot(); db = injector_database(snap); r = db.record
    profile = r["authority_envelope"]["controller_configuration"]
    if change == "missing": db.missing = True
    if change == "wrong_device": r["device_id"] = "wrong"
    if change == "wrong_channel": r["channel"] = 2
    if change == "no_authority": r["standing_authority"] = False
    if change == "revoked": db.authority_active = False
    if change == "invalidated": db.invalidated.add(r["commissioning_evidence"]["supervised"]["evidence_id"])
    if change == "configuration_invalidated": db.invalidated.add(profile["reference"]["evidence_id"])
    if change == "wrong_firmware": profile["firmware"] = "9.9"
    if change == "wrong_baseline": profile["controller_baseline_sha256"] = "b" * 64
    if change == "wrong_native": r["native_fail_stop_seconds"] = 119
    if change == "bad_digest": db.bad_digest = True
    if change == "future_proof": profile["reference"]["observed_at"] = (NOW+timedelta(seconds=1)).isoformat()
    if change == "no_profile": r["authority_envelope"].pop("controller_configuration")
    safety, artifact = eligibility(snap, db)
    assert not safety["commissioned"] and not artifact["eligible"]


def test_fresh_readback_and_final_edge_canonical_generation_are_required():
    snap = fertilizer_snapshot(); db = injector_database(snap)
    _, artifact = eligibility(snap, db)
    assert not eligibility(snap, db, now=NOW+timedelta(minutes=6))[1]["eligible"]
    db.record["registry_generation"] = 2
    fresh = transport(snap, db).read_safety_configuration(device_id="100204d497", channel=1)
    assert fresh["commissioned"]
    assert not revalidate_auxiliary_execution_edge(artifact, current_context=context(), current_safety=fresh, now=NOW)
    db.authority_active = False
    revoked = transport(snap, db).read_safety_configuration(device_id="100204d497", channel=1)
    assert not revalidate_auxiliary_execution_edge(artifact, current_context=context(), current_safety=revoked, now=NOW)


def test_default_transport_loader_is_bounded_readonly_and_off_observation_is_independent(monkeypatch):
    from modules.oom_sakkie import bounded_postgres_read
    snap = fertilizer_snapshot(); db = injector_database(snap); connections = []
    def connect(**kwargs):
        connections.append(kwargs)
        assert kwargs == {"database_url": "synthetic-db-no-network", "read_only": True}
        return db()
    monkeypatch.setattr(bounded_postgres_read, "connect_bounded_rootline_postgres", connect)
    actual = RootlineIFTTTTransport(token_store=object(),
        environ={"DATABASE_URL": "synthetic-db-no-network"}, readback=lambda **_: snap)
    assert actual.read_safety_configuration(device_id="100204d497", channel=1)["commissioned"]
    count = len(connections)
    assert actual.read_output_state(device_id="100204d497", channel=1)["state"] == "OFF"
    assert actual.read_safety_configuration(device_id="100204d497", channel=2)["commissioned"]
    assert len(connections) == count
    monkeypatch.setattr(bounded_postgres_read, "connect_bounded_rootline_postgres",
        lambda **_: (_ for _ in ()).throw(RuntimeError("synthetic unavailable")))
    assert not actual.read_safety_configuration(device_id="100204d497", channel=1)["commissioned"]
    assert actual.read_output_state(device_id="100204d497", channel=1)["state"] == "OFF"


def borehole_snapshot(**params):
    raw = {"fwVersion": "1.2.0", "switches": [{"outlet": i, "switch": "off"} for i in range(4)],
        "pulses": [{"outlet": 0, "pulse": "on", "width": 3599000}],
        "configure": [{"outlet": 0, "startup": "off"}], "timers": []}
    raw.update(params)
    value = normalize_device_readback(device={"deviceid": "1002851416", "name": "Boorgat 1 Krag Toevoer",
        "productModel": "MINIR4", "extra": {"uiid": 138}, "online": True, "params": raw},
        status={"params": {}}, retrieved_at=NOW)
    return {**value, "response_digest": digest(value), "provider_control_calls": 0}


def pump_database(snapshot):
    row = record_for(PUMP, "pump", 3599)
    profile = {"version": "rootline_borehole_controller_configuration.v1", "device_key": PUMP,
        "firmware": snapshot["firmware"], "device_model": "MINIR4", "device_uiid": 138,
        "native_fail_stop_seconds": 3599, "power_restoration_state": "OFF",
        "scenes_enabled": False, "interlock_enabled": False}
    row["authority_envelope"]["controller_configuration"] = {**profile, "reference": reference("pump-config", profile)}
    return CanonicalDatabase(PUMP, row)


def read_pump(monkeypatch, snap, db):
    from modules.telemetry import rootline_ewelink_readback as reads
    monkeypatch.setattr(reads, "_read_bound_device", lambda **_: deepcopy(snap))
    return reads.read_registered_device("1002851416", token_store=object(), environ={},
        commissioning_connect_factory=db)


def test_canonical_borehole_profile_reaches_actual_readback_and_transport(monkeypatch):
    snap = borehole_snapshot(); db = pump_database(snap)
    assert snap["scenes_enabled"] is None and snap["interlock_enabled"] is None
    actual = read_pump(monkeypatch, snap, db)
    assert actual["scenes_enabled"] is False and actual["interlock_enabled"] is False
    assert actual["actuation_configuration_safe"] is True
    safety = transport(actual, db).read_safety_configuration(device_id="1002851416", channel=1)
    assert safety["authoritative"] and safety["native_inching_seconds"] == 3599
    assert not safety["commissioned"]  # Configuration projection is not physical commissioning.


@pytest.mark.parametrize("change", ["missing", "invalidated", "wrong_firmware", "wrong_device",
    "native_changed", "timer", "provider_scene", "invalid_scene", "provider_interlock", "invalid_interlock"])
def test_borehole_configuration_proof_never_overrides_missing_or_conflicting_truth(monkeypatch, change):
    snap = borehole_snapshot(); db = pump_database(snap)
    if change == "missing": db.missing = True
    if change == "invalidated": db.invalidated.add("synthetic:pump-config")
    if change == "wrong_firmware": snap["firmware"] = "new"
    if change == "wrong_device": db.record["device_id"] = "other"
    if change == "native_changed": snap["channels"][0]["native_auto_off_seconds"] = 100
    if change == "timer": snap = borehole_snapshot(timers=[{"enabled": True}])
    if change == "provider_scene": snap = borehole_snapshot(scenes=[{"enabled": True}])
    if change == "invalid_scene": snap = borehole_snapshot(scenes="invalid")
    if change == "provider_interlock": snap = borehole_snapshot(interlock=1)
    if change == "invalid_interlock": snap = borehole_snapshot(interlock=2)
    actual = read_pump(monkeypatch, snap, db)
    assert not transport(actual, db).read_safety_configuration(device_id="1002851416", channel=1)["authoritative"]


def eskom_database():
    key = "ifttt_smartlife:smartlife_owner_account:synthetic-grid-001:1"
    row = record_for(key, "breaker", 0)
    row.update(adapter_profile="smartlife_eskom_hysteresis_v1", safe_state="UNCHANGED",
        independent_electrical_protection_proven=True)
    row.pop("independent_fail_stop_proven")
    row["commissioning_evidence"].pop("fail_stop_proven")
    row["commissioning_evidence"].update({k: reference(k) for k in
        ("electrical_protection_proven", "manual_isolation_proven")})
    row["authority_envelope"].update(eskom_policy="owner_30_on_35_solar_recovery_off", switch_code="switch")
    return CanonicalDatabase(key, row)


def test_actual_eskom_spine_accepts_only_electrically_proven_state_retaining_profile():
    db = eskom_database()
    actual = load_device_record(db.key, connect_factory=db)
    assert actual["device_record"]["native_fail_stop_seconds"] == 0
    assert "fail_stop_proven" not in actual["device_record"]["commissioning_evidence"]
    for field in ("electrical_protection_proven", "manual_isolation_proven"):
        db.invalidated = {"synthetic:" + field}
        with pytest.raises(ValueError, match="evidence_unresolved"):
            load_device_record(db.key, connect_factory=db)
    db.invalidated = set(); db.authority_active = False
    with pytest.raises(ValueError, match="standing_authority_unresolved"):
        load_device_record(db.key, connect_factory=db)


def test_actual_spine_profile_drives_grid_hysteresis_without_timer_or_physical_flow_claim():
    from modules.telemetry.rootline_eskom_runtime import run_eskom_cycle, EskomObservationCache
    db = eskom_database(); canonical = load_device_record(db.key, connect_factory=db)
    device = db.record["device_id"]; events = []; commands = []; state = ["OFF"]
    config = {"ROOTLINE_ESKOM_DEVICE_ID": device, "ROOTLINE_ESKOM_SWITCH_CODE": "switch",
        "ROOTLINE_ESKOM_ENABLED": "true", "ROOTLINE_ESKOM_ON_EVENT": "eskom_grid_on",
        "ROOTLINE_ESKOM_OFF_EVENT": "eskom_grid_off", "ROOTLINE_IFTTT_MAKER_KEY": "synthetic-not-a-key"}
    def store(action, payload):
        if action == "load_eskom_events": return deepcopy(events)
        if action == "dispatch_eskom_command_edge":
            value = dict(payload); outcome = value.pop("dispatch")()
            store("record_eskom_command_outcome", {**value, "outcome": outcome})
            return {"success": True, "dispatched": True}
        events.append({**deepcopy(payload), "action": action})
        return {"success": True, "created": True}
    def read():
        return {"authoritative": True, "device_id": device, "switch_code": "switch",
            "online": True, "state": state[0], "retrieved_at": NOW.isoformat(),
            "evidence_id": "synthetic-grid-" + state[0]}
    def send(desired, identity):
        commands.append(desired); state[0] = desired
        return {"accepted_unambiguous": True}
    def run(power):
        return run_eskom_cycle(power=power, configuration=config, canonical=canonical,
            store=store, now=NOW, readback=read, dispatch=send, observation_cache=EskomObservationCache())
    power = {"observed_at": NOW.isoformat(), "battery_soc_pct": 30, "solar_power_w": 0,
        "grid_power_w": 0, "load_power_w": 1000, "battery_power_w": 1000, "battery_state": "discharging"}
    assert run(power)["status"] == "eskom_state_verified"
    assert run({**power, "battery_soc_pct": 35, "grid_power_w": 3000,
        "battery_power_w": -2000, "battery_state": "charging"})["hardware_commands"] == 0
    assert state[0] == "ON"
    assert run({**power, "battery_soc_pct": 35, "solar_power_w": 3000,
        "battery_power_w": -2000, "battery_state": "charging"})["status"] == "eskom_state_verified"
    assert commands == ["ON", "OFF"]


@pytest.mark.parametrize("change", ["timer", "wrong_policy", "wrong_provider", "wrong_adapter", "no_electrical_proof", "no_isolator"])
def test_eskom_profile_is_not_a_generic_fail_stop_waiver(change):
    db = eskom_database(); r = db.record
    if change == "timer": r.update(maximum_runtime_seconds=60, native_fail_stop_seconds=60)
    if change == "wrong_policy": r["authority_envelope"]["eskom_policy"] = "other"
    if change == "wrong_provider": r["provider"] = "ewelink"
    if change == "wrong_adapter": r["adapter_profile"] = "generic"
    if change == "no_electrical_proof": r["independent_electrical_protection_proven"] = False
    if change == "no_isolator": r["manual_isolation"] = ""
    with pytest.raises(ValueError): load_device_record(db.key, connect_factory=db)
