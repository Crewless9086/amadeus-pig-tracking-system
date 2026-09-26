
from modules.oom_sakkie.model_budget import ModelBudgetError, budgeted_urlopen
import json
import os
import re
import uuid
import urllib.error
import urllib.request


TRUTHY = {"1", "true", "yes", "on"}
STT_ENABLED_ENV = "OOM_SAKKIE_STT_ENABLED"
STT_MODEL_ENV = "OOM_SAKKIE_STT_MODEL"
STT_URL_ENV = "OOM_SAKKIE_STT_URL"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
DEFAULT_STT_MODEL = "whisper-1"
DEFAULT_STT_URL = "https://api.openai.com/v1/audio/transcriptions"
MAX_AUDIO_BYTES = 6 * 1024 * 1024
MAX_AUDIO_SECONDS = 10
MAX_TRANSCRIPTION_RESPONSE_BYTES = 64 * 1024


def backend_voice_stt_policy(environ=None):
    source = environ if environ is not None else os.environ
    enabled = _env_truthy(source.get(STT_ENABLED_ENV))
    configured = bool(str(source.get(OPENAI_API_KEY_ENV, "") or "").strip())
    return {
        "enabled": enabled and configured,
        "configured": configured,
        "explicitly_enabled": enabled,
        "mode": "push_to_talk_backend_stt_fallback",
        "provider": "openai_audio_transcriptions",
        "model": str(source.get(STT_MODEL_ENV, DEFAULT_STT_MODEL) or DEFAULT_STT_MODEL).strip(),
        "endpoint": str(source.get(STT_URL_ENV, DEFAULT_STT_URL) or DEFAULT_STT_URL).strip(),
        "max_audio_seconds": MAX_AUDIO_SECONDS,
        "max_audio_bytes": MAX_AUDIO_BYTES,
        "stores_audio": False,
        "always_on_mic_enabled": False,
        "wake_word_enabled": False,
        "writes": False,
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
    }


def transcribe_oom_sakkie_voice_audio(file_storage, environ=None, *, language="en",
                                     filename="oom-sakkie-voice.webm", http_open=None,
                                     timeout=25):
    policy = backend_voice_stt_policy(environ=environ)
    if not policy["explicitly_enabled"]:
        return _result(False, "backend_stt_disabled", policy, 503)
    if not policy["configured"]:
        return _result(False, "backend_stt_not_configured", policy, 503)
    if language not in {"en", "af"} or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", filename):
        return _result(False, "backend_stt_input_metadata_invalid", policy, 400)
    if not file_storage:
        return _result(False, "audio_file_required", policy, 400)

    content_type = (getattr(file_storage, "mimetype", "") or getattr(file_storage, "content_type", "") or "").lower()
    if content_type and not (content_type.startswith("audio/") or content_type in {"video/webm", "application/octet-stream"}):
        return _result(False, "unsupported_audio_type", policy, 415)

    audio_bytes = file_storage.read(MAX_AUDIO_BYTES + 1)
    if not audio_bytes:
        return _result(False, "empty_audio", policy, 400)
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        return _result(False, "audio_too_large", policy, 413)

    try:
        text = _call_openai_transcription(audio_bytes, content_type or "audio/webm", policy,
            environ=environ, language=language, filename=filename, http_open=http_open,
            timeout=timeout)
    except ModelBudgetError as error:
        from modules.oom_sakkie.service import model_budget_denial_result
        notice = model_budget_denial_result(error.status, language, voice=True)
        body, code = _result(False, notice["status"], policy, 503)
        body.update({"answer": notice["answer"], "model_budget_denied": True, "text_only": True})
        return body, code
    except urllib.error.HTTPError as error:
        return _result(False, "backend_stt_http_error", policy, error.code if 400 <= error.code < 500 else 502)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return _result(False, "backend_stt_unavailable", policy, 502)

    text = (text or "").strip()
    if not text:
        return _result(False, "no_speech_transcribed", policy, 422)
    body, status_code = _result(True, "transcribed", policy, 200)
    body["text"] = text
    return body, status_code


def _call_openai_transcription(audio_bytes, content_type, policy, environ=None, *,
                               language="en", filename="oom-sakkie-voice.webm",
                               http_open=None, timeout=25):
    source = environ if environ is not None else os.environ
    api_key = str(source.get(OPENAI_API_KEY_ENV, "") or "").strip()
    boundary = f"oom-sakkie-{uuid.uuid4().hex}"
    fields = [
        ("model", policy["model"]),
        ("language", language),
    ]
    body = _multipart_body(boundary, fields, "file", filename, content_type, audio_bytes)
    request = urllib.request.Request(
        policy["endpoint"],
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    with budgeted_urlopen(request, timeout=timeout, purpose="oom_voice", environ=environ, http_open=http_open) as response:
        response_bytes = response.read(MAX_TRANSCRIPTION_RESPONSE_BYTES + 1)
    if len(response_bytes) > MAX_TRANSCRIPTION_RESPONSE_BYTES:
        raise ValueError("transcription_response_too_large")
    payload = json.loads(response_bytes.decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("text", ""), str):
        raise ValueError("transcription_response_invalid")
    return payload.get("text", "")


def _multipart_body(boundary, fields, file_field, filename, content_type, file_bytes):
    chunks = []
    for name, value in fields:
        chunks.extend([
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
            str(value).encode("utf-8"),
            b"\r\n",
        ])
    chunks.extend([
        f"--{boundary}\r\n".encode("utf-8"),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ])
    return b"".join(chunks)


def _result(success, status, policy, status_code):
    return {
        "success": success,
        "status": status,
        "mode": "push_to_talk_backend_stt_transcription",
        "backend_voice_stt": policy,
        "always_on_mic_enabled": False,
        "stores_audio": False,
        "writes": False,
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
    }, status_code


def _env_truthy(value):
    return str(value or "").strip().lower() in TRUTHY
