from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
import urllib.parse

import pytest

from modules.telemetry.rootline_ewelink_oauth import (
    ADAPTER_VERSION, OAuthFailure, _digest, _encrypt, _token_key,
    decrypt_access_token, decrypt_refresh_token,
)
from modules.telemetry.rootline_ewelink_readback import (
    read_current_device, read_registered_device,
)

NOW = datetime(2026, 8, 8, 16, 30, tzinfo=timezone.utc)


def env(**changes):
    value = {"EWELINK_CLIENT_SECRET": "c"*40, "EWELINK_OAUTH_STATE_SECRET": "s"*40,
        "EWELINK_CLIENT_ID": "client", "EWELINK_EXPECTED_DEVICE_ID": "100204e9bc",
        "EWELINK_READBACK_ENABLED": "true"}
    value.update(changes); return value


class Store:
    def __init__(self, source=None):
        source = source or env(); account = _digest("account")
        aad = f"eu|{account}|100204e9bc|{ADAPTER_VERSION}".encode()
        self.records = []
        self.record = {"token_binding_id": "ROOTLINE-EWELINK-ORIGINAL",
            "device_id": "100204e9bc", "region": "eu",
            "provider_account_digest": account, "adapter_version": ADAPTER_VERSION,
            "access_token_ciphertext": _encrypt("access", _token_key(source), aad),
            "refresh_token_ciphertext": _encrypt("refresh", _token_key(source), aad),
            "access_expires_at": NOW + timedelta(hours=1),
            "refresh_expires_at": NOW + timedelta(days=30)}
    def latest(self): return self.record
    def append(self, record):
        self.records.append(record); self.record = record; return True
    def rotate_exact(self, predecessor_id, build):
        if self.record["token_binding_id"] != predecessor_id:
            return None
        record = build(dict(self.record))
        record["predecessor_token_binding_id"] = predecessor_id
        record["generation"] = self.record.get("generation", 1) + 1
        self.records.append(record); self.record = record
        return record


def provider(overrides=None):
    params = {"fwVersion": "3.8.2", "switches": [{"outlet": i, "switch": "off"} for i in range(4)],
        "pulses": [{"outlet": i, "pulse": "on", "width": 3600000} for i in range(4)],
        "configure": [{"outlet": i, "startup": "off"} for i in range(4)],
        "timers": [], "interlock": 0, "scenes": []}
    data = {"/v2/family": {"currentFamilyId": "farm", "familyList": [{"id": "farm", "apikey": "account"}]},
        "/v2/device/thing": {"thingList": [{"itemType": 1, "itemData": {"deviceid": "100204e9bc",
            "apikey": "account", "online": True, "updatedAt": NOW.isoformat(), "params": params}}]},
        "/v2/device/thing/status": {"params": {}}}
    data.update(overrides or {}); calls=[]
    def request(method, url, **kwargs):
        calls.append((method, urllib.parse.urlparse(url).path)); return data[calls[-1][1]]
    return request, calls


def test_zero_command_readback_normalizes_exact_device_and_is_deterministic():
    request, calls = provider(); first = read_current_device(token_store=Store(), environ=env(),
        http_request=request, now=NOW)
    second = read_current_device(token_store=Store(), environ=env(), http_request=request, now=NOW)
    assert first == second and first["authoritative"] is True
    assert first["scenes_enabled"] is False
    assert first["actuation_safety_complete"] is True
    assert first["actuation_eligible"] is False
    assert first["provider_control_calls"] == 0
    assert first["provider_calls"] == 3 and first["token_refreshed"] is False
    assert first["freshness_clock_source"] == "provider_observation_timestamp"
    assert first["observation_fresh"] is True
    assert calls == [("GET", "/v2/family"), ("GET", "/v2/device/thing"),
        ("GET", "/v2/device/thing/status")]*2


def test_disabled_stale_offline_and_missing_interlock_fail_closed():
    with pytest.raises(OAuthFailure, match="disabled"):
        read_current_device(token_store=Store(), environ=env(EWELINK_READBACK_ENABLED="false"), now=NOW)
    stale=Store(); stale.record["access_expires_at"] = NOW
    stale.record["refresh_expires_at"] = NOW
    with pytest.raises(OAuthFailure, match="refresh_token_unavailable"):
        read_current_device(token_store=stale, environ=env(), now=NOW)
    offline = {"thingList": [{"itemType": 1, "itemData": {
        "deviceid": "100204e9bc", "apikey": "account", "online": False,
        "updatedAt": NOW.isoformat(),
        "params": {"switches": [{"outlet": i, "switch": "off"} for i in range(4)]}}}]}
    request,_=provider({"/v2/device/thing": offline})
    result=read_current_device(token_store=Store(), environ=env(), http_request=request, now=NOW)
    assert result["authoritative"] is False
    assert result["actuation_safety_complete"] is False


