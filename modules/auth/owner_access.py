import hmac
import ipaddress
import os
import json
import secrets
import time
from urllib.parse import parse_qsl, urlsplit
from datetime import datetime, timezone
from hashlib import sha256

from flask import jsonify, redirect, render_template, request, session, url_for


OWNER_ACCESS_ENABLED_ENV = "OWNER_ACCESS_ENABLED"
OWNER_ACCESS_ALLOW_LOCAL_DEV_ENV = "OWNER_ACCESS_ALLOW_LOCAL_DEV"
OWNER_READ_TOKEN_ENV = "OWNER_READ_TOKEN"
OWNER_ADMIN_TOKEN_ENV = "OWNER_ADMIN_TOKEN"
OWNER_SESSION_SECRET_ENV = "OWNER_SESSION_SECRET"
MIN_OWNER_TOKEN_CHARS = 32
SESSION_KEY = "owner_access"


def configure_owner_access(app):
    secret = _secret()
    app.secret_key = secret
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=owner_access_enabled() and not owner_local_dev_allowed(),
    )


def owner_access_enabled(environ=None):
    return _truthy(_source(environ).get(OWNER_ACCESS_ENABLED_ENV, "false"))


def owner_local_dev_allowed(environ=None):
    return _truthy(_source(environ).get(OWNER_ACCESS_ALLOW_LOCAL_DEV_ENV, "1"))


def is_loopback_request(req):
    remote_addr = getattr(req, "remote_addr", "")
    try:
        return ipaddress.ip_address(str(remote_addr or "").strip()).is_loopback
    except ValueError:
        return False


def require_owner_page_access():
    if _access_disabled_or_local_allowed():
        return None
    if not _configured():
        body, status_code = _denied("owner_access_not_configured", 503)
        return jsonify(body), status_code
    if owner_session_is_valid("read"):
        return None
    return redirect(url_for("owner_login_page", next=request.full_path if request.query_string else request.path))


def require_owner_read_access():
    if _access_disabled_or_local_allowed():
        return None
    # Pig profiles display reproductive history from this existing herd reader.
    if request.method == "GET" and request.endpoint == "mating.mating_list" and farm_session_principal():
        return None
    if not _configured():
        body, status_code = _denied("owner_access_not_configured", 503)
        return jsonify(body), status_code
    if owner_session_is_valid("read"):
        return None
    body, status_code = _denied("owner_read_access_denied", 403)
    return jsonify(body), status_code


def require_owner_admin_access():
    if _access_disabled_or_local_allowed():
        return None
    if not _configured():
        body, status_code = _denied("owner_access_not_configured", 503)
        return jsonify(body), status_code
    if owner_session_is_valid("admin"):
        return None
    if _session_role() == "admin":
        body, status_code = _denied("owner_identity_required", 403)
        return jsonify(body), status_code
    body, status_code = _denied("owner_admin_access_denied", 403)
    return jsonify(body), status_code


def require_strict_owner_read_access():
    """Require an authenticated owner read session, except explicit loopback dev."""
    if _correction_batch_local_dev_allowed():
        return None
    if not _configured():
        body, status_code = _denied("owner_access_not_configured", 503)
        return jsonify(body), status_code
    if owner_session_is_valid("read"):
        return None
    body, status_code = _denied("owner_read_access_denied", 403)
    return jsonify(body), status_code


def require_strict_owner_admin_access():
    """Require an authenticated owner admin session, except explicit loopback dev."""
    if _correction_batch_local_dev_allowed():
        return None
    if not _configured():
        body, status_code = _denied("owner_access_not_configured", 503)
        return jsonify(body), status_code
    if _owner_admin_session_principal():
        return None
    body, status_code = _denied("owner_admin_access_denied", 403)
    return jsonify(body), status_code


def strict_owner_admin_principal():
    """Return only the principal accepted by the strict owner-admin guard."""
    principal = _owner_admin_session_principal()
    if principal:
        return principal
    if _correction_batch_local_dev_allowed():
        return "owner-admin:local-development"
    return ""


