"""Owner-session binding for ROOTLINE browser controls."""
import hmac
import secrets
from urllib.parse import urlsplit

from flask import jsonify, request, session
from modules.auth.owner_access import (
    require_strict_owner_admin_access, strict_owner_admin_principal,
)


def rootline_csrf_token():
    if not strict_owner_admin_principal():
        return ""
    if not session.get("rootline_csrf"):
        session["rootline_csrf"] = secrets.token_urlsafe(32)
    return session["rootline_csrf"]


def require_rootline_mutation():
    guard = require_strict_owner_admin_access()
    if guard is not None:
        return guard
    if not request.is_json:
        return jsonify(success=False, status="json_body_required"), 415
    if request.headers.get("Sec-Fetch-Site", "") == "cross-site":
        return jsonify(success=False, status="same_origin_required"), 403
    origin = request.headers.get("Origin")
    if origin:
        try:
            supplied = urlsplit(origin)
        except ValueError:
            return jsonify(success=False, status="same_origin_required"), 403
        # Render terminates TLS before Flask; compare the public host, as the
        # existing owner Telegram login does, and retain session-bound CSRF.
        if supplied.scheme not in {"http", "https"} or supplied.netloc != request.host:
            return jsonify(success=False, status="same_origin_required"), 403
    expected_token = str(session.get("rootline_csrf") or "")
    supplied_token = str(request.headers.get("X-ROOTLINE-CSRF") or "")
    if not expected_token or not hmac.compare_digest(expected_token.encode("utf-8"), supplied_token.encode("utf-8")):
        return jsonify(success=False, status="rootline_request_binding_required"), 403
    if not isinstance(request.get_json(silent=True), dict):
        return jsonify(success=False, status="json_object_required"), 400
    return None
