"""Fail-closed eWeLink OAuth onboarding and read-only account/device binding.

This module intentionally implements no provider control method.  OAuth state
and encrypted token generations are durable; raw credentials are never returned
from public functions or stored in database JSON.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import string
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


AUTHORIZE_URL = "https://c2ccdn.coolkit.cc/oauth/index.html"
REGION_HOSTS = {
    "as": "https://as-apia.coolkit.cc",
    "eu": "https://eu-apia.coolkit.cc",
    "us": "https://us-apia.coolkit.cc",
    "cn": "https://cn-apia.coolkit.cn",
}
CALLBACK_PATH = "/api/rootline/provider/ewelink/oauth/callback"
STATE_TTL_SECONDS = 600
CODE_MAX_AGE_SECONDS = 30
MIN_SECRET_CHARS = 32
ADAPTER_VERSION = "rootline_ewelink_oauth_v1"
REQUIRED_ENV = (
    "EWELINK_CLIENT_ID", "EWELINK_CLIENT_SECRET",
    "EWELINK_EXPECTED_DEVICE_ID", "EWELINK_OAUTH_REDIRECT_URI",
    "EWELINK_OAUTH_STATE_SECRET",
)


class OAuthFailure(RuntimeError):
    """Sanitized failure whose message is safe for an HTTP response."""


def oauth_readiness(environ=None):
    source = environ if environ is not None else os.environ
    missing = [name for name in REQUIRED_ENV if not str(source.get(name) or "").strip()]
    redirect = str(source.get("EWELINK_OAUTH_REDIRECT_URI") or "").strip()
    expected_redirect = "https://amadeus-pig-tracking-system.onrender.com" + CALLBACK_PATH
    # Reauthorization may recover an already reviewed read-only deployment.
    # It must never bootstrap or retain any actuation authority.
    readback_enabled = str(source.get("EWELINK_READBACK_ENABLED") or "").strip().lower() == "true"
    flags_safe = all(_false(source.get(name)) for name in (
        "ROOTLINE_AUTONOMOUS_BC_ENABLED",
        "ROOTLINE_FERTILIZER_MIXING_ENABLED",
        "ROOTLINE_FERTILIZER_INJECTION_ENABLED",
    ))
    strong_secrets = all(
        len(str(source.get(name) or "")) >= MIN_SECRET_CHARS
        for name in ("EWELINK_CLIENT_SECRET", "EWELINK_OAUTH_STATE_SECRET")
    )
    return {
        "status": "ready" if not missing and redirect == expected_redirect and flags_safe and strong_secrets else "not_ready",
        "configured": not missing,
        "missing_secret_names": missing,
        "redirect_uri_matches": bool(redirect and redirect == expected_redirect),
        "activation_flags_false": flags_safe,
        "secret_strength_valid": strong_secrets,
        "readback_enabled": readback_enabled,
        "autonomous_control_enabled": False,
        "provider_control_implemented": False,
        "adapter_version": ADAPTER_VERSION,
        "secrets_exposed": False,
    }


def create_authorization_request(*, principal, state_store, environ=None, now=None):
    source = environ if environ is not None else os.environ
    ready = oauth_readiness(source)
    if ready["status"] != "ready" or not str(principal or "").strip():
        raise OAuthFailure("oauth_onboarding_not_ready")
    now = _aware(now or datetime.now(timezone.utc))
    expires = now + timedelta(seconds=STATE_TTL_SECONDS)
    # CoolKit's authorization page requires exactly eight alphanumeric
    # characters.  URL-safe tokens may contain '-' or '_' and cause the
    # hosted page to remain on its loading screen instead of rejecting the
    # request visibly.
    nonce = _coolkit_nonce()
    jti = secrets.token_urlsafe(24)
    payload = {
        "v": 1, "jti": jti, "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "principal": _digest(str(principal)),
        "nonce": _digest(nonce),
        "redirect": _digest(str(source["EWELINK_OAUTH_REDIRECT_URI"])),
    }
    encoded = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    signature = _b64(hmac.new(str(source["EWELINK_OAUTH_STATE_SECRET"]).encode(),
                               encoded.encode(), hashlib.sha256).digest())
    state = encoded + "." + signature
    state_store.create({
        "state_digest": _digest(state), "principal_digest": payload["principal"],
        "nonce_digest": _digest(nonce), "redirect_uri_digest": payload["redirect"],
        "expires_at": expires,
    })
    seq = str(int(now.timestamp() * 1000))
    client_id = str(source["EWELINK_CLIENT_ID"])
    authorization = base64.b64encode(hmac.new(
        str(source["EWELINK_CLIENT_SECRET"]).encode(),
        f"{client_id}_{seq}".encode(), hashlib.sha256).digest()).decode()
    query = urllib.parse.urlencode({
        "state": state, "clientId": client_id, "authorization": authorization,
        "seq": seq, "redirectUrl": str(source["EWELINK_OAUTH_REDIRECT_URI"]),
        "nonce": nonce, "grantType": "authorization_code", "showQRCode": "true",
    })
    return {"status": "authorization_ready", "authorization_url": AUTHORIZE_URL + "?" + query,
            "expires_at": expires.isoformat(), "readback_enabled": ready["readback_enabled"],
            "autonomous_control_enabled": False, "secrets_exposed": False}


def complete_authorization(*, query, state_store, token_store, environ=None,
                           http_request=None, now=None):
    source = environ if environ is not None else os.environ
    if oauth_readiness(source)["status"] != "ready":
        raise OAuthFailure("oauth_onboarding_not_ready")
    now = _aware(now or datetime.now(timezone.utc))
    code = str(query.get("code") or "").strip()
    region = str(query.get("region") or query.get("regin") or "").strip().lower()
    state = str(query.get("state") or "").strip()
    if not code or len(code) > 256 or region not in REGION_HOSTS or not state:
        raise OAuthFailure("oauth_callback_malformed")
    payload = _verify_state(state, source, now)
    consumed = state_store.consume(_digest(state), now)
    if not consumed or consumed.get("principal_digest") != payload["principal"]:
        raise OAuthFailure("oauth_state_replayed_or_expired")
    if consumed.get("nonce_digest") != payload["nonce"]:
        raise OAuthFailure("oauth_nonce_binding_mismatch")
    if consumed.get("redirect_uri_digest") != _digest(str(source["EWELINK_OAUTH_REDIRECT_URI"])):
        raise OAuthFailure("oauth_redirect_binding_mismatch")

    request = http_request or _provider_request
    token_body = {"code": code, "redirectUrl": str(source["EWELINK_OAUTH_REDIRECT_URI"]),
                  "grantType": "authorization_code"}
    token_data = request("POST", REGION_HOSTS[region] + "/v2/user/oauth/token",
                         body=token_body, mode="signed", environ=source)
    access = str(token_data.get("accessToken") or "")
    refresh = str(token_data.get("refreshToken") or "")
    if not access or not refresh:
        raise OAuthFailure("oauth_token_response_incomplete")

    family = request("GET", REGION_HOSTS[region] + "/v2/family",
                     mode="bearer", token=access, environ=source)
    things = request("GET", REGION_HOSTS[region] + "/v2/device/thing?num=0",
                     mode="bearer", token=access, environ=source)
    expected_device = str(source["EWELINK_EXPECTED_DEVICE_ID"])
    account_id, device = _bind_account_device(family, things, expected_device, source)
    status = request("GET", REGION_HOSTS[region] + "/v2/device/thing/status?" +
                     urllib.parse.urlencode({"type": 1, "id": expected_device}),
                     mode="bearer", token=access, environ=source)
    device_params = device.get("params") if isinstance(device.get("params"), dict) else {}
    status_params = status.get("params") if isinstance(status.get("params"), dict) else {}
    # CoolKit distributes one authenticated device snapshot across the thing
    # record and the status response.  Status may contain only fields changed
    # or selected for the device; validate the composed snapshot rather than
    # falsely requiring every configuration field in that one packet.
    params = {**device_params, **status_params}
    if not _current_output_status(params):
        raise OAuthFailure("ewelink_device_status_incomplete")
    safety_missing = _missing_safety_status(params)

    response_digest = _digest(json.dumps({"family": family, "device": device,
        "status": status, "composedParams": params}, sort_keys=True, default=str,
        separators=(",", ":")))
    aad = f"{region}|{_digest(account_id)}|{expected_device}|{ADAPTER_VERSION}".encode()
    key = _token_key(source)
    token_generation_digest = hmac.new(
        key, (access + "\0" + refresh).encode(), hashlib.sha256
    ).hexdigest()
    record = {
        "token_binding_id": "ROOTLINE-EWELINK-" + token_generation_digest[:24].upper(),
        "provider_account_digest": _digest(account_id), "device_id": expected_device,
        "region": region, "access_token_ciphertext": _encrypt(access, key, aad),
        "refresh_token_ciphertext": _encrypt(refresh, key, aad),
        "access_expires_at": _millis_time(token_data.get("atExpiredTime")),
        "refresh_expires_at": _millis_time(token_data.get("rtExpiredTime")),
        "response_digest": response_digest, "adapter_version": ADAPTER_VERSION,
        "status_field_names": sorted(str(key) for key in params),
        "created_at": now,
    }
    created = token_store.append(record)
    readback_enabled = oauth_readiness(source)["readback_enabled"]
    return {"status": ("authorization_stored_readback_enabled" if readback_enabled
                       else "authorization_stored_readback_disabled"),
            "binding_created": bool(created), "device_bound": True,
            "provider_account_bound": True, "region": region,
            "status_field_names": record["status_field_names"],
            "safety_readback_complete": not safety_missing,
            "safety_readback_missing": safety_missing,
            "readback_enabled": readback_enabled, "autonomous_control_enabled": False,
            "provider_control_implemented": False, "secrets_exposed": False}


def _verify_state(state, source, now):
    try:
        encoded, supplied = state.split(".", 1)
        expected = _b64(hmac.new(str(source["EWELINK_OAUTH_STATE_SECRET"]).encode(),
                                  encoded.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied, expected):
            raise ValueError
        payload = json.loads(_unb64(encoded))
    except Exception as exc:
        raise OAuthFailure("oauth_state_invalid") from None
    issued = int(payload.get("iat") or 0)
    expires = int(payload.get("exp") or 0)
    if (payload.get("v") != 1 or issued > int(now.timestamp()) or
            expires < int(now.timestamp()) or expires - issued != STATE_TTL_SECONDS):
        raise OAuthFailure("oauth_state_expired")
    if payload.get("redirect") != _digest(str(source["EWELINK_OAUTH_REDIRECT_URI"])):
        raise OAuthFailure("oauth_redirect_binding_mismatch")
    return payload


def _bind_account_device(family, things, expected_device, source):
    current = str(family.get("currentFamilyId") or "")
    families = family.get("familyList") if isinstance(family.get("familyList"), list) else []
    selected = next((item for item in families if str(item.get("id")) == current), None)
    account_id = str((selected or {}).get("apikey") or "")
    if not current or not account_id:
        raise OAuthFailure("ewelink_account_identity_incomplete")
    expected_account = str(source.get("EWELINK_EXPECTED_ACCOUNT_ID") or "").strip()
    if expected_account and not hmac.compare_digest(account_id, expected_account):
        raise OAuthFailure("ewelink_account_identity_mismatch")
    rows = things.get("thingList") if isinstance(things.get("thingList"), list) else []
    matches = [item for item in rows if item.get("itemType") == 1 and
               str((item.get("itemData") or {}).get("deviceid")) == expected_device]
    if len(matches) != 1:
        raise OAuthFailure("ewelink_expected_owned_device_not_found")
    device = matches[0]["itemData"]
    if str(device.get("apikey") or "") != account_id:
        raise OAuthFailure("ewelink_device_account_mismatch")
    return account_id, device


def _current_output_status(params):
    if not isinstance(params, dict):
        return False
    switches = params.get("switches")
    if not isinstance(switches, list) or len(switches) != 4:
        return False
    if any(not isinstance(item, dict) or item.get("switch") not in {"on", "off"}
           or not isinstance(item.get("outlet"), int) for item in switches):
        return False
    outlets = {item["outlet"] for item in switches}
    return outlets == {0, 1, 2, 3}


def _missing_safety_status(params):
    pulses = _outlet_records(params.get("pulses"), "pulse", {"on", "off"})
    configured = _outlet_records(params.get("configure"), "startup", {"on", "off", "stay"})
    checks = {
        "native_auto_off_enabled": bool(pulses),
        "native_auto_off_duration": bool(pulses) and all(
            isinstance(item.get("width"), int) for item in pulses.values()),
        "power_restoration": bool(configured),
        "timers": isinstance(params.get("timers"), list),
    }
    missing = [name for name, present in checks.items() if not present]
    _, scenes_supported, _ = _scene_evidence(params)
    if (params.get("interlock") not in {0, 1, False, True}
            or not scenes_supported):
        missing.append("conflicting_control_paths")
    return sorted(missing)


def normalize_device_readback(*, device, status, retrieved_at, commissioned_baseline=None):
    """Return a secret-free, fail-closed projection of one authenticated GET snapshot."""
    device_params = device.get("params") if isinstance(device.get("params"), dict) else {}
    status_params = status.get("params") if isinstance(status.get("params"), dict) else {}
    params = {**device_params, **status_params}
    if not _current_output_status(params):
        raise OAuthFailure("ewelink_device_status_incomplete")
    outputs = _outlet_records(params["switches"], "switch", {"on", "off"})
    pulses = _outlet_records(params.get("pulses"), "pulse", {"on", "off"})
    configured = _outlet_records(params.get("configure"), "startup", {"on", "off", "stay"})
    retrieved_at = _aware(retrieved_at)
    provider_timestamp_supplied = False
    observed_at = None
    for packet, field in ((status, "updatedAt"), (status, "updateTime"),
                          (device, "updatedAt")):
        if field in packet:
            observed_at = packet[field]
            provider_timestamp_supplied = True
            break
    observed_time = _provider_timestamp(observed_at)
    timestamp_fresh = (observed_time is not None and
        timedelta(seconds=-30) <= retrieved_at - observed_time <= timedelta(minutes=5))
    # The official CoolKit UIID9 profile does not promise a provider timestamp
    # in either GET response.  A completed authenticated, non-redirected GET is
    # nevertheless a current observation receipt.  Keep that clock distinct
    # from a provider/device observation time instead of manufacturing one.
    freshness_clock_source = (
        "provider_observation_timestamp" if observed_time is not None
        else "invalid_provider_timestamp" if provider_timestamp_supplied
        else "trusted_authenticated_receipt"
    )
    observation_fresh = timestamp_fresh if provider_timestamp_supplied else True
    timers = params.get("timers") if isinstance(params.get("timers"), list) else None
    scenes, provider_scenes_supported, scene_evidence_conflict = _scene_evidence(params)
    interlock = params.get("interlock")
    missing = _missing_safety_status(params)
    if provider_timestamp_supplied and not timestamp_fresh:
        missing.append("provider_timestamp")
    # UIID9 documents switches, pulses, configure and timers.  It does not
    # expose scene membership or an interlock parameter, and the official
    # scene-list API is not open.  Absence therefore means unsupported, never
    # disabled.  Collapse both unobservable activation paths into one precise
    # external safety prerequisite.
    provider_interlock_supported = interlock in {0, 1, False, True}
    firmware = str(params.get("fwVersion") or "") or None
    baseline = None
    if commissioned_baseline is not None:
        from modules.telemetry.rootline_ewelink_commissioned_baseline import (
            validate_commissioned_baseline,
        )
        baseline = validate_commissioned_baseline(
            commissioned_baseline,
            device_id=str(device.get("deviceid") or ""),
            firmware=firmware,
            observed_at=retrieved_at,
        )
    baseline_control_paths = bool(
        baseline
        and not scene_evidence_conflict
        and baseline.get("interlock_enabled") is False
        and baseline.get("conflicting_scenes") == []
    )
    if provider_interlock_supported and baseline and bool(interlock) != baseline["interlock_enabled"]:
        baseline_control_paths = False
    if provider_scenes_supported and baseline and bool(scenes) != bool(baseline["conflicting_scenes"]):
        baseline_control_paths = False
    if ((not provider_interlock_supported or not provider_scenes_supported)
            and not baseline_control_paths):
        missing.append("conflicting_control_paths")
    elif baseline_control_paths:
        missing = [item for item in missing if item != "conflicting_control_paths"]
    missing = sorted(set(missing))
    channel_rows = [{
        "channel": outlet + 1,
        "output_state": outputs[outlet]["switch"].upper(),
        "native_auto_off_enabled": ((pulses.get(outlet) or {}).get("pulse") == "on")
            if outlet in pulses else None,
        "native_auto_off_seconds": ((pulses.get(outlet) or {}).get("width") // 1000)
            if isinstance((pulses.get(outlet) or {}).get("width"), int) else None,
        "power_restoration_state": (configured.get(outlet) or {}).get("startup", "").upper() or None,
    } for outlet in range(4)]
    safety_complete = not missing and device.get("online") is True
    configuration_safe = (safety_complete and all(
        row["output_state"] == "OFF"
        and row["native_auto_off_enabled"] is True
        and 0 < int(row["native_auto_off_seconds"] or 0) <= 3600
        and row["power_restoration_state"] == "OFF" for row in channel_rows)
        and not any(not _timer_disabled(item) for item in timers)
        and (scenes == [] if provider_scenes_supported else baseline_control_paths)
        and (interlock in {0, False} if provider_interlock_supported else baseline_control_paths))
    return {
        "authoritative": device.get("online") is True,
        "current_outputs_authoritative": device.get("online") is True,
        "actuation_safety_complete": safety_complete,
        "actuation_configuration_safe": configuration_safe,
        "actuation_eligible": False,
        "device_id": str(device.get("deviceid") or ""),
        "online": device.get("online") is True,
        "firmware": firmware,
        "channels": channel_rows,
        "timers_enabled": any(not _timer_disabled(item) for item in timers) if timers is not None else None,
        "scenes_enabled": (bool(scenes) if provider_scenes_supported
            else False if baseline_control_paths else None),
        "interlock_enabled": (bool(interlock) if provider_interlock_supported
            else False if baseline_control_paths else None),
        "interlock_evidence_source": ("provider_readback" if provider_interlock_supported
            else "commissioned_configuration_baseline" if baseline_control_paths else None),
        "scenes_evidence_source": ("provider_readback" if provider_scenes_supported
            else "commissioned_configuration_baseline" if baseline_control_paths else None),
        "control_path_evidence_source": ("provider_readback" if
            provider_interlock_supported and provider_scenes_supported else
            "mixed_provider_and_commissioned_baseline" if baseline_control_paths and
                (provider_interlock_supported or provider_scenes_supported) else
            "commissioned_configuration_baseline" if baseline_control_paths else None),
        "commissioned_baseline_id": baseline.get("baseline_id") if baseline else None,
        "commissioned_baseline_sha256": baseline.get("baseline_sha256") if baseline else None,
        "commissioned_supervised_channels": (
            list(baseline.get("supervised_commissioning_channels") or []) if baseline else []),
        "configuration_generation": baseline.get("configuration_generation") if baseline else None,
        "commissioned_baseline_valid_until": baseline.get("valid_until") if baseline else None,
        "commissioned_baseline_fresh": baseline.get("baseline_fresh") if baseline else False,
        "provider_observed_at": observed_time.isoformat() if observed_time else None,
        "provider_timestamp_fresh": timestamp_fresh if observed_time is not None else None,
        "trusted_receipt_at": retrieved_at.isoformat(),
        "freshness_clock_source": freshness_clock_source,
        "observation_fresh": observation_fresh,
        "provider_interlock_supported": provider_interlock_supported,
        "provider_scenes_supported": provider_scenes_supported,
        "scene_evidence_conflict": scene_evidence_conflict,
        "retrieved_at": retrieved_at.isoformat(),
        "safety_readback_missing": missing,
        "secrets_exposed": False,
    }


def _outlet_records(value, field, allowed):
    if not isinstance(value, list) or len(value) != 4:
        return {}
    result = {}
    for item in value:
        if (not isinstance(item, dict) or not isinstance(item.get("outlet"), int)
                or item.get("outlet") in result or item.get(field) not in allowed):
            return {}
        result[item["outlet"]] = item
    return result if set(result) == {0, 1, 2, 3} else {}


def _timer_disabled(value):
    return isinstance(value, dict) and value.get("enabled") in {0, False, "off"}


def _scene_evidence(params):
    primary_present = "scenes" in params
    alias_present = "scene" in params
    primary = params.get("scenes")
    alias = params.get("scene")
    conflict = primary_present and alias_present and primary != alias
    if conflict:
        return None, False, True
    selected = primary if primary_present else alias if alias_present else None
    return (selected, True, False) if isinstance(selected, list) else (None, False, False)


def _provider_timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return _aware(parsed)
    except (TypeError, ValueError):
        return None


def _provider_request(method, url, *, body=None, mode, token=None, environ):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in {
        urllib.parse.urlparse(value).netloc for value in REGION_HOSTS.values()}:
        raise OAuthFailure("ewelink_provider_host_rejected")
    _enforce_provider_operation(method, parsed, body, mode, environ)
    headers = {"Accept": "application/json", "X-CK-Appid": str(environ["EWELINK_CLIENT_ID"])}
    data = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    if mode == "signed":
        signature = base64.b64encode(hmac.new(str(environ["EWELINK_CLIENT_SECRET"]).encode(),
                                               data or b"", hashlib.sha256).digest()).decode()
        headers["Authorization"] = "Sign " + signature
        headers["X-CK-Nonce"] = _coolkit_nonce()
    elif mode == "bearer" and token:
        headers["Authorization"] = "Bearer " + token
    else:
        raise OAuthFailure("ewelink_provider_auth_mode_rejected")
    try:
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        opener = urllib.request.build_opener(_RejectRedirects())
        with opener.open(request, timeout=min(15, CODE_MAX_AGE_SECONDS)) as response:
            if response.geturl() != url:
                raise OAuthFailure("ewelink_provider_redirect_rejected")
            packet = json.loads(response.read().decode("utf-8"))
    except OAuthFailure:
        raise
    except Exception:
        raise OAuthFailure("ewelink_provider_request_failed") from None
    if not isinstance(packet, dict) or packet.get("error") != 0 or not isinstance(packet.get("data"), dict):
        raise OAuthFailure("ewelink_provider_response_rejected")
    return packet["data"]


def _enforce_provider_operation(method, parsed, body, mode, environ):
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    expected_device = str(environ["EWELINK_EXPECTED_DEVICE_ID"])
    allowed = (
        method == "POST" and mode == "signed" and parsed.path == "/v2/user/oauth/token"
        and not query and isinstance(body, dict)
        and set(body) == {"code", "redirectUrl", "grantType"}
        and body.get("grantType") == "authorization_code"
        and body.get("redirectUrl") == environ["EWELINK_OAUTH_REDIRECT_URI"]
    ) or (
        method == "POST" and mode == "signed" and parsed.path == "/v2/user/refresh"
        and not query and isinstance(body, dict) and set(body) == {"rt"}
        and bool(str(body.get("rt") or ""))
    ) or (
        method == "GET" and mode == "bearer" and body is None
        and parsed.path == "/v2/family" and not query
    ) or (
        method == "GET" and mode == "bearer" and body is None
        and parsed.path == "/v2/device/thing" and query == {"num": ["0"]}
    ) or (
        method == "GET" and mode == "bearer" and body is None
        and parsed.path == "/v2/device/thing/status"
        and query == {"type": ["1"], "id": [expected_device]}
    )
    if not allowed:
        raise OAuthFailure("ewelink_provider_operation_rejected")


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise OAuthFailure("ewelink_provider_redirect_rejected")


def _token_key(source):
    return hmac.new(str(source["EWELINK_OAUTH_STATE_SECRET"]).encode(),
                    ("token-encryption-v1\0" + str(source["EWELINK_CLIENT_SECRET"])).encode(),
                    hashlib.sha256).digest()


def _encrypt(value, key, aad):
    nonce = secrets.token_bytes(12)
    return base64.b64encode(nonce + AESGCM(key).encrypt(nonce, value.encode(), aad)).decode()


def decrypt_access_token(record, environ=None):
    return _decrypt_token(record, "access_token_ciphertext", environ)


def decrypt_refresh_token(record, environ=None):
    return _decrypt_token(record, "refresh_token_ciphertext", environ)


def _decrypt_token(record, field, environ=None):
    source = environ if environ is not None else os.environ
    aad = (f"{record['region']}|{record['provider_account_digest']}|"
           f"{record['device_id']}|{record['adapter_version']}").encode()
    try:
        packet = base64.b64decode(record[field], validate=True)
    except Exception:
        raise OAuthFailure("ewelink_token_ciphertext_invalid") from None
    if len(packet) < 29:
        raise OAuthFailure("ewelink_token_ciphertext_invalid")
    try:
        return AESGCM(_token_key(source)).decrypt(packet[:12], packet[12:], aad).decode()
    except Exception:
        raise OAuthFailure("ewelink_token_decryption_failed") from None


def _millis_time(value):
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        raise OAuthFailure("oauth_token_expiry_incomplete") from None


def _false(value):
    return str(value or "").strip().lower() in {"", "0", "false", "off", "no"}


def _coolkit_nonce():
    """Return the exact eight-character nonce required by CoolKit APIs."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def _b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
