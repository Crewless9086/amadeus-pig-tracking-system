"""Cursor managed-VM OIDC verification for bounded CHARLIE hook requests."""

from __future__ import annotations

import base64
import json
import time
import urllib.request

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding


CURSOR_OIDC_ISSUER = "https://api.cursor.com"
CURSOR_OIDC_AUDIENCE = "urn:amadeus:charlie:cursor-hook:v1"
CURSOR_JWKS_URL = "https://api.cursor.com/keys"
APPROVED_REPOSITORY = "github.com/Crewless9086/amadeus-pig-tracking-system"
_JWKS_CACHE = {"expires_at": 0.0, "keys": {}}


class CursorIdentityError(ValueError):
    """A stable, non-secret identity rejection."""


def _b64url(value):
    try:
        return base64.urlsafe_b64decode(str(value) + "=" * (-len(str(value)) % 4))
    except Exception as exc:
        raise CursorIdentityError("cursor_oidc_malformed") from exc


def _load_jwks(*, opener=urllib.request.urlopen, now=None, force=False):
    observed = float(time.time() if now is None else now)
    if not force and _JWKS_CACHE["keys"] and observed < _JWKS_CACHE["expires_at"]:
        return dict(_JWKS_CACHE["keys"])
    try:
        request = urllib.request.Request(CURSOR_JWKS_URL, headers={"Accept": "application/json"})
        with opener(request, timeout=5) as response:
            packet = json.loads(response.read(262144).decode("utf-8"))
    except Exception as exc:
        raise CursorIdentityError("cursor_jwks_unavailable") from exc
    keys = {str(row.get("kid") or ""): row for row in packet.get("keys") or []
            if row.get("kty") == "RSA" and row.get("alg") in {None, "RS256"} and row.get("kid")}
    if not keys:
        raise CursorIdentityError("cursor_jwks_invalid")
    _JWKS_CACHE.update({"keys": keys, "expires_at": observed + 300})
    return dict(keys)


def verify_cursor_oidc_token(token, *, opener=urllib.request.urlopen, now=None, skew=30):
    """Verify Cursor's RS256 token and return only validated claims."""
    parts = str(token or "").split(".")
    if len(parts) != 3:
        raise CursorIdentityError("cursor_oidc_malformed")
    try:
        header = json.loads(_b64url(parts[0]))
        claims = json.loads(_b64url(parts[1]))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise CursorIdentityError("cursor_oidc_malformed") from exc
    if header.get("alg") != "RS256" or not str(header.get("kid") or ""):
        raise CursorIdentityError("cursor_oidc_algorithm_invalid")
    keys = _load_jwks(opener=opener, now=now)
    jwk = keys.get(header["kid"])
    if not jwk:
        jwk = _load_jwks(opener=opener, now=now, force=True).get(header["kid"])
    if not jwk:
        raise CursorIdentityError("cursor_oidc_unknown_kid")
    try:
        public_key = RSAPublicNumbers(
            int.from_bytes(_b64url(jwk["e"]), "big"), int.from_bytes(_b64url(jwk["n"]), "big")
        ).public_key()
        public_key.verify(_b64url(parts[2]), f"{parts[0]}.{parts[1]}".encode(), padding.PKCS1v15(), hashes.SHA256())
    except (KeyError, ValueError, InvalidSignature) as exc:
        raise CursorIdentityError("cursor_oidc_signature_invalid") from exc
    observed = int(time.time() if now is None else now)
    if claims.get("iss") != CURSOR_OIDC_ISSUER:
        raise CursorIdentityError("cursor_oidc_issuer_invalid")
    audience = claims.get("aud")
    if audience != CURSOR_OIDC_AUDIENCE and audience != [CURSOR_OIDC_AUDIENCE]:
        raise CursorIdentityError("cursor_oidc_audience_invalid")
    try:
        issued, not_before, expires = (int(claims[name]) for name in ("iat", "nbf", "exp"))
    except (KeyError, TypeError, ValueError) as exc:
        raise CursorIdentityError("cursor_oidc_time_invalid") from exc
    if issued > observed + skew or not_before > observed + skew or expires <= observed - skew or expires - issued > 330:
        raise CursorIdentityError("cursor_oidc_time_invalid")
    if claims.get("agent_runtime") != "managed" or not str(claims.get("cloud_agent_id") or "").startswith("bc-"):
        raise CursorIdentityError("cursor_oidc_runtime_invalid")
    if not str(claims.get("turn_id") or ""):
        raise CursorIdentityError("cursor_oidc_turn_required")
    if claims.get("repo_url") != APPROVED_REPOSITORY:
        raise CursorIdentityError("cursor_oidc_repository_invalid")
    repo_urls = claims.get("repo_urls")
    if repo_urls != [APPROVED_REPOSITORY]:
        raise CursorIdentityError("cursor_oidc_repository_set_invalid")
    if claims.get("repo_count") is not None and claims.get("repo_count") != 1:
        raise CursorIdentityError("cursor_oidc_repository_set_invalid")
    if claims.get("source") != "API":
        raise CursorIdentityError("cursor_oidc_source_invalid")
    return claims
