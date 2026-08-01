"""Bounded binary image transport for owner-approved Facebook Page packets."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import struct
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
import uuid


MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_WIDTH = 12_000
MAX_IMAGE_HEIGHT = 12_000
ALLOWED_IMAGE_FORMATS = {
    "jpeg": {"image/jpeg", "image/jpg"},
    "png": {"image/png"},
}
SERVER_READBACK_AUTHORITY = "server_private_object_authenticated_readback_v1"
MAX_READBACK_AGE_SECONDS = 300


class _RejectRedirects(urllib_request.HTTPRedirectHandler):
    """Never forward private-object credentials to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def resolve_server_publication_assets(asset_ids, database_url):
    """Resolve immutable media/approval evidence without trusting caller metadata."""
    identities = [str(value or "").strip() for value in asset_ids or []]
    database_url = str(
        database_url if database_url is not None
        else os.getenv("DATABASE_URL", "")
    ).strip()
    if not identities or len(set(identities)) != len(identities) or not database_url:
        return {"success": False, "status": "server_media_projection_invalid"}, 409
    try:
        import psycopg
        with psycopg.connect(
            database_url, connect_timeout=10,
            options="-c default_transaction_read_only=on -c statement_timeout=10000",
        ) as connection, connection.cursor() as cursor:
            cursor.execute(
                """select a.asset_id,b.binary_asset_id,b.storage_bucket,b.storage_path,
                          b.content_sha256,b.storage_readback_sha256,b.byte_size,
                          b.observed_mime_type,b.validation_version,
                          la.library_event_id,la.event_type,
                          pu.library_event_id,pu.event_type
                   from public.beacon_media_assets a
                   join public.beacon_media_source_links l on l.beacon_asset_id=a.asset_id
                   join public.beacon_media_binaries b using(binary_asset_id)
                   left join lateral (
                     select library_event_id from public.beacon_media_library_events
                     where binary_asset_id=b.binary_asset_id
                       and event_type in ('library_accepted','library_rejected','archived')
                     order by recorded_at desc,library_event_id desc limit 1
                   ) la on true
                   left join lateral (
                     select library_event_id from public.beacon_media_library_events
                     where binary_asset_id=b.binary_asset_id
                       and event_type in ('public_use_approved','public_use_revoked')
                     order by recorded_at desc,library_event_id desc limit 1
                   ) pu on true
                   where a.asset_id=any(%s)
                     and a.media_type='image'""", (identities,),
            )
            rows = cursor.fetchall()
    except Exception as exc:
        return {"success": False, "status": "server_media_projection_unavailable",
                "error_type": exc.__class__.__name__}, 503
    by_id = {row[0]: row for row in rows}
    if len(rows) != len(identities) or set(by_id) != set(identities):
        return {"success": False, "status": "canonical_media_identity_mismatch"}, 409
    projected = []
    for identity in identities:
        row = by_id[identity]
        if (not row[9] or not row[11] or row[10] != "library_accepted"
                or row[12] != "public_use_approved" or row[4] != row[5]):
            return {"success": False, "status": "server_media_approval_or_readback_missing"}, 409
        projected.append({
            "asset_id": row[0], "binary_asset_id": row[1],
            "storage_bucket": row[2], "storage_path": row[3],
            "content_sha256": row[4], "storage_readback_sha256": row[5],
            "file_size_bytes": int(row[6]), "mime_type": row[7],
            "media_type": "image", "validation_version": row[8],
            "library_accept_event_id": row[9], "public_use_event_id": row[11],
            "effective_public_use_approved": True,
            "content_hash_provenance": "server_stream_and_storage_readback_verified",
            "projection_authority": "server_database_private_binary_v1",
        })
    return {"success": True, "status": "server_media_projection_ready", "assets": projected}, 200


