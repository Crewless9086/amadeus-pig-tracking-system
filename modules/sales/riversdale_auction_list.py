"""Transactional owner shortlist events; never cohort or outlet assignments."""
import hashlib
import json
import os
import uuid

from services.database_service import DATABASE_URL_ENV

VERSION = "riversdale_auction_list_v2"
FARM_DATABASE_URL_ENV = "FARM_SUPABASE_DATABASE_URL"


def _result(ok, status, **extra):
    return {
        "success": ok, "status": status, "version": VERSION,
        "creates_cohort": False, "creates_outlet_assignment": False,
        "creates_reservation": False, "books_auction": False,
        "creates_sale": False, "contacts_customer": False,
        "sends_reminder": False, "changes_animal_or_farm_state": False,
        **extra,
    }


def _factory(url, connect_factory):
    if connect_factory:
        return lambda: connect_factory(url)
    import psycopg
    return lambda: psycopg.connect(
        url, connect_timeout=3, options="-c statement_timeout=3000"
    )


def _canonical_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _resolve_database_url(database_url=None):
    if database_url is not None:
        return str(database_url).strip()
    farm_override = os.getenv(FARM_DATABASE_URL_ENV, "").strip()
    if farm_override:
        return farm_override
    return os.getenv(DATABASE_URL_ENV, "").strip()


def eligibility_tokens(packet):
    """Hash the exact server-derived candidate evidence accepted for Add."""
    result = {}
    for item in packet.get("candidate_preview", []) if isinstance(packet, dict) else []:
        if not isinstance(item, dict):
            continue
        pig_id = str(item.get("pig_id") or "").strip()
        evidence = item.get("herdmaster_evidence")
        withdrawal = str((evidence or {}).get("withdrawal_clear") or "").strip().lower()
        quality = str((evidence or {}).get("observed_quality") or "").strip().lower()
        health = str((evidence or {}).get("health_status") or "").strip().lower()
        medical = str((evidence or {}).get("medical_status") or "").strip().lower()
        eligible = (
            withdrawal in {"yes", "clear", "cleared", "true", "1"}
            and quality in {"suitable", "clear", "cleared", "yes"}
            and medical == "clear"
            and "hold" not in health
        )
        if pig_id and isinstance(evidence, dict) and eligible:
            result[pig_id] = _canonical_hash({
                "version": VERSION, "pig_id": pig_id,
                "candidate": item, "coordination": packet.get("coordination_evidence", {}),
            })
    return result


