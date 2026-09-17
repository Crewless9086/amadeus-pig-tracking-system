"""Safe Telegram media normalization for private CHARLIE."""

from __future__ import annotations

import os

import requests

MAX_VOICE_BYTES = 20 * 1024 * 1024


def normalize_private_media(payload):
    message = payload.get("message") or payload.get("edited_message") or {}
    media = []
    if message.get("voice"):
        voice = message["voice"]
        media.append({"kind": "voice", "file_id": str(voice.get("file_id") or ""), "file_size": int(voice.get("file_size") or 0), "duration": int(voice.get("duration") or 0), "mime_type": str(voice.get("mime_type") or "audio/ogg")})
    photos = message.get("photo") or []
    if photos:
        photo = photos[-1]
        media.append({"kind": "photo", "file_id": str(photo.get("file_id") or ""), "file_size": int(photo.get("file_size") or 0), "width": int(photo.get("width") or 0), "height": int(photo.get("height") or 0)})
    if message.get("document"):
        document = message["document"]
        media.append({"kind": "document", "file_id": str(document.get("file_id") or ""), "file_size": int(document.get("file_size") or 0), "file_name": str(document.get("file_name") or "")[:180], "mime_type": str(document.get("mime_type") or "")[:120]})
    return media


def transcribe_voice(media, policy, *, environ=None, http_client=None):
    voice = next((item for item in media if item.get("kind") == "voice"), None)
    if not voice:
        return {"success": False, "status": "voice_not_present", "text": ""}
    if voice.get("file_size", 0) > MAX_VOICE_BYTES:
        return {"success": False, "status": "voice_too_large", "text": ""}
    if not policy.get("transcription_enabled"):
        return {"success": False, "status": "voice_transcription_disabled", "text": ""}
    source = environ if environ is not None else os.environ
    token = str(policy.get("token") or "")
    api_key = str(source.get("OPENAI_API_KEY") or "")
    client = http_client or requests
    try:
        file_response = client.get(f"https://api.telegram.org/bot{token}/getFile", params={"file_id": voice.get("file_id")}, timeout=15)
        file_response.raise_for_status()
        file_path = str((file_response.json().get("result") or {}).get("file_path") or "")
        if not file_path:
            return {"success": False, "status": "voice_file_path_missing", "text": ""}
        audio_response = client.get(f"https://api.telegram.org/file/bot{token}/{file_path}", timeout=30)
        audio_response.raise_for_status()
        audio = audio_response.content
        if len(audio) > MAX_VOICE_BYTES:
            return {"success": False, "status": "voice_too_large", "text": ""}
        transcription = client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            data={"model": policy.get("transcription_model")},
            files={"file": ("owner-voice.ogg", audio, voice.get("mime_type") or "audio/ogg")},
            timeout=60,
        )
        transcription.raise_for_status()
        text = str(transcription.json().get("text") or "").strip()
    except (OSError, ValueError, requests.RequestException):
        return {"success": False, "status": "voice_transcription_failed", "text": ""}
    return {"success": bool(text), "status": "voice_transcribed" if text else "voice_transcription_empty", "text": text[:12000]}
