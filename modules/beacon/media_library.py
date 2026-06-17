import hashlib
import json
import mimetypes
import os
from datetime import datetime, timezone
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from services.database_service import DATABASE_URL_ENV


SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_SERVICE_ROLE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
RAW_INTAKE_BUCKET = "beacon-raw-intake"
APPROVED_MEDIA_BUCKET = "beacon-approved-media"
MAX_STANDARD_UPLOAD_BYTES = 6 * 1024 * 1024

MEDIA_TYPES = {"image", "video", "document", "unknown"}
ASSET_SOURCES = {
    "farm_app_upload",
    "telegram_upload",
    "folder_import",
    "whatsapp_media",
    "owner_note",
    "other",
}
APPROVAL_STATUSES = {"needs_review", "approved", "rejected", "archived"}
EVENT_TYPES = {
    "intake_registered",
    "review_note",
    "approved_public_use",
    "rejected_public_use",
    "archived",
    "tags_updated",
    "quality_reviewed",
    "campaign_usage_observed",
}
PRIVACY_RISKS = {"unknown", "low", "medium", "high"}

AUTHORITY_FLAGS = {
    "sends_customer_message": False,
    "posts_publicly": False,
    "calls_chatwoot": False,
    "calls_meta": False,
    "calls_n8n": False,
    "creates_quote": False,
    "creates_invoice": False,
    "creates_order": False,
    "changes_stock": False,
    "reserves_stock": False,
    "dispatch_enabled": False,
    "changes_runtime_now": False,
    "changes_prompt_now": False,
    "physical_controls_enabled": False,
    "customer_public_output_enabled": False,
    "writes_farm_data": False,
}


def beacon_media_storage_policy(environ=None):
    source = environ if environ is not None else os.environ
    url = _clean(source.get(SUPABASE_URL_ENV), 300)
    service_key = _clean(source.get(SUPABASE_SERVICE_ROLE_KEY_ENV), 300)
    return {
        "success": True,
        "mode": "beacon_media_library_storage_policy",
        "storage_backend": "supabase_storage",
        "metadata_backend": "postgres",
        "raw_intake_bucket": RAW_INTAKE_BUCKET,
        "approved_media_bucket": APPROVED_MEDIA_BUCKET,
        "standard_upload_max_bytes": MAX_STANDARD_UPLOAD_BYTES,
        "supabase_url_configured": bool(url),
        "service_role_key_configured": bool(service_key),
        "farm_app_standard_upload_enabled": bool(url and service_key),
        "large_video_upload_mode": "planned_tus_resumable_upload_not_enabled",
        "public_asset_use_enabled": False,
        "automatic_posting_enabled": False,
        "required_envs_for_upload": [SUPABASE_URL_ENV, SUPABASE_SERVICE_ROLE_KEY_ENV],
        **AUTHORITY_FLAGS,
    }


