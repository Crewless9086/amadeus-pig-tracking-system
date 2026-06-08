import ipaddress
import os


ALLOW_PRIVATE_LAN_ENV = "OOM_SAKKIE_REVIEW_ALLOW_PRIVATE_LAN"
LLM_MESSAGE_GUARD_ENVS = (
    "OOM_SAKKIE_LLM_ROUTER_ENABLED",
    "OOM_SAKKIE_LLM_ANSWER_ENABLED",
    "OOM_SAKKIE_LLM_LEARNING_ENABLED",
)


def is_review_request_allowed(remote_addr, environ=None):
    address = _parse_ip(remote_addr)
    if not address:
        return False
    if address.is_loopback:
        return True
    if address.is_private and _allow_private_lan(environ):
        return True
    return False


def is_message_request_allowed(remote_addr, environ=None):
    if not _llm_surface_enabled(environ):
        return True
    return is_review_request_allowed(remote_addr, environ=environ)


def review_access_denied_response(remote_addr):
    return {
        "success": False,
        "status": "review_access_denied",
        "message": "Oom Sakkie review endpoints are local-only. Use the kiosk browser on this machine or explicitly enable private-LAN review access.",
        "remote_addr": str(remote_addr or ""),
    }, 403


def message_access_denied_response(remote_addr):
    return {
        "success": False,
        "status": "message_access_denied",
        "message": "Oom Sakkie message access is local-only while LLM features are enabled, because unrouted questions can create outbound API calls.",
        "remote_addr": str(remote_addr or ""),
        "llm_guard_active": True,
    }, 403


def _allow_private_lan(environ=None):
    source = environ if environ is not None else os.environ
    value = str(source.get(ALLOW_PRIVATE_LAN_ENV, "") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _llm_surface_enabled(environ=None):
    source = environ if environ is not None else os.environ
    return any(
        str(source.get(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}
        for name in LLM_MESSAGE_GUARD_ENVS
    )


def _parse_ip(value):
    try:
        return ipaddress.ip_address(str(value or "").strip())
    except ValueError:
        return None
