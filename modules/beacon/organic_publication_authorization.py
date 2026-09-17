"""Append-only authorization generations for one-attempt organic publication."""

from hashlib import sha256
import json
import os


AUTHORIZATION_VERSION = "beacon-organic-publication-authorization/v1"
STATUSES = {
    "awaiting_owner_authorization",
    "owner_authorized",
    "closed_pre_meta_caption_drift",
    "attempt_claimed",
    "contained",
    "confirmed",
}


def canonical_caption_text(value):
    """Canonicalize line endings only; preserve every other text code point."""
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError("canonical_caption_invalid")
    return value.replace("\r\n", "\n").replace("\r", "\n")


def caption_sha256(value):
    return sha256(canonical_caption_text(value).encode("utf-8")).hexdigest()


def payload_sha256(payload):
    return sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def authorization_generation_identity(binding_id, payload_hash, created_at):
    seed = f"{binding_id}\0{payload_hash}\0{created_at}"
    return "BEACON-ORGANIC-AUTH-" + sha256(seed.encode()).hexdigest()[:24].upper()


def append_authorization_event(
    event,
    *,
    database_url=None,
):
    """Append one exact state event; identical replay is withheld."""
    event = event if isinstance(event, dict) else {}
    database_url = str(
        database_url if database_url is not None
        else os.getenv("DATABASE_URL", "")
    ).strip()
    required = (
        "authorization_event_id", "authorization_generation_id", "binding_id",
        "event_status", "transport_sha256", "payload_sha256",
        "expected_attempt_identity",
    )
    if not database_url or any(not str(event.get(key) or "") for key in required):
        return _failure("publication_authorization_event_invalid", 400)
    if event["event_status"] not in STATUSES:
        return _failure("publication_authorization_status_invalid", 400)
    try:
        import psycopg
    except ImportError:
        return _failure("publication_authorization_persistence_unavailable", 503)
    params = {
        key: str(event.get(key) or "")[:240]
        for key in required
    }
    params.update({
        "authorization_version": AUTHORIZATION_VERSION,
        "predecessor_generation_id": str(
            event.get("predecessor_generation_id") or ""
        )[:160],
        "reason": str(event.get("reason") or "")[:240],
    })
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select authorization_event_id, authorization_version,
                           authorization_generation_id, binding_id,
                           event_status, transport_sha256, payload_sha256,
                           expected_attempt_identity,
                           predecessor_generation_id, reason, created_at
                    from public.beacon_organic_publication_authorization_events
                    where authorization_event_id=%s
                       or (authorization_generation_id=%s and event_status=%s)
                    order by created_at desc limit 1
                    """,
                    (
                        params["authorization_event_id"],
                        params["authorization_generation_id"],
                        params["event_status"],
                    ),
                )
                row = cursor.fetchone()
                if row:
                    existing = _row(row)
                    if all(
                        existing.get(key) == params.get(key)
                        for key in (
                            "authorization_event_id", "authorization_version",
                            "authorization_generation_id", "binding_id",
                            "event_status", "transport_sha256", "payload_sha256",
                            "expected_attempt_identity",
                            "predecessor_generation_id", "reason",
                        )
                    ):
                        return {
                            "success": True,
                            "status": "publication_authorization_replay_withheld",
                            "created_count": 0,
                            "authorization": existing,
                            **_no_action(),
                        }, 200
                    return _failure("publication_authorization_conflict", 409)
                cursor.execute(
                    """
                    insert into public.beacon_organic_publication_authorization_events (
                        authorization_event_id, authorization_version,
                        authorization_generation_id, binding_id, event_status,
                        transport_sha256, payload_sha256,
                        expected_attempt_identity, predecessor_generation_id,
                        reason
                    ) values (
                        %(authorization_event_id)s, %(authorization_version)s,
                        %(authorization_generation_id)s, %(binding_id)s,
                        %(event_status)s, %(transport_sha256)s,
                        %(payload_sha256)s, %(expected_attempt_identity)s,
                        %(predecessor_generation_id)s, %(reason)s
                    )
                    """,
                    params,
                )
        return {
            "success": True,
            "status": "publication_authorization_event_created",
            "created_count": 1,
            "authorization": params,
            **_no_action(),
        }, 201
    except Exception as exc:
        return {
            **_failure("publication_authorization_append_failed", 503)[0],
            "error_type": exc.__class__.__name__,
        }, 503


def read_authorized_generation(cursor, generation_id, binding_id):
    cursor.execute(
        """
        select authorization_event_id, authorization_version,
               authorization_generation_id, binding_id, event_status,
               transport_sha256, payload_sha256, expected_attempt_identity,
               predecessor_generation_id, reason, created_at
        from public.beacon_organic_publication_authorization_events
        where authorization_generation_id=%s and binding_id=%s
        order by created_at desc
        """,
        (str(generation_id or "")[:160], str(binding_id or "")[:160]),
    )
    rows = [_row(row) for row in cursor.fetchall()]
    authorized = next(
        (row for row in rows if row["event_status"] == "owner_authorized"),
        None,
    )
    terminal = next(
        (
            row for row in rows
            if row["event_status"] in {"attempt_claimed", "contained", "confirmed"}
        ),
        None,
    )
    return None if terminal else authorized


def _row(row):
    keys = (
        "authorization_event_id", "authorization_version",
        "authorization_generation_id", "binding_id", "event_status",
        "transport_sha256", "payload_sha256", "expected_attempt_identity",
        "predecessor_generation_id", "reason", "created_at",
    )
    return {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in zip(keys, row)
    }


def _failure(status, code):
    return {"success": False, "status": status, **_no_action()}, code


def _no_action():
    return {
        "publish": False, "upload": False, "scheduled": False,
        "meta_call": False, "boost": False, "advert": False, "spend": False,
    }