def register_beacon_media_asset(payload, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    params = _asset_params(payload)
    if not params["storage_path"] and params["source"] != "owner_note":
        return {"success": False, "status": "storage_path_required", "asset": _public_asset(params), **AUTHORITY_FLAGS}, 400

    database_url = _database_url(database_url)
    if not database_url:
        return _unavailable("not_configured", configured=False), 503
    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", configured=True), 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.beacon_media_assets (
                        asset_id, mode, storage_bucket, storage_path, original_filename,
                        media_type, mime_type, file_size_bytes, source, source_reference,
                        uploader_label, title, description, sale_stream_relevance_json,
                        subject_tags_json, location_context, quality_score, privacy_risk,
                        safety_flags_json, public_use_approved, approval_status,
                        campaign_usage_count, notes, created_by,
                        sends_customer_message, posts_publicly, calls_chatwoot, calls_meta,
                        calls_n8n, creates_quote, creates_invoice, creates_order,
                        changes_stock, reserves_stock, dispatch_enabled, changes_runtime_now,
                        changes_prompt_now, physical_controls_enabled, customer_public_output_enabled,
                        writes_farm_data
                    )
                    values (
                        %(asset_id)s, %(mode)s, %(storage_bucket)s, %(storage_path)s,
                        %(original_filename)s, %(media_type)s, %(mime_type)s,
                        %(file_size_bytes)s, %(source)s, %(source_reference)s,
                        %(uploader_label)s, %(title)s, %(description)s,
                        %(sale_stream_relevance_json)s::jsonb,
                        %(subject_tags_json)s::jsonb,
                        %(location_context)s, %(quality_score)s, %(privacy_risk)s,
                        %(safety_flags_json)s::jsonb, %(public_use_approved)s,
                        %(approval_status)s, %(campaign_usage_count)s, %(notes)s,
                        %(created_by)s, %(sends_customer_message)s, %(posts_publicly)s,
                        %(calls_chatwoot)s, %(calls_meta)s, %(calls_n8n)s,
                        %(creates_quote)s, %(creates_invoice)s, %(creates_order)s,
                        %(changes_stock)s, %(reserves_stock)s, %(dispatch_enabled)s,
                        %(changes_runtime_now)s, %(changes_prompt_now)s,
                        %(physical_controls_enabled)s, %(customer_public_output_enabled)s,
                        %(writes_farm_data)s
                    )
                    on conflict (asset_id) do nothing
                    """,
                    params,
                )
                created_count = cursor.rowcount
    except Exception as exc:
        return _write_failed("beacon_media_asset_write_failed", exc, params), 500

    if created_count:
        record_beacon_media_asset_event(params["asset_id"], {
            "event_type": "intake_registered",
            "notes": "Asset registered for Beacon media review.",
            "recorded_by": params["created_by"],
            "approval_status": params["approval_status"],
            "public_use_approved": False,
            "sale_stream_relevance": _loads(params["sale_stream_relevance_json"], []),
            "subject_tags": _loads(params["subject_tags_json"], []),
            "quality_score": params["quality_score"],
            "privacy_risk": params["privacy_risk"],
            "safety_flags": _loads(params["safety_flags_json"], []),
        }, database_url=database_url)

    return {
        "success": True,
        "configured": True,
        "status": "beacon_media_asset_registered" if created_count else "beacon_media_asset_already_registered",
        "created_count": created_count,
        "asset_id": params["asset_id"],
        "asset": _public_asset(params),
        "next_gate": "owner_review_before_public_asset_use",
        **AUTHORITY_FLAGS,
    }, 201 if created_count else 200


def upload_beacon_media_asset(file_storage, form=None, environ=None, database_url=None, uploader=None):
    form = form if isinstance(form, dict) else {}
    if file_storage is None:
        return {"success": False, "status": "file_required", **AUTHORITY_FLAGS}, 400

    filename = _clean_filename(getattr(file_storage, "filename", "") or form.get("original_filename") or "upload.bin")
    content_type = _clean(getattr(file_storage, "mimetype", "") or mimetypes.guess_type(filename)[0] or "application/octet-stream", 120)
    data = file_storage.read()
    if not data:
        return {"success": False, "status": "empty_file", **AUTHORITY_FLAGS}, 400
    if len(data) > MAX_STANDARD_UPLOAD_BYTES:
        return {
            "success": False,
            "status": "file_too_large_for_standard_upload",
            "max_bytes": MAX_STANDARD_UPLOAD_BYTES,
            "actual_bytes": len(data),
            "next_gate": "add_tus_resumable_upload_before_large_video_intake",
            **AUTHORITY_FLAGS,
        }, 413

    media_type = _media_type_from_mime(content_type)
    asset_id = _asset_id({
        "filename": filename,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    })
    storage_path = _storage_path(asset_id, filename)
    upload_fn = uploader or upload_bytes_to_supabase_storage
    upload_result, upload_status = upload_fn(
        RAW_INTAKE_BUCKET,
        storage_path,
        data,
        content_type,
        environ=environ,
    )
    if upload_status >= 400:
        return upload_result, upload_status

    payload = {
        **form,
        "asset_id": asset_id,
        "storage_bucket": RAW_INTAKE_BUCKET,
        "storage_path": storage_path,
        "original_filename": filename,
        "media_type": media_type,
        "mime_type": content_type,
        "file_size_bytes": len(data),
        "source": form.get("source") or "farm_app_upload",
        "approval_status": "needs_review",
        "public_use_approved": False,
    }
    registered, register_status = register_beacon_media_asset(payload, database_url=database_url)
    return {
        **registered,
        "upload": {
            "status_code": upload_status,
            "status": upload_result.get("status"),
            "bucket": RAW_INTAKE_BUCKET,
            "storage_path": storage_path,
        },
    }, register_status


def upload_bytes_to_supabase_storage(bucket, storage_path, data, content_type, environ=None):
    source = environ if environ is not None else os.environ
    url = _clean(source.get(SUPABASE_URL_ENV), 300).rstrip("/")
    key = _clean(source.get(SUPABASE_SERVICE_ROLE_KEY_ENV), 2000)
    if not url or not key:
        return {
            "success": False,
            "status": "supabase_storage_not_configured",
            "required_envs": [SUPABASE_URL_ENV, SUPABASE_SERVICE_ROLE_KEY_ENV],
            **AUTHORITY_FLAGS,
        }, 503

    endpoint = f"{url}/storage/v1/object/{urllib_parse.quote(bucket, safe='')}/{urllib_parse.quote(storage_path, safe='/')}"
    req = urllib_request.Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            "Content-Type": content_type or "application/octet-stream",
            "x-upsert": "false",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return {
            "success": False,
            "status": "supabase_storage_upload_failed",
            "http_status": exc.code,
            "error": detail,
            **AUTHORITY_FLAGS,
        }, exc.code
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        return {
            "success": False,
            "status": "supabase_storage_upload_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            **AUTHORITY_FLAGS,
        }, 503
    return {
        "success": True,
        "status": "supabase_storage_upload_complete",
        "bucket": bucket,
        "storage_path": storage_path,
        "response": _loads(body, {}),
        **AUTHORITY_FLAGS,
    }, 201


def list_beacon_media_assets(limit=50, approval_status="", media_type="", database_url=None):
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 50
    approval_status = _approval_status_or_blank(approval_status)
    media_type = _media_type_or_blank(media_type)
    database_url = _database_url(database_url)
    if not database_url:
        return _unavailable("not_configured", configured=False), 503
    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", configured=True), 500

    filters = []
    params = {"limit": limit}
    if approval_status:
        filters.append("a.approval_status = %(approval_status)s")
        params["approval_status"] = approval_status
    if media_type:
        filters.append("a.media_type = %(media_type)s")
        params["media_type"] = media_type
    where = "where " + " and ".join(filters) if filters else ""
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select a.asset_id, a.storage_bucket, a.storage_path, a.original_filename,
                           a.media_type, a.mime_type, a.file_size_bytes, a.source,
                           a.source_reference, a.uploader_label, a.title, a.description,
                           a.sale_stream_relevance_json, a.subject_tags_json, a.location_context,
                           a.quality_score, a.privacy_risk, a.safety_flags_json,
                           a.public_use_approved, a.approval_status, a.campaign_usage_count,
                           a.notes, a.created_by, a.created_at,
                           coalesce(e.event_type, '') as latest_event_type,
                           coalesce(e.notes, '') as latest_event_notes,
                           e.created_at as latest_event_at
                    from public.beacon_media_assets a
                    left join lateral (
                        select event_type, notes, created_at
                        from public.beacon_media_asset_events
                        where asset_id = a.asset_id
                        order by created_at desc
                        limit 1
                    ) e on true
                    {where}
                    order by a.created_at desc
                    limit %(limit)s
                    """,
                    params,
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return _read_failed(exc), 500

    assets = [_asset_row(row) for row in rows]
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "beacon_media_library_review_only",
        "assets": assets,
        "counts": _asset_counts(assets),
        "policy": beacon_media_storage_policy(),
        "next_gate": "owner_review_before_public_asset_use",
        **AUTHORITY_FLAGS,
    }, 200


