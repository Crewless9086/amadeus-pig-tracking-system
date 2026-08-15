"""Default-disabled, bounded owner Telegram media intake for BEACON.

Object storage and PostgreSQL are deliberately treated as separate systems.
Every stage is append-only and any uncertain cross-service outcome is exposed
as pending/quarantined for owner reconciliation.
"""

import hashlib
import hmac
import io
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from services.database_service import DATABASE_URL_ENV
from modules.beacon.media_library import (
    RAW_INTAKE_BUCKET,
    SUPABASE_SERVICE_ROLE_KEY_ENV,
    SUPABASE_URL_ENV,
    upload_bytes_to_supabase_storage,
)


ENABLED_ENV = "BEACON_TELEGRAM_MEDIA_INTAKE_ENABLED"
ALLOWED_CHAT_IDS_ENV = "BEACON_TELEGRAM_MEDIA_ALLOWED_CHAT_IDS"
BOT_TOKEN_ENV = "OOM_SAKKIE_TELEGRAM_BOT_TOKEN"
ALLOWED_USER_IDS_ENV = "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS"
REQUEST_NOT_BEFORE_ENV = "BEACON_TELEGRAM_MEDIA_REQUEST_NOT_BEFORE_UTC"
RETIRED_SHA256_ENV = "BEACON_TELEGRAM_MEDIA_RETIRED_SHA256"
RECOVERY_CONTEXT_TOKEN_ENV = "BEACON_TELEGRAM_MEDIA_RECOVERY_CONTEXT_TOKEN"
SIGNING_SECRET_ENVS = ("OWNER_SESSION_SECRET", "SECRET_KEY")
CONTRACT_VERSION = "beacon_media_intake_v1"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_THUMBNAIL_BYTES = 1024 * 1024
MAX_IMAGE_DIMENSION = 12000
MAX_IMAGE_PIXELS = 40_000_000
STREAM_CHUNK_BYTES = 64 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 20
STORAGE_TIMEOUT_SECONDS = 20
THUMBNAIL_MAX_EDGE = 512
THUMBNAIL_TOKEN_TTL_SECONDS = 120
SUPPORTED_MIME = {"image/jpeg": "JPEG", "image/png": "PNG"}
AUTHORITY = {
    "library_accept": False,
    "public_use_approved": False,
    "publish": False,
    "meta_call": False,
    "upload_to_meta": False,
    "schedule": False,
    "send_customer_message": False,
    "advertise": False,
    "boost": False,
    "spend": False,
    "business_data_mutation": False,
}


def media_intake_policy(environ=None):
    source = environ if environ is not None else os.environ
    chat_ids = _csv(source.get(ALLOWED_CHAT_IDS_ENV))
    user_ids = _csv(source.get(ALLOWED_USER_IDS_ENV))
    stable_secret = _secret(source)
    explicitly_enabled = _truthy(source.get(ENABLED_ENV))
    request_not_before = _utc_datetime(source.get(REQUEST_NOT_BEFORE_ENV))
    retired_hashes = _sha256_set(source.get(RETIRED_SHA256_ENV))
    bot_configured = bool(str(source.get(BOT_TOKEN_ENV) or "").strip())
    database_configured = bool(str(source.get(DATABASE_URL_ENV) or "").strip())
    storage_configured = bool(
        str(source.get(SUPABASE_URL_ENV) or "").strip()
        and str(source.get(SUPABASE_SERVICE_ROLE_KEY_ENV) or "").strip()
    )
    enabled = bool(
        explicitly_enabled and request_not_before and retired_hashes
        and chat_ids and user_ids and stable_secret
        and bot_configured and database_configured and storage_configured
    )
    return {
        "success": True,
        "mode": CONTRACT_VERSION,
        "enabled": enabled,
        "explicitly_enabled": explicitly_enabled,
        "fresh_request_bound": bool(request_not_before),
        "retired_hash_registry_configured": bool(retired_hashes),
        "allowed_private_chat_configured": bool(chat_ids),
        "allowed_private_chat_count": len(chat_ids),
        "allowed_owner_user_configured": bool(user_ids),
        "stable_identity_secret_configured": bool(stable_secret),
        "bot_token_configured": bot_configured,
        "database_configured": database_configured,
        "private_storage_configured": storage_configured,
        "private_bucket": RAW_INTAKE_BUCKET,
        "supported_mime_types": sorted(SUPPORTED_MIME),
        "photo_max_bytes": MAX_IMAGE_BYTES,
        "photo_max_dimension": MAX_IMAGE_DIMENSION,
        "photo_max_pixels": MAX_IMAGE_PIXELS,
        "video_state": "unsupported_until_bounded_resumable_upload",
        "album_completion": "explicit_owner_completion_required",
        "automatic_retry": False,
        "gateway_active": enabled,
        **AUTHORITY,
    }


def telegram_media_envelope(payload):
    payload = payload if isinstance(payload, dict) else {}
    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    photos = message.get("photo") if isinstance(message.get("photo"), list) else []
    video = message.get("video") if isinstance(message.get("video"), dict) else None
    if not photos and not video:
        return None
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    if photos:
        candidates = [row for row in photos if isinstance(row, dict) and row.get("file_id")]
        media = max(
            candidates,
            key=lambda row: (
                _integer(row.get("file_size")),
                _integer(row.get("width")) * _integer(row.get("height")),
            ),
            default={},
        )
        kind = "photo"
    else:
        media, kind = video or {}, "video"
    return {
        "update_id": _integer(payload.get("update_id"), allow_zero=True),
        "message_id": _integer(message.get("message_id"), allow_zero=True),
        "chat_id": str(chat.get("id") or "").strip(),
        "chat_type": str(chat.get("type") or "").strip(),
        "owner_user_id": str(sender.get("id") or "").strip(),
        "media_group_id": str(message.get("media_group_id") or "").strip()[:160],
        "file_id": str(media.get("file_id") or "").strip()[:300],
        "file_unique_id": str(media.get("file_unique_id") or "").strip()[:300],
        "declared_mime_type": str(media.get("mime_type") or ("image/jpeg" if kind == "photo" else "")).strip().lower()[:120],
        "original_filename": _filename(media.get("file_name") or f"telegram-{message.get('message_id') or 'media'}.jpg"),
        "media_kind": kind,
        "owner_explanation": str(message.get("caption") or "").strip()[:2000],
        "source_message_at": _telegram_time(message.get("date")),
        "capture_time": None,
        "capture_time_state": "unknown",
        "forwarded": any(key in message for key in (
            "forward_origin", "forward_from", "forward_from_chat", "forward_date",
        )),
    }


