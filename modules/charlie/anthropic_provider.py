import json
import os
import time
from urllib import request as url_request
from urllib.error import HTTPError, URLError

from modules.charlie.environment import env_value


ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 8192
RETRYABLE_HTTP_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504, 529}


def anthropic_api_key():
    return (
        str(os.getenv("ANTHROPIC_API_KEY") or "").strip()
        or str(os.getenv("ANTROPIC_API_KEY") or "").strip()
    )


def anthropic_api_key_env_name():
    if str(os.getenv("ANTHROPIC_API_KEY") or "").strip():
        return "ANTHROPIC_API_KEY"
    if str(os.getenv("ANTROPIC_API_KEY") or "").strip():
        return "ANTROPIC_API_KEY"
    return ""


def run_anthropic_prompt(prompt, model="", timeout_seconds=600, max_tokens=DEFAULT_MAX_TOKENS, opener=None, attempts=3, sleep_fn=time.sleep):
    api_key = anthropic_api_key()
    if not api_key:
        return {
            "success": False,
            "status": "anthropic_api_key_missing",
            "error": "Set ANTHROPIC_API_KEY. ANTROPIC_API_KEY is accepted as a temporary typo alias.",
        }, 503
    model = str(model or env_value("CORE_CLAUDE_MODEL") or "claude-sonnet-5").strip()
    max_tokens = _anthropic_max_tokens(max_tokens)
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": str(prompt or ""),
            }
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    request = url_request.Request(
        ANTHROPIC_MESSAGES_URL,
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        method="POST",
    )
    open_fn = opener or url_request.urlopen
    parsed_attempts = max(int(attempts or 1), 1)
    last_error = {}
    for attempt in range(1, parsed_attempts + 1):
        try:
            with open_fn(request, timeout=max(30, int(timeout_seconds or 600))) as response:
                response_body = response.read().decode("utf-8", errors="replace")
                parsed = json.loads(response_body)
            break
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
            last_error = {
                "success": False,
                "status": "anthropic_api_rejected",
                "http_status": exc.code,
                "error": error_body[:1000],
                "attempts": attempt,
            }
            if exc.code not in RETRYABLE_HTTP_STATUSES or attempt >= parsed_attempts:
                return last_error, 502
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = {
                "success": False,
                "status": "anthropic_api_unreachable",
                "error_type": exc.__class__.__name__,
                "error": str(exc)[:1000],
                "attempts": attempt,
            }
            if attempt >= parsed_attempts:
                return last_error, 502
        sleep_fn(min(2 ** (attempt - 1), 8))
    else:
        return last_error or {"success": False, "status": "anthropic_api_unreachable", "attempts": parsed_attempts}, 502

    text = _extract_text(parsed)
    if not text:
        return {
            "success": False,
            "status": "anthropic_empty_response",
            "raw_response": _compact_response(parsed),
        }, 502
    return {
        "success": True,
        "status": "anthropic_completed",
        "provider": "anthropic",
        "model": model,
        "text": text,
        "usage": parsed.get("usage") if isinstance(parsed.get("usage"), dict) else {},
        "stop_reason": parsed.get("stop_reason", ""),
    }, 200


def _anthropic_max_tokens(max_tokens=None):
    configured = str(env_value("CORE_ANTHROPIC_MAX_TOKENS") or "").strip()
    raw = configured or max_tokens or DEFAULT_MAX_TOKENS
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = DEFAULT_MAX_TOKENS
    return max(1024, min(parsed, 16000))


def _extract_text(parsed):
    if not isinstance(parsed, dict):
        return ""
    chunks = []
    for item in parsed.get("content") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            text = str(item.get("text") or "").strip()
            if text:
                chunks.append(text)
    return "\n\n".join(chunks).strip()


def _compact_response(parsed):
    if not isinstance(parsed, dict):
        return {}
    return {
        "id": parsed.get("id", ""),
        "type": parsed.get("type", ""),
        "role": parsed.get("role", ""),
        "model": parsed.get("model", ""),
        "stop_reason": parsed.get("stop_reason", ""),
        "usage": parsed.get("usage", {}),
        "content_count": len(parsed.get("content") or []),
    }