def validate_facebook_image_asset(asset, data, returned_mime="", readback_proof=None, now=None):
    """Validate approval, provenance, bytes, MIME, digest and dimensions."""
    asset = asset if isinstance(asset, dict) else {}
    reasons = []
    if not (
        asset.get("effective_public_use_approved")
        or asset.get("public_use_approved")
    ):
        reasons.append("asset_not_approved_for_public_use")
    proof = readback_proof if isinstance(readback_proof, dict) else {}
    if asset.get("projection_authority") != "server_database_private_binary_v1":
        reasons.append("authoritative_server_projection_required")
    if asset.get("content_hash_provenance") != "server_stream_and_storage_readback_verified":
        reasons.append("trusted_server_hash_required")
    expected_hash = str(asset.get("content_sha256") or "").strip().lower()
    if len(expected_hash) != 64:
        reasons.append("trusted_sha256_required")
    if not isinstance(data, bytes) or not data:
        reasons.append("image_bytes_missing")
        return _validation_result(False, reasons)
    if len(data) > MAX_IMAGE_BYTES:
        reasons.append("image_size_limit_exceeded")

    actual_hash = sha256(data).hexdigest()
    if expected_hash and actual_hash != expected_hash:
        reasons.append("image_hash_mismatch")
    if proof.get("authority") != SERVER_READBACK_AUTHORITY:
        reasons.append("authenticated_private_readback_required")
    if proof.get("trusted_server_hash") != actual_hash:
        reasons.append("trusted_server_hash_mismatch")
    if proof.get("byte_count") != len(data) or asset.get("file_size_bytes") != len(data):
        reasons.append("image_byte_count_mismatch")
    object_identity = f"{asset.get('storage_bucket','')}/{asset.get('storage_path','')}"
    if proof.get("storage_object_identity") != object_identity:
        reasons.append("storage_object_identity_mismatch")
    if not str(proof.get("storage_object_version") or "").strip():
        reasons.append("storage_object_version_required")
    observed_at = _aware_time(proof.get("authenticated_readback_at"))
    current = _aware_time(now) or datetime.now(timezone.utc)
    if not observed_at or not (0 <= (current - observed_at).total_seconds() <= MAX_READBACK_AGE_SECONDS):
        reasons.append("authenticated_readback_stale")

    image_format, width, height = _image_details(data)
    if image_format not in ALLOWED_IMAGE_FORMATS:
        reasons.append("image_format_not_jpeg_or_png")
    if not width or not height:
        reasons.append("image_dimensions_unreadable")
    elif width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
        reasons.append("image_dimensions_limit_exceeded")

    declared_mime = _mime(asset.get("mime_type"))
    returned_mime = _mime(returned_mime)
    allowed_mimes = ALLOWED_IMAGE_FORMATS.get(image_format, set())
    if declared_mime not in allowed_mimes:
        reasons.append("declared_mime_mismatch")
    if returned_mime not in allowed_mimes:
        reasons.append("returned_mime_mismatch")
    if _mime(proof.get("returned_mime")) != returned_mime:
        reasons.append("readback_mime_mismatch")

    return _validation_result(
        not reasons,
        reasons,
        asset_id=asset.get("asset_id", ""),
        image_format=image_format,
        byte_count=len(data),
        width=width,
        height=height,
        declared_mime=declared_mime,
        returned_mime=returned_mime,
        content_sha256=actual_hash,
        binary_asset_id=asset.get("binary_asset_id", ""),
        expected_byte_count=asset.get("file_size_bytes"),
        library_accept_event_id=asset.get("library_accept_event_id", ""),
        public_use_event_id=asset.get("public_use_event_id", ""),
        readback_authority=proof.get("authority", ""),
        authenticated_readback_at=proof.get("authenticated_readback_at", ""),
        storage_object_identity_sha256=sha256(object_identity.encode("utf-8")).hexdigest(),
        storage_object_version_sha256=sha256(
            str(proof.get("storage_object_version") or "").encode("utf-8")
        ).hexdigest(),
    )


