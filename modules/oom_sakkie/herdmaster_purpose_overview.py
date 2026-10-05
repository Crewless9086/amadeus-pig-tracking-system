"""One receipt-bound Telegram overview over existing purpose cases.

This module owns presentation receipts only. It never marks a case delivered,
changes material, approves an animal purpose, or creates a second work queue.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import time

from modules.oom_sakkie.bounded_postgres_read import ReadBudgetCursor, connect_bounded_postgres
from modules.oom_sakkie.herdmaster_purpose_decision import current_purpose_owner, purpose_decision_binding

CONTRACT = "herdmaster.purpose_overview.v1"
FIELD = "purpose_overview"
MAX_CASES = 64
MAX_EVENTS = 9
RESERVE_SECONDS = 30


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _instant(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except (ValueError, TypeError):
        return None


def _factory(connect):
    return connect or (lambda: connect_bounded_postgres(read_only=False))


def _deadline(deadline):
    return deadline-RESERVE_SECONDS if deadline is not None else time.monotonic()+20


def _available(deadline):
    return time.monotonic() < deadline


def _empty(status, **extra):
    return dict(success=False, status=status, coverage=[], telegram_sends=0, telegram_edits=0,
        delivery_confirmed=False, writes_farm_data=False, **extra)


def _valid_manifest(manifest):
    if (not isinstance(manifest, list) or not 1 <= len(manifest) <= MAX_CASES
            or any(not isinstance(v, dict) for v in manifest)):
        return False
    keys = ("case_id", "generation", "evidence_digest", "membership_digest")
    return (manifest == sorted(manifest, key=lambda x: x.get("case_id", ""))
        and len({v.get("case_id") for v in manifest}) == len(manifest)
        and all(isinstance(v, dict) and set(v) == set(keys)
            and re.fullmatch(r"OOM-CASE-[A-F0-9]{24}", str(v["case_id"]))
            and type(v["generation"]) is int and v["generation"] > 0
            and all(re.fullmatch(r"[A-Fa-f0-9]{64}", str(v[k])) for k in keys[2:]) for v in manifest))


def overview_identity(manifest, owner_id, occurrence_id):
    return "OOM-PURPOSE-OVERVIEW-"+_digest([CONTRACT, str(owner_id), manifest, occurrence_id])[:32].upper()


def verify_overview_receipt(events, *, manifest, owner_id, occurrence_id):
    """Verify the acknowledged family receipt, not a success-shaped outcome."""
    if not _valid_manifest(manifest) or not owner_id or not isinstance(events, list) or len(events) > MAX_EVENTS:
        return None
    verified = [e for e in events if isinstance(e, dict) and e.get("state") == "purpose_overview_verified"]
    if len(verified) != 1:
        return None
    end = verified[0]
    meta = end.get(FIELD) or {}
    mission = overview_identity(manifest, owner_id, occurrence_id)
    requests = meta.get("request_ids")
    if (not isinstance(requests, list) or len(requests) > MAX_CASES
            or any(not isinstance(v, str) or not re.fullmatch(r"[a-f0-9]{64}", v) for v in requests)
            or requests != sorted(set(requests))
            or occurrence_id != ("review:"+_digest(requests) if requests else "initial")):
        return None
    if (meta.get("contract") != CONTRACT or meta.get("manifest") != manifest
            or meta.get("owner_id") != str(owner_id) or meta.get("occurrence_id") != occurrence_id
            or meta.get("language") not in {"en", "af"}
            or not re.fullmatch(r"[a-f0-9]{64}", str(meta.get("preview_digest", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(meta.get("render_sha256", "")))
            or not re.fullmatch(r"[a-f0-9]{64}", str(meta.get("keyboard_sha256", "")))):
        return None
    card = mission+":TELEGRAM"
    required = {card+"-DELIVERY-ATTEMPT": "delivery_attempted", card+"-DELIVERED": "delivered",
        card+"-PURPOSE-VERIFIED": "purpose_overview_verified"}
    selected = [e for e in events if isinstance(e, dict) and e.get("event_id") in required]
    if len(selected) != 3 or len({e["event_id"] for e in selected}) != 3:
        return None
    common = {"mission_id": mission, "card_mission_id": card, "owner_user_id": str(owner_id),
        "chat_id": str(owner_id), "specialist_identity": "HERDMASTER", "task_state": "purpose_telegram_overview",
        "provider_message_id": mission, "provider_timestamp": "", "text_sha256": meta["render_sha256"],
        "inbound_text_sha256": hashlib.sha256(mission.encode()).hexdigest()}
    if any(e.get("state") != required[e["event_id"]] or e.get(FIELD) != meta
            or any(e.get(k) != v for k, v in common.items()) for e in selected):
        return None
    sent = next(e for e in selected if e["state"] == "delivered")
    if not str(sent.get("telegram_message_id") or "") or end.get("telegram_message_id") != sent["telegram_message_id"]:
        return None
    # Any competing provider effect/history makes this exact overview unproven.
    if any(e.get("event_id") not in required for e in events):
        return None
    return {"contract": CONTRACT, "mission_id": mission, "card_mission_id": card,
        "event_id": end["event_id"], "telegram_message_id": sent["telegram_message_id"],
        "manifest_digest": _digest(manifest), "occurrence_id": occurrence_id,
        "owner_id": str(owner_id), "language": meta["language"], "receipt_digest": _digest(sorted(selected, key=lambda e:e["event_id"]))}


def _read_events(*, mission=None, manifest=None, owner_id=None, connect=None, deadline):
    from modules.oom_sakkie.family_message_lifecycle import EVENT_SOURCE
    with _factory(connect)() as db, db.cursor() as raw:
        raw.execute("set transaction read only")
        cur = ReadBudgetCursor(raw, min(deadline, time.monotonic()+6), failure_kind="purpose_overview_read_deadline")
        if mission is not None:
            cur.execute("""select review_json->'family_message_lifecycle'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s and review_json->'family_message_lifecycle'->>'mission_id'=%s
                  and (review_json->'family_message_lifecycle') ? 'purpose_overview'
                order by created_at,review_event_id limit 10""", (EVENT_SOURCE, mission))
            rows = [v[0] for v in cur.fetchall()]
            if len(rows) > MAX_EVENTS: raise ValueError("purpose_overview_event_bound")
        else:
            # Read all family rows for matching exact owner-request occurrences,
            # not just a success marker that could conceal an ambiguous attempt.
            cur.execute("""select review_json->'family_message_lifecycle'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s and
                  review_json->'family_message_lifecycle'->>'owner_user_id'=%s and
                  (review_json->'family_message_lifecycle'->'purpose_overview'->'manifest') @> any(%s::jsonb[])
                order by created_at,review_event_id limit 577""",
                (EVENT_SOURCE, owner_id, [json.dumps([member]) for member in manifest]))
            rows = [v[0] for v in cur.fetchall()]
            if len(rows) > MAX_CASES*MAX_EVENTS: raise ValueError("purpose_overview_event_bound")
        if not _available(deadline): raise TimeoutError("purpose_overview_read_deadline")
        return rows


def _store(connect, deadline, metadata):
    from modules.oom_sakkie.family_message_lifecycle import EVENT_SOURCE
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event, record_sam_live_stock_review_event
    def store(action, identity, payload):
        if not _available(deadline): raise TimeoutError("purpose_overview_read_deadline")
        if action == "load":
            return [e for e in _read_events(mission=metadata["mission_id"], connect=connect, deadline=deadline)
                if e.get("card_mission_id") == identity]
        enriched = {**payload, FIELD: metadata}
        event = build_sam_live_stock_review_event({"conversation_id": payload["card_mission_id"]}, {}, {},
            {"score": 0, "safe_to_send": False, "recommended_action": "family_message_lifecycle"}, event_source=EVENT_SOURCE)
        event.update(review_event_id=identity, chatwoot_conversation_id=payload["card_mission_id"],
            review_json={"family_message_lifecycle": enriched}, decision_json={}, facts_json={},
            customer_message_excerpt="", sam_reply_excerpt="")
        value, status = record_sam_live_stock_review_event(event, database_url="purpose-overview-owned-connection",
            connect_factory=_factory(connect))
        return {**value, "success": status < 400 and value.get("success") is True}
    return store


def _current_rows(manifest, *, cycle_id, now, connect, deadline, deferrals=()):
    with _factory(connect)() as db, db.cursor() as raw:
        raw.execute("set transaction read only")
        cur = ReadBudgetCursor(raw, min(deadline, time.monotonic()+6), failure_kind="purpose_overview_read_deadline")
        cur.execute("""select c.case_id,c.generation,c.evidence_digest,c.status,c.assigned_worker_id,c.lease_until,
            (select jsonb_agg(jsonb_build_array(d.event_payload->'purpose_review_deferred'->>'request_id',d.occurred_at)
                 order by d.occurred_at desc,d.event_id desc) from (
                select event_id,event_payload,occurred_at from app_private.oom_manager_case_events e
                where e.case_id=c.case_id and e.generation=c.generation and e.event_type='reassessment_scheduled'
                  and e.event_payload ? 'purpose_review_deferred'
                order by occurred_at desc,event_id desc limit 2) d)
            from app_private.oom_manager_cases c where c.case_id=any(%s) order by c.case_id limit 65""",
            ([v["case_id"] for v in manifest],))
        rows = cur.fetchall()
    if len(rows) != len(manifest) or not _available(deadline): return False
    checked_at = max(now, datetime.now(timezone.utc))
    latest = {d["case_id"]: d["request_id"] for d in deferrals}
    if any((row[6] or [[None]])[0][0] != latest.get(row[0])
            or (row[6] and len(row[6]) > 1 and _instant(row[6][0][1]) == _instant(row[6][1][1])) for row in rows):
        return False
    return all(tuple(row[:3]) == tuple(value[k] for k in ("case_id", "generation", "evidence_digest"))
        and ((row[3] in {"open", "waiting_reassessment", "exception"} and not row[4] and row[5] is None)
            or (row[3] == "delegated" and row[4] == cycle_id and row[5] and row[5] > checked_at))
        for row, value in zip(rows, manifest))


def _deferrals(manifest, *, owner_id, connect, deadline, now):
    """Newest exact attributable request wins; equal-time requests are ambiguous."""
    with _factory(connect)() as db, db.cursor() as raw:
        raw.execute("set transaction read only")
        cur = ReadBudgetCursor(raw, min(deadline, time.monotonic()+6), failure_kind="purpose_overview_read_deadline")
        cur.execute("""select e.case_id,e.generation,e.event_id,e.event_payload,e.occurred_at
            from app_private.oom_manager_cases c cross join lateral (
                select case_id,generation,event_id,event_payload,occurred_at
                from app_private.oom_manager_case_events h where h.case_id=c.case_id
                and h.generation=c.generation and h.event_type='reassessment_scheduled'
                and h.event_payload ? 'purpose_review_deferred'
                order by h.occurred_at desc,h.event_id desc limit 2) e
            where c.case_id=any(%s) order by e.case_id,e.occurred_at desc limit 129""",
            ([v["case_id"] for v in manifest],))
        rows = cur.fetchall()
    if len(rows) > MAX_CASES*2 or not _available(deadline): raise ValueError("purpose_overview_deferral_bound")
    result = []
    for member in manifest:
        found = [v for v in rows if v[0] == member["case_id"]]
        if not found: continue
        if len(found) > 1 and found[0][4] == found[1][4]: raise ValueError("purpose_review_date_ambiguous")
        case, generation, identity, payload, occurred = found[0]
        value = payload.get("purpose_review_deferred") or {}
        requested, due = _instant(value.get("requested_at")), _instant(value.get("review_at"))
        if (value.get("contract") != "herdmaster.purpose_deferment.v1"
                or any(value.get(k) != v for k, v in member.items())
                or generation != member["generation"] or value.get("owner_user_id") != owner_id
                or value.get("private_chat_id") != owner_id or not value.get("provider_message_id")
                or not value.get("source_card_message_id") or not requested or not due
                or requested != occurred or requested > now or not requested < due
                or value.get("reason") != "owner_requested_review"
                or not re.fullmatch(r"[a-f0-9]{64}", str(value.get("request_id", "")))
                or identity != "OOM-PURPOSE-DEFER-"+value["request_id"][:32].upper()):
            raise ValueError("purpose_review_date_unproven")
        result.append(value)
    return result


def dispatch_purpose_overview(candidates, *, cycle_id, now, deadline_monotonic,
                              connect=None, context=None, event_store=None, sender=None,
                              clock=None, builder=None, protected_delivery=None):
    """Called once after reconciliation commits, before individual dispatch."""
    from modules.oom_sakkie import family_message_lifecycle as family
    from modules.oom_sakkie.general_manager_worker import normalize_candidate
    from modules.oom_sakkie.herdmaster_purpose_membership import list_current_review_cases
    from modules.oom_sakkie.herdmaster_purpose_telegram import build_telegram_purpose_overview
    from modules.oom_sakkie.protected_action_claims import bind_claim_card
    from modules.oom_sakkie.protected_delivery_lifecycle import recover_protected_card
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = _instant(now)
    deadline = _deadline(deadline_monotonic)
    outcome = _empty("purpose_overview_unavailable")
    try:
        owner = current_purpose_owner()
        if not owner or not now or not cycle_id or deadline-time.monotonic() < 3:
            return _empty("purpose_overview_owner_or_deadline_unavailable")
        pairs = [(v, normalize_candidate(v, now=now)) for v in candidates]
        admitted = [(v, n) for v, n in pairs if purpose_decision_binding(n)]
        raw = [v for v, _ in admitted]
        if not raw: return {**_empty("purpose_overview_no_current_decisions"), "success": True}
        if len(raw) > MAX_CASES: raise ValueError("purpose_overview_case_bound")
        normalized = {n["case_id"]: n for _, n in admitted}
        if len(normalized) != len(raw): raise ValueError("purpose_overview_duplicate_case")
        snapshot = raw[0].get("_purpose_source_snapshot")
        if context is None:
            if not snapshot or any(v.get("_purpose_source_snapshot") != snapshot for v in raw):
                raise ValueError("purpose_overview_source_missing_or_mixed")
            context = {"snapshot": snapshot, **list_current_review_cases(snapshot, now=now, connect=connect,
                owning_cycle_id=cycle_id, deadline_monotonic=deadline)}
        rows = sorted([r for r in context["cases"] if r["case_id"] in normalized], key=lambda r:r["case_id"])
        if len(rows) != len(raw) or any(r["evidence_digest"] != normalized[r["case_id"]]["evidence_digest"] for r in rows):
            raise ValueError("purpose_overview_current_evidence_unavailable")
        # A known unavailable legacy/leased membership is not authority and
        # must not erase independently proven sibling work. Missing rows or
        # contradictory material above still contain the whole source packet.
        rows = [r for r in rows if r.get("available") is True]
        if not rows:
            return {**_empty("purpose_overview_no_proven_membership"), "success": True}
        manifest = [{"case_id": r["case_id"], "generation": r["generation"], "evidence_digest": r["evidence_digest"],
            "membership_digest": r["membership"]["membership_digest"]} for r in rows]
        if not _valid_manifest(manifest): raise ValueError("purpose_overview_manifest_invalid")
        deferrals = _deferrals(manifest, owner_id=owner.telegram_user_id, connect=connect, deadline=deadline, now=now)
        history = _read_events(manifest=manifest, owner_id=owner.telegram_user_id, connect=connect, deadline=deadline)
        prior_receipts, covered, consumed = [], set(), set()
        for event in history:
            meta = event.get(FIELD) or {}
            if event.get("state") != "purpose_overview_verified": continue
            same = [e for e in history if e.get("mission_id") == event.get("mission_id")]
            proof = verify_overview_receipt(same, manifest=meta.get("manifest"), owner_id=owner.telegram_user_id,
                occurrence_id=meta.get("occurrence_id"))
            if not proof: continue
            prior_receipts.append((proof, same, meta))
            covered.update(m["case_id"] for m in meta["manifest"] if m in manifest)
            consumed.update(meta.get("request_ids") or [])
        due = [d for d in deferrals if _instant(d["review_at"]) <= now and d["request_id"] not in consumed]
        future = {d["case_id"] for d in deferrals if _instant(d["review_at"]) > now}
        if any("last_delivery_digest" not in row for row in rows):
            raise ValueError("purpose_overview_delivery_history_unavailable")
        eligible = {d["case_id"] for d in due} | {r["case_id"] for r in rows
            if r["last_delivery_digest"] != r["evidence_digest"] and r["case_id"] not in covered | future}
        if not eligible:
            # Return one unchanged verified subset for idempotent admission.
            # Other previously admitted subsets stay quiet through the worker's
            # own current-generation coverage read; none are newly delivered.
            prior = next(((proof, same, meta) for proof,same,meta in prior_receipts
                if all(m in manifest for m in meta["manifest"])), None)
            if prior:
                proof, same, meta = prior
                if not _current_rows(meta["manifest"], cycle_id=cycle_id, now=clock(), connect=connect,
                        deadline=deadline, deferrals=[d for d in deferrals if d["case_id"] in {m["case_id"] for m in meta["manifest"]}]):
                    raise ValueError("purpose_overview_current_case_changed")
                return {"success": True, "status": "purpose_overview_verified", "delivery_confirmed": False,
                    "writes_farm_data": False, "telegram_sends": 0, "telegram_edits": 0,
                    "manifest": meta["manifest"], "owner_id": owner.telegram_user_id,
                    "occurrence_id": meta["occurrence_id"], "receipt_events": same,
                    "coverage": [{**m, "receipt": proof} for m in meta["manifest"]]}
            return {**_empty("purpose_overview_no_unnotified_due_work"), "success": True}
        rows = [r for r in rows if r["case_id"] in eligible]
        manifest = [m for m in manifest if m["case_id"] in eligible]
        deferrals = [d for d in deferrals if d["case_id"] in eligible]
        occurrence = "initial" if not due else "review:"+_digest(sorted(d["request_id"] for d in due))
        mission = overview_identity(manifest, owner.telegram_user_id, occurrence)
        events = _read_events(mission=mission, connect=connect, deadline=deadline)
        receipt = verify_overview_receipt(events, manifest=manifest, owner_id=owner.telegram_user_id, occurrence_id=occurrence)
        def result_for(receipt, events, **effects):
            return {"success": True, "status": "purpose_overview_verified", "delivery_confirmed": False,
                "writes_farm_data": False, "telegram_sends": 0, "telegram_edits": 0,
                "manifest": manifest, "owner_id": owner.telegram_user_id, "occurrence_id": occurrence,
                "receipt_events": events, "coverage": [{**m, "receipt": receipt} for m in manifest], **effects}
        if receipt:
            if not _current_rows(manifest, cycle_id=cycle_id, now=clock(), connect=connect, deadline=deadline, deferrals=deferrals):
                raise ValueError("purpose_overview_current_case_changed")
            return result_for(receipt, events)
        if events: return _empty("purpose_overview_prior_attempt_contained")
        parsed = {"telegram_user_id": owner.telegram_user_id, "telegram_chat_id": owner.telegram_user_id,
            "telegram_chat_type": "private", "provider_message_id": mission, "provider_timestamp": "",
            "text": mission, "output_language": owner.language}
        prepared, status = (builder or build_telegram_purpose_overview)({**context, "cases": rows,
            "purpose_overview_revisit": [{"request_id": d["request_id"], "review_at": d["review_at"]} for d in due]},
            parsed, mission=mission, connect=connect)
        if status >= 400 or not prepared.get("success"): raise ValueError("purpose_overview_preview_unavailable")
        localized = family.localize_recipient_result(parsed, prepared, "HERDMASTER")
        from modules.oom_sakkie.family_presentation import envelope
        if localized.get("recipient_language_render_unrecognized"): raise ValueError("purpose_overview_language_unproven")
        metadata = {"contract": CONTRACT, "manifest": manifest, "owner_id": owner.telegram_user_id,
            "occurrence_id": occurrence, "mission_id": mission, "language": owner.language,
            "request_ids": sorted(d["request_id"] for d in due), "preview_digest": prepared.get("preview_digest"),
            "render_sha256": hashlib.sha256(envelope(localized["answer"]).encode()).hexdigest(),
            "keyboard_sha256": _digest(prepared.get("reply_markup"))}
        store = event_store or _store(connect, deadline_monotonic or time.monotonic()+80, metadata)
        # Even injected existing stores retain the exact coverage binding.
        def bound_store(action, identity, payload):
            return store(action, identity, {**payload, FIELD: metadata} if payload else payload)
        def guarded_sender(chat, text, **kwargs):
            fresh = current_purpose_owner()
            if (not fresh or fresh != owner or clock() < now or not _available(deadline)
                    or not _current_rows(manifest, cycle_id=cycle_id, now=clock(), connect=connect, deadline=deadline, deferrals=deferrals)):
                return {"success": False, "delivery_definitely_not_sent": True}
            response = (sender(chat, text, **kwargs) if sender else
                family._send_telegram(chat, text, reply_markup=prepared.get("reply_markup"), **kwargs))
            if response.get("success") is True and response.get("telegram_message_id"):
                outcome["telegram_sends"] = 1
            return response
        delivery = family.deliver_family_result(parsed, prepared, specialist="HERDMASTER", mission_id=mission,
            card_mission_id=prepared["card_mission_id"], event_store=bound_store, sender=guarded_sender,
            protected_delivery=protected_delivery or (lambda **kwargs: recover_protected_card(**kwargs, connect_factory=_factory(connect))),
            deadline_monotonic=deadline_monotonic)
        outcome.update(telegram_sends=max(outcome["telegram_sends"], int(delivery.get("telegram_sends") or 0)), telegram_edits=int(delivery.get("telegram_edits") or 0))
        message = str(delivery.get("telegram_message_id") or delivery.get("provider_card_message_id") or "")
        if (delivery.get("success") is not True or not message or
                not bind_claim_card(prepared["callback_token"], message, connect_factory=_factory(connect))):
            return {**outcome, "status": "purpose_overview_delivery_unproven"}
        events = list(bound_store("load", prepared["card_mission_id"], None) or [])
        delivered = [e for e in events if e.get("state") == "delivered" and e.get("telegram_message_id") == message]
        if len(delivered) != 1: return {**outcome, "status": "purpose_overview_receipt_missing"}
        identity = prepared["card_mission_id"]+"-PURPOSE-VERIFIED"
        recorded = bound_store("record", identity, {**delivered[0], "event_id": identity, "state": "purpose_overview_verified"})
        if recorded.get("success") is not True: return {**outcome, "status": "purpose_overview_receipt_unavailable"}
        events = list(bound_store("load", prepared["card_mission_id"], None) or [])
        receipt = verify_overview_receipt(events, manifest=manifest, owner_id=owner.telegram_user_id, occurrence_id=occurrence)
        if not receipt: return {**outcome, "status": "purpose_overview_receipt_unproven"}
        return result_for(receipt, events, telegram_sends=outcome["telegram_sends"], telegram_edits=outcome["telegram_edits"])
    except Exception as exc:
        return {**outcome, "failure_kind": type(exc).__name__}
