"""Exact successor identity and fresh timing gate for the contained BEACON proposal."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import os

PROPOSAL_ID = "BEACON-PROPOSAL-18DEAAD8E896A87FE961F45B"
SUCCESSOR_EXECUTION_ID = "BEACON-PUBLICATION-EXECUTION-928F7D5A9731FFDE3D62CE1A"
PUBLISH_NOW_EXECUTION_ID = "BEACON-PUBLICATION-EXECUTION-46D1D86994D3483F6404CEDA"
PUBLISH_NOW_AUTHORITY_ID = "OOM-BEACON-PUBLISH-NOW-20260801"
AUTHORITY_MODES = frozenset({"publish_now", "scheduled_exact"})
PUBLISH_NOW_TERMINAL_STATES = frozenset({
    "owner_cancelled", "evidence_invalidated", "provider_ambiguous",
    "provider_confirmed",
})
TERMINAL_EXECUTION_IDS = frozenset({
    "BEACON-FB-POST-A3E2BBED0CEA5F93E2",
    "BEACON-FB-POST-A3E2BBED0CEA5F93E2-RESULT",
    "BEACON-FB-POST-E29F04C57CA75EEDC0",
})
ASSET_ID = "BEACON-ASSET-15EBF5E67DBFD12693"
ASSET_SHA256 = "15ebf5e67dbfd12693bab79464c7012d221c4686207a730dac3161e097048b55"
CAPTION_SHA256 = "58a60223599365b90803570909e09f3828c32768d8b27470dc1304ff27fc17d4"


def validate_successor_execution(
    payload, *, now=None, authoritative_timing_authorization_id=None
):
    """Require one newly timed authority for the exact preserved publication."""
    if any(str(payload.get(key) or "") in TERMINAL_EXECUTION_IDS for key in (
            "publish_packet_id", "execution_event_id",
            "publication_execution_identity")):
        return "terminal_publication_execution_non_reusable"
    if str(payload.get("publish_packet_id") or "") != PROPOSAL_ID:
        return ""
    authority_mode = str(payload.get("publication_authority_mode") or "scheduled_exact")
    if authority_mode not in AUTHORITY_MODES:
        return "successor_publication_authority_mode_invalid"
    expected_execution = (
        PUBLISH_NOW_EXECUTION_ID
        if authority_mode == "publish_now" else SUCCESSOR_EXECUTION_ID
    )
    if payload.get("publication_execution_identity") != expected_execution:
        return "successor_publication_execution_identity_required"
    if payload.get("asset_id") != ASSET_ID:
        return "successor_publication_asset_mismatch"
    selected = payload.get("selected_assets")
    if not isinstance(selected, list):
        selected = [payload.get("selected_asset")] if isinstance(
            payload.get("selected_asset"), dict
        ) else []
    if (len(selected) != 1 or selected[0].get("asset_id") != ASSET_ID
            or str(selected[0].get("media_type") or "").lower() != "image"):
        return "successor_publication_media_order_mismatch"
    selected_hash = (
        selected[0].get("storage_readback_sha256")
        or selected[0].get("content_sha256")
    )
    if selected_hash != ASSET_SHA256:
        return "successor_publication_asset_hash_mismatch"
    caption = payload.get("exact_text") if isinstance(payload.get("exact_text"), str) else ""
    if sha256(caption.encode("utf-8")).hexdigest() != CAPTION_SHA256:
        return "successor_publication_caption_mismatch"
    if payload.get("channel") != "facebook_organic":
        return "successor_publication_channel_mismatch"
    if payload.get("zero_spend") is not True:
        return "successor_publication_zero_spend_required"
    if not str(payload.get("publication_authority_id") or payload.get("timing_authorization_id") or "").strip():
        return "successor_publication_timing_authorization_required"
    if authority_mode == "publish_now":
        if payload.get("publication_authority_id") != PUBLISH_NOW_AUTHORITY_ID:
            return "successor_publish_now_authority_mismatch"
        if str(payload.get("publication_authority_state") or "") != "active":
            return "successor_publish_now_authority_not_actionable"
        return ""
    if (authoritative_timing_authorization_id is not None
            and payload.get("timing_authorization_id")
            != authoritative_timing_authorization_id):
        return "successor_publication_timing_authorization_mismatch"
    start = _time(payload.get("timing_start")); end = _time(payload.get("timing_end"))
    current = _time(now) or datetime.now(timezone.utc)
    if not start or not end or not start <= current <= end or end <= start:
        return "successor_publication_timing_window_invalid"
    return ""


def require_publish_now_authority(database_url=None):
    """Read the latest durable owner authority state; caller fields are not authority."""
    database_url = str(database_url if database_url is not None else os.getenv("DATABASE_URL", "")).strip()
    if not database_url:
        return {"success": False, "status": "publish_now_authority_persistence_unavailable"}, 503
    try:
        import psycopg
        with psycopg.connect(
            database_url, connect_timeout=10,
            options="-c default_transaction_read_only=on -c statement_timeout=10000",
        ) as connection, connection.cursor() as cursor:
            cursor.execute("""
                select review_event_id, review_json, created_at
                  from public.sam_live_stock_conversation_review_events
                 where review_json->'beacon_publish_now_authority'->>'authority_id'=%s
                 order by created_at desc, review_event_id desc
            """, (PUBLISH_NOW_AUTHORITY_ID,))
            rows = cursor.fetchall()
    except Exception as exc:
        return {"success": False, "status": "publish_now_authority_read_failed",
                "error_type": exc.__class__.__name__}, 503
    if not rows:
        return {"success": False, "status": "publish_now_authority_missing"}, 409
    try:
        review = rows[0][1] if isinstance(rows[0][1], dict) else json.loads(rows[0][1])
        if not isinstance(review, dict):
            raise ValueError("review_json_not_object")
        authority = review.get("beacon_publish_now_authority") or {}
        if not isinstance(authority, dict):
            raise ValueError("authority_not_object")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"success": False, "status": "publish_now_authority_malformed"}, 409
    expected = {
        "authority_id": PUBLISH_NOW_AUTHORITY_ID,
        "authority_mode": "publish_now", "authority_state": "active",
        "proposal_identity": PROPOSAL_ID,
        "publication_execution_identity": PUBLISH_NOW_EXECUTION_ID,
        "asset_identity": ASSET_ID, "asset_sha256": ASSET_SHA256,
        "caption_sha256": CAPTION_SHA256, "channel": "facebook_organic",
        "zero_spend": True,
    }
    if any(authority.get(key) != value for key, value in expected.items()):
        return {"success": False, "status": "publish_now_authority_not_actionable"}, 409
    return {"success": True, "status": "publish_now_authority_verified",
            "authority_event_id": rows[0][0], "authority": authority}, 200


def _time(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)
