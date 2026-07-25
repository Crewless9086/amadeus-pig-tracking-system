"""Append-only exact owner decisions for Beacon weekly review packets."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import os

from modules.beacon.media_library import list_beacon_media_assets
from modules.beacon.weekly_owner_review import (
    PACKET_ID,
    SUPERSEDED_PACKET_ID,
    build_post_one_owner_review,
    load_post_one_thumbnail,
)


DECISIONS = {
    "approve": "owner_approved",
    "request_changes": "changes_requested",
    "reject": "owner_rejected",
}
AUTHORITY = {
    "publish": False,
    "meta_call": False,
    "upload": False,
    "scheduled": False,
    "send": False,
    "spend": False,
    "business_data_mutation": False,
}


def record_weekly_owner_review_decision(
    payload, *, owner_identity, database_url=None, environ=None
):
    """Re-read, revalidate and append one exact packet decision."""
    payload = payload if isinstance(payload, dict) else {}
    owner_identity = _clean(owner_identity, 180)
    if not owner_identity:
        return _failure("owner_identity_required", 403)
    decision = _clean(payload.get("decision"), 40).lower()
    decision_status = DECISIONS.get(decision)
    if not decision_status:
        return _failure("owner_review_decision_invalid", 400)
    if _clean(payload.get("packet_id"), 160) == SUPERSEDED_PACKET_ID:
        return _failure("weekly_owner_review_packet_superseded", 409)
    database_url = _database_url(database_url)
    if not database_url:
        return _failure("weekly_owner_review_persistence_unavailable", 503)

    assets_result, assets_status = list_beacon_media_assets(
        limit=100, database_url=database_url
    )
    if assets_status != 200:
        return _failure("weekly_owner_review_evidence_unavailable", 503)
    packet = build_post_one_owner_review(assets_result.get("assets", []))
    mismatch = _packet_mismatch(payload, packet)
    if mismatch:
        return _failure(mismatch, 409)
    if packet.get("review_status") != "awaiting_exact_owner_review":
        return _failure("weekly_owner_review_packet_not_reviewable", 409)
    if not packet.get("public_livestock_policy", {}).get("allowed"):
        return _failure("weekly_owner_review_policy_failed", 409)
    for asset_id in packet["media"]["exact_order"]:
        validated, status = load_post_one_thumbnail(
            asset_id,
            database_url=database_url,
            environ=environ,
        )
        if status != 200 or not validated.get("success"):
            return _failure("weekly_owner_review_asset_drift", 409)

    notes = _clean_multiline(payload.get("owner_notes"), 1200)
    if decision == "request_changes" and not notes:
        return _failure("owner_change_notes_required", 400)
    proposed_at = _clean(payload.get("proposed_publication_datetime"), 80)
    proposed_timezone = _clean(payload.get("proposed_timezone"), 80)
    if proposed_at and (not proposed_timezone or not _valid_local_datetime(proposed_at)):
        return _failure("proposed_publication_datetime_invalid", 400)
    params = _decision_params(
        packet,
        decision_status,
        notes,
        owner_identity,
        proposed_at,
        proposed_timezone,
    )
    try:
        import psycopg
    except ImportError:
        return _failure("weekly_owner_review_persistence_unavailable", 503)
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                existing = _read_decision(cursor, packet["packet_id"])
                if existing:
                    return _existing_result(existing, params)
                cursor.execute(
                    """
                    insert into public.beacon_weekly_review_decision_events (
                        decision_event_id, packet_id, packet_version,
                        canonical_sha256, caption_sha256, exact_caption,
                        ordered_media_ids_json, owner_confirmed_subject,
                        album_story, channel, proposed_publication_datetime,
                        proposed_timezone, supersedes_packet_id, decision_status,
                        owner_notes, owner_identity, decision_at
                    ) values (
                        %(decision_event_id)s, %(packet_id)s, %(packet_version)s,
                        %(canonical_sha256)s, %(caption_sha256)s, %(exact_caption)s,
                        %(ordered_media_ids_json)s::jsonb,
                        %(owner_confirmed_subject)s, %(album_story)s, %(channel)s,
                        %(proposed_publication_datetime)s, %(proposed_timezone)s,
                        %(supersedes_packet_id)s, %(decision_status)s,
                        %(owner_notes)s, %(owner_identity)s, %(decision_at)s
                    )
                    """,
                    params,
                )
            connection.commit()
    except Exception as exc:
        if _is_unique_conflict(exc):
            try:
                existing = _load_one(packet["packet_id"], database_url)
                if existing:
                    return _existing_result(existing, params)
            except Exception:
                pass
        return _failure("weekly_owner_review_persistence_failed", 503)
    return _success(params, "owner_review_decision_recorded"), 201


def get_weekly_owner_review_decision(packet_id=PACKET_ID, *, database_url=None):
    """Read the one immutable decision for the current packet."""
    database_url = _database_url(database_url)
    if not database_url:
        return None, "persistence_unavailable"
    try:
        item = _load_one(packet_id, database_url)
    except Exception:
        return None, "persistence_unavailable"
    return item, "recorded" if item else "awaiting_exact_owner_review"


def _load_one(packet_id, database_url):
    import psycopg

    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            return _read_decision(cursor, packet_id)


def _read_decision(cursor, packet_id):
    cursor.execute(
        """
        select decision_event_id, packet_id, packet_version, canonical_sha256,
               caption_sha256, exact_caption, ordered_media_ids_json,
               owner_confirmed_subject, album_story, channel,
               proposed_publication_datetime, proposed_timezone,
               supersedes_packet_id, decision_status, owner_notes,
               owner_identity, decision_at
        from public.beacon_weekly_review_decision_events
        where packet_id = %s
        order by decision_at desc
        limit 1
        """,
        (packet_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    result = {
        "decision_event_id": row[0],
        "packet_id": row[1],
        "packet_version": row[2],
        "canonical_sha256": row[3],
        "caption_sha256": row[4],
        "exact_caption": row[5],
        "ordered_media_ids": row[6] if isinstance(row[6], list) else [],
        "owner_confirmed_subject": row[7],
        "album_story": row[8],
        "channel": row[9],
        "proposed_publication_datetime": row[10],
        "proposed_timezone": row[11],
        "supersedes_packet_id": row[12],
        "decision_status": row[13],
        "owner_notes": row[14],
        "owner_identity": row[15],
        "decision_at": row[16].isoformat() if hasattr(row[16], "isoformat") else str(row[16]),
        "publication_authority_status": "publication_not_authorized",
        **AUTHORITY,
    }
    result["next_gate"] = _next_gate(result["decision_status"])
    return result


def _packet_mismatch(payload, packet):
    media = packet.get("media", {}).get("assets", [])
    expected = {
        "packet_id": packet.get("packet_id"),
        "packet_version": "S1",
        "canonical_sha256": packet.get("canonical_sha256"),
        "caption_sha256": packet.get("caption_sha256"),
        "exact_caption": packet.get("caption"),
        "ordered_media_ids": packet.get("media", {}).get("exact_order"),
        "owner_confirmed_subject": (
            media[0].get("owner_confirmed_subject") if media else ""
        ),
        "album_story": packet.get("album_story"),
        "channel": packet.get("channel"),
        "supersedes_packet_id": packet.get("supersedes", {}).get("packet_id"),
    }
    statuses = {
        "packet_id": "weekly_owner_review_packet_mismatch",
        "packet_version": "weekly_owner_review_packet_version_mismatch",
        "canonical_sha256": "weekly_owner_review_hash_mismatch",
        "caption_sha256": "weekly_owner_review_caption_hash_mismatch",
        "exact_caption": "weekly_owner_review_caption_changed",
        "ordered_media_ids": "weekly_owner_review_media_order_changed",
        "owner_confirmed_subject": "weekly_owner_review_subject_changed",
        "album_story": "weekly_owner_review_album_changed",
        "channel": "weekly_owner_review_channel_changed",
        "supersedes_packet_id": "weekly_owner_review_supersession_changed",
    }
    for key, value in expected.items():
        supplied = payload.get(key)
        if key == "ordered_media_ids":
            supplied = supplied if isinstance(supplied, list) else []
        if supplied != value:
            return statuses[key]
    return ""


def _decision_params(packet, status, notes, owner, proposed_at, timezone_name):
    media = packet["media"]["assets"]
    subject = media[0]["owner_confirmed_subject"] if media else ""
    seed = {
        "packet_id": packet["packet_id"],
        "canonical_sha256": packet["canonical_sha256"],
        "decision_status": status,
        "proposed_publication_datetime": proposed_at,
        "proposed_timezone": timezone_name,
        "owner_notes": notes,
    }
    return {
        "decision_event_id": "BEACON-WEEKLY-REVIEW-" + _digest(seed)[:24].upper(),
        "packet_id": packet["packet_id"],
        "packet_version": "S1",
        "canonical_sha256": packet["canonical_sha256"],
        "caption_sha256": packet["caption_sha256"],
        "exact_caption": packet["caption"],
        "ordered_media_ids_json": json.dumps(packet["media"]["exact_order"]),
        "ordered_media_ids": packet["media"]["exact_order"],
        "owner_confirmed_subject": subject,
        "album_story": packet["album_story"],
        "channel": packet["channel"],
        "proposed_publication_datetime": proposed_at,
        "proposed_timezone": timezone_name,
        "supersedes_packet_id": packet["supersedes"]["packet_id"],
        "decision_status": status,
        "owner_notes": notes,
        "owner_identity": owner,
        "decision_at": datetime.now(timezone.utc).isoformat(),
    }


def _existing_result(existing, requested):
    same = all(
        existing.get(key) == requested.get(key)
        for key in (
            "canonical_sha256",
            "caption_sha256",
            "decision_status",
            "owner_notes",
            "proposed_publication_datetime",
            "proposed_timezone",
        )
    )
    if same:
        result = dict(existing)
        result.update(
            success=True,
            status="duplicate_owner_decision_withheld",
            duplicate_withheld=True,
            next_gate=_next_gate(existing["decision_status"]),
        )
        return result, 200
    return _failure("conflicting_owner_decision_exists", 409)


def _success(params, status):
    return {
        "success": True,
        "status": status,
        "decision_event_id": params["decision_event_id"],
        "packet_id": params["packet_id"],
        "canonical_sha256": params["canonical_sha256"],
        "caption_sha256": params["caption_sha256"],
        "decision_status": params["decision_status"],
        "owner_identity": params["owner_identity"],
        "decision_at": params["decision_at"],
        "owner_notes": params["owner_notes"],
        "proposed_publication_datetime": params["proposed_publication_datetime"],
        "proposed_timezone": params["proposed_timezone"],
        "publication_authority_status": "publication_not_authorized",
        "next_gate": _next_gate(params["decision_status"]),
        **AUTHORITY,
    }


def _next_gate(status):
    if status == "owner_approved":
        return "Approved for a separately authorized one-attempt publication"
    if status == "changes_requested":
        return "A new packet and hash are required before another owner review"
    return "Post rejected; publication remains prohibited"


def _failure(status, code):
    return {
        "success": False,
        "status": status,
        "publication_authority_status": "publication_not_authorized",
        **AUTHORITY,
    }, code


def _database_url(database_url):
    return str(
        database_url if database_url is not None else os.getenv("DATABASE_URL", "")
    ).strip()


def _valid_local_datetime(value):
    try:
        datetime.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def _clean(value, limit):
    return " ".join(str(value or "").strip().split())[:limit]


def _clean_multiline(value, limit):
    return "\n".join(
        line.strip() for line in str(value or "").strip().splitlines()
    )[:limit]


def _digest(value):
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _is_unique_conflict(exc):
    return getattr(exc, "sqlstate", "") == "23505"
