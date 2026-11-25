from datetime import timedelta
import pytest
from modules.telemetry.rootline_energy_policy import managed_energy_decision, validate_energy_control_fields
from tests.test_rootline_eskom_runtime import NOW, power, Store, Switch, run


def controls(device, **fields):
    return {"devices": {device: {"mode": "automatic", "fields": fields}}, "requests": [], "consumed": []}


def request(kind):
    return {"request_id": "owner-request-44", "change": {"device_id": "eskom", "kind": kind},
            "effective_at": (NOW-timedelta(seconds=1)).isoformat(),
            "expires_at": (NOW+timedelta(minutes=5)).isoformat()}


def test_no_owner_overlay_keeps_existing_decisions():
    for packet in (power(), power(battery_soc_pct=36), power(battery_soc_pct=80, solar_power_w=1600)):
        assert managed_energy_decision(packet, now=NOW) == managed_energy_decision(packet, now=NOW, owner_controls={"devices": {}})


def test_borehole_thresholds_reach_actual_energy_decision():
    packet = power(battery_soc_pct=40, solar_power_w=1600)
    assert not managed_energy_decision(packet, now=NOW)["continuous_borehole_eligible"]
    assert managed_energy_decision(packet, now=NOW, owner_controls=controls("borehole", solar_proxy_w=1800, battery_floor_pct=35))["continuous_borehole_eligible"]
    assert not managed_energy_decision(packet, now=NOW, owner_controls=controls("borehole", solar_proxy_w=1800, battery_floor_pct=45))["continuous_borehole_eligible"]


def test_eskom_thresholds_reach_actual_decision_and_keep_solar_recovery():
    packet = power(battery_soc_pct=40)
    assert managed_energy_decision(packet, now=NOW)["eskom_requested_state"] == "UNCHANGED"
    changed = controls("eskom", on_soc_pct=45, off_soc_pct=50)
    assert managed_energy_decision(packet, now=NOW, owner_controls=changed)["eskom_requested_state"] == "ON"
    grid_only = power(battery_soc_pct=60, grid_power_w=2000, battery_power_w=-1000, battery_state="charging")
    assert managed_energy_decision(grid_only, now=NOW, owner_controls=changed)["eskom_requested_state"] == "UNCHANGED"
    solar = power(battery_soc_pct=50, solar_power_w=3000, battery_power_w=-2000, battery_state="charging")
    assert managed_energy_decision(solar, now=NOW, owner_controls=changed)["eskom_requested_state"] == "OFF"


def test_mixer_reserve_changes_start_and_continuation():
    packet = power(battery_soc_pct=60)
    before = managed_energy_decision(packet, now=NOW)
    after = managed_energy_decision(packet, now=NOW, owner_controls=controls("mixer", reserve_soc_pct=55))
    assert not before["mixing_eligible"] and not before["mixing_continue_eligible"]
    assert after["mixing_eligible"] and after["mixing_continue_eligible"]


def test_expired_or_future_settings_do_not_affect_energy():
    changed = controls("mixer", reserve_soc_pct=55)
    changed["devices"]["mixer"]["expires_at"] = NOW.isoformat()
    assert not managed_energy_decision(power(battery_soc_pct=60), now=NOW, owner_controls=changed)["mixing_eligible"]
    changed["devices"]["mixer"].pop("expires_at")
    changed["devices"]["mixer"]["effective_at"] = (NOW+timedelta(seconds=1)).isoformat()
    assert not managed_energy_decision(power(battery_soc_pct=60), now=NOW, owner_controls=changed)["mixing_eligible"]


@pytest.mark.parametrize("device,fields", [("eskom", {"on_soc_pct":50,"off_soc_pct":40}),
    ("mixer", {"reserve_soc_pct":49}), ("mixer", {"reserve_soc_pct":True}),
    ("mixer", {"reserve_soc_pct":float("nan")}), ("borehole", {"solar_proxy_w":0}),
    ("borehole", {"unknown":1}), ("mixer", {"reserve_soc_pct":"70"})])
def test_invalid_settings_rejected(device, fields):
    with pytest.raises(ValueError):
        validate_energy_control_fields(device, fields)


def test_manual_grid_on_requires_fresh_evidence():
    packet = power(battery_soc_pct=80)
    assert managed_energy_decision(packet, now=NOW, owner_request=request("run"))["eskom_requested_state"] == "ON"
    packet["observed_at"] = (NOW-timedelta(minutes=16)).isoformat()
    assert managed_energy_decision(packet, now=NOW, owner_request=request("run"))["eskom_requested_state"] == "UNCHANGED"


def test_manual_grid_off_keeps_existing_off_conditions():
    assert managed_energy_decision(power(), now=NOW, owner_request=request("stop"))["eskom_requested_state"] == "UNCHANGED"
    solar = power(battery_soc_pct=50, solar_power_w=3000, battery_power_w=-2000, battery_state="charging")
    assert managed_energy_decision(solar, now=NOW, owner_request=request("stop"))["eskom_requested_state"] == "OFF"


def test_runtime_pause_retains_grid_and_dispatches_nothing():
    changed = controls("eskom")
    changed["devices"]["eskom"]["mode"] = "paused"
    store, switch = Store(), Switch()
    switch.state = "ON"
    result = run(store, switch, owner_controls=changed)
    assert result["hardware_commands"] == 0 and switch.state == "ON" and switch.calls == []


def test_runtime_uses_saved_thresholds_without_changing_device_authority():
    store, switch = Store(), Switch()
    result = run(store, switch, power=power(battery_soc_pct=40),
        owner_controls=controls("eskom", on_soc_pct=45, off_soc_pct=50))
    assert result["status"] == "eskom_state_verified"
    assert [state for state, _ in switch.calls] == ["ON"]


def test_unrelated_valid_device_settings_do_not_break_energy_overlay():
    value = controls("mixer", reserve_soc_pct=55, session_minutes=10)
    assert managed_energy_decision(power(battery_soc_pct=60), now=NOW, owner_controls=value)["mixing_eligible"]


def test_expired_manual_request_cannot_fall_back_to_automatic_command():
    value = request("run")
    value["expires_at"] = NOW.isoformat()
    assert managed_energy_decision(power(), now=NOW, owner_request=value)["eskom_requested_state"] == "UNCHANGED"


def test_already_on_manual_grid_request_is_satisfied_without_send():
    value = controls("eskom")
    value["requests"] = [request("run")]
    store, switch = Store(), Switch()
    switch.state = "ON"
    satisfied = []
    def recording(action, payload):
        if action == "satisfy_owner_eskom_request":
            satisfied.append(payload)
            return {"success": True, "created": True}
        return store(action, payload)
    result = run(recording, switch, owner_controls=value, power=power(battery_soc_pct=80))
    assert result["status"] == "eskom_owner_request_satisfied"
    assert satisfied[0]["owner_request_id"] == "owner-request-44"
    assert switch.calls == []
