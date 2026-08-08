import urllib.parse
import re
from datetime import datetime, timedelta, timezone

import pytest

from modules.telemetry.rootline_ewelink_oauth import (
    OAuthFailure, complete_authorization, create_authorization_request, oauth_readiness,
    normalize_device_readback,
)
from modules.telemetry import rootline_ewelink_oauth as oauth_module

NOW = datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc)
REDIRECT = "https://amadeus-pig-tracking-system.onrender.com/api/rootline/provider/ewelink/oauth/callback"


def env(**changes):
    result = {"EWELINK_CLIENT_ID": "client-id", "EWELINK_CLIENT_SECRET": "c" * 40,
              "EWELINK_EXPECTED_DEVICE_ID": "100204e9bc",
              "EWELINK_OAUTH_REDIRECT_URI": REDIRECT,
              "EWELINK_OAUTH_STATE_SECRET": "s" * 40,
              "EWELINK_READBACK_ENABLED": "false", "ROOTLINE_AUTONOMOUS_BC_ENABLED": "false"}
    result.update(changes)
    return result


class States:
    def __init__(self): self.item, self.used = None, False
    def create(self, item): self.item = item
    def consume(self, digest, now):
        if self.used or not self.item or self.item["state_digest"] != digest or self.item["expires_at"] < now:
            return None
        self.used = True
        return {key: self.item[key] for key in ("principal_digest", "nonce_digest", "redirect_uri_digest")}


class Tokens:
    def __init__(self): self.records = []
    def append(self, item): self.records.append(item); return True


def start(source=None):
    store = States()
    result = create_authorization_request(principal="owner:stable", state_store=store,
                                          environ=source or env(), now=NOW)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(result["authorization_url"]).query)
    return store, result, query


def fake_provider(overrides=None):
    calls = []
    data = {
        "/v2/user/oauth/token": {"accessToken": "secret-access", "refreshToken": "secret-refresh",
            "atExpiredTime": int((NOW + timedelta(days=30)).timestamp() * 1000),
            "rtExpiredTime": int((NOW + timedelta(days=60)).timestamp() * 1000)},
        "/v2/family": {"currentFamilyId": "farm", "familyList": [{"id": "farm", "apikey": "account"}]},
        "/v2/device/thing": {"thingList": [{"itemType": 1, "itemData": {
            "deviceid": "100204e9bc", "apikey": "account", "online": True}}]},
        "/v2/device/thing/status": {"params": {
            "switches": [{"outlet": outlet, "switch": "off"} for outlet in range(4)],
            "pulse": "on", "pulseWidth": 3600000, "startup": ["off"] * 4,
            "timers": [], "interlock": 0}},
    }
    data.update(overrides or {})
    def request(method, url, **kwargs):
        path = urllib.parse.urlparse(url).path
        calls.append((method, path, kwargs["mode"]))
        return data[path]
    return request, calls


def authorize(source=None, overrides=None):
    source = source or env(); states, _, query = start(source); tokens = Tokens()
    request, calls = fake_provider(overrides)
    result = complete_authorization(query={"code": "code", "region": "eu", "state": query["state"][0]},
        state_store=states, token_store=tokens, environ=source, http_request=request,
        now=NOW + timedelta(seconds=5))
    return result, states, tokens, calls, query, request


def test_readiness_requires_exact_redirect_and_false_flags():
    assert oauth_readiness(env())["status"] == "ready"
    assert oauth_readiness(env(EWELINK_READBACK_ENABLED="true"))["status"] == "not_ready"
    assert oauth_readiness(env(EWELINK_OAUTH_REDIRECT_URI="https://evil.test"))["status"] == "not_ready"


def test_start_binds_nonce_and_persists_no_raw_secret():
    states, result, query = start()
    assert query["redirectUrl"] == [REDIRECT] and query["nonce"] and query["state"]
    assert re.fullmatch(r"[A-Za-z0-9]{8}", query["nonce"][0])
    assert env()["EWELINK_CLIENT_SECRET"] not in repr(states.item)
    assert env()["EWELINK_OAUTH_STATE_SECRET"] not in repr(states.item)
    assert result["readback_enabled"] is False and result["autonomous_control_enabled"] is False


def test_callback_uses_only_allowlisted_reads_and_encrypts_tokens():
    result, _, tokens, calls, _, _ = authorize()
    assert calls == [("POST", "/v2/user/oauth/token", "signed"), ("GET", "/v2/family", "bearer"),
                     ("GET", "/v2/device/thing", "bearer"),
                     ("GET", "/v2/device/thing/status", "bearer")]
    assert "secret-access" not in repr(tokens.records) and "secret-refresh" not in repr(tokens.records)
    assert result["provider_control_implemented"] is False


