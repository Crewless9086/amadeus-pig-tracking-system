"""Least-privilege, zero-command eWeLink device readback."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import urllib.parse

from modules.telemetry.rootline_ewelink_oauth import (
    ADAPTER_VERSION, REGION_HOSTS, OAuthFailure, _bind_account_device,
    _digest, _provider_request, decrypt_access_token, normalize_device_readback,
)


def read_current_device(*, token_store, environ=None, http_request=None, now=None):
    source = environ if environ is not None else os.environ
    if str(source.get("EWELINK_READBACK_ENABLED") or "").lower() != "true":
        raise OAuthFailure("ewelink_readback_disabled")
    now = now or datetime.now(timezone.utc)
    record = token_store.latest()
    expected = str(source.get("EWELINK_EXPECTED_DEVICE_ID") or "")
    if (not record or record.get("device_id") != expected
            or record.get("adapter_version") != ADAPTER_VERSION
            or record.get("region") not in REGION_HOSTS
            or record.get("access_expires_at") <= now):
        raise OAuthFailure("ewelink_readback_token_unavailable")
    access = decrypt_access_token(record, source)
    request = http_request or _provider_request
    host = REGION_HOSTS[record["region"]]
    family = request("GET", host + "/v2/family", mode="bearer", token=access, environ=source)
    things = request("GET", host + "/v2/device/thing?num=0", mode="bearer", token=access, environ=source)
    account, device = _bind_account_device(family, things, expected, source)
    if not __import__("hmac").compare_digest(_digest(account), record["provider_account_digest"]):
        raise OAuthFailure("ewelink_account_binding_changed")
    status = request("GET", host + "/v2/device/thing/status?" +
        urllib.parse.urlencode({"type": 1, "id": expected}),
        mode="bearer", token=access, environ=source)
    result = normalize_device_readback(device=device, status=status, retrieved_at=now)
    if result["device_id"] != expected:
        raise OAuthFailure("ewelink_readback_device_mismatch")
    safe_material = {key: value for key, value in result.items() if key != "response_digest"}
    result["response_digest"] = sha256(json.dumps(safe_material, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest()
    result["provider_calls"] = 3
    result["provider_control_calls"] = 0
    result["autonomous_control_enabled"] = False
    return result