def require_correction_batch_owner_admin_access():
    """Require an admin session for correction batches, with loopback-only dev access.

    Correction batches can change canonical pig purpose records, so they must not
    inherit the global disabled-access compatibility behavior.  In particular,
    OWNER_ACCESS_ENABLED=0 never permits a remote request through this guard.
    """
    if _correction_batch_local_dev_allowed():
        return None
    if not _configured():
        body, status_code = _denied("owner_access_not_configured", 503)
        return jsonify(body), status_code
    if _owner_admin_session_principal():
        return None
    body, status_code = _denied("owner_admin_access_denied", 403)
    return jsonify(body), status_code


def owner_session_is_valid(required_role="read"):
    role, principal = _validated_session_principal()
    if not principal:
        return False
    if required_role == "admin":
        return role == "admin"
    return role in {"read", "admin"}


def set_owner_session(role):
    if role not in {"read", "admin"}:
        raise ValueError("owner session role must be read or admin")
    principal = _stable_owner_principal(role)
    if not principal:
        raise ValueError("stable owner principal is unavailable")
    session.clear()
    session[SESSION_KEY] = {
        "role": role,
        # This opaque, server-signed session principal is audit provenance.  It
        # is deliberately not supplied by a browser request body.
        "principal_id": principal,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    session.permanent = False


def clear_owner_session():
    session.pop(SESSION_KEY, None)
    session.pop("farm_access", None)


def farm_session_principal():
    """Recheck the existing family delegation; this never grants owner access."""
    from modules.oom_sakkie.family_access import resolve_family_principal
    data = session.get("farm_access")
    if not isinstance(data, dict) or not _secret_configured():
        return None
    if not 0 <= time.time() - float(data.get("authenticated_at") or 0) <= 8 * 60 * 60:
        return None
    actor = str(data.get("principal_id") or "")
    principal = resolve_family_principal({"telegram_user_id": actor,
        "telegram_chat_id": actor, "telegram_chat_type": "private"}, os.environ)
    if (not principal.authenticated or principal.binding_digest != data.get("binding_digest")
            or not ({"*", "mortality_confirmation"} & principal.effective_permissions)):
        return None
    return principal


def mortality_session_identity():
    principal = farm_session_principal()
    if principal:
        return {"actor_id": principal.telegram_user_id, "role": principal.role.value,
                "capabilities": principal.effective_permissions, "language": principal.language}
    actor = _owner_admin_session_principal()
    if actor:
        return {"actor_id": actor, "role": "owner", "capabilities": frozenset({"*"}), "language": "en"}
    return None


def mortality_csrf_token():
    if not mortality_session_identity():
        return ""
    if not session.get("mortality_csrf"):
        session["mortality_csrf"] = secrets.token_urlsafe(32)
    return session["mortality_csrf"]


def require_mortality_session():
    if not mortality_session_identity():
        return jsonify(success=False, status="authenticated_mortality_permission_required"), 403
    expected = str(session.get("mortality_csrf") or "")
    supplied = str(request.headers.get("X-Mortality-CSRF") or "")
    if not expected or not hmac.compare_digest(expected, supplied):
        return jsonify(success=False, status="mortality_request_binding_required"), 403
    return None


def telegram_farm_login_post():
    """Validate Telegram Mini App initData before resolving a farm principal.

    Protocol: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    The signed user identity is verified locally; no provider request is made.
    """
    token = str(os.environ.get("OOM_SAKKIE_TELEGRAM_BOT_TOKEN") or "")
    if not token or not _secret_configured() or not owner_access_enabled():
        return jsonify(success=False, status="farm_login_not_configured"), 503
    # JSON-only input and same-origin browser fetch prevent form-based login CSRF.
    if not request.is_json or request.headers.get("X-Farm-Login") != "telegram":
        return jsonify(success=False, status="farm_login_request_invalid"), 403
    origin = request.headers.get("Origin")
    # TLS terminates at the deployment proxy; Host remains the public authority
    # even when Flask sees an internal HTTP request.
    try:
        origin_url = urlsplit(origin or "")
    except ValueError:
        return jsonify(success=False, status="farm_login_origin_invalid"), 403
    if origin and (origin_url.scheme not in {"http", "https"}
                   or origin_url.netloc.casefold() != request.host.casefold()):
        return jsonify(success=False, status="farm_login_origin_invalid"), 403
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValueError("object required")
        raw = str(payload.get("init_data") or "")
        if not raw or len(raw) > 16384:
            raise ValueError("invalid init data")
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError("duplicate keys")
        received = fields.pop("hash", "")
        secret = hmac.new(b"WebAppData", token.encode(), sha256).digest()
        check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
        if not hmac.compare_digest(hmac.new(secret, check.encode(), sha256).hexdigest(), received):
            raise ValueError("invalid signature")
        authenticated_at = int(fields["auth_date"])
        if not 0 <= time.time() - authenticated_at <= 300:
            raise ValueError("expired authentication")
        user = json.loads(fields["user"])
        actor = str(user["id"])
        if not actor.isdigit() or user.get("is_bot"):
            raise ValueError("invalid user")
        from modules.oom_sakkie.family_access import resolve_family_principal
        principal = resolve_family_principal({"telegram_user_id": actor,
            "telegram_chat_id": actor, "telegram_chat_type": "private"}, os.environ)
        if not principal.authenticated or not ({"*", "mortality_confirmation"} & principal.effective_permissions):
            raise ValueError("missing delegation")
    except (ValueError, TypeError, KeyError):
        return jsonify(success=False, status="farm_login_not_authorized"), 403
    session.clear()
    session["farm_access"] = {"principal_id": actor, "binding_digest": principal.binding_digest,
                              "authenticated_at": authenticated_at}
    session.permanent = False
    return jsonify(success=True, role=principal.role.value, language=principal.language)


def owner_admin_principal():
    """Return the server-bound principal for an already-authorized admin request.

    Local development remains explicitly labelled rather than pretending an
    anonymous request was an authenticated production owner session.
    """
    principal = _owner_admin_session_principal()
    if principal:
        return principal
    if _access_disabled_or_local_allowed():
        return "owner-admin:local-development"
    return ""


def correction_batch_owner_admin_principal():
    """Return the actor accepted by the correction-batch-specific strict guard."""
    principal = _owner_admin_session_principal()
    if principal:
        return principal
    if _correction_batch_local_dev_allowed():
        return "owner-admin:local-development"
    return ""


def owner_login_get():
    return render_template(
        "owner-login.html",
        error="",
        next_url=_safe_next(request.args.get("next")),
        owner_access_enabled=owner_access_enabled(),
        local_dev_allowed=owner_local_dev_allowed(),
        session_valid=owner_session_is_valid("read"),
        session_role=_session_role(),
        status_mode=False,
    )


def owner_login_post():
    if not owner_access_enabled():
        return render_template(
            "owner-login.html",
            error="Owner access is not enabled.",
            next_url=_safe_next(request.form.get("next")),
            owner_access_enabled=owner_access_enabled(),
            local_dev_allowed=owner_local_dev_allowed(),
            session_valid=owner_session_is_valid("read"),
            session_role=_session_role(),
            status_mode=False,
        ), 503
    if not _configured():
        return render_template(
            "owner-login.html",
            error="Owner access is not configured.",
            next_url=_safe_next(request.form.get("next")),
            owner_access_enabled=owner_access_enabled(),
            local_dev_allowed=owner_local_dev_allowed(),
            session_valid=owner_session_is_valid("read"),
            session_role=_session_role(),
            status_mode=False,
        ), 503
    token = str(request.form.get("owner_token") or "").strip()
    role = _role_for_token(token)
    if not role:
        return render_template(
            "owner-login.html",
            error="Owner token was not accepted.",
            next_url=_safe_next(request.form.get("next")),
            owner_access_enabled=owner_access_enabled(),
            local_dev_allowed=owner_local_dev_allowed(),
            session_valid=owner_session_is_valid("read"),
            session_role=_session_role(),
            status_mode=False,
        ), 403
    set_owner_session(role)
    return redirect(_safe_next(request.form.get("next")) or url_for("meat_sales_leads_page"))


def owner_logout_post():
    clear_owner_session()
    return redirect("/")


def owner_status():
    return render_template(
        "owner-login.html",
        error="",
        next_url="",
        owner_access_enabled=owner_access_enabled(),
        local_dev_allowed=owner_local_dev_allowed(),
        session_valid=owner_session_is_valid("read"),
        session_role=_session_role(),
        status_mode=True,
    )


def owner_status_payload():
    return {
        "success": True,
        "owner_access_enabled": owner_access_enabled(),
        "local_dev_allowed": owner_local_dev_allowed(),
        "session_valid": owner_session_is_valid("read"),
        "session_role": _session_role(),
    }


def _access_disabled_or_local_allowed():
    if not owner_access_enabled():
        return True
    return owner_local_dev_allowed() and is_loopback_request(request)


def _correction_batch_local_dev_allowed():
    return owner_local_dev_allowed() and is_loopback_request(request)


def _owner_admin_session_principal():
    role, principal = _validated_session_principal()
    return principal if role == "admin" else ""


def _validated_session_principal():
    data = session.get(SESSION_KEY)
    if not isinstance(data, dict):
        return "", ""
    role = str(data.get("role") or "").strip()
    if role not in {"read", "admin"}:
        return "", ""
    principal = str(data.get("principal_id") or "").strip()
    expected = _stable_owner_principal(role)
    if not principal or not expected or not hmac.compare_digest(principal, expected):
        return role, ""
    return role, principal


def _stable_owner_principal(role):
    if role not in {"read", "admin"}:
        return ""
    token_name = OWNER_ADMIN_TOKEN_ENV if role == "admin" else OWNER_READ_TOKEN_ENV
    token = str(os.environ.get(token_name, "") or "").strip()
    secret = str(
        os.environ.get(OWNER_SESSION_SECRET_ENV)
        or os.environ.get("SECRET_KEY")
        or ""
    ).strip()
    if len(token) < MIN_OWNER_TOKEN_CHARS or not secret:
        return ""
    digest = hmac.new(
        secret.encode("utf-8"),
        f"owner-access-principal:v1\0{role}\0{token}".encode("utf-8"),
        sha256,
    ).hexdigest()
    return f"owner-{role}:{digest}"


def _configured():
    return bool(_secret_configured() and (_valid_token_env(OWNER_READ_TOKEN_ENV) or _valid_token_env(OWNER_ADMIN_TOKEN_ENV)))


def _session_role():
    data = session.get(SESSION_KEY)
    if not isinstance(data, dict):
        return ""
    role = str(data.get("role") or "").strip()
    return role if role in {"read", "admin"} else ""


def _role_for_token(token):
    admin = str(os.environ.get(OWNER_ADMIN_TOKEN_ENV, "") or "").strip()
    read = str(os.environ.get(OWNER_READ_TOKEN_ENV, "") or "").strip()
    if len(admin) >= MIN_OWNER_TOKEN_CHARS and hmac.compare_digest(token, admin):
        return "admin"
    if len(read) >= MIN_OWNER_TOKEN_CHARS and hmac.compare_digest(token, read):
        return "read"
    return ""


def _valid_token_env(name):
    return len(str(os.environ.get(name, "") or "").strip()) >= MIN_OWNER_TOKEN_CHARS


def _secret_configured():
    return bool(str(os.environ.get(OWNER_SESSION_SECRET_ENV) or os.environ.get("SECRET_KEY") or "").strip())


def _secret():
    return str(os.environ.get(OWNER_SESSION_SECRET_ENV) or os.environ.get("SECRET_KEY") or "local-owner-access-dev-session-secret").strip()


def _denied(status, status_code):
    return {
        "success": False,
        "status": status,
        "owner_access_enabled": owner_access_enabled(),
        "requires_owner_session": True,
        "sends_customer_message": False,
        "creates_order": False,
        "changes_stock": False,
        "posts_publicly": False,
    }, status_code


def _safe_next(value):
    text = str(value or "").strip()
    if (
        not text
        or not text.startswith("/")
        or text.startswith("//")
        or "\\" in text
        or any(ord(character) < 32 for character in text)
    ):
        return ""
    return text


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _source(environ):
    return environ if environ is not None else os.environ
