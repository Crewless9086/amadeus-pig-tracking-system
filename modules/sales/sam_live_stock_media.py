"""Env-gated voice and image understanding for SAM Live Stock Chatwoot media."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Any, Mapping

from modules.oom_sakkie.voice_stt import _multipart_body


VOICE_ENABLED_ENV = "SAM_LIVE_STOCK_VOICE_TRANSCRIPTION_ENABLED"
VOICE_MODEL_ENV = "SAM_LIVE_STOCK_VOICE_TRANSCRIPTION_MODEL"
IMAGE_ENABLED_ENV = "SAM_LIVE_STOCK_IMAGE_UNDERSTANDING_ENABLED"
IMAGE_MODEL_ENV = "SAM_LIVE_STOCK_IMAGE_UNDERSTANDING_MODEL"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
CHATWOOT_TOKEN_ENV = "CHATWOOT_API_ACCESS_TOKEN"
DEFAULT_TRANSCRIPTION_URL = "https://api.openai.com/v1/audio/transcriptions"
DEFAULT_CHAT_URL = "https://api.openai.com/v1/chat/completions"
MAX_MEDIA_BYTES = 6 * 1024 * 1024


def media_policy(environ=None):
    source = environ if environ is not None else os.environ
    configured = bool(str(source.get(OPENAI_API_KEY_ENV) or "").strip())
    return {
        "voice_enabled": truthy(source.get(VOICE_ENABLED_ENV)) and configured,
        "voice_explicitly_enabled": truthy(source.get(VOICE_ENABLED_ENV)),
        "voice_model": str(source.get(VOICE_MODEL_ENV) or "whisper-1").strip(),
        "image_enabled": truthy(source.get(IMAGE_ENABLED_ENV)) and configured,
        "image_explicitly_enabled": truthy(source.get(IMAGE_ENABLED_ENV)),
        "image_model": str(source.get(IMAGE_MODEL_ENV) or "gpt-4.1-mini").strip(),
        "configured": configured,
        "stores_media": False,
        "facts_from_images_trusted": False,
        "customer_send_allowed": False,
    }


def transcribe_chatwoot_voice(attachment: Mapping[str, Any], _payload=None, *, environ=None):
    source = environ if environ is not None else os.environ
    policy = media_policy(source)
    if not policy["voice_enabled"]:
        return {"status": "voice_transcription_disabled", "transcript": "", **policy}
    try:
        media, content_type = download_media(attachment, source)
        boundary = f"sam-live-{uuid.uuid4().hex}"
        body = _multipart_body(
            boundary,
            [("model", policy["voice_model"])],
            "file",
            str(attachment.get("file_name") or "sam-live-voice.ogg"),
            content_type or "audio/ogg",
            media,
        )
        request = urllib.request.Request(
            DEFAULT_TRANSCRIPTION_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {str(source.get(OPENAI_API_KEY_ENV) or '').strip()}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
        return {"status": "transcribed", "transcript": clean(result.get("text"), 1800), **policy}
    except Exception as exc:
        return {"status": "voice_transcription_failed", "transcript": "", "error_type": exc.__class__.__name__, **policy}


def classify_chatwoot_image(attachment: Mapping[str, Any], payload=None, *, environ=None):
    source = environ if environ is not None else os.environ
    policy = media_policy(source)
    if not policy["image_enabled"]:
        return {"status": "image_understanding_disabled", "classification": "unknown_image", **policy}
    try:
        media, content_type = download_media(attachment, source)
        data_url = f"data:{content_type or 'image/jpeg'};base64,{base64.b64encode(media).decode('ascii')}"
        request_payload = {
            "model": policy["image_model"],
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": (
                        "Classify this customer image for farm sales. Return JSON only with classification and note. "
                        "Allowed classifications: customer_pig_image, advert_screenshot, payment_proof_possible, "
                        "location_map, unrelated_image, unknown_image. Never identify an animal, payment status, weight, or reservation."
                    )},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            DEFAULT_CHAT_URL,
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {str(source.get(OPENAI_API_KEY_ENV) or '').strip()}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        allowed = {"customer_pig_image", "advert_screenshot", "payment_proof_possible", "location_map", "unrelated_image", "unknown_image"}
        classification = clean(parsed.get("classification"), 80)
        if classification not in allowed:
            classification = "unknown_image"
        return {"status": "classified", "classification": classification, "note": clean(parsed.get("note"), 240), **policy}
    except Exception as exc:
        return {"status": "image_understanding_failed", "classification": "unknown_image", "error_type": exc.__class__.__name__, **policy}


def download_media(attachment: Mapping[str, Any], source: Mapping[str, Any]):
    url = str(attachment.get("url") or "").strip()
    if not url:
        raise ValueError("media_url_required")
    headers = {}
    token = str(source.get(CHATWOOT_TOKEN_ENV) or "").strip()
    if token:
        headers["api_access_token"] = token
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        content_type = str(response.headers.get("Content-Type") or attachment.get("content_type") or "").split(";", 1)[0]
        data = response.read(MAX_MEDIA_BYTES + 1)
    if not data:
        raise ValueError("empty_media")
    if len(data) > MAX_MEDIA_BYTES:
        raise ValueError("media_too_large")
    return data, content_type


def truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def clean(value, limit):
    return " ".join(str(value or "").strip().split())[:limit]
