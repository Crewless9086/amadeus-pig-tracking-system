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
            "apikey": "account", "extra": {"uiid": 4}, "online": True, "updatedAt": NOW.isoformat(), "params": params}}]},
        "/v2/device/thing/status": {"params": {}}}
    data.update(overrides or {}); calls=[]
    def request(method, url, **kwargs):
        calls.append((method, urllib.parse.urlparse(url).path))
        value = data[calls[-1][1]]
        if method == "POST" and calls[-1][1] == "/v2/device/thing":
            requested = kwargs["body"]["thingList"][0]["id"]
            return {"thingList": [row for row in value["thingList"] if row["itemData"]["deviceid"] == requested]}
        return value
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
    assert first["provider_calls"] == 1 and first["token_refreshed"] is False
    assert first["freshness_clock_source"] == "provider_observation_timestamp"
    assert first["observation_fresh"] is True
    assert calls == [("POST", "/v2/device/thing")]*2


def test_disabled_stale_offline_and_missing_interlock_fail_closed():
    with pytest.raises(OAuthFailure, match="disabled"):
        read_current_device(token_store=Store(), environ=env(EWELINK_READBACK_ENABLED="false"), now=NOW)
    stale=Store(); stale.record["access_expires_at"] = NOW
    stale.record["refresh_expires_at"] = NOW
    with pytest.raises(OAuthFailure, match="refresh_token_unavailable"):
        read_current_device(token_store=stale, environ=env(), now=NOW)
    offline = {"thingList": [{"itemType": 1, "itemData": {
        "deviceid": "100204e9bc", "apikey": "account", "extra": {"uiid": 4}, "online": False,
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
    assert result["provider_calls"] == 2 and result["token_refreshed"] is True
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
    assert restart_calls == [("POST", "/v2/device/thing")]


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
            "apikey": "account", "extra": {"uiid": 4}, "online": True, "params": {}}},
        {"itemType": 1, "itemData": {"deviceid": "100204d497",
            "apikey": "account", "extra": {"uiid": 4}, "online": True,
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
    assert calls == [("POST", "/v2/device/thing")]


def test_unregistered_device_is_rejected_before_provider_or_token_access():
    class NoAccess:
        def latest(self):
            raise AssertionError("token must not be read")
    with pytest.raises(OAuthFailure, match="registered_device_rejected"):
        read_registered_device("unregistered", token_store=NoAccess(), environ=env(), now=NOW)


@pytest.mark.parametrize("fault", ["shared", "group", "bool_type", "empty", "extra", "wrong_id", "missing_params", "missing_outlet", "duplicate_outlet", "bool_outlet", "bad_uiid"])
def test_complete_snapshot_rejects_ambiguous_identity_or_incomplete_outputs(fault):
    from copy import deepcopy
    raw, calls = provider()
    def request(method, url, **kwargs):
        packet = deepcopy(raw(method, url, **kwargs)); rows = packet["thingList"]; device = rows[0]["itemData"]
        if fault == "shared": rows[0]["itemType"] = 2
        if fault == "group": rows[0]["itemType"] = 3
        if fault == "bool_type": rows[0]["itemType"] = True
        if fault == "empty": rows.clear()
        if fault == "extra": rows.append(deepcopy(rows[0]))
        if fault == "wrong_id": device["deviceid"] = "100204d497"
        if fault == "missing_params": device.pop("params")
        if fault == "missing_outlet": device["params"]["switches"].pop()
        if fault == "duplicate_outlet": device["params"]["switches"][1]["outlet"] = 0
        if fault == "bool_outlet": device["params"]["switches"][0]["outlet"] = False
        if fault == "bad_uiid": device["extra"]["uiid"] = True
        return packet
    with pytest.raises(OAuthFailure):
        read_current_device(token_store=Store(), environ=env(), http_request=request, now=NOW)
    assert calls == [("POST", "/v2/device/thing")]


@pytest.mark.parametrize("timestamp", ["malformed", "", None, (NOW-timedelta(minutes=6)).isoformat(), (NOW+timedelta(minutes=1)).isoformat()])
def test_complete_snapshot_supplied_invalid_timestamp_never_becomes_safe(timestamp):
    from copy import deepcopy
    raw, calls = provider()
    def request(method, url, **kwargs):
        packet = deepcopy(raw(method, url, **kwargs)); packet["thingList"][0]["itemData"]["updatedAt"] = timestamp
        return packet
    result = read_current_device(token_store=Store(), environ=env(), http_request=request, now=NOW)
    assert result["observation_fresh"] is False
    assert result["actuation_safety_complete"] is False
    assert "provider_timestamp" in result["safety_readback_missing"]
    assert calls == [("POST", "/v2/device/thing")]


@pytest.mark.parametrize("fault", ["extra_key", "two_devices", "bool_type", "shared", "unknown", "other_device", "query", "fragment", "status_path", "signed"])
def test_single_snapshot_post_allowlist_rejects_every_control_or_expansion(fault):
    from modules.telemetry.rootline_ewelink_oauth import _enforce_provider_operation
    body = {"thingList": [{"itemType": 1, "id": "100204e9bc"}]}
    path = "https://eu-apia.coolkit.cc/v2/device/thing"; mode = "bearer"
    if fault == "extra_key": body["params"] = {"switch": "on"}
    if fault == "two_devices": body["thingList"].append({"itemType": 1, "id": "100204d497"})
    if fault == "bool_type": body["thingList"][0]["itemType"] = True
    if fault == "shared": body["thingList"][0]["itemType"] = 2
    if fault == "unknown": body["thingList"][0]["id"] = "unknown"
    if fault == "other_device": body["thingList"][0]["id"] = "100204d497"
    if fault == "query": path += "?num=0"
    if fault == "fragment": path += "#other"
    if fault == "status_path": path += "/status"
    if fault == "signed": mode = "signed"
    with pytest.raises(OAuthFailure, match="operation_rejected"):
        _enforce_provider_operation("POST", urllib.parse.urlparse(path), body, mode, env())


def test_single_snapshot_post_allowlist_accepts_only_exact_registered_request():
    from modules.telemetry.rootline_ewelink_oauth import _enforce_provider_operation
    for device in ("100204e9bc", "100204d497", "1002851416"):
        _enforce_provider_operation("POST", urllib.parse.urlparse("https://eu-apia.coolkit.cc/v2/device/thing"),
            {"thingList": [{"itemType": 1, "id": device}]}, "bearer", env(EWELINK_EXPECTED_DEVICE_ID=device))


@pytest.mark.parametrize("provider_error", [0, 412])
def test_single_snapshot_actual_http_boundary_and_budget_charge(monkeypatch, provider_error):
    import json
    from copy import deepcopy
    from modules.telemetry import rootline_ewelink_oauth as oauth
    from modules.telemetry import rootline_ewelink_readback as readback
    from modules.telemetry import rootline_ewelink_request_budget as budget
    from tests.test_rootline_ewelink_request_budget import MemoryBudget
    source=env(); client=MemoryBudget(environ=source); client.backend.now=NOW
    monkeypatch.setattr(budget,"RequestBudget",lambda *_a,**_k:client)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return client.backend.now
    monkeypatch.setattr(readback,"datetime",Clock)
    raw,_=provider(); captured=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def geturl(self):return "https://eu-apia.coolkit.cc/v2/device/thing"
        def read(self,_):
            body=deepcopy(raw("POST",self.geturl(),body={"thingList":[{"itemType":1,"id":"100204e9bc"}]}))
            body["thingList"][0]["itemData"].pop("updatedAt")
            client.backend.advance(4)
            return json.dumps({"error":provider_error,"data":body}).encode()
    class Opener:
        def open(self,request,timeout):
            captured.append((request.method,request.full_url,json.loads(request.data)))
            return Response()
    monkeypatch.setattr(oauth.urllib.request,"build_opener",lambda *_:Opener())
    if provider_error:
        with pytest.raises(OAuthFailure):readback.read_current_device(token_store=Store(),environ=source,now=NOW)
    else:
        result=readback.read_current_device(token_store=Store(),environ=source,now=NOW)
        assert result["provider_calls"]==1 and result["snapshot_source"]=="complete_owned_device"
        assert result["trusted_receipt_at"]==(NOW+timedelta(seconds=4)).isoformat()
        assert result["freshness_clock_source"]=="trusted_authenticated_receipt"
        assert result["actuation_safety_complete"] is True
    assert captured==[("POST","https://eu-apia.coolkit.cc/v2/device/thing",{"thingList":[{"itemType":1,"id":"100204e9bc"}]})]
    assert sum(row['units'] for row in client.backend.events)==1


@pytest.mark.parametrize("alias", ["malformed", (NOW-timedelta(minutes=6)).isoformat(), (NOW+timedelta(minutes=1)).isoformat()])
def test_complete_snapshot_does_not_hide_bad_second_timestamp(alias):
    from copy import deepcopy
    raw,_=provider()
    def request(method,url,**kwargs):
        packet=deepcopy(raw(method,url,**kwargs))
        packet["thingList"][0]["itemData"]["updateTime"]=alias
        return packet
    result=read_current_device(token_store=Store(),environ=env(),http_request=request,now=NOW)
    assert not result["observation_fresh"] and not result["actuation_safety_complete"]