def handle_telegram_media_intake(
    payload,
    *,
    environ=None,
    database_url=None,
    fetcher=None,
    storage=None,
    receipt_sender=None,
):
    source = environ if environ is not None else os.environ
    policy = media_intake_policy(source)
    envelope = telegram_media_envelope(payload)
    if envelope is None:
        return _result(False, "telegram_media_required", policy), 400
    if not policy["enabled"]:
        return _result(False, "beacon_telegram_media_intake_disabled", policy), 503
    if not policy["stable_identity_secret_configured"]:
        return _result(False, "stable_identity_secret_required", policy), 503
    if envelope["chat_type"] != "private" or envelope["forwarded"]:
        return _result(False, "owner_private_original_media_required", policy), 403
    if envelope["chat_id"] not in _csv(source.get(ALLOWED_CHAT_IDS_ENV)):
        return _result(False, "telegram_private_chat_not_allowed", policy), 403
    if envelope["owner_user_id"] not in _csv(source.get(ALLOWED_USER_IDS_ENV)):
        return _result(False, "telegram_owner_user_not_allowed", policy), 403
    recovery_requested = isinstance(payload.get("beacon_media_recovery"), dict)
    recovery_context = _validated_recovery_context(payload, envelope, source)
    if recovery_requested and not recovery_context:
        return _result(False, "beacon_media_recovery_context_invalid", policy), 403
    if recovery_context:
        envelope["owner_context_supplement"] = recovery_context
    if not envelope["update_id"] or not envelope["message_id"] or not envelope["owner_user_id"]:
        return _result(False, "telegram_source_identity_incomplete", policy), 400
    if not envelope["source_message_at"]:
        return _result(False, "telegram_source_message_time_required", policy), 400
    request_not_before = _utc_datetime(source.get(REQUEST_NOT_BEFORE_ENV))
    source_message_at = _utc_datetime(envelope["source_message_at"])
    if not request_not_before or not source_message_at or source_message_at < request_not_before:
        return _result(False, "telegram_media_predates_fresh_owner_request", policy), 409
    if envelope["media_kind"] == "video":
        receipt = receipt_sender(
            envelope["chat_id"],
            "BEACON could not receive this video. Video intake remains unsupported "
            "until the bounded resumable-upload phase; no file was downloaded and "
            "no library, public-use, or publication approval was granted.",
        ) if receipt_sender else None
        return {
            **_result(False, "video_intake_requires_bounded_resumable_phase", policy),
            "receipt_sent": bool(receipt and receipt.get("success") is True),
        }, 415

    identity = _identities(envelope, source)
    store = IntakeStore(database_url)
    source_state, source_status = store.source_status(envelope, identity)
    if source_status >= 400 or source_state.get("replayed"):
        result = {
            **_result(source_status < 400, source_state["status"], policy),
            **source_state,
        }
        if envelope["media_group_id"] and source_state.get("replayed"):
            progress, progress_status = (store.album_progress(identity) if hasattr(store, "album_progress")
                else ({"stored_count": 1, "canonical_digest": _canonical_sha(identity)}, 200))
            progress.pop("status", None)
            progress["album_progress_verified"] = hasattr(store, "album_progress") and progress_status < 400
            result.update(_album_receipt(identity))
            result.update(progress)
        return result, source_status

    fetch_fn = fetcher or _download_telegram_file
    storage_adapter = storage or SupabasePrivateStorage(source)
    temp_path = None
    storage_path = ""
    uploaded_paths = []
    try:
        streamed = fetch_fn(envelope, source)
        if isinstance(streamed, tuple) and len(streamed) == 2:
            temp_path, download_meta = streamed
        else:
            raise IntakeFailure("telegram_download_contract_invalid", 502)
        validated = _validate_streamed_image(
            temp_path, envelope["declared_mime_type"], download_meta
        )
        existing = store.existing_binary(validated["content_sha256"])
        if (
            validated["content_sha256"] in _sha256_set(source.get(RETIRED_SHA256_ENV))
            or existing
            or store.existing_asset_hash(validated["content_sha256"])
        ):
            raise IntakeFailure("retired_or_previously_ingested_photo_withheld", 409)

        prepared, prepare_status = store.prepare(envelope, identity)
        if prepare_status >= 400 or prepared.get("replayed"):
            return {
                **_result(prepare_status < 400, prepared["status"], policy),
                **prepared,
            }, prepare_status

        if not store.event(identity, "stream_validated", validated):
            raise IntakeFailure("stream_validation_evidence_failed", 500)
        if not existing:
            binary_id = "BEACON-BINARY-" + validated["content_sha256"][:24].upper()
            extension = ".jpg" if validated["observed_mime_type"] == "image/jpeg" else ".png"
            storage_path = f"telegram/{validated['content_sha256'][:2]}/{validated['content_sha256']}{extension}"
            thumbnail_path = f"telegram-thumbnails/{validated['content_sha256'][:2]}/{validated['content_sha256']}.jpg"
            original_bytes = Path(temp_path).read_bytes()
            thumbnail_bytes = _thumbnail_bytes(temp_path)
            thumbnail_sha = hashlib.sha256(thumbnail_bytes).hexdigest()
            uploaded = storage_adapter.put(storage_path, original_bytes, validated["observed_mime_type"])
            if uploaded.get("success") is not True:
                raise IntakeFailure("private_storage_upload_failed", 502)
            uploaded_paths.append(storage_path)
            if not store.event(identity, "storage_uploaded", {"storage_path": storage_path}):
                raise IntakeFailure("storage_upload_evidence_failed", 500)
            thumb_uploaded = storage_adapter.put(thumbnail_path, thumbnail_bytes, "image/jpeg")
            if thumb_uploaded.get("success") is not True:
                raise IntakeFailure("private_thumbnail_upload_failed", 502)
            uploaded_paths.append(thumbnail_path)
            readback = storage_adapter.get(storage_path, MAX_IMAGE_BYTES)
            if hashlib.sha256(readback).hexdigest() != validated["content_sha256"]:
                raise IntakeFailure("storage_readback_hash_mismatch", 409)
            if not store.event(identity, "storage_verified", {
                "content_sha256": validated["content_sha256"],
            }):
                raise IntakeFailure("storage_verification_evidence_failed", 500)
        classification = {
            "classification": "private_farm_photo",
            "media_type": "image",
            "mime_type": validated["observed_mime_type"],
            "orientation": (
                "landscape" if validated["width"] > validated["height"]
                else "portrait" if validated["height"] > validated["width"]
                else "square"
            ),
            "width": validated["width"],
            "height": validated["height"],
            "owner_context": envelope["owner_explanation"],
            "public_use_approved": False,
        }
        finalized, finalize_status = store.finalize(
            envelope,
            identity,
            {
                **validated,
                "binary_asset_id": binary_id,
                "storage_path": storage_path,
                "thumbnail_storage_path": thumbnail_path,
                "thumbnail_sha256": thumbnail_sha,
                "classification": classification,
            },
        )
        if finalize_status >= 400:
            cleanup = (
                storage_adapter.delete_many(uploaded_paths)
                if uploaded_paths else {"success": True}
            )
            store.event(identity, "quarantined", {
                "reason": "metadata_finalization_failed",
                "compensating_cleanup_complete": cleanup.get("success") is True,
            })
            return {
                **_result(False, "metadata_finalization_failed", policy),
                "reconciliation_required": cleanup.get("success") is not True,
            }, 500
        receipt = None
        if envelope["media_group_id"] and receipt_sender:
            completion = store.offer_album_completion(identity)
            if completion.get("created_count"):
                receipt = receipt_sender(
                    envelope["chat_id"],
                    "BEACON started this private album. Use Finish Album when every "
                    "photo has been sent. No public-use or publication "
                    "approval was granted.",
                )
        elif receipt_sender:
            receipt = receipt_sender(
                envelope["chat_id"],
                "BEACON received 1 photo. Stored privately; 0 failed or quarantined. "
                "Review status: pending Library Accept. No public-use or publication approval was granted.",
            )
        return {
            **_result(True, finalized["status"], policy),
            **finalized,
            "receipt_sent": bool(receipt and receipt.get("success") is True),
            "album_state": (
                "awaiting_explicit_owner_completion"
                if envelope["media_group_id"] else "single_item_complete"
            ),
            **(_album_receipt(identity) if envelope["media_group_id"] else {}),
            **((_progress_payload(store, identity))
               if envelope["media_group_id"] else {}),
        }, 201
    except IntakeFailure as exc:
        cleanup = (
            storage_adapter.delete_many(uploaded_paths)
            if uploaded_paths else {"success": True}
        )
        event_type = "failed" if cleanup.get("success") is True else "quarantined"
        store.event(identity, event_type, {
            "reason": exc.status,
            "compensating_cleanup_complete": cleanup.get("success") is True,
        })
        return {
            **_result(False, exc.status, policy),
            "reconciliation_required": cleanup.get("success") is not True,
            "failure_detail": {"classification": exc.status},
        }, exc.http_status
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass


def _progress_payload(store, identity):
    if not hasattr(store, "album_progress"):
        return {"stored_count": 1, "canonical_digest": _canonical_sha(identity),
            "album_progress_verified": False}
    progress, status = store.album_progress(identity)
    progress.pop("status", None)
    return {**progress, "album_progress_verified": status < 400}


def complete_telegram_album(payload, *, environ=None, database_url=None, receipt_sender=None):
    source = environ if environ is not None else os.environ
    policy = media_intake_policy(source)
    if not policy["enabled"]:
        return _result(False, "beacon_telegram_media_intake_disabled", policy), 503
    chat_id = str(payload.get("chat_id") or "").strip()
    user_id = str(payload.get("owner_user_id") or "").strip()
    completion_code = str(payload.get("completion_code") or "").strip()[:96]
    if (
        chat_id not in _csv(source.get(ALLOWED_CHAT_IDS_ENV))
        or user_id not in _csv(source.get(ALLOWED_USER_IDS_ENV))
    ):
        return _result(False, "telegram_private_chat_not_allowed", policy), 403
    if not completion_code:
        return _result(False, "album_completion_code_required", policy), 400
    identity = {
        "chat_hmac": _keyed(source, "chat", chat_id),
        "owner_principal": f"telegram-owner:{_keyed(source, 'owner', user_id)}",
    }
    completed, status = IntakeStore(database_url).complete_album_by_code(
        identity, completion_code
    )
    if status < 400 and completed.get("created_count") and receipt_sender:
        receipt_sender(
            chat_id,
            f"BEACON received {completed['received_count']} album items. "
            f"{completed['attention_count']} failed or quarantined. Review status: pending Library Accept. "
            "No public-use or publication approval was granted.",
        )
    return {**_result(status < 400, completed["status"], policy), **completed}, status


