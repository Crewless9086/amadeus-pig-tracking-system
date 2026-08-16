"""Durable exact binding between owner review and organic publication packets."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import os

from modules.beacon.media_library import list_beacon_media_assets
from modules.beacon.organic_publication_authorization import (
    canonical_caption_text,
    caption_sha256,
    read_authorized_generation,
)
from modules.beacon.weekly_owner_review import build_post_one_owner_review
from modules.beacon.text_only_organic_review import (
    PACKET_CLASS as TEXT_ONLY_PACKET_CLASS,
    load_text_only_owner_review,
    validate_text_only_owner_review,
)


BINDING_VERSION = "beacon-organic-publication-binding/v1"


def create_organic_publication_binding(
    execution_packet, *, target_page_id, database_url=None, now=None,
):
    """Reconstruct both rails and append their exact one-to-one binding."""
    execution_packet = execution_packet if isinstance(execution_packet, dict) else {}
    database_url = _database_url(database_url)
    target_page_id = _text(target_page_id, 180)
    if not database_url or not target_page_id:
        return _failure("publication_binding_configuration_missing", 503)
    if execution_packet.get("packet_class") == TEXT_ONLY_PACKET_CLASS:
        weekly = load_text_only_owner_review(
            _text(execution_packet.get("weekly_packet_id"), 180),
            database_url=database_url,
        )
        validation = validate_text_only_owner_review(weekly)
        if validation:
            return _failure(validation, 409)
        if target_page_id != weekly.get("page_id"):
            return _failure("publication_binding_target_drift", 409)
    else:
        assets_result, assets_status = list_beacon_media_assets(
            limit=100, approval_status="approved", database_url=database_url
        )
        if assets_status != 200:
            return _failure("publication_binding_media_unavailable", 503)
        weekly = build_post_one_owner_review(assets_result.get("assets", []))
    mismatch = _execution_packet_mismatch(weekly, execution_packet)
    if mismatch:
        return _failure(mismatch, 409)
    try:
        import psycopg
    except ImportError:
        return _failure("publication_binding_persistence_unavailable", 503)
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                decision = _read_decision(cursor, weekly["packet_id"])
                if not decision or decision["decision_status"] != "owner_approved":
                    return _failure("publication_binding_owner_approval_required", 409)
                decision_mismatch = _decision_mismatch(decision, weekly)
                if decision_mismatch:
                    return _failure(decision_mismatch, 409)
                params = _binding_params(
                    weekly, decision, execution_packet, target_page_id, now
                )
                existing = _read_binding_by_weekly(cursor, weekly["packet_id"])
                if existing:
                    if _binding_equal(existing, params):
                        return {
                            "success": True,
                            "status": "publication_binding_replay_withheld",
                            "created_count": 0,
                            "binding": _public_binding(existing),
                            **_no_action(),
                        }, 200
                    return _failure("publication_binding_conflict", 409)
                cursor.execute(
                    """
                    insert into public.beacon_organic_publication_bindings (
                        binding_id, binding_version, weekly_packet_id,
                        owner_decision_event_id, execution_publish_packet_id,
                        canonical_sha256, caption_sha256, media_order_sha256,
                        exact_media_order_json, owner_confirmed_subject,
                        channel, target_page_id, bound_at
                    ) values (
                        %(binding_id)s, %(binding_version)s,
                        %(weekly_packet_id)s, %(owner_decision_event_id)s,
                        %(execution_publish_packet_id)s, %(canonical_sha256)s,
                        %(caption_sha256)s, %(media_order_sha256)s,
                        %(exact_media_order_json)s::jsonb,
                        %(owner_confirmed_subject)s, %(channel)s,
                        %(target_page_id)s, %(bound_at)s
                    )
                    """,
                    params,
                )
        return {
            "success": True,
            "status": "publication_binding_created",
            "created_count": 1,
            "binding": _public_binding(params),
            **_no_action(),
        }, 201
    except Exception as exc:
        return {
            **_failure("publication_binding_append_failed", 503)[0],
            "error_type": exc.__class__.__name__,
        }, 503


def require_organic_publication_binding(
    params, *, target_page_id, database_url=None
):
    """Fail closed unless execution exactly matches one durable approved binding."""
    params = params if isinstance(params, dict) else {}
    database_url = _database_url(database_url)
    if not database_url:
        return _failure("publication_binding_persistence_unavailable", 503)
    try:
        import psycopg
    except ImportError:
        return _failure("publication_binding_persistence_unavailable", 503)
    try:
        with psycopg.connect(
            database_url,
            connect_timeout=10,
            options="-c default_transaction_read_only=on -c statement_timeout=10000",
        ) as connection:
            with connection.cursor() as cursor:
                binding = _read_binding_by_execution(
                    cursor, params.get("publish_packet_id")
                )
                if not binding:
                    return _failure("organic_publication_packet_unbound", 409)
                decision = _read_decision(cursor, binding["weekly_packet_id"])
                authorization = read_authorized_generation(
                    cursor,
                    params.get("authorization_generation_id"),
                    binding["binding_id"],
                )
    except Exception as exc:
        return {
            **_failure("publication_binding_read_failed", 503)[0],
            "error_type": exc.__class__.__name__,
        }, 503
    mismatch = _runtime_mismatch(binding, decision, params, target_page_id)
    if mismatch:
        return _failure(mismatch, 409)
    if not authorization:
        return _failure("organic_publication_authorization_required", 409)
    return {
        "success": True,
        "status": "organic_publication_binding_verified",
        "binding": _public_binding(binding),
        "authorization": authorization,
        **_no_action(),
    }, 200


def _execution_packet_mismatch(weekly, execution):
    selected = execution.get("selected_draft") or {}
    order = [
        item.get("asset_id")
        for item in execution.get("selected_assets", [])
        if isinstance(item, dict)
    ]
    checks = (
        (weekly.get("review_status") == "awaiting_exact_owner_review",
         "publication_binding_weekly_packet_not_reviewable"),
        (selected.get("exact_text") == weekly.get("caption"),
         "publication_binding_caption_mismatch"),
        (order == weekly.get("media", {}).get("exact_order"),
         "publication_binding_media_order_mismatch"),
        (_text(execution.get("publish_packet_id"), 160) != "",
         "publication_binding_execution_packet_required"),
        (execution.get("campaign_lane") == "live_stock_awareness",
         "publication_binding_channel_mismatch"),
    )
    if weekly.get("packet_class") == TEXT_ONLY_PACKET_CLASS:
        checks += (
            (execution.get("packet_class") == TEXT_ONLY_PACKET_CLASS,
             "publication_binding_packet_class_mismatch"),
            (execution.get("weekly_packet_id") == weekly.get("packet_id"),
             "publication_binding_weekly_packet_mismatch"),
            (execution.get("canonical_sha256") == weekly.get("canonical_sha256"),
             "publication_binding_canonical_hash_mismatch"),
            (order == [], "publication_binding_text_only_media_forbidden"),
            (execution.get("owner_confirmed_subject") == "",
             "publication_binding_text_only_subject_forbidden"),
            (execution.get("target_page_id") == weekly.get("page_id"),
             "publication_binding_target_drift"),
        )
    return next((status for allowed, status in checks if not allowed), "")


def _decision_mismatch(decision, weekly):
    assets = weekly.get("media", {}).get("assets", [])
    subject = assets[0].get("owner_confirmed_subject") if assets else ""
    checks = (
        (decision["canonical_sha256"] == weekly["canonical_sha256"],
         "publication_binding_canonical_hash_mismatch"),
        (decision["caption_sha256"] == weekly["caption_sha256"],
         "publication_binding_caption_hash_mismatch"),
        (decision["exact_caption"] == weekly["caption"],
         "publication_binding_caption_mismatch"),
        (decision["exact_media_order"] == weekly["media"]["exact_order"],
         "publication_binding_media_order_mismatch"),
        (decision["owner_confirmed_subject"] == subject,
         "publication_binding_subject_mismatch"),
        (decision["channel"] == weekly["channel"],
         "publication_binding_channel_mismatch"),
    )
    return next((status for allowed, status in checks if not allowed), "")


def _runtime_mismatch(binding, decision, params, target_page_id):
    if not decision or decision["decision_status"] != "owner_approved":
        return "organic_publication_owner_approval_missing"
    order = [
        item.get("asset_id")
        for item in params.get("selected_assets", [])
        if isinstance(item, dict)
    ]
    checks = (
        (decision["canonical_sha256"] == binding["canonical_sha256"],
         "organic_publication_binding_stale"),
        (decision["caption_sha256"] == binding["caption_sha256"],
         "organic_publication_binding_stale"),
        (caption_sha256(params.get("exact_text", ""))
         == binding["caption_sha256"], "organic_publication_caption_drift"),
        (order == binding["exact_media_order"],
         "organic_publication_media_order_drift"),
        (_media_order_hash(order) == binding["media_order_sha256"],
         "organic_publication_media_hash_drift"),
        (_text(target_page_id, 180) == binding["target_page_id"],
         "organic_publication_target_drift"),
        ("facebook" in _text(params.get("channel"), 80).lower(),
         "organic_publication_channel_drift"),
    )
    return next((status for allowed, status in checks if not allowed), "")


def _binding_params(weekly, decision, execution, target_page_id, now):
    order = weekly["media"]["exact_order"]
    seed = {
        "binding_version": BINDING_VERSION,
        "weekly_packet_id": weekly["packet_id"],
        "owner_decision_event_id": decision["decision_event_id"],
        "execution_publish_packet_id": execution["publish_packet_id"],
        "canonical_sha256": weekly["canonical_sha256"],
        "caption_sha256": weekly["caption_sha256"],
        "media_order_sha256": _media_order_hash(order),
        "target_page_id": target_page_id,
    }
    digest = sha256(_canonical(seed)).hexdigest().upper()
    return {
        **seed,
        "binding_id": "BEACON-ORGANIC-BINDING-" + digest[:24],
        "exact_media_order": order,
        "exact_media_order_json": json.dumps(order, separators=(",", ":")),
        "owner_confirmed_subject": (
            weekly["media"]["assets"][0]["owner_confirmed_subject"]
            if weekly["media"]["assets"] else ""
        ),
        "channel": "Facebook Page",
        "bound_at": (now or datetime.now(timezone.utc)).isoformat(),
    }


def _read_decision(cursor, weekly_packet_id):
    cursor.execute(
        """
        select decision_event_id, decision_status, canonical_sha256,
               caption_sha256, exact_caption, ordered_media_ids_json,
               owner_confirmed_subject, channel
        from public.beacon_weekly_review_decision_events
        where packet_id=%s
        """,
        (_text(weekly_packet_id, 160),),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "decision_event_id": row[0], "decision_status": row[1],
        "canonical_sha256": row[2], "caption_sha256": row[3],
        "exact_caption": row[4], "exact_media_order": row[5],
        "owner_confirmed_subject": row[6], "channel": row[7],
    }


def _read_binding_by_weekly(cursor, packet_id):
    return _read_binding(cursor, "weekly_packet_id", packet_id)


def _read_binding_by_execution(cursor, packet_id):
    return _read_binding(cursor, "execution_publish_packet_id", packet_id)


def _read_binding(cursor, column, value):
    cursor.execute(
        f"""
        select binding_id, binding_version, weekly_packet_id,
               owner_decision_event_id, execution_publish_packet_id,
               canonical_sha256, caption_sha256, media_order_sha256,
               exact_media_order_json, owner_confirmed_subject, channel,
               target_page_id, bound_at
        from public.beacon_organic_publication_bindings
        where {column}=%s
        """,
        (_text(value, 180),),
    )
    row = cursor.fetchone()
    if not row:
        return None
    keys = (
        "binding_id", "binding_version", "weekly_packet_id",
        "owner_decision_event_id", "execution_publish_packet_id",
        "canonical_sha256", "caption_sha256", "media_order_sha256",
        "exact_media_order", "owner_confirmed_subject", "channel",
        "target_page_id", "bound_at",
    )
    return dict(zip(keys, row))


def _binding_equal(existing, params):
    keys = (
        "binding_id", "binding_version", "weekly_packet_id",
        "owner_decision_event_id", "execution_publish_packet_id",
        "canonical_sha256", "caption_sha256", "media_order_sha256",
        "owner_confirmed_subject", "channel", "target_page_id",
    )
    return all(existing.get(key) == params.get(key) for key in keys) and (
        existing["exact_media_order"] == params["exact_media_order"]
    )


def _public_binding(binding):
    return {
        key: (
            value.isoformat() if hasattr(value, "isoformat") else value
        )
        for key, value in binding.items()
        if key != "exact_media_order_json"
    }


def _media_order_hash(order):
    return sha256(_canonical(list(order or []))).hexdigest()


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _database_url(value):
    return str(value if value is not None else os.getenv("DATABASE_URL", "")).strip()


def _text(value, limit):
    return str(value or "").strip()[:limit]


def _failure(status, code):
    return {
        "success": False, "status": status, **_no_action()
    }, code


def _no_action():
    return {
        "publish": False, "upload": False, "scheduled": False,
        "meta_call": False, "boost": False, "advert": False, "spend": False,
    }