def load_supabase_asset_bytes(asset, environ=None, opener=None):
    """Read private storage bytes server-side without generating a signed URL."""
    source = environ if environ is not None else os.environ
    base_url = str(source.get("SUPABASE_URL") or "").strip().rstrip("/")
    service_key = str(source.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    bucket = str((asset or {}).get("storage_bucket") or "").strip()
    path = str((asset or {}).get("storage_path") or "").strip().replace("\\", "/")
    if not base_url or not service_key:
        return {"success": False, "status": "private_storage_not_configured"}, 503
    if not bucket or not path:
        return {"success": False, "status": "asset_storage_reference_missing"}, 400
    endpoint = (
        f"{base_url}/storage/v1/object/authenticated/"
        f"{urllib_parse.quote(bucket, safe='')}/{urllib_parse.quote(path, safe='/')}"
    )
    req = urllib_request.Request(
        endpoint,
        method="GET",
        headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Accept": "image/jpeg,image/png",
        },
    )
    open_fn = opener or urllib_request.build_opener(_RejectRedirects()).open
    try:
        with open_fn(req, timeout=20) as response:
            if (not 200 <= int(response.status) < 300
                    or str(getattr(response, "url", "")) != endpoint):
                return {
                    "success": False,
                    "status": "private_storage_readback_redirect_or_status_rejected",
                    "http_status": response.status,
                }, 409
            content_length = _safe_int(response.headers.get("Content-Length"))
            if content_length and content_length > MAX_IMAGE_BYTES:
                return {
                    "success": False,
                    "status": "image_size_limit_exceeded",
                    "http_status": response.status,
                }, 413
            data = response.read(MAX_IMAGE_BYTES + 1)
            if len(data) > MAX_IMAGE_BYTES:
                return {
                    "success": False,
                    "status": "image_size_limit_exceeded",
                    "http_status": response.status,
                }, 413
            return {
                "success": True,
                "status": "private_storage_image_loaded",
                "http_status": response.status,
                "redirected": False,
                "returned_mime": response.headers.get("Content-Type", ""),
                "data": data,
                "readback_proof": {
                    "authority": SERVER_READBACK_AUTHORITY,
                    "trusted_server_hash": sha256(data).hexdigest(),
                    "byte_count": len(data),
                    "returned_mime": response.headers.get("Content-Type", ""),
                    "storage_object_identity": f"{bucket}/{path}",
                    "storage_object_version": str(
                        response.headers.get("ETag")
                        or response.headers.get("x-supabase-version") or ""
                    ).strip(),
                    "authenticated_readback_at": datetime.now(timezone.utc).isoformat(),
                },
            }, response.status
    except urllib_error.HTTPError as exc:
        return {
            "success": False,
            "status": "private_storage_http_error",
            "http_status": exc.code,
        }, exc.code
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        return {
            "success": False,
            "status": "private_storage_read_failed",
            "error_type": exc.__class__.__name__,
        }, 503


def upload_unpublished_photo_binary(
    page_id,
    token,
    version,
    asset,
    data,
    mime_type,
    *,
    requester=None,
):
    """POST one validated image as multipart source; never retry."""
    boundary = "----BeaconMedia" + uuid.uuid4().hex
    body = _multipart_body(
        boundary,
        fields={"published": "false"},
        filename=f"{asset.get('asset_id', 'beacon-image')}.{_extension(mime_type)}",
        mime_type=mime_type,
        data=data,
    )
    endpoint = (
        f"https://graph.facebook.com/{urllib_parse.quote(version, safe='')}/"
        f"{urllib_parse.quote(page_id, safe='')}/photos"
    )
    req = urllib_request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    return _meta_request(req, "facebook_binary_photo_upload_failed", requester)


def create_multi_photo_feed(
    page_id,
    token,
    version,
    caption,
    media_ids,
    *,
    requester=None,
):
    endpoint = (
        f"https://graph.facebook.com/{urllib_parse.quote(version, safe='')}/"
        f"{urllib_parse.quote(page_id, safe='')}/feed"
    )
    fields = {"message": caption}
    for index, media_id in enumerate(media_ids):
        fields[f"attached_media[{index}]"] = json.dumps({"media_fbid": media_id})
    req = urllib_request.Request(
        endpoint,
        data=urllib_parse.urlencode(fields).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
    )
    return _meta_request(req, "facebook_multi_photo_post_failed", requester)