def complete_claimed_telegram_album(preview, *, owner_user_id, private_chat_id,
                                    environ=None, database_url=None):
    """Complete an album only while the button's canonical snapshot is current."""
    source = environ if environ is not None else os.environ
    identity={"group_id":str((preview or {}).get("intake_group_id") or ""),
        "chat_hmac":_keyed(source,"chat",private_chat_id),
        "owner_principal":f"telegram-owner:{_keyed(source,'owner',owner_user_id)}"}
    return IntakeStore(database_url).complete_album_claimed(
        identity, str((preview or {}).get("canonical_digest") or ""))


def list_media_intakes(*, database_url=None, limit=50, environ=None):
    result, status = IntakeStore(database_url).list(limit)
    if status < 400:
        for item in result.get("items", []):
            binary_id = item.get("binary_asset_id")
            available = item.pop("thumbnail_available", False)
            token = _thumbnail_token(binary_id, environ) if binary_id and available else None
            item["thumbnail_url"] = (
                f"/api/oom-sakkie/beacon/media-intakes/{urllib_parse.quote(binary_id, safe='')}/thumbnail"
                f"?expires={token['expires']}&token={token['token']}"
                if token else ""
            )
    return result, status


def read_private_thumbnail(
    binary_asset_id, *, token="", expires="", database_url=None, environ=None
):
    if not _thumbnail_token_valid(binary_asset_id, token, expires, environ):
        return {
            "success": False,
            "status": "private_thumbnail_authorization_invalid",
            **AUTHORITY,
        }, 403
    row, status = IntakeStore(database_url).thumbnail(binary_asset_id)
    if status >= 400:
        return row, status
    try:
        body = SupabasePrivateStorage(environ).get(row["thumbnail_storage_path"], 1024 * 1024)
    except IntakeFailure as exc:
        return {"success": False, "status": exc.status, **AUTHORITY}, exc.http_status
    return {
        "success": True,
        "status": "private_thumbnail_ready",
        "body": body,
        "content_type": "image/jpeg",
        "cache_control": "private, max-age=60, no-store",
        **AUTHORITY,
    }, 200


def record_media_review(binary_asset_id, decision, owner_principal, *, database_url=None):
    return IntakeStore(database_url).review(binary_asset_id, decision, owner_principal)


def record_media_group_review(intake_group_id, decision, owner_principal, *, database_url=None):
    return IntakeStore(database_url).review_group(
        intake_group_id, decision, owner_principal
    )