def record_beacon_media_asset_event(asset_id, payload, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    params = _event_params(asset_id, payload)
    if not params["asset_id"]:
        return {"success": False, "status": "asset_id_required", "event": _public_event(params), **AUTHORITY_FLAGS}, 400
    database_url = _database_url(database_url)
    if not database_url:
        return _unavailable("not_configured", configured=False), 503
    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", configured=True), 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.beacon_media_asset_events (
                        event_id, asset_id, event_type, notes, recorded_by,
                        approval_status, public_use_approved, sale_stream_relevance_json,
                        subject_tags_json, quality_score, privacy_risk, safety_flags_json,
                        campaign_id, sends_customer_message, posts_publicly, calls_chatwoot,
                        calls_meta, calls_n8n, creates_quote, creates_invoice, creates_order,
                        changes_stock, reserves_stock, dispatch_enabled, changes_runtime_now,
                        changes_prompt_now, physical_controls_enabled, customer_public_output_enabled,
                        writes_farm_data
                    )
                    values (
                        %(event_id)s, %(asset_id)s, %(event_type)s, %(notes)s,
                        %(recorded_by)s, %(approval_status)s, %(public_use_approved)s,
                        %(sale_stream_relevance_json)s::jsonb,
                        %(subject_tags_json)s::jsonb, %(quality_score)s, %(privacy_risk)s,
                        %(safety_flags_json)s::jsonb, %(campaign_id)s,
                        %(sends_customer_message)s, %(posts_publicly)s, %(calls_chatwoot)s,
                        %(calls_meta)s, %(calls_n8n)s, %(creates_quote)s,
                        %(creates_invoice)s, %(creates_order)s, %(changes_stock)s,
                        %(reserves_stock)s, %(dispatch_enabled)s, %(changes_runtime_now)s,
                        %(changes_prompt_now)s, %(physical_controls_enabled)s,
                        %(customer_public_output_enabled)s, %(writes_farm_data)s
                    )
                    on conflict (event_id) do nothing
                    """,
                    params,
                )
                created_count = cursor.rowcount
    except Exception as exc:
        return _write_failed("beacon_media_asset_event_write_failed", exc, params), 500

    return {
        "success": True,
        "configured": True,
        "status": "beacon_media_asset_event_recorded" if created_count else "beacon_media_asset_event_already_recorded",
        "created_count": created_count,
        "asset_id": params["asset_id"],
        "event_id": params["event_id"],
        "event": _public_event(params),
        "next_gate": "owner_review_before_public_asset_use",
        **AUTHORITY_FLAGS,
    }, 201 if created_count else 200


def _asset_params(payload):
    media_type = _media_type_or_blank(payload.get("media_type")) or _media_type_from_mime(payload.get("mime_type", ""))
    source = _source_or_default(payload.get("source"))
    approval_status = _approval_status_or_blank(payload.get("approval_status")) or "needs_review"
    public_use_approved = bool(payload.get("public_use_approved")) and approval_status == "approved"
    params = {
        "asset_id": _clean(payload.get("asset_id"), 120),
        "mode": "beacon_media_asset_metadata_only",
        "storage_bucket": _clean(payload.get("storage_bucket") or RAW_INTAKE_BUCKET, 100),
        "storage_path": _clean_path(payload.get("storage_path"), 500),
        "original_filename": _clean_filename(payload.get("original_filename")),
        "media_type": media_type,
        "mime_type": _clean(payload.get("mime_type"), 120),
        "file_size_bytes": _int(payload.get("file_size_bytes"), 0),
        "source": source,
        "source_reference": _clean(payload.get("source_reference"), 220),
        "uploader_label": _clean(payload.get("uploader_label") or payload.get("uploaded_by"), 120),
        "title": _clean(payload.get("title"), 180),
        "description": _clean(payload.get("description"), 800),
        "sale_stream_relevance_json": _json(_list(payload.get("sale_stream_relevance"))),
        "subject_tags_json": _json(_list(payload.get("subject_tags") or payload.get("tags"))),
        "location_context": _clean(payload.get("location_context"), 180),
        "quality_score": _quality_score(payload.get("quality_score")),
        "privacy_risk": _privacy_risk(payload.get("privacy_risk")),
        "safety_flags_json": _json(_list(payload.get("safety_flags"))),
        "public_use_approved": public_use_approved,
        "approval_status": approval_status,
        "campaign_usage_count": _int(payload.get("campaign_usage_count"), 0),
        "notes": _clean(payload.get("notes"), 1000),
        "created_by": _clean(payload.get("created_by") or "beacon_media_library", 100),
        **AUTHORITY_FLAGS,
    }
    if not params["asset_id"]:
        params["asset_id"] = _asset_id(params)
    return params


def _event_params(asset_id, payload):
    event_type = _event_type(payload.get("event_type") or "review_note")
    approval_status = _approval_status_or_blank(payload.get("approval_status"))
    if event_type == "approved_public_use":
        approval_status = "approved"
    elif event_type == "rejected_public_use":
        approval_status = "rejected"
    elif event_type == "archived":
        approval_status = "archived"
    public_use_approved = event_type == "approved_public_use" and approval_status == "approved"
    params = {
        "event_id": _clean(payload.get("event_id"), 120),
        "asset_id": _clean(asset_id or payload.get("asset_id"), 120),
        "event_type": event_type,
        "notes": _clean(payload.get("notes"), 1000),
        "recorded_by": _clean(payload.get("recorded_by") or "owner_review", 100),
        "approval_status": approval_status,
        "public_use_approved": public_use_approved,
        "sale_stream_relevance_json": _json(_list(payload.get("sale_stream_relevance"))),
        "subject_tags_json": _json(_list(payload.get("subject_tags") or payload.get("tags"))),
        "quality_score": _quality_score(payload.get("quality_score")),
        "privacy_risk": _privacy_risk(payload.get("privacy_risk"), allow_blank=True),
        "safety_flags_json": _json(_list(payload.get("safety_flags"))),
        "campaign_id": _clean(payload.get("campaign_id"), 120),
        **AUTHORITY_FLAGS,
    }
    if not params["event_id"]:
        params["event_id"] = _event_id(params)
    return params


def _public_asset(params):
    return {
        "asset_id": params.get("asset_id", ""),
        "storage_bucket": params.get("storage_bucket", ""),
        "storage_path": params.get("storage_path", ""),
        "original_filename": params.get("original_filename", ""),
        "media_type": params.get("media_type", ""),
        "mime_type": params.get("mime_type", ""),
        "file_size_bytes": params.get("file_size_bytes", 0),
        "source": params.get("source", ""),
        "source_reference": params.get("source_reference", ""),
        "uploader_label": params.get("uploader_label", ""),
        "title": params.get("title", ""),
        "description": params.get("description", ""),
        "sale_stream_relevance": _loads(params.get("sale_stream_relevance_json"), []),
        "subject_tags": _loads(params.get("subject_tags_json"), []),
        "location_context": params.get("location_context", ""),
        "quality_score": params.get("quality_score"),
        "privacy_risk": params.get("privacy_risk", ""),
        "safety_flags": _loads(params.get("safety_flags_json"), []),
        "public_use_approved": bool(params.get("public_use_approved")),
        "approval_status": params.get("approval_status", ""),
        "campaign_usage_count": params.get("campaign_usage_count", 0),
        "notes": params.get("notes", ""),
        "created_by": params.get("created_by", ""),
        **AUTHORITY_FLAGS,
    }


def _public_event(params):
    return {
        "event_id": params.get("event_id", ""),
        "asset_id": params.get("asset_id", ""),
        "event_type": params.get("event_type", ""),
        "notes": params.get("notes", ""),
        "recorded_by": params.get("recorded_by", ""),
        "approval_status": params.get("approval_status", ""),
        "public_use_approved": bool(params.get("public_use_approved")),
        "sale_stream_relevance": _loads(params.get("sale_stream_relevance_json"), []),
        "subject_tags": _loads(params.get("subject_tags_json"), []),
        "quality_score": params.get("quality_score"),
        "privacy_risk": params.get("privacy_risk", ""),
        "safety_flags": _loads(params.get("safety_flags_json"), []),
        "campaign_id": params.get("campaign_id", ""),
        **AUTHORITY_FLAGS,
    }


def _asset_row(row):
    return {
        "asset_id": row[0],
        "storage_bucket": row[1],
        "storage_path": row[2],
        "original_filename": row[3],
        "media_type": row[4],
        "mime_type": row[5],
        "file_size_bytes": row[6],
        "source": row[7],
        "source_reference": row[8],
        "uploader_label": row[9],
        "title": row[10],
        "description": row[11],
        "sale_stream_relevance": row[12] or [],
        "subject_tags": row[13] or [],
        "location_context": row[14],
        "quality_score": row[15],
        "privacy_risk": row[16],
        "safety_flags": row[17] or [],
        "public_use_approved": bool(row[18]),
        "approval_status": row[19],
        "campaign_usage_count": row[20],
        "notes": row[21],
        "created_by": row[22],
        "created_at": row[23].isoformat() if hasattr(row[23], "isoformat") else str(row[23] or ""),
        "latest_event": {
            "event_type": row[24] or "",
            "notes": row[25] or "",
            "created_at": row[26].isoformat() if hasattr(row[26], "isoformat") else str(row[26] or ""),
        },
        **AUTHORITY_FLAGS,
    }


def _asset_counts(assets):
    counts = {"total": len(assets), "needs_review": 0, "approved": 0, "rejected": 0, "archived": 0}
    for asset in assets:
        status = asset.get("approval_status") or "needs_review"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _storage_path(asset_id, filename):
    now = datetime.now(timezone.utc)
    safe_name = _clean_filename(filename) or "upload.bin"
    return f"{now:%Y/%m/%d}/{asset_id}/{safe_name}"


def _asset_id(seed):
    digest = hashlib.sha256(_json(seed).encode("utf-8")).hexdigest()[:18].upper()
    return f"BEACON-ASSET-{digest}"


def _event_id(seed):
    seed = {**seed, "created_at": datetime.now(timezone.utc).isoformat()}
    digest = hashlib.sha256(_json(seed).encode("utf-8")).hexdigest()[:18].upper()
    return f"BEACON-ASSET-EVENT-{digest}"


def _media_type_from_mime(mime_type):
    mime_type = str(mime_type or "").lower()
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type:
        return "document"
    return "unknown"


def _media_type_or_blank(value):
    value = _clean(value, 40)
    return value if value in MEDIA_TYPES else ""


def _source_or_default(value):
    value = _clean(value, 80)
    return value if value in ASSET_SOURCES else "other" if value else "farm_app_upload"


def _approval_status_or_blank(value):
    value = _clean(value, 80)
    return value if value in APPROVAL_STATUSES else ""


def _event_type(value):
    value = _clean(value, 80)
    return value if value in EVENT_TYPES else "review_note"


def _privacy_risk(value, allow_blank=False):
    value = _clean(value, 40)
    if allow_blank and not value:
        return ""
    return value if value in PRIVACY_RISKS else "unknown"


def _quality_score(value):
    if value in {"", None}:
        return None
    try:
        score = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(0, min(score, 100))


def _int(value, default=0):
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def _clean_filename(value):
    value = _clean(value, 180).replace("\\", "/").split("/")[-1]
    return "".join(ch if ch.isalnum() or ch in {"-", "_", ".", " "} else "_" for ch in value).strip()[:180]


def _clean_path(value, max_len=500):
    value = _clean(value, max_len).replace("\\", "/")
    return "/".join(_clean_filename(part) for part in value.split("/") if _clean_filename(part))[:max_len]


def _list(value):
    if isinstance(value, list):
        return [_clean(item, 120) for item in value if _clean(item, 120)]
    if isinstance(value, str) and value.strip():
        return [_clean(part, 120) for part in value.split(",") if _clean(part, 120)]
    return []


def _json(value):
    return json.dumps(value, sort_keys=True, default=str)


def _loads(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _clean(value, max_len=300):
    return " ".join(str(value or "").strip().split())[:max_len]


def _database_url(database_url):
    return (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()


def _unavailable(status, configured):
    return {
        "success": False,
        "configured": configured,
        "status": status,
        "mode": "beacon_media_library_review_only",
        "assets": [],
        "counts": {},
        **AUTHORITY_FLAGS,
    }


def _write_failed(status, exc, params):
    return {
        "success": False,
        "configured": True,
        "status": status,
        "error_type": exc.__class__.__name__,
        "error": str(exc)[:240],
        "asset": _public_asset(params),
        **AUTHORITY_FLAGS,
    }


def _read_failed(exc):
    return {
        "success": False,
        "configured": True,
        "status": "beacon_media_asset_read_failed",
        "error_type": exc.__class__.__name__,
        "error": str(exc)[:240],
        "assets": [],
        "counts": {},
        **AUTHORITY_FLAGS,
    }