def manual_composer_handoff(params, validations, reason):
    """Return exact recoverable owner handoff without URLs or credentials."""
    selected = params.get("selected_assets") or []
    safe_validations = [
        {
            key: item.get(key)
            for key in (
                "asset_id", "position", "allowed", "status", "reasons",
                "image_format", "byte_count", "width", "height",
                "declared_mime", "returned_mime",
            )
            if key in item
        }
        for item in validations
        if isinstance(item, dict)
    ]
    return {
        "mode": "beacon_manual_facebook_composer_handoff",
        "status": "manual_composer_required",
        "reason": reason,
        "publish_packet_id": params.get("publish_packet_id", ""),
        "caption": params.get("exact_text", ""),
        "caption_sha256": sha256(
            str(params.get("exact_text") or "").encode("utf-8")
        ).hexdigest(),
        "asset_order": [item.get("asset_id", "") for item in selected],
        "asset_validations": safe_validations,
        "uses_existing_approved_assets": True,
        "automatic_attempt_reusable": False,
        "requires_new_manual_composer_session": True,
        "signed_urls_exposed": False,
        "credentials_exposed": False,
        "publishes_now": False,
        "calls_meta_now": False,
    }


def _meta_request(req, failure_status, requester=None):
    open_fn = requester or urllib_request.urlopen
    try:
        with open_fn(req, timeout=35) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
            return {"success": True, **payload}, response.status
    except urllib_error.HTTPError as exc:
        return {
            "success": False,
            "status": failure_status,
            "http_status": exc.code,
            "meta_error": _safe_meta_error(exc.read()),
            "outcome": "definite_failure",
        }, exc.code
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        return {
            "success": False,
            "status": failure_status,
            "error_type": exc.__class__.__name__,
            "outcome": "ambiguous",
        }, 502
    except (ValueError, json.JSONDecodeError):
        return {
            "success": False,
            "status": "facebook_response_malformed",
            "outcome": "ambiguous",
        }, 502


def _image_details(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return "png", width, height
    if data.startswith(b"\xff\xd8\xff"):
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(data):
                break
            length = struct.unpack(">H", data[index:index + 2])[0]
            if marker in {
                0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
            } and index + 7 <= len(data):
                height, width = struct.unpack(">HH", data[index + 3:index + 7])
                return "jpeg", width, height
            if length < 2:
                break
            index += length
        return "jpeg", 0, 0
    if data.startswith((b"RIFF", b"\x00\x00\x00\x18ftypheic", b"\x00\x00\x00\x18ftypheix")):
        return "webp_or_heic", 0, 0
    return "unknown", 0, 0


def _multipart_body(boundary, fields, filename, mime_type, data):
    chunks = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode(),
            b"\r\n",
        ])
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="source"; '
            f'filename="{filename}"\r\n'
        ).encode(),
        f"Content-Type: {mime_type}\r\n\r\n".encode(),
        data,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return b"".join(chunks)


def _safe_meta_error(raw):
    try:
        body = json.loads(raw.decode("utf-8", errors="replace") or "{}")
    except (ValueError, json.JSONDecodeError):
        return {"type": "", "code": None, "subcode": None}
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    return {
        "type": str(error.get("type") or "")[:80],
        "code": error.get("code"),
        "subcode": error.get("error_subcode"),
        "message": str(error.get("message") or "")[:160],
    }


def _validation_result(allowed, reasons, **details):
    return {
        "allowed": bool(allowed),
        "status": "validated" if allowed else "rejected",
        "reasons": sorted(set(reasons)),
        **details,
    }


def _mime(value):
    return str(value or "").split(";", 1)[0].strip().lower()


def _extension(mime_type):
    return "png" if _mime(mime_type) == "image/png" else "jpg"


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _aware_time(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