def test_expired_access_token_rotates_append_only_and_survives_restart():
    store = Store(); store.record["access_expires_at"] = NOW - timedelta(seconds=1)
    request, calls = provider({"/v2/user/refresh": {"at": "rotated-access", "rt": "rotated-refresh"}})
    result = read_current_device(token_store=store, environ=env(), http_request=request, now=NOW)
    assert result["authoritative"] is True
    assert result["provider_calls"] == 4 and result["token_refreshed"] is True
    assert calls[0] == ("POST", "/v2/user/refresh")
    assert len(store.records) == 1
    generation = store.records[0]
    assert generation["token_binding_id"] != "ROOTLINE-EWELINK-ORIGINAL"
    assert decrypt_access_token(generation, env()) == "rotated-access"
    assert decrypt_refresh_token(generation, env()) == "rotated-refresh"
    assert "rotated-access" not in repr(generation)
    assert "rotated-refresh" not in repr(generation)

    restarted = Store(); restarted.record = dict(generation)
    request_after_restart, restart_calls = provider()
    after_restart = read_current_device(token_store=restarted, environ=env(),
        http_request=request_after_restart, now=NOW + timedelta(seconds=1))
    assert after_restart["authoritative"] is True
    assert restart_calls == [("GET", "/v2/family"), ("GET", "/v2/device/thing"),
        ("GET", "/v2/device/thing/status")]


def test_refresh_response_failure_writes_no_generation():
    store = Store(); store.record["access_expires_at"] = NOW - timedelta(seconds=1)
    request, _ = provider({"/v2/user/refresh": {"at": "", "rt": "rotated-refresh"}})
    with pytest.raises(OAuthFailure, match="refresh_response_incomplete"):
        read_current_device(token_store=store, environ=env(), http_request=request, now=NOW)
    assert store.records == []


def test_two_workers_refresh_exact_predecessor_once_and_replay_latest():
    class SerializedStore(Store):
        def __init__(self):
            super().__init__(); self.lock = threading.Lock()
            self.record["access_expires_at"] = NOW - timedelta(seconds=1)
        def rotate_exact(self, predecessor_id, build):
            with self.lock:
                return super().rotate_exact(predecessor_id, build)
    store = SerializedStore()
    request, calls = provider({"/v2/user/refresh": {"at": "rotated-access", "rt": "rotated-refresh"}})
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: read_current_device(
            token_store=store, environ=env(), http_request=request, now=NOW), range(2)))
    assert len(store.records) == 1
    assert calls.count(("POST", "/v2/user/refresh")) == 1
    assert all(result["provider_control_calls"] == 0 for result in results)
    assert all(result["authoritative"] is True for result in results)


def test_provider_success_persistence_failure_fails_closed_without_reuse():
    class FailedStore(Store):
        def rotate_exact(self, predecessor_id, build):
            self.pending = build(dict(self.record))
            raise RuntimeError("database unavailable after provider success")
    store = FailedStore(); store.record["access_expires_at"] = NOW - timedelta(seconds=1)
    request, calls = provider({"/v2/user/refresh": {"at": "rotated-access", "rt": "rotated-refresh"}})
    with pytest.raises(OAuthFailure, match="refresh_recovery_required"):
        read_current_device(token_store=store, environ=env(), http_request=request, now=NOW)
    assert calls == [("POST", "/v2/user/refresh")]
    assert store.records == []
    assert "rotated-access" not in repr(store.pending)
    assert "rotated-refresh" not in repr(store.pending)


def test_registered_fertilizer_device_uses_anchor_token_for_zero_command_read():
    fertilizer_params = {
        "fwVersion": "3.8.2",
        "switches": [{"outlet": i, "switch": "off"} for i in range(4)],
        "pulses": [
            {"outlet": 0, "pulse": "on", "width": 120000},
            {"outlet": 1, "pulse": "off", "width": 1000},
            {"outlet": 2, "pulse": "off", "width": 1000},
            {"outlet": 3, "pulse": "off", "width": 1000},
        ],
        "configure": [{"outlet": i, "startup": "off"} for i in range(4)],
        "timers": [],
    }
    things = {"thingList": [
        {"itemType": 1, "itemData": {"deviceid": "100204e9bc",
            "apikey": "account", "online": True, "params": {}}},
        {"itemType": 1, "itemData": {"deviceid": "100204d497",
            "apikey": "account", "online": True,
            "updatedAt": NOW.isoformat(), "params": fertilizer_params}},
    ]}
    request, calls = provider({"/v2/device/thing": things})
    result = read_registered_device("100204d497", token_store=Store(),
        environ=env(), http_request=request, now=NOW)
    assert result["device_id"] == "100204d497"
    assert result["channels"][0]["native_auto_off_seconds"] == 120
    assert result["channels"][1]["native_auto_off_enabled"] is False
    assert result["registered_discovery_only"] is False
    assert result["provider_control_calls"] == 0
    assert calls == [("GET", "/v2/family"), ("GET", "/v2/device/thing"),
                     ("GET", "/v2/device/thing/status")]


def test_unregistered_device_is_rejected_before_provider_or_token_access():
    class NoAccess:
        def latest(self):
            raise AssertionError("token must not be read")
    with pytest.raises(OAuthFailure, match="registered_device_rejected"):
        read_registered_device("unregistered", token_store=NoAccess(), environ=env(), now=NOW)