def test_replay_rejected_without_more_provider_calls():
    result, states, tokens, calls, query, request = authorize()
    with pytest.raises(OAuthFailure, match="replayed_or_expired"):
        complete_authorization(query={"code": "code", "region": "eu", "state": query["state"][0]},
            state_store=states, token_store=tokens, environ=env(), http_request=request,
            now=NOW + timedelta(seconds=6))
    assert len(calls) == 4 and len(tokens.records) == 1


@pytest.mark.parametrize("changes,match", [({"EWELINK_EXPECTED_ACCOUNT_ID": "wrong"}, "mismatch"),
                                             ({"EWELINK_EXPECTED_DEVICE_ID": "wrong"}, "not_found")])
def test_wrong_account_or_device_rejected(changes, match):
    with pytest.raises(OAuthFailure, match=match): authorize(env(**changes))


def test_missing_or_malformed_current_output_status_and_wrong_region_rejected():
    with pytest.raises(OAuthFailure, match="status_incomplete"):
        authorize(overrides={"/v2/device/thing/status": {"params": {"switches": []}}})
    with pytest.raises(OAuthFailure, match="status_incomplete"):
        authorize(overrides={"/v2/device/thing/status": {"params": {"switches": [
            {"outlet": 0, "switch": "off"}, {"outlet": 1, "switch": "unknown"}]}}})
    states, _, query = start(); request, calls = fake_provider()
    with pytest.raises(OAuthFailure, match="malformed"):
        complete_authorization(query={"code": "code", "region": "evil", "state": query["state"][0]},
            state_store=states, token_store=Tokens(), environ=env(), http_request=request, now=NOW)
    assert calls == [] and states.used is False


def test_device_and_status_params_are_composed_before_validation():
    device_params = {"pulse": "on", "pulseWidth": 3600000,
                     "startup": ["off"] * 4, "timers": [], "interlock": 0}
    things = {"thingList": [{"itemType": 1, "itemData": {
        "deviceid": "100204e9bc", "apikey": "account", "online": True,
        "params": device_params}}]}
    status = {"params": {"switches": [
        {"outlet": outlet, "switch": "off"} for outlet in range(4)]}}
    result, _, tokens, _, _, _ = authorize(overrides={
        "/v2/device/thing": things, "/v2/device/thing/status": status})
    assert result["binding_created"] is True
    assert set(tokens.records[0]["status_field_names"]) >= {
        "switches", "pulse", "pulseWidth", "startup", "timers", "interlock"}
    assert result["safety_readback_complete"] is False
    assert set(result["safety_readback_missing"]) >= {
        "native_auto_off_enabled", "native_auto_off_duration", "power_restoration"}


def test_valid_device_binding_and_current_outputs_preserve_grant_when_safety_fields_are_sparse():
    status = {"params": {"switches": [
        {"outlet": 0, "switch": "off"}, {"outlet": 1, "switch": "off"},
        {"outlet": 2, "switch": "off"}, {"outlet": 3, "switch": "off"}]}}
    result, _, tokens, calls, _, _ = authorize(overrides={
        "/v2/device/thing/status": status})
    assert result["binding_created"] is True
    assert result["safety_readback_complete"] is False
    assert result["safety_readback_missing"] == [
        "conflicting_control_paths", "native_auto_off_duration",
        "native_auto_off_enabled", "power_restoration", "timers"]
    assert tokens.records[0]["status_field_names"] == ["switches"]
    assert calls[-1] == ("GET", "/v2/device/thing/status", "bearer")
    assert result["readback_enabled"] is False
    assert result["autonomous_control_enabled"] is False


def test_genuine_four_channel_shape_normalizes_nested_pulses_and_power_restoration():
    params = {
        "fwVersion": "3.8.2", "switches": [
            {"outlet": outlet, "switch": "off"} for outlet in range(4)],
        "pulses": [{"outlet": outlet, "pulse": "on", "width": 3600000}
                   for outlet in range(4)],
        "configure": [{"outlet": outlet, "startup": "off"} for outlet in range(4)],
        "timers": [], "scenes": [], "interlock": 0,
    }
    result = normalize_device_readback(device={"deviceid": "100204e9bc", "online": True,
        "params": params, "updatedAt": NOW.isoformat()}, status={"params": {}},
        retrieved_at=NOW)
    assert result["authoritative"] is True
    assert result["actuation_safety_complete"] is True
    assert result["actuation_configuration_safe"] is True
    assert result["actuation_eligible"] is False
    assert [item["output_state"] for item in result["channels"]] == ["OFF"] * 4
    assert [item["native_auto_off_seconds"] for item in result["channels"]] == [3600] * 4
    assert [item["power_restoration_state"] for item in result["channels"]] == ["OFF"] * 4
    assert result["interlock_enabled"] is False and result["timers_enabled"] is False


