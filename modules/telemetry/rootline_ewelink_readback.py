"""Least-privilege, zero-command eWeLink device readback."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
import urllib.parse

from modules.telemetry.rootline_ewelink_oauth import (
    ADAPTER_VERSION, REGION_HOSTS, OAuthFailure, _bind_account_device,
    _digest, _encrypt, _provider_request, _token_key, decrypt_access_token,
    decrypt_refresh_token, normalize_device_readback,
)
from modules.telemetry.rootline_ewelink_commissioned_baseline import (
    commissioned_controller_baseline, commissioned_registered_device_baseline,
)
from modules.telemetry.rootline_device_registry import rootline_device_registry


def read_current_device(*, token_store, environ=None, http_request=None, now=None):
    source = environ if environ is not None else os.environ
    return _read_bound_device(
        expected=str(source.get("EWELINK_EXPECTED_DEVICE_ID") or ""),
        token_store=token_store,
        source=source,
        http_request=http_request,
        now=now,
        commissioned_baseline=commissioned_controller_baseline(),
        registered_discovery_only=False,
    )


def read_registered_device(device_id, *, token_store, environ=None,
                           http_request=None, now=None):
    """Read an exact registry-bound device without expanding command authority."""
    source = environ if environ is not None else os.environ
    requested = str(device_id or "").strip()
    contracts = [row for row in rootline_device_registry().values()
                 if row.get("device_id") == requested]
    if (not requested or not contracts
            or any(row.get("provider_account_binding") != "ewelink_owner_account"
                   for row in contracts)):
        raise OAuthFailure("ewelink_registered_device_rejected")
    return _read_bound_device(
        expected=requested,
        token_store=token_store,
        source=source,
        http_request=http_request,
        now=now,
        commissioned_baseline=commissioned_registered_device_baseline(requested),
        registered_discovery_only=False,
    )


def _read_bound_device(*, expected, token_store, source, http_request, now,
                       commissioned_baseline, registered_discovery_only):
    if str(source.get("EWELINK_READBACK_ENABLED") or "").lower() != "true":
        raise OAuthFailure("ewelink_readback_disabled")
    now = now or datetime.now(timezone.utc)
    record = token_store.latest()
    anchor = str(source.get("EWELINK_EXPECTED_DEVICE_ID") or "")
    if (not record or record.get("device_id") != anchor
            or record.get("adapter_version") != ADAPTER_VERSION
            or record.get("region") not in REGION_HOSTS):
        raise OAuthFailure("ewelink_readback_token_unavailable")
    request = http_request or _provider_request
    token_refreshed = False
    if record.get("access_expires_at") <= now:
        record = _refresh_token_generation(record, token_store=token_store,
            source=source, request=request, now=now)
        token_refreshed = True
    access = decrypt_access_token(record, source)
    host = REGION_HOSTS[record["region"]]
    family = request("GET", host + "/v2/family", mode="bearer", token=access, environ=source)
    things = request("GET", host + "/v2/device/thing?num=0", mode="bearer", token=access, environ=source)
    account, device = _bind_account_device(family, things, expected, source)
    if not __import__("hmac").compare_digest(_digest(account), record["provider_account_digest"]):
        raise OAuthFailure("ewelink_account_binding_changed")
    request_source = dict(source)
    request_source["EWELINK_EXPECTED_DEVICE_ID"] = expected
    status = request("GET", host + "/v2/device/thing/status?" +
        urllib.parse.urlencode({"type": 1, "id": expected}),
        mode="bearer", token=access, environ=request_source)
    result = normalize_device_readback(device=device, status=status, retrieved_at=now,
        commissioned_baseline=commissioned_baseline)
    if result["device_id"] != expected:
        raise OAuthFailure("ewelink_readback_device_mismatch")
    safe_material = {key: value for key, value in result.items() if key != "response_digest"}
    result["response_digest"] = sha256(json.dumps(safe_material, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest()
    result["provider_calls"] = 4 if token_refreshed else 3
    result["provider_control_calls"] = 0
    result["token_refreshed"] = token_refreshed
    result["autonomous_control_enabled"] = False
    result["registered_discovery_only"] = registered_discovery_only
    return result


def _refresh_token_generation(record, *, token_store, source, request, now):
    """Rotate an expired access token into one append-only encrypted generation."""
    if not record.get("refresh_expires_at") or record["refresh_expires_at"] <= now:
        raise OAuthFailure("ewelink_refresh_token_unavailable")
    refresh = decrypt_refresh_token(record, source)
    data = request("POST", REGION_HOSTS[record["region"]] + "/v2/user/refresh",
        body={"rt": refresh}, mode="signed", environ=source)
    access = str(data.get("at") or "")
    rotated_refresh = str(data.get("rt") or "")
    if not access or not rotated_refresh:
        raise OAuthFailure("ewelink_refresh_response_incomplete")
    key = _token_key(source)
    generation_digest = __import__("hmac").new(
        key, (access + "\0" + rotated_refresh).encode(), __import__("hashlib").sha256
    ).hexdigest()
    aad = (f"{record['region']}|{record['provider_account_digest']}|"
           f"{record['device_id']}|{record['adapter_version']}").encode()
    refreshed = {
        **record,
        "token_binding_id": "ROOTLINE-EWELINK-" + generation_digest[:24].upper(),
        "access_token_ciphertext": _encrypt(access, key, aad),
        "refresh_token_ciphertext": _encrypt(rotated_refresh, key, aad),
        "access_expires_at": now + timedelta(days=30),
        "refresh_expires_at": now + timedelta(days=60),
        "response_digest": _digest(json.dumps({
            "previous_generation": record["token_binding_id"],
            "access_expires_at": (now + timedelta(days=30)).isoformat(),
            "refresh_expires_at": (now + timedelta(days=60)).isoformat(),
        }, sort_keys=True, separators=(",", ":"))),
        "status_field_names": [],
        "created_at": now,
    }
    if token_store.append(refreshed) is not True:
        latest = token_store.latest()
        if not latest or latest.get("token_binding_id") != refreshed["token_binding_id"]:
            raise OAuthFailure("ewelink_refresh_persistence_failed")
        refreshed = latest
    return refreshed