def read_auction_list(*, database_url=None, connect_factory=None):
    url = _resolve_database_url(database_url)
    if not url and connect_factory is None:
        return _result(False, "auction_list_store_unavailable"), 503
    try:
        with _factory(url, connect_factory)() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""with cycle as (
                  select auction_cycle_id from public.riversdale_auction_cycles
                  where operating_confirmed
                  order by owner_confirmed_at desc, created_at desc limit 1
                ), latest as (
                  select distinct on(e.pig_id)
                    e.pig_id,e.event_type,e.owner_note,e.recorded_at,
                    e.auction_list_event_id,e.decision_sequence
                  from public.riversdale_auction_list_events e join cycle c using(auction_cycle_id)
                  order by e.pig_id,e.decision_sequence desc
                )
                select c.auction_cycle_id,l.pig_id,l.event_type,l.owner_note,l.recorded_at,
                       l.auction_list_event_id,l.decision_sequence
                from cycle c left join latest l on true order by l.pig_id""")
                rows = cursor.fetchall()
        if not rows:
            return _result(False, "confirmed_auction_cycle_required"), 409
        cycle_id = rows[0][0]
        heads = {
            row[1]: {"event_id": row[5], "decision_sequence": row[6]}
            for row in rows if row[1]
        }
        items = [{
            "pig_id": row[1], "owner_note": row[3],
            "listed_at": row[4].isoformat(), "prior_event_id": row[5],
            "decision_sequence": row[6],
        } for row in rows if row[1] and row[2] == "added"]
        return _result(True, "available", auction_cycle_id=cycle_id,
                       causal_heads=heads, items=items), 200
    except Exception as exc:
        return _result(False, "auction_list_store_unavailable",
                       error_type=exc.__class__.__name__), 503


def record_auction_list_events(payload, *, actor_id, eligibility_loader,
                               database_url=None, connect_factory=None):
    """Validate and append one all-or-nothing batch in a serializable transaction."""
    payload = payload if isinstance(payload, dict) else {}
    actor_id = str(actor_id or "").strip()
    action = str(payload.get("action") or "").strip().lower()
    pig_ids = payload.get("pig_ids")
    idem = str(payload.get("idempotency_key") or "").strip()
    cycle_id = str(payload.get("auction_cycle_id") or "").strip()
    note = str(payload.get("owner_note") or "").strip()
    expected_tokens = payload.get("eligibility_tokens")
    expected_prior = payload.get("prior_event_ids")
    if not actor_id:
        return _result(False, "owner_identity_required"), 403
    if (action not in {"add", "remove"} or not isinstance(pig_ids, list)
            or not pig_ids or not idem or not cycle_id
            or not isinstance(expected_tokens, dict)
            or not isinstance(expected_prior, dict)):
        return _result(False, "invalid_auction_list_event"), 400
    ids = sorted({str(value).strip() for value in pig_ids if str(value).strip()})
    if not ids:
        return _result(False, "invalid_auction_list_event"), 400
    request_identity = {
        "version": VERSION, "auction_cycle_id": cycle_id, "action": action,
        "pig_ids": ids, "actor_id": actor_id, "idempotency_key": idem,
        "owner_note": note,
        "eligibility_tokens": {pig_id: str(expected_tokens.get(pig_id) or "") for pig_id in ids},
        "prior_event_ids": {pig_id: str(expected_prior.get(pig_id) or "") for pig_id in ids},
    }
    request_hash = _canonical_hash(request_identity)
    url = _resolve_database_url(database_url)
    if not url and connect_factory is None:
        return _result(False, "auction_list_store_unavailable"), 503
    try:
        with _factory(url, connect_factory)() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select pg_advisory_xact_lock(hashtextextended('riversdale-auction-cycle',0))"
                )
                # Freeze every canonical relation used by the eligibility reader.
                # SHARE permits concurrent reads but blocks farm/evidence writes
                # until this all-or-nothing list decision commits.
                cursor.execute("""lock table
                    public.pigs,public.pig_weight_events,public.pig_medical_events,
                    public.orders,public.order_lines,public.litters,public.pens
                    in share mode""")
                cursor.execute("""select auction_cycle_id
                    from public.riversdale_auction_cycles where operating_confirmed
                    order by owner_confirmed_at desc, created_at desc limit 1 for update""")
                current_cycle = cursor.fetchone()
                if not current_cycle or current_cycle[0] != cycle_id:
                    connection.rollback()
                    return _result(False, "auction_list_stale_cycle"), 409
                cursor.execute(
                    "select pig_id from public.pigs where pig_id=any(%s) order by pig_id for update",
                    (ids,),
                )
                if [row[0] for row in cursor.fetchall()] != ids:
                    connection.rollback()
                    return _result(False, "auction_list_unknown_pig"), 409
                keys = [f"{idem}:{pig_id}" for pig_id in ids]
                cursor.execute("""select idempotency_key,request_hash
                    from public.riversdale_auction_list_events
                    where idempotency_key=any(%s) order by idempotency_key""", (keys,))
                replay_rows = cursor.fetchall()
                if replay_rows:
                    if len(replay_rows) == len(ids) and all(row[1] == request_hash for row in replay_rows):
                        return _result(True, "auction_list_replayed", event_count=0), 200
                    connection.rollback()
                    return _result(False, "auction_list_idempotency_conflict"), 409
                packet = eligibility_loader(connection, ids)
                if not isinstance(packet, dict) or packet.get("success") is not True:
                    connection.rollback()
                    return _result(False, "auction_list_eligibility_unavailable"), 503
                actual_cycle = str(
                    (packet.get("confirmation") or {}).get("auction_cycle_id") or ""
                )
                if actual_cycle != cycle_id:
                    connection.rollback()
                    return _result(False, "auction_list_stale_cycle"), 409
                actual_tokens = eligibility_tokens(packet)
                selectable = set(actual_tokens)
                cursor.execute("""select distinct on(pig_id)
                    pig_id,event_type,auction_list_event_id,decision_sequence
                    from public.riversdale_auction_list_events
                    where auction_cycle_id=%s and pig_id=any(%s)
                    order by pig_id,decision_sequence desc""", (cycle_id, ids))
                latest = {row[0]: row[1:] for row in cursor.fetchall()}
                actual_prior = {pig_id: latest.get(pig_id, ("", "", 0))[1] or "" for pig_id in ids}
                if any(str(expected_prior.get(pig_id) or "") != actual_prior[pig_id] for pig_id in ids):
                    connection.rollback()
                    return _result(False, "auction_list_stale_membership"), 409
                if action == "add":
                    invalid = [
                        pig_id for pig_id in ids
                        if pig_id not in selectable
                        or str(expected_tokens.get(pig_id) or "") != actual_tokens.get(pig_id)
                        or latest.get(pig_id, ("",))[0] == "added"
                    ]
                else:
                    invalid = [
                        pig_id for pig_id in ids
                        if latest.get(pig_id, ("",))[0] != "added"
                    ]
                if invalid:
                    connection.rollback()
                    return _result(False, "auction_list_selection_not_allowed"), 409
                for pig_id in ids:
                    previous = latest.get(pig_id)
                    prior_id = previous[1] if previous else None
                    sequence = int(previous[2]) + 1 if previous else 1
                    evidence_token = actual_tokens.get(pig_id, "") if action == "add" else ""
                    event_hash = _canonical_hash({
                        **request_identity, "pig_id": pig_id,
                        "eligibility_evidence": evidence_token,
                        "prior_event_id": prior_id or "", "decision_sequence": sequence,
                    })
                    event_id = "RIV-LIST-" + uuid.uuid5(
                        uuid.NAMESPACE_URL, f"{cycle_id}:{idem}:{pig_id}"
                    ).hex.upper()
                    cursor.execute("""insert into public.riversdale_auction_list_events
                      (auction_list_event_id,auction_cycle_id,pig_id,event_type,
                       decision_sequence,prior_event_id,eligibility_evidence_hash,
                       owner_principal,owner_note,idempotency_key,request_hash,event_hash)
                      values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                      (event_id, cycle_id, pig_id,
                       "added" if action == "add" else "removed",
                       sequence, prior_id, evidence_token, actor_id, note,
                       f"{idem}:{pig_id}", request_hash, event_hash))
        return _result(True, "auction_list_updated", event_count=len(ids)), 201
    except Exception as exc:
        return _result(False, "auction_list_store_unavailable",
                       error_type=exc.__class__.__name__), 503
