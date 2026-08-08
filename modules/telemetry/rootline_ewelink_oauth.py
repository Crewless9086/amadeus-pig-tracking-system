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
    flags_safe = (
        _false(source.get("EWELINK_READBACK_ENABLED"))
        and _false(source.get("ROOTLINE_AUTONOMOUS_BC_ENABLED"))
    )
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
        "readback_enabled": False,
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
            "expires_at": expires.isoformat(), "readback_enabled": False,
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
    if not _complete_device_status(params):
        raise OAuthFailure("ewelink_device_status_incomplete")

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
    return {"status": "authorization_stored_readback_disabled",
            "binding_created": bool(created), "device_bound": True,
            "provider_account_bound": True, "region": region,
            "status_field_names": record["status_field_names"],
            "readback_enabled": False, "autonomous_control_enabled": False,
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


def _complete_device_status(params):
    if not isinstance(params, dict):
        return False
    switches = params.get("switches")
    if not isinstance(switches, list) or len(switches) < 2:
        return False
    if any(not isinstance(item, dict) or "switch" not in item or "outlet" not in item
           for item in switches):
        return False
    return (("pulse" in params or "pulses" in params)
            and ("pulseWidth" in params or "pulseWidths" in params)
            and "startup" in params and "timers" in params and "interlock" in params)


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