def test_configure_does_not_prove_interlock_and_unexposed_control_paths_fail_closed():
    params = {"switches": [{"outlet": outlet, "switch": "off"} for outlet in range(4)],
        "pulses": [{"outlet": outlet, "pulse": "on", "width": 3600000} for outlet in range(4)],
        "configure": [{"outlet": outlet, "startup": "off"} for outlet in range(4)], "timers": []}
    result = normalize_device_readback(device={"deviceid": "100204e9bc", "online": True,
        "params": params}, status={"params": {}}, retrieved_at=NOW)
    assert result["authoritative"] is True and result["interlock_enabled"] is None
    assert result["actuation_safety_complete"] is False
    assert "conflicting_control_paths" in result["safety_readback_missing"]
    assert "provider_timestamp" not in result["safety_readback_missing"]
    assert result["freshness_clock_source"] == "trusted_authenticated_receipt"
    assert result["trusted_receipt_at"] == NOW.isoformat()
    assert result["provider_observed_at"] is None
    assert result["provider_timestamp_fresh"] is None
    assert result["observation_fresh"] is True
    assert result["provider_interlock_supported"] is False
    assert result["provider_scenes_supported"] is False


@pytest.mark.parametrize("observed", ["malformed", "2026-08-08T07:00:00Z", "2026-08-08T08:01:00Z"])
def test_stale_malformed_or_future_provider_timestamp_blocks_only_actuation(observed):
    params = {"switches": [{"outlet": outlet, "switch": "off"} for outlet in range(4)],
        "pulses": [{"outlet": outlet, "pulse": "on", "width": 3600000} for outlet in range(4)],
        "configure": [{"outlet": outlet, "startup": "off"} for outlet in range(4)],
        "timers": [], "scenes": [], "interlock": 0}
    result = normalize_device_readback(device={"deviceid": "100204e9bc", "online": True,
        "params": params, "updatedAt": observed}, status={"params": {}}, retrieved_at=NOW)
    assert result["current_outputs_authoritative"] is True
    assert result["actuation_safety_complete"] is False
    assert "provider_timestamp" in result["safety_readback_missing"]


@pytest.mark.parametrize("observed", ["", None, 0, False])
def test_falsey_but_supplied_provider_timestamp_is_malformed_not_absent(observed):
    params = {"switches": [{"outlet": outlet, "switch": "off"} for outlet in range(4)],
        "pulses": [{"outlet": outlet, "pulse": "on", "width": 3600000} for outlet in range(4)],
        "configure": [{"outlet": outlet, "startup": "off"} for outlet in range(4)],
        "timers": [], "scenes": [], "interlock": 0}
    result = normalize_device_readback(device={"deviceid": "100204e9bc", "online": True,
        "params": params}, status={"params": {}, "updatedAt": observed}, retrieved_at=NOW)
    assert result["observation_fresh"] is False
    assert result["freshness_clock_source"] == "invalid_provider_timestamp"
    assert "provider_timestamp" in result["safety_readback_missing"]


def test_conflicting_scene_aliases_fail_closed_without_hiding_active_scene():
    params = {"switches": [{"outlet": outlet, "switch": "off"} for outlet in range(4)],
        "pulses": [{"outlet": outlet, "pulse": "on", "width": 3600000} for outlet in range(4)],
        "configure": [{"outlet": outlet, "startup": "off"} for outlet in range(4)],
        "timers": [], "scenes": [], "scene": [{"enabled": True}], "interlock": 0}
    result = normalize_device_readback(device={"deviceid": "100204e9bc", "online": True,
        "updatedAt": NOW.isoformat(), "params": params}, status={"params": {}}, retrieved_at=NOW)
    assert result["scene_evidence_conflict"] is True
    assert result["provider_scenes_supported"] is False
    assert result["actuation_configuration_safe"] is False
    assert "conflicting_control_paths" in result["safety_readback_missing"]


