"""Optional provider-backed voice input and output for private CHARLIE."""

from __future__ import annotations

import os

import requests

MAX_AUDIO_BYTES = 20 * 1024 * 1024


def transcribe_web_audio(audio, filename, mime_type, policy, *, environ=None, http_client=None):
    if not policy.get("transcription_enabled"):
        return {"success": False, "status": "voice_transcription_disabled", "text": ""}, 503
    if not audio:
        return {"success": False, "status": "voice_audio_required", "text": ""}, 400
    if len(audio) > MAX_AUDIO_BYTES:
        return {"success": False, "status": "voice_too_large", "text": ""}, 413
    source = environ if environ is not None else os.environ
    client = http_client or requests
    try:
        response = client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {source.get('OPENAI_API_KEY', '')}"},
            data={"model": policy.get("transcription_model"), "language": "en"},
            files={"file": (str(filename or "owner-voice.webm")[:180], audio, str(mime_type or "audio/webm")[:120])},
            timeout=60,
        )
        response.raise_for_status()
        text = str(response.json().get("text") or "").strip()
    except (OSError, ValueError, requests.RequestException):
        return {"success": False, "status": "voice_transcription_failed", "text": ""}, 502
    return {"success": bool(text), "status": "voice_transcribed" if text else "voice_transcription_empty", "text": text[:12000]}, 200 if text else 422


def synthesize_private_speech(text, policy, *, environ=None, http_client=None):
    clean = str(text or "").strip()[:1200]
    if not clean:
        return {"success": False, "status": "speech_text_required", "audio": b""}, 400
    if not policy.get("tts_enabled"):
        return {"success": False, "status": "private_tts_disabled", "audio": b""}, 503
    if policy.get("tts_provider") != "elevenlabs":
        return {"success": False, "status": "private_tts_provider_unsupported", "audio": b""}, 503
    source = environ if environ is not None else os.environ
    client = http_client or requests
    try:
        response = client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{policy.get('tts_voice_id')}",
            headers={"xi-api-key": str(source.get("ELEVENLABS_API_KEY") or ""), "Accept": "audio/mpeg", "Content-Type": "application/json"},
            json={"text": clean, "model_id": policy.get("tts_model"), "voice_settings": {"stability": 0.55, "similarity_boost": 0.75}},
            timeout=60,
        )
        response.raise_for_status()
        audio = bytes(response.content or b"")
    except (OSError, ValueError, requests.RequestException):
        return {"success": False, "status": "private_tts_failed", "audio": b""}, 502
    return {"success": bool(audio), "status": "private_tts_ready" if audio else "private_tts_empty", "audio": audio, "content_type": "audio/mpeg"}, 200 if audio else 502
