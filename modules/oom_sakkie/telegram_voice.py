"""Authenticated Telegram voice input for the existing protected herd dialogue.

Audio remains in bounded memory. Append-only input receipts reuse the existing
conversation event table, before any specialist dispatch; no schema or queue.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import os
import queue
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from modules.oom_sakkie.family_access import FamilyRole, resolve_family_principal
from modules.oom_sakkie.telegram_voice_audio import MAX_VOICE_SECONDS, validate_ogg_opus_duration
from modules.oom_sakkie.voice_stt import MAX_AUDIO_BYTES, backend_voice_stt_policy, transcribe_oom_sakkie_voice_audio

EVENT_SOURCE = "oom_sakkie_telegram_voice_input"
NETWORK_DEADLINE_SECONDS = 20
NETWORK_CALL_TIMEOUT_SECONDS = 10
MAX_JSON_BYTES = 64 * 1024
MAX_TRANSCRIPT_CHARS = 2000
_NETWORK_SLOTS = threading.BoundedSemaphore(4)


class VoiceFailure(ValueError):
    def __init__(self, status, http_status=409):
        super().__init__(status)
        self.status, self.http_status = status, http_status


def is_telegram_voice_payload(payload):
    if not isinstance(payload, dict) or payload.get("callback_query"):
        return False
    message = payload.get("message") or payload.get("edited_message") or {}
    return isinstance(message, dict) and ("voice" in message or "audio" in message)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _authorize_native(payload, parsed, source):
    message = payload.get("message")
    if (not isinstance(message, dict) or payload.get("edited_message") or payload.get("callback_query")
            or parsed.get("callback_data") or payload.get("callback_data") or payload.get("callback_query_id")):
        raise VoiceFailure("telegram_voice_original_message_required", 403)
    sender, chat = message.get("from") or {}, message.get("chat") or {}
    if not isinstance(sender, dict) or not isinstance(chat, dict):
        raise VoiceFailure("telegram_voice_identity_malformed", 403)
    native = {"telegram_user_id": str(sender.get("id") or ""),
              "telegram_chat_id": str(chat.get("id") or ""),
              "telegram_chat_type": str(chat.get("type") or "")}
    if any(str(parsed.get(key) or "") != value for key, value in native.items()):
        raise VoiceFailure("telegram_voice_identity_mismatch", 403)
    allowed = {item.strip() for item in str(source.get("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS") or "").split(",")}
    principal = resolve_family_principal(native, source)
    if (native["telegram_user_id"] not in allowed or sender.get("is_bot")
            or principal.role not in {FamilyRole.OWNER, FamilyRole.FARM_MANAGER}):
        raise VoiceFailure("telegram_voice_private_family_authority_required", 403)
    if (not isinstance(message.get("message_id"), int) or isinstance(message["message_id"], bool)
            or message["message_id"] <= 0 or str(message["message_id"]) != parsed.get("provider_message_id")
            or not isinstance(message.get("date"), int) or isinstance(message["date"], bool)):
        raise VoiceFailure("telegram_voice_provider_identity_required", 403)
    stamp = datetime.fromtimestamp(message["date"], timezone.utc)
    if stamp.isoformat() != parsed.get("provider_timestamp"):
        raise VoiceFailure("telegram_voice_provider_identity_mismatch", 403)
    if not -30 <= (datetime.now(timezone.utc) - stamp).total_seconds() <= 6 * 3600:
        raise VoiceFailure("telegram_voice_provider_time_invalid", 403)
    return principal


def _binding(payload, parsed, principal):
    message = payload["message"]
    voice = message.get("voice")
    if not isinstance(voice, dict) or "audio" in message:
        raise VoiceFailure("telegram_voice_ogg_opus_required", 415)
    if any(key in message for key in ("forward_origin", "forward_from", "forward_from_chat",
                                     "forward_date", "forward_sender_name", "sender_chat")):
        raise VoiceFailure("telegram_voice_original_recording_required", 415)
    if any((payload.get("text"), message.get("text"), message.get("caption"),
            payload.get("transcript"), payload.get("voice_transcript"), message.get("transcript"))):
        raise VoiceFailure("telegram_voice_separate_text_required", 415)
    file_id = voice.get("file_id")
    if not isinstance(file_id, str) or not file_id or len(file_id) > 300:
        raise VoiceFailure("telegram_voice_file_identity_required", 400)
    mime = str(voice.get("mime_type") or "audio/ogg").split(";", 1)[0].lower()
    if mime not in {"audio/ogg", "application/ogg"}:
        raise VoiceFailure("telegram_voice_ogg_opus_required", 415)
    duration, size = voice.get("duration"), voice.get("file_size")
    if (not isinstance(duration, int) or isinstance(duration, bool)
            or not 1 <= duration <= MAX_VOICE_SECONDS):
        raise VoiceFailure("telegram_voice_duration_exceeded", 413)
    if size is not None and (not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_AUDIO_BYTES):
        raise VoiceFailure("telegram_voice_size_invalid", 413)
    return {"contract": "telegram_voice_reported_input_v1",
        "telegram_user_id": principal.telegram_user_id, "telegram_chat_id": principal.private_chat_id,
        "provider_message_id": parsed["provider_message_id"], "provider_timestamp": parsed["provider_timestamp"],
        "reply_to_message_id": str(parsed.get("reply_to_message_id") or ""),
        "binding_digest": principal.binding_digest, "language": principal.language,
        "file_id_sha256": hashlib.sha256(file_id.encode()).hexdigest(),
        "file_unique_id": str(voice.get("file_unique_id") or "")[:300],
        "declared_duration_seconds": duration, "declared_bytes": size, "mime_type": mime}


def _receipt_id(parsed):
    return "OOM-VOICE-" + _digest([parsed["telegram_user_id"], parsed["telegram_chat_id"], parsed["provider_message_id"]])


def _connect(source):
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    return connect_bounded_rootline_postgres(database_url=source.get("DATABASE_URL"), read_only=False)


def _append(cursor, identity, phase, payload, binding):
    cursor.execute("""insert into public.sam_live_stock_conversation_review_events(
        review_event_id,chatwoot_conversation_id,chatwoot_message_id,channel,source_agent,event_source,review_json)
        values(%s,%s,%s,'telegram','OOM_SAKKIE',%s,%s::jsonb)
        on conflict (review_event_id) do nothing returning review_event_id""",
        (identity + ":" + phase, binding["telegram_user_id"], binding["provider_message_id"],
         EVENT_SOURCE, json.dumps({"telegram_voice_input": payload}, ensure_ascii=False)))
    return cursor.fetchone() is not None


def _claim_input(identity, binding, source):
    """Commit one start event before any outbound call; no lock spans HTTP."""
    attempt = uuid.uuid4().hex
    with _connect(source) as db, db.cursor() as cursor:
        created = _append(cursor, identity, "start", {"binding": binding, "attempt": attempt,
            "started_at": datetime.now(timezone.utc).isoformat()}, binding)
        cursor.execute("""select review_event_id,review_json->'telegram_voice_input'
            from public.sam_live_stock_conversation_review_events
            where review_event_id=any(%s) and event_source=%s""",
            ([identity + ":start", identity + ":result"], EVENT_SOURCE))
        rows = dict(cursor.fetchall())
        start = rows.get(identity + ":start") or {}
        if start.get("binding") != binding:
            raise VoiceFailure("telegram_voice_replay_binding_conflict")
        result = rows.get(identity + ":result")
        if result:
            if result.get("binding") != binding or result.get("attempt") != start.get("attempt"):
                raise VoiceFailure("telegram_voice_replay_result_conflict")
            return "", result
        if not created:
            started = datetime.fromisoformat(str(start.get("started_at") or ""))
            if (datetime.now(timezone.utc) - started).total_seconds() < 60:
                raise VoiceFailure("telegram_voice_attempt_processing", 503)
            raise VoiceFailure("telegram_voice_attempt_incomplete")
    return attempt, None


def _retain_input(identity, binding, attempt, result, source):
    retained = {"binding": binding, "attempt": attempt, **result}
    with _connect(source) as db, db.cursor() as cursor:
        if not _append(cursor, identity, "result", retained, binding):
            raise VoiceFailure("telegram_voice_result_already_retained")
    return retained


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise VoiceFailure("telegram_voice_provider_redirect_denied", 502)


def _open_bounded(request, *, deadline, max_bytes, timeout=NETWORK_CALL_TIMEOUT_SECONDS):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise VoiceFailure("telegram_voice_network_deadline", 504)
    target = urllib.parse.urlsplit(request.full_url)
    if target.scheme != "https" or not target.hostname or target.username or target.password:
        raise VoiceFailure("telegram_voice_provider_url_invalid", 502)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    with opener.open(request, timeout=min(timeout, remaining)) as response:
        if response.geturl() != request.full_url or response.status != 200:
            raise VoiceFailure("telegram_voice_provider_response_invalid", 502)
        declared = response.headers.get("Content-Length")
        if declared is not None and (not declared.isdecimal() or int(declared) > max_bytes):
            raise VoiceFailure("telegram_voice_provider_body_too_large", 413)
        chunks, total = [], 0
        while True:
            if time.monotonic() >= deadline:
                raise VoiceFailure("telegram_voice_network_deadline", 504)
            chunk = (getattr(response, "read1", None) or response.read)(min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise VoiceFailure("telegram_voice_provider_body_too_large", 413)
            chunks.append(chunk)
        if declared is not None and int(declared) != total:
            raise VoiceFailure("telegram_voice_provider_body_truncated", 422)
        if time.monotonic() >= deadline:
            raise VoiceFailure("telegram_voice_network_deadline", 504)
        buffered = io.BytesIO(b"".join(chunks))
        buffered.headers = response.headers
        return buffered


def _download_and_transcribe(payload, principal, source, deadline):
    token = str(source.get("OOM_SAKKIE_TELEGRAM_BOT_TOKEN") or source.get("SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise VoiceFailure("telegram_voice_bot_token_not_configured", 503)
    voice = payload["message"]["voice"]
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/getFile",
        data=json.dumps({"file_id": voice["file_id"]}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with _open_bounded(request, deadline=deadline, max_bytes=MAX_JSON_BYTES) as response:
        metadata = json.loads(response.read().decode("utf-8"))
    file = metadata.get("result") if isinstance(metadata, dict) else None
    if not isinstance(metadata, dict) or metadata.get("ok") is not True or not isinstance(file, dict):
        raise VoiceFailure("telegram_voice_file_unavailable", 502)
    path = file.get("file_path")
    if (not isinstance(path, str) or not re.fullmatch(r"[A-Za-z0-9_./-]{1,512}", path)
            or any(part in {"", ".", ".."} for part in path.split("/"))):
        raise VoiceFailure("telegram_voice_file_path_invalid", 502)
    if file.get("file_id") and file["file_id"] != voice["file_id"]:
        raise VoiceFailure("telegram_voice_file_identity_mismatch", 502)
    if file.get("file_unique_id") and file["file_unique_id"] != voice.get("file_unique_id"):
        raise VoiceFailure("telegram_voice_file_identity_mismatch", 502)
    size = file.get("file_size")
    if size is not None and (not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_AUDIO_BYTES):
        raise VoiceFailure("telegram_voice_size_invalid", 413)
    request = urllib.request.Request(f"https://api.telegram.org/file/bot{token}/{path}")
    with _open_bounded(request, deadline=deadline, max_bytes=MAX_AUDIO_BYTES) as response:
        mime = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
        if mime not in {"audio/ogg", "application/ogg", "application/octet-stream", ""}:
            raise VoiceFailure("telegram_voice_ogg_opus_required", 415)
        audio = response.read()
    if not audio or any(value is not None and value != len(audio) for value in (size, voice.get("file_size"))):
        raise VoiceFailure("telegram_voice_download_size_mismatch", 422)
    framing = validate_ogg_opus_duration(audio)
    if abs(framing["duration_seconds"] - voice["duration"]) > 1:
        raise VoiceFailure("telegram_voice_duration_mismatch", 422)
    upload = io.BytesIO(audio)
    upload.mimetype = "audio/ogg"
    result, status = transcribe_oom_sakkie_voice_audio(upload, environ=source,
        language=principal.language, filename="telegram-voice.ogg",
        http_open=lambda req, timeout: _open_bounded(req, deadline=deadline, max_bytes=MAX_JSON_BYTES, timeout=timeout),
        timeout=NETWORK_CALL_TIMEOUT_SECONDS)
    if status != 200 or result.get("success") is not True:
        raise VoiceFailure(str(result.get("status") or "telegram_voice_transcription_failed"), status)
    text = str(result.get("text") or "").strip()
    if not text or len(text) > MAX_TRANSCRIPT_CHARS:
        raise VoiceFailure("telegram_voice_transcript_length_invalid", 422)
    return {"status": "transcribed", "text": text, "provenance": {**framing,
        "source_kind": "telegram_voice", "transcript_status": "transcribed",
        "language": principal.language, "model": result["backend_voice_stt"]["model"],
        "audio_sha256": hashlib.sha256(audio).hexdigest(), "audio_bytes": len(audio),
        "stores_audio": False, "reported_input_only": True}}


def _bounded_transcription(payload, principal, source, *, timeout=NETWORK_DEADLINE_SECONDS):
    """The worker can only prepare input; a timed-out worker can never dispatch."""
    if not _NETWORK_SLOTS.acquire(blocking=False):
        raise VoiceFailure("telegram_voice_capacity_unavailable", 503)
    results = queue.Queue(maxsize=1)
    deadline = time.monotonic() + timeout
    def prepare():
        try:
            try:
                result = (True, _download_and_transcribe(payload, principal, source, deadline))
            except Exception as exc:
                result = (False, exc)
            results.put_nowait(result)
        finally:
            _NETWORK_SLOTS.release()
    worker = threading.Thread(target=prepare, name="telegram-voice-input", daemon=True)
    try:
        worker.start()
    except Exception:
        _NETWORK_SLOTS.release()
        raise VoiceFailure("telegram_voice_worker_unavailable", 503) from None
    try:
        success, value = results.get(timeout=max(0, deadline - time.monotonic()))
    except queue.Empty:
        raise VoiceFailure("telegram_voice_network_deadline", 504) from None
    if time.monotonic() >= deadline:
        raise VoiceFailure("telegram_voice_network_deadline", 504)
    if not success:
        raise value
    return value


def voice_confirmation_required(parsed):
    language = str(parsed.get("output_language") or "en")
    return {"handled": True, "success": True, "status": "telegram_voice_preview_button_required",
        "answer": ("Gebruik die bevestiging op die presiese voorskou. As daar geen voorskou is nie, tik die opdrag vir hersiening. 'n Stemnota gee nie uitvoeringstoestemming nie."
                   if language == "af" else "Use the confirmation on the exact preview. If there is no preview, type the command for review. A voice note does not authorize execution."),
        "writes_farm_data": False, "protected_actions_performed": False,
        "hardware_commands": 0, "provider_control_calls": 0}, 200


def _failure(error, language):
    if str(error.status or "").startswith("farm_model_"):
        from modules.oom_sakkie.service import model_budget_denial_result
        return model_budget_denial_result(error.status, language, voice=True), error.http_status
    if error.status == "telegram_voice_attempt_processing":
        return {"handled": True, "success": False, "status": error.status,
                "suppress_family_delivery": True, "writes_farm_data": False}, error.http_status
    note = ("Ek kon hierdie stemnota nie veilig gebruik nie. Stuur 'n nuwe Telegram-stemnota van hoogstens 60 sekondes, of tik die feite. Niks is aangeteken nie."
            if language == "af" else "I could not safely use this voice note. Send a new Telegram voice note of up to 60 seconds, or type the facts. Nothing was recorded.")
    return {"handled": True, "success": False, "status": error.status, "answer": note,
            "writes_farm_data": False, "protected_actions_performed": False}, error.http_status


def prepare_telegram_voice_input(payload, parsed, *, environ=None):
    """Return (enriched input, None) or (None, ingress response).

    Called after either existing ingress credential gate. The durable transcript
    precedes semantic interpretation; successful input resumes that ingress's
    normal dialogue, context, preview, delivery and replay handling.
    """
    source = environ if environ is not None else os.environ
    try:
        principal = _authorize_native(payload, parsed, source)
    except (VoiceFailure, TypeError, ValueError, OverflowError):
        return None, ({"success": False, "status": "telegram_voice_private_family_authority_required",
                       "writes": False, "sends_telegram": False}, 403)
    parsed = {**parsed, "output_language": principal.language}
    identity = _receipt_id(parsed)
    try:
        policy = backend_voice_stt_policy(source)
        if not policy["enabled"]:
            raise VoiceFailure("telegram_voice_transcription_disabled", 503)
        binding = _binding(payload, parsed, principal)
        attempt, retained = _claim_input(identity, binding, source)
        if retained is None:
            try:
                prepared = _bounded_transcription(payload, principal, source)
            except Exception as exc:
                error = exc if isinstance(exc, VoiceFailure) else VoiceFailure("telegram_voice_transcription_unavailable", 502)
                prepared = {"status": "failed", "failure_status": error.status, "http_status": error.http_status}
            retained = _retain_input(identity, binding, attempt, prepared, source)
        if retained.get("status") != "transcribed":
            raise VoiceFailure(retained.get("failure_status") or "telegram_voice_transcription_unavailable",
                               int(retained.get("http_status") or 502))
        parsed = {**parsed, "text": retained["text"],
            "input_provenance": {**retained["provenance"], "receipt_id": identity,
                                 "provider_message_id": parsed["provider_message_id"],
                                 "provider_timestamp": parsed["provider_timestamp"]}}
        return parsed, None
    except VoiceFailure as exc:
        result, status = _failure(exc, principal.language)
    except Exception:
        result, status = _failure(VoiceFailure("telegram_voice_input_retention_unavailable", 503), principal.language)
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    delivery = ({"success": True, "telegram_sends": 0, "telegram_edits": 0}
                if result.get("suppress_owner_delivery") or result.get("suppress_family_delivery") else
                deliver_family_result(parsed, result, specialist="OOM_SAKKIE",
                    mission_id=str(result.get("mission_id") or identity),
                    card_mission_id=str(result.get("card_mission_id") or result.get("mission_id") or identity)))
    return None, ({"success": result.get("success") is True, "status": result.get("status"),
        "message": result, "answer": result.get("answer", ""), "delivery": delivery,
        "family_role": principal.role.value, "language": principal.language,
        "input_provenance": parsed.get("input_provenance", {}),
        "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0,
        "writes": False}, status if delivery.get("success") else 503)
