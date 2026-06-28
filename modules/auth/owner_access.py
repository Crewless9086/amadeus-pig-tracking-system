import hmac
import ipaddress
import os
from datetime import datetime, timezone

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
    body, status_code = _denied("owner_admin_access_denied", 403)
    return jsonify(body), status_code


def owner_session_is_valid(required_role="read"):
    data = session.get(SESSION_KEY)
    if not isinstance(data, dict):
        return False
    role = str(data.get("role") or "").strip()
    if role not in {"read", "admin"}:
        return False
    if required_role == "admin":
        return role == "admin"
    return role in {"read", "admin"}


def set_owner_session(role):
    if role not in {"read", "admin"}:
        raise ValueError("owner session role must be read or admin")
    session.clear()
    session[SESSION_KEY] = {
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    session.permanent = False


def clear_owner_session():
    session.pop(SESSION_KEY, None)


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
    if not text or not text.startswith("/") or text.startswith("//"):
        return ""
    return text


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _source(environ):
    return environ if environ is not None else os.environ
