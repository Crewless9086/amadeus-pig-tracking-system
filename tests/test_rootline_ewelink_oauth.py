import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

from modules.telemetry.rootline_ewelink_oauth import (
    OAuthFailure, complete_authorization, create_authorization_request, oauth_readiness,
)

NOW = datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc)
REDIRECT = "https://amadeus-pig-tracking-system.onrender.com/api/rootline/provider/ewelink/oauth/callback"


def env(**changes):
    result = {"EWELINK_CLIENT_ID": "client-id", "EWELINK_CLIENT_SECRET": "client-secret",
              "EWELINK_EXPECTED_DEVICE_ID": "100204e9bc",
              "EWELINK_OAUTH_REDIRECT_URI": REDIRECT,
              "EWELINK_OAUTH_STATE_SECRET": "state-secret",
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
            "switches": [{"outlet": 0, "switch": "off"}, {"outlet": 1, "switch": "off"}],
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
    assert "client-secret" not in repr(states.item) and "state-secret" not in repr(states.item)
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


def test_incomplete_status_and_wrong_region_rejected():
    with pytest.raises(OAuthFailure, match="status_incomplete"):
        authorize(overrides={"/v2/device/thing/status": {"params": {"switches": []}}})
    states, _, query = start(); request, calls = fake_provider()
    with pytest.raises(OAuthFailure, match="malformed"):
        complete_authorization(query={"code": "code", "region": "evil", "state": query["state"][0]},
            state_store=states, token_store=Tokens(), environ=env(), http_request=request, now=NOW)
    assert calls == [] and states.used is False


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