class IntakeStore:
    def __init__(self, database_url=None):
        self.database_url = str(
            database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")
        ).strip()

    def _connect(self):
        if not self.database_url:
            raise IntakeFailure("media_intake_persistence_unavailable", 503)
        try:
            import psycopg
        except ImportError as exc:
            raise IntakeFailure("media_intake_postgres_dependency_missing", 500) from exc
        return psycopg.connect(self.database_url, connect_timeout=10)

    def source_status(self, envelope, identity):
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """select intake_item_id,source_identity_sha256,telegram_file_id,
                              coalesce(telegram_file_unique_id,'')
                       from public.beacon_media_intake_items
                       where intake_item_id=%s or source_identity_sha256=%s
                          or (private_chat_identity_hmac=%s and telegram_update_id=%s)
                          or (private_chat_identity_hmac=%s and telegram_message_id=%s)
                       limit 1""",
                    (
                        identity["item_id"], identity["source_sha256"],
                        identity["chat_hmac"], envelope["update_id"],
                        identity["chat_hmac"], envelope["message_id"],
                    ),
                )
                prior = cursor.fetchone()
        except Exception as exc:
            return {
                "status": "media_intake_source_check_failed",
                "replayed": False,
                "error_type": exc.__class__.__name__,
            }, 500
        if not prior:
            return {"status": "media_intake_source_is_fresh", "replayed": False}, 200
        if prior == (
            identity["item_id"], identity["source_sha256"],
            envelope["file_id"], envelope["file_unique_id"],
        ):
            return {"status": "exact_intake_replay_withheld", "replayed": True}, 200
        return {"status": "intake_identity_conflict", "replayed": False}, 409

    def prepare(self, envelope, identity):
        evidence = _canonical_sha({
            "group": identity["group_id"], "item": identity["item_id"],
            "source": identity["source_sha256"], "file_unique_id": envelope["file_unique_id"],
        })
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",
                    ("beacon-album:"+identity["group_id"],))
                cursor.execute("""select 1 from public.beacon_media_intake_events
                    where intake_group_id=%s and event_type='album_completed' limit 1""",
                    (identity["group_id"],))
                if cursor.fetchone():
                    return {"status":"album_already_completed","replayed":False},409
                cursor.execute(
                    """select intake_item_id,source_identity_sha256,telegram_file_id,
                              coalesce(telegram_file_unique_id,'')
                       from public.beacon_media_intake_items
                       where intake_item_id=%s or source_identity_sha256=%s
                          or (private_chat_identity_hmac=%s and telegram_update_id=%s)
                          or (private_chat_identity_hmac=%s and telegram_message_id=%s)
                       limit 1""",
                    (
                        identity["item_id"], identity["source_sha256"],
                        identity["chat_hmac"], envelope["update_id"],
                        identity["chat_hmac"], envelope["message_id"],
                    ),
                )
                prior = cursor.fetchone()
                if prior:
                    if prior == (
                        identity["item_id"], identity["source_sha256"],
                        envelope["file_id"], envelope["file_unique_id"],
                    ):
                        return {"status": "exact_intake_replay_withheld", "replayed": True}, 200
                    return {"status": "intake_identity_conflict", "replayed": False}, 409
                cursor.execute(
                    """insert into public.beacon_media_intake_groups
                       (intake_group_id,contract_version,source_channel,owner_principal,
                        private_chat_identity_hmac,telegram_update_id,telegram_message_id,
                        telegram_media_group_id,owner_explanation,source_message_at,
                        capture_time,capture_time_state,completion_mode,
                        completion_code_sha256)
                       values (%s,%s,'telegram_owner_private',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       on conflict (intake_group_id) do nothing""",
                    (
                        identity["group_id"], CONTRACT_VERSION, identity["owner_principal"],
                        identity["chat_hmac"], envelope["update_id"], envelope["message_id"],
                        envelope["media_group_id"] or None, envelope["owner_explanation"],
                        envelope["source_message_at"], envelope["capture_time"],
                        envelope["capture_time_state"],
                        "explicit_owner_album_completion" if envelope["media_group_id"] else "single_item",
                        _canonical_sha(_album_completion_code(identity["group_id"]))
                        if envelope["media_group_id"] else None,
                    ),
                )
                cursor.execute(
                    """insert into public.beacon_media_intake_items
                       (intake_item_id,intake_group_id,source_identity_sha256,
                        private_chat_identity_hmac,telegram_update_id,telegram_message_id,telegram_file_id,
                        telegram_file_unique_id,original_filename,declared_mime_type,
                        media_kind,source_order_key,capture_time,capture_time_state)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        identity["item_id"], identity["group_id"], identity["source_sha256"],
                        identity["chat_hmac"], envelope["update_id"], envelope["message_id"], envelope["file_id"],
                        envelope["file_unique_id"] or None, envelope["original_filename"],
                        envelope["declared_mime_type"], envelope["media_kind"],
                        envelope["message_id"], envelope["capture_time"],
                        envelope["capture_time_state"],
                    ),
                )
                self._event_cursor(cursor, identity, "pending", {"source_evidence_sha256": evidence})
                if envelope["owner_explanation"]:
                    self._event_cursor(cursor, identity, "pending", {
                        "owner_context": envelope["owner_explanation"],
                        "provider_message_id": envelope["message_id"],
                        "provenance": "telegram_album_caption",
                    })
                supplement = envelope.get("owner_context_supplement")
                if supplement:
                    self._event_cursor(cursor, identity, "pending", {
                        "owner_context": supplement,
                        "provider_message_id": envelope["message_id"],
                        "provenance": "owner_directed_incident_recovery",
                    })
            return {"status": "media_intake_pending_created", "replayed": False}, 201
        except IntakeFailure:
            raise
        except Exception as exc:
            return {"status": "media_intake_prepare_failed", "replayed": False, "error_type": exc.__class__.__name__}, 500

    def event(self, identity, event_type, evidence):
        if not self.database_url:
            return False
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                self._event_cursor(cursor, identity, event_type, evidence)
            return True
        except Exception:
            return False

    def existing_binary(self, content_sha256):
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """select binary_asset_id,observed_mime_type,byte_size,width,height,
                              storage_path,thumbnail_storage_path,thumbnail_sha256
                       from public.beacon_media_binaries where content_sha256=%s""",
                    (content_sha256,),
                )
                row = cursor.fetchone()
        except Exception:
            return None
        if not row:
            return None
        return {
            "binary_asset_id": row[0], "observed_mime_type": row[1],
            "byte_size": row[2], "width": row[3], "height": row[4],
            "storage_path": row[5], "thumbnail_storage_path": row[6],
            "thumbnail_sha256": row[7],
        }

    def existing_asset_hash(self, content_sha256):
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """select 1 from public.beacon_media_assets
                       where content_sha256=%s limit 1""",
                    (content_sha256,),
                )
                return cursor.fetchone() is not None
        except Exception:
            return True

    def _event_cursor(self, cursor, identity, event_type, evidence):
        evidence_sha = _canonical_sha(evidence)
        event_id = _stable_id(
            "BEACON-INTAKE-EVENT",
            _canonical_sha([identity["item_id"], event_type, evidence_sha]),
        )
        cursor.execute(
            """insert into public.beacon_media_intake_events
               (event_id,intake_group_id,intake_item_id,event_type,evidence_sha256,evidence_json)
               values (%s,%s,%s,%s,%s,%s::jsonb)
               on conflict (event_id) do nothing""",
            (
                event_id, identity["group_id"], identity["item_id"], event_type,
                evidence_sha, json.dumps(evidence, sort_keys=True),
            ),
        )

    def finalize(self, envelope, identity, media):
        asset_id = "BEACON-ASSET-" + media["content_sha256"][:18].upper()
        link_id = _stable_id("BEACON-SOURCE-LINK", identity["item_id"])
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",
                    ("beacon-album:"+identity["group_id"],))
                cursor.execute("""select 1 from public.beacon_media_intake_events
                    where intake_group_id=%s and event_type='album_completed' limit 1""",
                    (identity["group_id"],))
                if cursor.fetchone():
                    return {"status":"album_already_completed"},409
                cursor.execute(
                    """insert into public.beacon_media_binaries
                       (binary_asset_id,content_sha256,observed_mime_type,byte_size,width,height,
                        storage_bucket,storage_path,storage_readback_sha256,
                        thumbnail_storage_path,thumbnail_sha256,validation_version)
                       values (%s,%s,%s,%s,%s,%s,'beacon-raw-intake',%s,%s,%s,%s,'image-v1')
                       on conflict (content_sha256) do nothing""",
                    (
                        media["binary_asset_id"], media["content_sha256"],
                        media["observed_mime_type"], media["byte_size"], media["width"],
                        media["height"], media["storage_path"], media["content_sha256"],
                        media["thumbnail_storage_path"], media["thumbnail_sha256"],
                    ),
                )
                cursor.execute(
                    """select binary_asset_id,storage_path from public.beacon_media_binaries
                       where content_sha256=%s""",
                    (media["content_sha256"],),
                )
                binary_id, canonical_path = cursor.fetchone()
                cursor.execute(
                    """insert into public.beacon_media_assets
                       (asset_id,storage_bucket,storage_path,original_filename,media_type,mime_type,
                        file_size_bytes,content_sha256,content_hash_provenance,source,source_reference,
                        uploader_label,title,description,approval_status,public_use_approved,created_by)
                       values (%s,'beacon-raw-intake',%s,%s,'image',%s,%s,%s,
                               'server_stream_and_storage_readback_verified','telegram_upload',%s,
                               'owner_telegram','Telegram owner media','', 'needs_review',false,
                               'beacon_media_intake_v1')
                       on conflict (asset_id) do nothing""",
                    (
                        asset_id, canonical_path, envelope["original_filename"],
                        media["observed_mime_type"], media["byte_size"], media["content_sha256"],
                        identity["source_sha256"],
                    ),
                )
                cursor.execute(
                    """select intake_item_id from public.beacon_media_source_links
                       where binary_asset_id=%s order by linked_at limit 1""",
                    (binary_id,),
                )
                duplicate = cursor.fetchone()
                cursor.execute(
                    """insert into public.beacon_media_source_links
                       (source_link_id,intake_item_id,binary_asset_id,beacon_asset_id,
                        exact_duplicate_of_item_id)
                       values (%s,%s,%s,%s,%s)""",
                    (
                        link_id, identity["item_id"], binary_id, asset_id,
                        duplicate[0] if duplicate else None,
                    ),
                )
                self._event_cursor(cursor, identity, "stored", {
                    "binary_asset_id": binary_id,
                    "asset_id": asset_id,
                    "content_sha256": media["content_sha256"],
                    "exact_duplicate": bool(duplicate),
                })
                classification = media.get("classification") or {
                    "classification": "private_farm_photo",
                    "media_type": "image",
                    "mime_type": media["observed_mime_type"],
                    "orientation": (
                        "landscape" if media["width"] > media["height"]
                        else "portrait" if media["height"] > media["width"]
                        else "square"
                    ),
                    "width": media["width"],
                    "height": media["height"],
                    "owner_context": envelope.get("owner_explanation", ""),
                    "public_use_approved": False,
                }
                observation_id = _stable_id(
                    "BEACON-UNDERSTANDING",
                    _canonical_sha([binary_id, "server_private_classification_v1"]),
                )
                cursor.execute(
                    """insert into public.beacon_media_understanding_events
                       (observation_event_id,binary_asset_id,asset_sha256,source_type,
                        observer_identity,observer_version,confidence_state,
                        observation_json,observed_at)
                       values (%s,%s,%s,'model_observation','beacon-server',
                               'server_private_classification_v1','evidence_supported',
                               %s::jsonb,now())
                       on conflict (observation_event_id) do nothing""",
                    (
                        observation_id, binary_id, media["content_sha256"],
                        json.dumps(classification, sort_keys=True),
                    ),
                )
                if not envelope["media_group_id"]:
                    cursor.execute(
                        """insert into public.beacon_media_intake_album_members
                           (intake_group_id,intake_item_id,album_position)
                           values (%s,%s,1)""",
                        (identity["group_id"], identity["item_id"]),
                    )
            return {
                "status": "media_intake_stored_private_review_pending",
                "created_count": 1,
                "intake_group_id": identity["group_id"],
                "intake_item_id": identity["item_id"],
                "binary_asset_id": binary_id,
                "beacon_asset_id": asset_id,
                "exact_duplicate": bool(duplicate),
                "classification": classification,
                "observation_event_id": observation_id,
                **AUTHORITY,
            }, 201
        except Exception as exc:
            return {
                "status": "media_intake_finalize_failed",
                "error_type": exc.__class__.__name__,
                "error_constraint": str(getattr(getattr(exc, "diag", None), "constraint_name", "") or "")[:120],
            }, 500

    def complete_album(self, identity):
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """select i.intake_item_id
                       from public.beacon_media_intake_items i
                       join public.beacon_media_source_links l using (intake_item_id)
                       where i.intake_group_id=%s order by i.source_order_key""",
                    (identity["group_id"],),
                )
                items = [row[0] for row in cursor.fetchall()]
                if not items:
                    return {"status": "album_has_no_durable_items"}, 409
                cursor.execute(
                    """select count(*) from public.beacon_media_intake_items
                       where intake_group_id=%s""",
                    (identity["group_id"],),
                )
                received = cursor.fetchone()[0]
                if received != len(items):
                    return {"status": "album_contains_unresolved_items"}, 409
                for position, item_id in enumerate(items, 1):
                    cursor.execute(
                        """insert into public.beacon_media_intake_album_members
                           (intake_group_id,intake_item_id,album_position)
                           values (%s,%s,%s) on conflict do nothing""",
                        (identity["group_id"], item_id, position),
                    )
                evidence = {"ordered_intake_item_ids": items, "received_count": received}
                event_id = _stable_id("BEACON-INTAKE-EVENT", _canonical_sha([identity["group_id"], "album_completed", evidence]))
                cursor.execute(
                    """insert into public.beacon_media_intake_events
                       (event_id,intake_group_id,event_type,evidence_sha256,evidence_json)
                       values (%s,%s,'album_completed',%s,%s::jsonb)
                       on conflict (event_id) do nothing""",
                    (event_id, identity["group_id"], _canonical_sha(evidence), json.dumps(evidence, sort_keys=True)),
                )
                created = cursor.rowcount
            return {
                "status": "album_completed" if created else "album_completion_replay_withheld",
                "created_count": created,
                "received_count": received,
                "attention_count": 0,
                "ordered_intake_item_ids": items,
            }, 201 if created else 200
        except Exception as exc:
            return {"status": "album_completion_failed", "error_type": exc.__class__.__name__}, 500

    def offer_album_completion(self, identity):
        evidence = {"completion_code_offered": True}
        event_id = _stable_id(
            "BEACON-INTAKE-EVENT",
            _canonical_sha([identity["group_id"], "album_completion_offered"]),
        )
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """insert into public.beacon_media_intake_events
                       (event_id,intake_group_id,event_type,evidence_sha256,evidence_json)
                       values (%s,%s,'album_completion_offered',%s,%s::jsonb)
                       on conflict (event_id) do nothing""",
                    (
                        event_id,
                        identity["group_id"],
                        _canonical_sha(evidence),
                        json.dumps(evidence, sort_keys=True),
                    ),
                )
                created = cursor.rowcount
            return {
                "created_count": created,
                "completion_code": _album_completion_code(identity["group_id"]),
            }
        except Exception:
            return {"created_count": 0, "completion_code": ""}

    def album_progress(self, identity):
        """Return one canonical, private album snapshot for the owner card."""
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """select count(*), coalesce(nullif(g.owner_explanation,''),oc.owner_context,''),
                              count(*) filter (where b.thumbnail_storage_path is not null),
                              array_agg(i.intake_item_id order by i.source_order_key),
                              array_agg(b.content_sha256 order by i.source_order_key)
                       from public.beacon_media_intake_groups g
                       join public.beacon_media_intake_items i using (intake_group_id)
                       join public.beacon_media_source_links l using (intake_item_id)
                       join public.beacon_media_binaries b using (binary_asset_id)
                       left join lateral (
                         select e.evidence_json->>'owner_context' as owner_context
                         from public.beacon_media_intake_events e
                         join public.beacon_media_intake_items ci
                           on ci.intake_item_id=e.intake_item_id
                         where e.intake_group_id=g.intake_group_id
                           and e.event_type='pending' and e.evidence_json ? 'owner_context'
                         order by (e.evidence_json->>'provenance'=
                           'owner_directed_incident_recovery') desc,
                           ci.source_order_key desc,e.event_id desc limit 1
                       ) oc on true
                       where g.intake_group_id=%s
                       group by g.owner_explanation,oc.owner_context""",
                    (identity["group_id"],),
                )
                row = cursor.fetchone()
            if not row:
                return {"status": "album_progress_not_found"}, 404
            count = int(row[0])
            context = str(row[1] or "")
            digest = _canonical_sha({"group_id": identity["group_id"],
                "stored_count": count, "owner_context": context,
                "ordered_intake_item_ids": list(row[3] or []),
                "ordered_content_sha256": list(row[4] or [])})
            return {"status": "album_progress_loaded", "stored_count": count,
                "owner_context": context, "contact_sheet_available": int(row[2]) == count,
                "canonical_digest": digest}, 200
        except Exception as exc:
            return {"status": "album_progress_failed", "error_type": exc.__class__.__name__}, 500

    def complete_album_by_code(self, identity, completion_code):
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """select intake_group_id from public.beacon_media_intake_groups
                       where private_chat_identity_hmac=%s
                         and owner_principal=%s
                         and completion_code_sha256=%s""",
                    (
                        identity["chat_hmac"],
                        identity["owner_principal"],
                        _canonical_sha(completion_code),
                    ),
                )
                row = cursor.fetchone()
            if not row:
                return {"status": "album_completion_identity_not_found"}, 404
            completed, status = self.complete_album({**identity, "group_id": row[0]})
            return {**completed, "intake_group_id": row[0]}, status
        except Exception as exc:
            return {
                "status": "album_completion_lookup_failed",
                "error_type": exc.__class__.__name__,
            }, 500

    def complete_album_claimed(self, identity, expected_digest):
        """Compare and complete one exact album generation under one DB lock."""
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",
                    ("beacon-album:"+identity["group_id"],))
                cursor.execute("""select 1 from public.beacon_media_intake_groups
                    where intake_group_id=%s and private_chat_identity_hmac=%s
                      and owner_principal=%s for update""",
                    (identity["group_id"],identity["chat_hmac"],identity["owner_principal"]))
                if not cursor.fetchone():
                    return {"success":False,"status":"album_completion_identity_not_found"},404
                cursor.execute("""select i.intake_item_id,b.content_sha256,b.thumbnail_storage_path,
                    coalesce(nullif(g.owner_explanation,''),oc.owner_context,'')
                    from public.beacon_media_intake_groups g
                    join public.beacon_media_intake_items i using(intake_group_id)
                    join public.beacon_media_source_links l using(intake_item_id)
                    join public.beacon_media_binaries b using(binary_asset_id)
                    left join lateral (select e.evidence_json->>'owner_context' owner_context
                      from public.beacon_media_intake_events e
                      join public.beacon_media_intake_items ci on ci.intake_item_id=e.intake_item_id
                      where e.intake_group_id=g.intake_group_id and e.event_type='pending'
                        and e.evidence_json ? 'owner_context'
                      order by (e.evidence_json->>'provenance'=
                        'owner_directed_incident_recovery') desc,
                        ci.source_order_key desc,e.event_id desc limit 1) oc on true
                    where g.intake_group_id=%s order by i.source_order_key""",(identity["group_id"],))
                rows=cursor.fetchall();items=[r[0] for r in rows]
                cursor.execute("select count(*) from public.beacon_media_intake_items where intake_group_id=%s",
                    (identity["group_id"],))
                total_items=int(cursor.fetchone()[0])
                if total_items!=len(rows):
                    return {"success":False,"status":"album_contains_unresolved_items",
                        "telegram_sends":0,"telegram_edits":0},409
                context=str(rows[-1][3] or "") if rows else ""
                digest=_canonical_sha({"group_id":identity["group_id"],"stored_count":len(rows),
                    "owner_context":context,"ordered_intake_item_ids":items,
                    "ordered_content_sha256":[r[1] for r in rows]})
                if not rows or not expected_digest or digest!=expected_digest:
                    return {"success":False,"status":"album_finish_button_stale",
                        "telegram_sends":0,"telegram_edits":0},409
                for position,item_id in enumerate(items,1):
                    cursor.execute("""insert into public.beacon_media_intake_album_members
                      (intake_group_id,intake_item_id,album_position) values(%s,%s,%s)
                      on conflict do nothing""",(identity["group_id"],item_id,position))
                evidence={"ordered_intake_item_ids":items,"received_count":len(items),
                    "canonical_digest":digest}
                event_id=_stable_id("BEACON-INTAKE-EVENT",
                    _canonical_sha([identity["group_id"],"album_completed",evidence]))
                cursor.execute("""insert into public.beacon_media_intake_events
                  (event_id,intake_group_id,event_type,evidence_sha256,evidence_json)
                  values(%s,%s,'album_completed',%s,%s::jsonb) on conflict(event_id) do nothing""",
                  (event_id,identity["group_id"],_canonical_sha(evidence),json.dumps(evidence,sort_keys=True)))
                created=cursor.rowcount
            return {"success":True,"status":"album_completed" if created else "album_completion_replay_withheld",
                "created_count":created,"received_count":len(items),"attention_count":0,
                "ordered_intake_item_ids":items,"owner_context":context,
                "contact_sheet_available":all(bool(r[2]) for r in rows)},201 if created else 200
        except Exception as exc:
            return {"success":False,"status":"album_completion_failed",
                "error_type":exc.__class__.__name__},500

    def list(self, limit):
        try:
            limit = max(1, min(int(limit), 100))
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """select g.intake_group_id,
                              coalesce(nullif(g.owner_explanation,''),oc.owner_context,''),
                              g.source_message_at,
                              g.capture_time,g.capture_time_state,g.intake_at,
                              i.intake_item_id,m.album_position,b.binary_asset_id,b.content_sha256,
                              b.observed_mime_type,b.byte_size,b.width,b.height,
                              l.beacon_asset_id,l.exact_duplicate_of_item_id,b.thumbnail_storage_path,
                              b.storage_readback_sha256,b.storage_path,
                              o.observation_json,o.confidence_state,
                              le.event_type,le.library_event_id,
                              coalesce(pe.event_type='approved_public_use',false),pe.event_id,
                              coalesce(a.campaign_usage_count,0),
                              coalesce(cs.album_completed,false)
                       from public.beacon_media_intake_groups g
                       join public.beacon_media_intake_items i using (intake_group_id)
                       left join public.beacon_media_intake_album_members m using (intake_group_id,intake_item_id)
                       left join public.beacon_media_source_links l using (intake_item_id)
                       left join public.beacon_media_binaries b using (binary_asset_id)
                       left join public.beacon_media_assets a on a.asset_id=l.beacon_asset_id
                       left join lateral (
                         select e.evidence_json->>'owner_context' as owner_context
                         from public.beacon_media_intake_events e
                         join public.beacon_media_intake_items ci
                           on ci.intake_item_id=e.intake_item_id
                         where e.intake_group_id=g.intake_group_id
                           and e.event_type='pending'
                           and e.evidence_json ? 'owner_context'
                         order by
                           (e.evidence_json->>'provenance'=
                              'owner_directed_incident_recovery') desc,
                           ci.source_order_key desc,e.event_id desc limit 1
                       ) oc on true
                       left join lateral (
                         select observation_json,confidence_state
                         from public.beacon_media_understanding_events
                         where binary_asset_id=b.binary_asset_id
                         order by observed_at desc limit 1
                       ) o on true
                       left join lateral (
                         select event_type,public_use_approved,library_event_id
                         from public.beacon_media_library_events
                         where binary_asset_id=b.binary_asset_id
                           and event_type in ('library_accepted','library_rejected','archived')
                         order by recorded_at desc,library_event_id desc limit 1
                       ) le on true
                       left join lateral (
                         select event_id,event_type
                         from public.beacon_media_asset_events
                         where asset_id=l.beacon_asset_id
                           and event_type in ('approved_public_use','rejected_public_use')
                         order by created_at desc,event_id desc limit 1
                       ) pe on true
                       left join lateral (
                         select true as album_completed
                         from public.beacon_media_intake_events
                         where intake_group_id=g.intake_group_id
                           and event_type='album_completed'
                         limit 1
                       ) cs on true
                       order by g.intake_at desc,i.source_order_key limit %s""",
                    (limit,),
                )
                rows = cursor.fetchall()
        except Exception as exc:
            return {"success": False, "status": "media_intake_read_unavailable", "items": [], "error_type": exc.__class__.__name__, **AUTHORITY}, 503
        items = [{
            "intake_group_id": row[0], "owner_explanation": row[1],
            "source_message_at": _iso(row[2]), "capture_time": _iso(row[3]),
            "capture_time_state": row[4], "intake_at": _iso(row[5]),
            "intake_item_id": row[6], "album_position": row[7],
            "binary_asset_id": row[8], "content_sha256": row[9] or "",
            "observed_mime_type": row[10] or "", "byte_size": row[11],
            "width": row[12], "height": row[13], "beacon_asset_id": row[14],
            "exact_duplicate": bool(row[15]), "thumbnail_available": bool(row[16]),
            "private_storage_proof_id": (
                f"{row[8]}:readback:{row[17]}" if row[17] and row[17] == row[9] and row[18] else ""),
            "observation": row[19] or {},
            "observation_confidence": row[20] or "unavailable",
            "latest_library_event": row[21] or "",
            "current_library_accept_event_id": row[22] or "",
            "effective_public_use_approved": bool(row[23]),
            "current_public_use_event_id": row[24] or "",
            "prior_campaign_use_count": row[25] or 0,
            "album_completed": bool(row[26]),
            "latest_review_event_id": row[22] or "",
            **AUTHORITY,
        } for row in rows]
        return {"success": True, "status": "media_intakes_listed", "items": items, **AUTHORITY}, 200

    def thumbnail(self, binary_asset_id):
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """select thumbnail_storage_path from public.beacon_media_binaries
                       where binary_asset_id=%s""",
                    (str(binary_asset_id or "")[:120],),
                )
                row = cursor.fetchone()
            if not row or not row[0]:
                return {"success": False, "status": "private_thumbnail_not_found"}, 404
            return {"success": True, "thumbnail_storage_path": row[0]}, 200
        except Exception as exc:
            return {"success": False, "status": "private_thumbnail_read_failed", "error_type": exc.__class__.__name__}, 500

    def review(self, binary_asset_id, decision, owner_principal):
        decision = decision if isinstance(decision, dict) else {}
        event_type = str(decision.get("event_type") or "")
        allowed = {
            "library_accepted", "library_rejected", "archived",
            "owner_context_recorded", "public_use_approved", "public_use_revoked",
        }
        if event_type not in allowed or not owner_principal:
            return {"success": False, "status": "media_review_decision_invalid", **AUTHORITY}, 400
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                return self._review_cursor(
                    cursor, binary_asset_id, decision, owner_principal
                )
        except Exception as exc:
            return {"success": False, "status": "media_review_write_failed", "error_type": exc.__class__.__name__, **AUTHORITY}, 500

    def review_group(self, intake_group_id, decision, owner_principal):
        decision = decision if isinstance(decision, dict) else {}
        event_type = str(decision.get("event_type") or "")
        if event_type not in {
            "library_accepted", "library_rejected", "archived",
            "public_use_approved", "public_use_revoked",
        } or not owner_principal:
            return {"success": False, "status": "media_group_review_invalid", **AUTHORITY}, 400
        if not str(decision.get("owner_action_id") or "").strip():
            return {
                "success": False,
                "status": "media_review_owner_action_id_required",
                **AUTHORITY,
            }, 400
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """select exists (
                         select 1 from public.beacon_media_intake_events
                         where intake_group_id=%s and event_type='album_completed'
                       )""",
                    (intake_group_id,),
                )
                if not cursor.fetchone()[0]:
                    return {
                        "success": False,
                        "status": "media_group_completion_required_before_review",
                        **AUTHORITY,
                    }, 409
                cursor.execute(
                    """select count(*),count(l.binary_asset_id)
                       from public.beacon_media_intake_items i
                       left join public.beacon_media_source_links l using (intake_item_id)
                       where i.intake_group_id=%s""",
                    (intake_group_id,),
                )
                item_count, linked_count = cursor.fetchone()
                if not item_count or item_count != linked_count:
                    return {
                        "success": False,
                        "status": "media_group_contains_unresolved_items",
                        **AUTHORITY,
                    }, 409
                cursor.execute(
                    """select distinct l.binary_asset_id
                       from public.beacon_media_intake_items i
                       join public.beacon_media_source_links l using (intake_item_id)
                       where i.intake_group_id=%s order by l.binary_asset_id""",
                    (intake_group_id,),
                )
                binary_ids = [row[0] for row in cursor.fetchall()]
                created = replayed = 0
                for binary_id in binary_ids:
                    group_action_id = str(
                        decision.get("owner_action_id") or ""
                    ).strip()[:120]
                    expected_by_binary = decision.get(
                        "expected_predecessors"
                    ) if isinstance(decision.get("expected_predecessors"), dict) else {}
                    item_decision = {
                        **decision,
                        "owner_action_id": f"{group_action_id}:{binary_id}"[:160],
                        "expected_predecessor_event_id": str(
                            expected_by_binary.get(binary_id) or ""
                        )[:160],
                    }
                    result, status = self._review_cursor(
                        cursor, binary_id, item_decision, owner_principal
                    )
                    if status >= 400:
                        connection.rollback()
                        return result, status
                    created += result["created_count"]
                    replayed += int(result["created_count"] == 0)
            return {
                "success": True,
                "status": (
                    "media_group_review_recorded"
                    if created else "media_group_review_replay_withheld"
                ),
                "created_count": created,
                "replayed_count": replayed,
                "reviewed_binary_count": len(binary_ids),
                **AUTHORITY,
            }, 201 if created else 200
        except Exception as exc:
            return {
                "success": False,
                "status": "media_group_review_write_failed",
                "error_type": exc.__class__.__name__,
                **AUTHORITY,
            }, 500

    def _review_cursor(self, cursor, binary_asset_id, decision, owner_principal):
        event_type = str(decision.get("event_type") or "")
        notes = str(decision.get("notes") or "")[:2000]
        owner_action_id = str(decision.get("owner_action_id") or "").strip()[:160]
        expected_predecessor = str(
            decision.get("expected_predecessor_event_id") or ""
        ).strip()[:160]
        if not owner_action_id:
            return {
                "success": False,
                "status": "media_review_owner_action_id_required",
                **AUTHORITY,
            }, 400
        cursor.execute(
            """select binary_asset_id from public.beacon_media_binaries
               where binary_asset_id=%s for update""",
            (binary_asset_id,),
        )
        if not cursor.fetchone():
            return {
                "success": False,
                "status": "canonical_binary_required",
                **AUTHORITY,
            }, 409
        cursor.execute(
            """select library_event_id,event_type,owner_principal,notes
               from public.beacon_media_library_events
               where binary_asset_id=%s
               order by recorded_at desc,library_event_id desc limit 1""",
            (binary_asset_id,),
        )
        predecessor = cursor.fetchone()
        predecessor_id = predecessor[0] if predecessor else None
        if expected_predecessor != (predecessor_id or ""):
            cursor.execute(
                """select event_type,decision_identity_sha256
                   from public.beacon_media_library_events
                   where binary_asset_id=%s and owner_principal=%s
                     and owner_action_id=%s""",
                (binary_asset_id, owner_principal, owner_action_id),
            )
            prior_action = cursor.fetchone()
            if prior_action:
                prior_identity = _canonical_sha({
                    "binary_asset_id": binary_asset_id,
                    "event_type": event_type,
                    "notes": notes,
                    "owner_principal": owner_principal,
                    "owner_action_id": owner_action_id,
                    "predecessor_event_id": expected_predecessor or None,
                })
                if prior_action == (event_type, prior_identity):
                    return {
                        "success": True,
                        "status": "media_review_replay_withheld",
                        "created_count": 0,
                        **AUTHORITY,
                    }, 200
                return {
                    "success": False,
                    "status": "media_review_owner_action_conflict",
                    **AUTHORITY,
                }, 409
            return {
                "success": False,
                "status": "media_review_predecessor_changed",
                **AUTHORITY,
            }, 409
        identity = _canonical_sha({
            "binary_asset_id": binary_asset_id, "event_type": event_type,
            "notes": notes, "owner_principal": owner_principal,
            "owner_action_id": owner_action_id,
            "predecessor_event_id": expected_predecessor or None,
        })
        event_id = _stable_id(
            "BEACON-LIBRARY-EVENT",
            identity,
        )
        cursor.execute(
            """select event_type,decision_identity_sha256
               from public.beacon_media_library_events
               where library_event_id=%s""",
            (event_id,),
        )
        prior = cursor.fetchone()
        if prior:
            if prior == (event_type, identity):
                return {"success": True, "status": "media_review_replay_withheld", "created_count": 0, **AUTHORITY}, 200
            return {"success": False, "status": "media_review_identity_conflict", "created_count": 0, **AUTHORITY}, 409
        if event_type == "public_use_approved":
            cursor.execute(
                """select event_type from public.beacon_media_library_events
                   where binary_asset_id=%s
                     and event_type in ('library_accepted','library_rejected','archived')
                   order by recorded_at desc,library_event_id desc limit 1""",
                (binary_asset_id,),
            )
            library_state = cursor.fetchone()
            if not library_state or library_state[0] != "library_accepted":
                return {
                    "success": False,
                    "status": "library_accept_required_before_public_use",
                    **AUTHORITY,
                }, 409
        cursor.execute(
            """select l.beacon_asset_id
               from public.beacon_media_source_links l
               where l.binary_asset_id=%s and l.beacon_asset_id is not null
               order by l.linked_at limit 1""",
            (binary_asset_id,),
        )
        asset = cursor.fetchone()
        if not asset:
            return {
                "success": False,
                "status": "canonical_beacon_asset_required",
                **AUTHORITY,
            }, 409
        cursor.execute(
            """insert into public.beacon_media_library_events
               (library_event_id,binary_asset_id,event_type,owner_principal,
                owner_action_id,decision_identity_sha256,notes,
                predecessor_event_id,public_use_approved)
               values (%s,%s,%s,%s,%s,%s,%s,%s,false)""",
            (
                event_id, binary_asset_id, event_type, owner_principal,
                owner_action_id, identity, notes, predecessor_id,
            ),
        )
        canonical_event_id = ""
        if event_type in {"public_use_approved", "public_use_revoked"}:
            canonical_type = (
                "approved_public_use"
                if event_type == "public_use_approved"
                else "rejected_public_use"
            )
            canonical_event_id = _stable_id(
                "BEACON-MEDIA-EVENT",
                _canonical_sha([asset[0], canonical_type, identity]),
            )
            cursor.execute(
                """insert into public.beacon_media_asset_events
                   (event_id,asset_id,event_type,notes,recorded_by,
                    approval_status,public_use_approved)
                   values (%s,%s,%s,%s,%s,%s,%s)""",
                (
                    canonical_event_id,
                    asset[0],
                    canonical_type,
                    notes,
                    owner_principal,
                    "approved" if canonical_type == "approved_public_use" else "rejected",
                    canonical_type == "approved_public_use",
                ),
            )
        return {
            "success": True, "status": "media_review_event_recorded",
            "created_count": 1, "library_event_id": event_id,
            "canonical_public_use_event_id": canonical_event_id,
            **AUTHORITY,
        }, 201


class SupabasePrivateStorage:
    def __init__(self, environ=None):
        self.environ = environ if environ is not None else os.environ

    def put(self, path, body, content_type):
        result, status = upload_bytes_to_supabase_storage(
            RAW_INTAKE_BUCKET, path, body, content_type, environ=self.environ
        )
        return {**result, "http_status": status}

    def get(self, path, max_bytes):
        response = self._request("GET", path)
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise IntakeFailure("private_storage_object_oversized", 502)
        return body

    def delete_many(self, paths):
        source = self.environ
        url, key = _storage_config(source)
        if not url or not key:
            return {"success": False, "status": "private_storage_not_configured"}
        endpoint = f"{url}/storage/v1/object/{urllib_parse.quote(RAW_INTAKE_BUCKET, safe='')}"
        request = urllib_request.Request(
            endpoint, data=json.dumps({"prefixes": paths}).encode("utf-8"), method="DELETE",
            headers={"Authorization": f"Bearer {key}", "apikey": key, "Content-Type": "application/json"},
        )
        try:
            with urllib_request.urlopen(request, timeout=STORAGE_TIMEOUT_SECONDS):
                return {"success": True, "status": "compensating_cleanup_complete"}
        except (urllib_error.HTTPError, urllib_error.URLError, OSError, TimeoutError):
            return {"success": False, "status": "compensating_cleanup_unconfirmed"}

    def _request(self, method, path):
        url, key = _storage_config(self.environ)
        if not url or not key:
            raise IntakeFailure("private_storage_not_configured", 503)
        endpoint = (
            f"{url}/storage/v1/object/authenticated/{urllib_parse.quote(RAW_INTAKE_BUCKET, safe='')}/"
            f"{urllib_parse.quote(path, safe='/')}"
        )
        request = urllib_request.Request(
            endpoint, method=method,
            headers={"Authorization": f"Bearer {key}", "apikey": key},
        )
        try:
            return urllib_request.urlopen(request, timeout=STORAGE_TIMEOUT_SECONDS)
        except (urllib_error.HTTPError, urllib_error.URLError, OSError, TimeoutError) as exc:
            raise IntakeFailure("private_storage_read_failed", 502) from exc


class IntakeFailure(Exception):
    def __init__(self, status, http_status, safe_detail=None):
        super().__init__(status)
        self.status = status
        self.http_status = http_status
        self.safe_detail = safe_detail if isinstance(safe_detail, dict) else {}


def _download_telegram_file(envelope, source):
    token = str(source.get(BOT_TOKEN_ENV) or "").strip()
    if not token:
        raise IntakeFailure("telegram_bot_token_not_configured", 503)
    get_file = urllib_request.Request(
        f"https://api.telegram.org/bot{token}/getFile",
        data=json.dumps({"file_id": envelope["file_id"]}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    temp_path = ""
    try:
        with urllib_request.urlopen(get_file, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            metadata = json.loads(response.read(64 * 1024).decode("utf-8"))
        file_path = str((metadata.get("result") or {}).get("file_path") or "").strip()
        if not metadata.get("ok") or not file_path:
            raise IntakeFailure("telegram_file_path_unavailable", 502)
        request = urllib_request.Request(f"https://api.telegram.org/file/bot{token}/{urllib_parse.quote(file_path, safe='/')}")
        with urllib_request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            declared_length = response.headers.get("Content-Length")
            suffix = Path(file_path).suffix[:10]
            with tempfile.NamedTemporaryFile(prefix="beacon-intake-", suffix=suffix, delete=False) as target:
                total = 0
                while True:
                    chunk = response.read(STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        raise IntakeFailure("telegram_media_oversized", 413)
                    target.write(chunk)
                temp_path = target.name
            if declared_length:
                try:
                    if int(declared_length) != total:
                        Path(temp_path).unlink(missing_ok=True)
                        raise IntakeFailure("telegram_media_truncated", 422)
                except ValueError:
                    pass
        return temp_path, {"byte_size": total, "returned_mime_type": response.headers.get("Content-Type", "")}
    except IntakeFailure:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
        raise
    except (urllib_error.HTTPError, urllib_error.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
        raise IntakeFailure("telegram_media_download_failed", 502, {"error_type": exc.__class__.__name__}) from exc


def _validate_streamed_image(path, declared_mime, download_meta):
    byte_size = Path(path).stat().st_size
    if byte_size <= 0:
        raise IntakeFailure("telegram_media_empty", 422)
    if byte_size > MAX_IMAGE_BYTES:
        raise IntakeFailure("telegram_media_oversized", 413)
    head = Path(path).read_bytes()[:16]
    observed = (
        "image/jpeg" if head.startswith(b"\xff\xd8\xff")
        else "image/png" if head.startswith(b"\x89PNG\r\n\x1a\n")
        else ""
    )
    returned = str(download_meta.get("returned_mime_type") or "").split(";")[0].strip().lower()
    if observed not in SUPPORTED_MIME:
        raise IntakeFailure("telegram_media_type_unsupported", 415)
    if declared_mime and declared_mime not in {observed, "application/octet-stream"}:
        raise IntakeFailure("telegram_declared_mime_mismatch", 415)
    if returned and returned not in {observed, "application/octet-stream"}:
        raise IntakeFailure("telegram_returned_mime_mismatch", 415)
    try:
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format
    except Exception as exc:
        raise IntakeFailure("telegram_media_malformed_or_truncated", 422) from exc
    if image_format != SUPPORTED_MIME[observed]:
        raise IntakeFailure("telegram_media_magic_decoder_mismatch", 415)
    if (
        width <= 0 or height <= 0
        or width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise IntakeFailure("telegram_media_dimensions_out_of_bounds", 413)
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(STREAM_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return {
        "content_sha256": digest.hexdigest(),
        "observed_mime_type": observed,
        "byte_size": byte_size,
        "width": width,
        "height": height,
        "duration_seconds": None,
    }


def _thumbnail_bytes(path):
    from PIL import Image
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((THUMBNAIL_MAX_EDGE, THUMBNAIL_MAX_EDGE))
        output = io.BytesIO()
        image.save(output, "JPEG", quality=82, optimize=True)
    return output.getvalue()


def _identities(envelope, source):
    chat_hmac = _keyed(source, "chat", envelope["chat_id"])
    owner = _keyed(source, "owner", envelope["owner_user_id"])
    group_source = envelope["media_group_id"] or f"single:{envelope['message_id']}"
    group_id = _stable_id("BEACON-INTAKE-GROUP", _keyed(source, "group", f"{envelope['chat_id']}\0{group_source}"))
    source_sha = _keyed(
        source, "telegram-source",
        f"{envelope['chat_id']}\0{envelope['update_id']}\0{envelope['message_id']}\0"
        f"{envelope['file_unique_id'] or envelope['file_id']}",
    )
    return {
        "chat_hmac": chat_hmac,
        "owner_principal": f"telegram-owner:{owner}",
        "group_id": group_id,
        "source_sha256": source_sha,
        "item_id": _stable_id("BEACON-INTAKE-ITEM", source_sha),
    }


def _keyed(source, domain, value):
    secret = _secret(source)
    if not secret:
        return ""
    return hmac.new(
        secret.encode("utf-8"),
        f"beacon-media-intake:{CONTRACT_VERSION}:{domain}\0{value}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _secret(source):
    for name in SIGNING_SECRET_ENVS:
        value = str(source.get(name) or "").strip()
        if value:
            return value
    return ""


def _canonical_sha(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _stable_id(prefix, digest):
    bounded = hashlib.sha256(str(digest).encode("utf-8")).hexdigest().upper()[:24]
    return f"{prefix}-{bounded}"


def _album_completion_code(group_id):
    return hashlib.sha256(
        f"beacon-album-completion:v1\0{group_id}".encode("utf-8")
    ).hexdigest().upper()[:20]


def _album_receipt(identity):
    return {
        "receipt_mission_id": identity["group_id"],
        "receipt_text": (
            "BEACON started this private album. Use Finish Album when every photo "
            "has been sent. No library acceptance, "
            "public-use or publication approval was granted."
        ),
    }


def _validated_recovery_context(payload, envelope, source):
    recovery = payload.get("beacon_media_recovery") if isinstance(payload, dict) else None
    if not isinstance(recovery, dict):
        return ""
    expected = str(source.get(RECOVERY_CONTEXT_TOKEN_ENV) or "").strip()
    supplied = str(recovery.get("token") or "").strip()
    context = str(recovery.get("owner_context") or "").strip()[:2000]
    group_id = str(recovery.get("media_group_id") or "").strip()
    if (
        len(expected) < 32 or not hmac.compare_digest(supplied, expected)
        or not context or group_id != envelope.get("media_group_id")
    ):
        return ""
    return context


def _storage_config(source):
    return (
        str(source.get(SUPABASE_URL_ENV) or "").strip().rstrip("/"),
        str(source.get(SUPABASE_SERVICE_ROLE_KEY_ENV) or "").strip(),
    )


def _thumbnail_token(binary_asset_id, environ=None, now=None):
    source = environ if environ is not None else os.environ
    secret = _secret(source)
    if not secret or not binary_asset_id:
        return None
    expires = int(now if now is not None else time.time()) + THUMBNAIL_TOKEN_TTL_SECONDS
    payload = f"beacon-private-thumbnail:v1\0{binary_asset_id}\0{expires}"
    token = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return {"expires": expires, "token": token}


def _thumbnail_token_valid(binary_asset_id, token, expires, environ=None, now=None):
    source = environ if environ is not None else os.environ
    secret = _secret(source)
    try:
        expires_int = int(expires)
    except (TypeError, ValueError):
        return False
    current = int(now if now is not None else time.time())
    if (
        not secret or not binary_asset_id
        or expires_int < current
        or expires_int > current + THUMBNAIL_TOKEN_TTL_SECONDS
    ):
        return False
    payload = f"beacon-private-thumbnail:v1\0{binary_asset_id}\0{expires_int}"
    expected = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return bool(token) and hmac.compare_digest(str(token), expected)


def _result(success, status, policy):
    return {
        "success": success,
        "status": status,
        "mode": CONTRACT_VERSION,
        "policy": policy,
        "credentials_exposed": False,
        "private_chat_identity_exposed": False,
        "owner_identity_exposed": False,
        **AUTHORITY,
    }


def _csv(value):
    return {item.strip() for item in str(value or "").split(",") if item.strip()}


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _sha256_set(value):
    return {
        item.strip().lower()
        for item in str(value or "").split(",")
        if len(item.strip()) == 64
        and all(character in "0123456789abcdefABCDEF" for character in item.strip())
    }


def _integer(value, allow_zero=False):
    try:
        result = int(value)
        return result if result > 0 or (allow_zero and result == 0) else 0
    except (TypeError, ValueError):
        return 0


def _filename(value):
    value = str(value or "").replace("\\", "/").split("/")[-1][:180]
    return "".join(character if character.isalnum() or character in " ._-" else "_" for character in value).strip()


def _telegram_time(value):
    try:
        return datetime.fromtimestamp(int(value), timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _utc_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")