def test_consistent_scene_aliases_are_accepted_once():
    scenes = []
    params = {"switches": [{"outlet": outlet, "switch": "off"} for outlet in range(4)],
        "pulses": [{"outlet": outlet, "pulse": "on", "width": 3600000} for outlet in range(4)],
        "configure": [{"outlet": outlet, "startup": "off"} for outlet in range(4)],
        "timers": [], "scenes": scenes, "scene": scenes, "interlock": 0}
    result = normalize_device_readback(device={"deviceid": "100204e9bc", "online": True,
        "updatedAt": NOW.isoformat(), "params": params}, status={"params": {}}, retrieved_at=NOW)
    assert result["scene_evidence_conflict"] is False
    assert result["provider_scenes_supported"] is True
    assert result["actuation_safety_complete"] is True


@pytest.mark.parametrize("scenes", [None, "malformed", {"enabled": False}])
def test_malformed_scene_evidence_cannot_complete_actuation_safety(scenes):
    params = {"switches": [{"outlet": outlet, "switch": "off"} for outlet in range(4)],
        "pulses": [{"outlet": outlet, "pulse": "on", "width": 3600000} for outlet in range(4)],
        "configure": [{"outlet": outlet, "startup": "off"} for outlet in range(4)],
        "timers": [], "scenes": scenes, "interlock": 0}
    result = normalize_device_readback(device={"deviceid": "100204e9bc", "online": True,
        "params": params, "updatedAt": NOW.isoformat()}, status={"params": {}}, retrieved_at=NOW)
    assert result["actuation_safety_complete"] is False
    assert result["actuation_configuration_safe"] is False
    assert "conflicting_control_paths" in result["safety_readback_missing"]


def test_tampered_and_expired_state_are_rejected_before_provider_calls():
    states, _, query = start()
    request, calls = fake_provider()
    with pytest.raises(OAuthFailure, match="state_invalid"):
        complete_authorization(query={"code": "code", "region": "eu",
            "state": query["state"][0] + "x"}, state_store=states,
            token_store=Tokens(), environ=env(), http_request=request, now=NOW)
    assert states.used is False and calls == []

    expired, _, expired_query = start()
    with pytest.raises(OAuthFailure, match="state_expired"):
        complete_authorization(query={"code": "code", "region": "eu",
            "state": expired_query["state"][0]}, state_store=expired,
            token_store=Tokens(), environ=env(), http_request=request,
            now=NOW + timedelta(minutes=11))
    assert calls == []


def test_weak_secrets_and_unallowlisted_provider_operations_are_rejected():
    assert oauth_readiness(env(EWELINK_CLIENT_SECRET="short"))["status"] == "not_ready"
    assert oauth_readiness(env(EWELINK_OAUTH_STATE_SECRET="short"))["status"] == "not_ready"
    with pytest.raises(OAuthFailure, match="operation_rejected"):
        oauth_module._provider_request("POST", "https://eu-apia.coolkit.cc/v2/device/thing/status",
            body={"switch": "on"}, mode="signed", environ=env())
    with pytest.raises(OAuthFailure, match="operation_rejected"):
        oauth_module._provider_request("GET", "https://eu-apia.coolkit.cc/v2/device/thing?num=1",
            mode="bearer", token="not-used", environ=env())
    with pytest.raises(OAuthFailure, match="host_rejected"):
        oauth_module._provider_request("GET", "https://evil.example/v2/family",
            mode="bearer", token="not-used", environ=env())


def test_transport_exchanges_once_with_bounded_timeout_and_rejects_redirect(monkeypatch):
    import json
    target = "https://eu-apia.coolkit.cc/v2/user/oauth/token"
    calls = []
    class Response:
        def __init__(self, final_url): self.final_url = final_url
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def geturl(self): return self.final_url
        def read(self): return json.dumps({"error": 0, "data": {"ok": True}}).encode()
    class Opener:
        def __init__(self, final_url): self.final_url = final_url
        def open(self, request, timeout):
            calls.append((request.full_url, timeout, request.get_header("X-ck-nonce")))
            return Response(self.final_url)
    monkeypatch.setattr(oauth_module.urllib.request, "build_opener", lambda *_: Opener(target))
    body = {"code": "one-use", "redirectUrl": REDIRECT, "grantType": "authorization_code"}
    assert oauth_module._provider_request("POST", target, body=body, mode="signed", environ=env()) == {"ok": True}
    assert len(calls) == 1 and calls[0][:2] == (target, 15)
    assert re.fullmatch(r"[A-Za-z0-9]{8}", calls[0][2])

    monkeypatch.setattr(oauth_module.urllib.request, "build_opener",
                        lambda *_: Opener("https://eu-apia.coolkit.cc/v2/family"))
    with pytest.raises(OAuthFailure, match="redirect_rejected"):
        oauth_module._provider_request("POST", target, body=body, mode="signed", environ=env())
