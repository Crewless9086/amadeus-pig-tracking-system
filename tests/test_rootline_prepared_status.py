"""Independent STATUS evidence never inherits earlier output state."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from modules.telemetry.rootline_ewelink_oauth import OAuthFailure
from modules.telemetry.rootline_ewelink_readback import _normalize_prepared_status


def metadata(single):
    outlets = range(1 if single else 4)
    return {"deviceid": "1002851416" if single else "100204e9bc",
        "productModel": "MINIR4" if single else "4CHPROR3",
        "extra": {"uiid": 138 if single else 9}, "online": True,
        "params": {"fwVersion": "3.8.2",
            # Deliberately cached OFF: strict raw STATUS must still refuse missing outputs.
            "switches": [{"outlet": i, "switch": "off"} for i in range(4)],
            "pulses": [{"outlet": i, "pulse": "on", "width": 3599500} for i in outlets],
            "configure": [{"outlet": i, "startup": "off"} for i in outlets],
            "timers": [], "interlock": 0, "scenes": []}}


def normalize(device, status):
    return _normalize_prepared_status(device=device, status=status,
        expected=device["deviceid"], baseline=None,
        metadata_received_at=datetime.now(timezone.utc)-timedelta(seconds=10),
        token_refreshed=False)


@pytest.mark.parametrize("single", [False, True])
@pytest.mark.parametrize("fault", ["empty", "missing", "partial", "duplicate", "boolean_outlet",
    "unknown_state", "on", "identity", "online_conflict", "switch_conflict"])
def test_status_requires_independent_complete_exact_off(single, fault):
    device = metadata(single)
    status = {"params": {"switches": [{"outlet": i, "switch": "off"} for i in range(4)]}}
    rows = status["params"]["switches"]
    if fault == "empty": status["params"] = {}
    elif fault == "missing": status = {}
    elif fault == "partial": status["params"]["switches"] = rows[:2]
    elif fault == "duplicate": rows[1]["outlet"] = 0
    elif fault == "boolean_outlet": rows[0]["outlet"] = False
    elif fault == "unknown_state": rows[0]["switch"] = "unknown"
    elif fault == "on": rows[0]["switch"] = "on"
    elif fault == "identity": status["deviceid"] = "other"
    elif fault == "online_conflict": status["online"] = False
    else: status["params"]["switch"] = "on"
    with pytest.raises(OAuthFailure):
        normalize(device, status)


@pytest.mark.parametrize("single", [False, True])
def test_fresh_status_preserves_separate_metadata_clock(single):
    device = metadata(single)
    status = {"params": {"switches": [{"outlet": i, "switch": "off"} for i in range(4)]}}
    before = deepcopy(device)
    result = normalize(device, status)
    assert device == before
    assert result["online_from_fresh_status"] is False
    assert result["configuration_from_fresh_status"] is False
    assert result["metadata_received_at"] == result["online_metadata_received_at"]
    assert result["metadata_received_at"] < result["retrieved_at"]
    assert result["provider_control_calls"] == 0 and result["autonomous_control_enabled"] is False
    assert result["response_digest"] and all(row["output_state"] == "OFF" for row in result["channels"])


def test_mini_single_physical_output_status_is_supported():
    assert normalize(metadata(True), {"params": {"switch": "off"}})["channels"][0]["output_state"] == "OFF"


def test_mini_scalar_on_cannot_fall_back_to_cached_off():
    with pytest.raises(OAuthFailure, match="outputs_not_off"):
        normalize(metadata(True), {"params": {"switch": "on"}})


def test_prior_metadata_timestamp_cannot_supply_status_observation_clock():
    device = metadata(True)
    device["updatedAt"] = "2000-01-01T00:00:00+00:00"
    result = normalize(device, {"params": {"switch": "off"}})
    assert result["freshness_clock_source"] == "trusted_authenticated_receipt"
    assert result["provider_observed_at"] is None
    assert result["online_from_fresh_status"] is False


def test_prepared_client_cleanup_attempts_second_close_when_first_raises():
    import threading
    from modules.telemetry.rootline_ewelink_request_budget import _PreparedNoSendClients
    calls = []
    class Client:
        def __init__(self, name): self.name = name
        def close(self):
            calls.append(self.name)
            if self.name == "first": raise RuntimeError("synthetic close failure")
    prepared = object.__new__(_PreparedNoSendClients)
    prepared._gate = threading.Lock()
    prepared._clients = [Client("first"), Client("second")]
    prepared._spent = False
    prepared.close()
    assert calls == ["first", "second"] and prepared._spent and prepared._clients == []


@pytest.mark.parametrize("stamp", ["2000-01-01T00:00:00+00:00", "invalid", "2999-01-01T00:00:00+00:00"])
def test_explicit_status_timestamp_cannot_be_refreshed_by_receipt(stamp):
    with pytest.raises(OAuthFailure, match="status_not_fresh"):
        normalize(metadata(True), {"params": {"switch": "off"}, "updatedAt": stamp})


def test_fresh_explicit_status_timestamp_remains_distinct_from_receipt():
    stamp = datetime.now(timezone.utc).isoformat()
    result = normalize(metadata(True), {"params": {"switch": "off"}, "updatedAt": stamp})
    assert result["freshness_clock_source"] == "provider_observation_timestamp"
    assert result["provider_observed_at"] == stamp and result["observation_fresh"] is True
