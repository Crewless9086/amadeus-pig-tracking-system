"""Canonical, read-only candidate collectors for the general manager worker."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from typing import Callable, Iterable

from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read


def collect_manager_candidates(*, now: datetime, collectors=None):
    selected = collectors or (_rootline, _herdmaster, _sam, _beacon, _delivery_gaps, _runtime)
    result = []
    for collector in selected:
        try:
            rows = collector(now)
            result.extend(dict(row) for row in rows or ())
        except Exception as exc:
            name = getattr(collector, "__name__", "collector").strip("_") or "collector"
            result.append(_candidate(
                dedupe_key=f"runtime:collector:{name}", specialist="RUNTIME", urgency="urgent",
                refs=[f"collector:{name}:{exc.__class__.__name__}"],
                unknowns=[f"current_{name}_specialist_evidence"],
                summary=f"Oom Sakkie could not load current {name} evidence.",
                next_action=f"Retry the canonical {name} collector; retain the case until evidence loads or one precise dependency is recorded.",
                next_at=now + timedelta(minutes=5)))
    return result


def collect_manager_candidate(*, now: datetime, dedupe_key: str, specialist: str):
    """Refresh one case from only its canonical owning collector."""
    prefix = str(dedupe_key or "").split(":", 1)[0].casefold()
    selected = {
        "rootline": (_rootline, "ROOTLINE"),
        "herdmaster": (_herdmaster, "HERDMASTER"),
        "sam": (_sam, "SAM"), "beacon": (_beacon, "BEACON"),
        "delivery": (_delivery_gaps, None), "runtime": (_runtime, "RUNTIME"),
    }.get(prefix)
    claimed_specialist = str(specialist or "").upper()
    if selected is None or (selected[1] and selected[1] != claimed_specialist):
        return None
    collector = selected[0]
    rows = collect_manager_candidates(now=now, collectors=(collector,))
    return next((row for row in rows
                 if str(row.get("dedupe_key") or "") == str(dedupe_key)
                 and str(row.get("specialist") or "").upper() == claimed_specialist), None)


def _rootline(now):
    with connect_bounded_read() as connection:
        with connection.cursor() as cur:
            cur.execute("""select review_event_id,created_at,
                    review_json->'automatic_reassessment'
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_automatic_reassessment'
                  and review_json->'automatic_reassessment'->>'status'='completed'
                order by created_at desc,review_event_id desc limit 1""")
            row = cur.fetchone()
            cur.execute("""select count(*) from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_automatic_reassessment'
                  and created_at>=%s
                  and review_json->'automatic_reassessment'->>'terminal_outcome'='zone_contained'""",
                (now - timedelta(hours=2),))
            contained_count = int(cur.fetchone()[0])
    if not row:
        return [_candidate("rootline:current-plan", "ROOTLINE", "urgent",
            ["canonical:automatic_reassessment:none"], ["current_irrigation_plan"],
            "ROOTLINE has no durable completed reassessment outcome.",
            "Run the existing ROOTLINE reassessment rail and retain ownership until a current plan or precise contained reason exists.", now)]
    event_id, observed, payload = row; payload = payload or {}
    outcome = str(payload.get("terminal_outcome") or "")
    next_at = _time(payload.get("next_due_at"), now + timedelta(minutes=15))
    if outcome not in {"zone_contained", "rootline_reassessment_legacy_delivery_unresolved"}:
        return []
    return [_candidate("rootline:current-plan", "ROOTLINE", "urgent",
        [f"event:{event_id}", f"material:{payload.get('material_digest') or 'unknown'}",
         f"contained_cycles_2h:{contained_count}",
         f"observed:{observed.isoformat()}"],
        ["delivered_current_irrigation_plan"],
        "ROOTLINE reassessment remains contained without a delivered current irrigation plan.",
        "Delegate current evidence reconciliation to ROOTLINE and reassess at the durable due time; do not infer irrigation or actuate hardware.", next_at)]


def _herdmaster(now):
    owner = _configured_owner()
    if not owner:
        raise ValueError("owner_binding_unavailable")
    from modules.oom_sakkie.farm_manager_runtime import _load_herdmaster
    result = _load_herdmaster(None, owner, now)
    candidates = []
    for item in tuple(getattr(result, "work_items", ()) or ()):
        unknowns = [item.genuine_question] if str(item.genuine_question or "").strip() else []
        due = item.due_at or now
        urgency = {"urgent": "urgent", "due_today": "due", "planned": "planned",
                   "waiting_for_evidence": "urgent", "protected_owner_decision": "due"}.get(item.state.value, "watch")
        candidates.append(_candidate(
            "herdmaster:" + str(item.dedupe_key), "HERDMASTER", urgency,
            [f"result:{result.result_id}",
             f"observed:{item.provenance.observed_at.isoformat()}",
             *item.provenance.source_refs], unknowns,
            item.title + ": " + item.why, item.next_action, due))
    from modules.pig_weights.farm_supabase_read_service import get_allocation_input_rows
    snapshot = get_allocation_input_rows()
    snapshot_observed = _time(snapshot.get("snapshot_observed_at"), now)
    for row in snapshot.get("overview_rows") or ():
        if str(row.get("Tag_Number") or "").strip().casefold() != "151":
            continue
        withdrawal = str(row.get("Withdrawal_Evidence_State") or "unknown").casefold()
        if withdrawal not in {"cleared", "not_applicable"}:
            candidates.append(_candidate("herdmaster:pig-151-withdrawal-sales", "HERDMASTER", "urgent",
                [f"pig:{row.get('Pig_ID') or 'tag-151'}", f"withdrawal:{withdrawal}",
                 f"allocation:{row.get('Allocation_Evidence_State') or 'unknown'}",
                 f"observed:{snapshot_observed.isoformat()}"],
                ["withdrawal_clearance", "sales_eligibility"],
                "Pig 151 does not have proved withdrawal clearance and sales eligibility.",
                "Delegate to HERDMASTER; retain the hold until canonical withdrawal and allocation evidence both support eligibility.",
                now + timedelta(minutes=5)))
    for row in snapshot.get("litter_rows") or ():
        sow = str(row.get("Sow_Tag_Number") or "").strip()
        status = str(row.get("Litter_Status") or "").strip().casefold()
        if sow.casefold() == "molly" and status not in {"completed", "closed", "weaned"}:
            litter_id = str(row.get("Litter_ID") or "unknown")
            farrowing = str(row.get("Farrowing_Date") or "unknown")
            wean = str(row.get("Wean_Date") or "unknown")
            weaned = row.get("Weaned_Count")
            candidates.append(_candidate("herdmaster:molly-active-litter", "HERDMASTER", "due",
                [f"litter:{litter_id}", f"status:{status or 'unknown'}",
                 f"farrowing:{farrowing}", f"wean_due:{wean}",
                 f"weaned_count:{weaned if weaned is not None else 'unknown'}",
                 f"observed:{snapshot_observed.isoformat()}"],
                ([] if wean != "unknown" else ["current_litter_weaning_due_date"]),
                f"Molly's litter {litter_id} is Active; farrowed {farrowing}, planned weaning {wean}, and recorded weaned count is {weaned if weaned is not None else 'Unknown'}.",
                "HERDMASTER retains care ownership now; prepare the exact piglet, tag, weight and movement preview at the planned weaning boundary, and record nothing without confirmation.",
                now + timedelta(minutes=30)))
    return candidates


def _sam(now):
    with connect_bounded_read() as connection:
        with connection.cursor() as cur:
            cur.execute("""select review_event_id,created_at,decision_json
                from public.sam_live_stock_conversation_review_events
                where event_source='sam_live_stock_direct_inbound'
                  and created_at>=%s
                order by created_at desc,review_event_id desc limit 50""", (now - timedelta(days=7),))
            rows = cur.fetchall()
    result, seen = [], set()
    for event_id, observed, decision in rows:
        decision = decision or {}; inbound = decision.get("inbound") or {}
        identity = str(inbound.get("conversation_id") or "").strip()
        if not identity or identity in seen: continue
        seen.add(identity)
        confirmed = bool(decision.get("customer_send_confirmed") or
                         (decision.get("routine_reply_delivery") or {}).get("sent"))
        if confirmed or decision.get("no_reply_recommended") is True: continue
        digest = hashlib.sha256(identity.encode()).hexdigest()[:20]
        blockers = (decision.get("sales_autonomy_level1") or {}).get("blockers") or []
        result.append(_candidate(
            f"sam:conversation:{digest}", "SAM", "urgent",
            [f"event:{event_id}", f"observed:{observed.isoformat()}"],
            [str(value) for value in blockers[:6]] or ["provider_confirmed_customer_outcome"],
            "SAM has a current unresolved customer conversation without provider-confirmed completion.",
            "Delegate to SAM; retain ownership until a supported provider-confirmed result or one precise protected exception is recorded.",
            now + timedelta(minutes=5)))
    return result


def _beacon(now):
    from modules.oom_sakkie.beacon_request_runtime import build_scheduled_sale_ready_stock_result
    scheduled = build_scheduled_sale_ready_stock_result()
    result_digest = str(scheduled.get("result_digest") or "")
    packet = scheduled.get("proposal") if isinstance(scheduled.get("proposal"), dict) else {}
    if len(result_digest) != 64 or not packet.get("packet_id"):
        raise ValueError("beacon_scheduled_result_identity_unavailable")
    with connect_bounded_read() as connection:
        with connection.cursor() as cur:
            cur.execute("""select review_event_id,created_at from public.sam_live_stock_conversation_review_events
                where event_source='sam_live_stock_direct_inbound'
                order by created_at desc,review_event_id desc limit 1""")
            sam = cur.fetchone()
    refs = [f"beacon_result:{result_digest}", f"packet:{packet['packet_id']}",
            f"sam:{sam[0] if sam else 'none'}"]
    return [_candidate("beacon:current-sale-opportunity", "BEACON", "due", refs,
        ["current_sale_opportunity_proposal_or_exact_media_request"],
        "BEACON has no current proposal or exact media request reconciled after the latest sales evidence.",
        "Delegate a protected internal BEACON proposal or exact media request from current canonical sales, inventory and media evidence; never publish, spend, contact customers, reserve stock or infer public-use authority.",
        now)]


def _delivery_gaps(now):
    """Own specialist results whose existing family delivery is contained."""
    with connect_bounded_read() as connection:
        with connection.cursor() as cur:
            cur.execute("""select distinct on (
                    review_json->'family_message_lifecycle'->>'card_mission_id')
                    review_event_id,created_at,review_json->'family_message_lifecycle'
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_family_message_lifecycle'
                  and created_at>=%s
                order by review_json->'family_message_lifecycle'->>'card_mission_id',
                         created_at desc,review_event_id desc""", (now - timedelta(days=2),))
            rows = cur.fetchall()
    result = []
    for event_id, observed, payload in rows:
        payload = payload or {}; status = str(payload.get("status") or "")
        if not any(word in status for word in ("contained", "ambiguous", "unavailable")):
            continue
        identity = str(payload.get("card_mission_id") or "")
        specialist = _specialist(payload.get("specialist_identity"))
        if not identity or not specialist:
            continue
        digest = hashlib.sha256(identity.encode()).hexdigest()[:20]
        result.append(_candidate(f"delivery:{specialist.lower()}:{digest}", specialist, "urgent",
            [f"event:{event_id}", f"observed:{observed.isoformat()}", f"status:{status}"],
            ["provider_confirmed_useful_owner_result"],
            f"A current {specialist} result exists internally but its Oom Sakkie delivery is {status}.",
            "Retain the result and use the existing family/protected delivery rail only after its exact retry state is safe.",
            now + timedelta(minutes=5)))
    return result


def _specialist(value):
    text = str(value or "").upper()
    for name in ("ROOTLINE", "HERDMASTER", "SAM", "BEACON"):
        if name in text:
            return name
    return ""


def _runtime(now):
    with connect_bounded_read() as connection:
        with connection.cursor() as cur:
            cur.execute("select max(heartbeat_at),max(next_cycle_at) from app_private.oom_protected_payment_recovery_cycles")
            payment = cur.fetchone()
            cur.execute("""select max(created_at) from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_automatic_reassessment'
                  and review_json->'automatic_reassessment'->>'status'='completed'""")
            rootline = cur.fetchone()[0]
    stale = []
    if not payment or not payment[0] or now - payment[0] > timedelta(minutes=12): stale.append("oom_recovery_heartbeat")
    if not rootline or now - rootline > timedelta(minutes=35): stale.append("rootline_reassessment_heartbeat")
    if not stale: return []
    return [_candidate("runtime:scheduled-worker-health", "RUNTIME", "critical",
        [f"payment:{payment[0] if payment else 'none'}", f"rootline:{rootline or 'none'}"], stale,
        "One or more existing Oom Sakkie scheduled workers is stale.",
        "Escalate one precise runtime exception and reassess after the provider schedule or supervisor recovers.",
        now + timedelta(minutes=5))]


def _candidate(dedupe_key, specialist, urgency, refs, unknowns, summary, next_action, next_at):
    return {"dedupe_key": dedupe_key, "specialist": specialist, "urgency": urgency,
        "evidence_refs": list(refs), "unknowns": list(unknowns), "summary": summary,
        "next_action": next_action, "next_reassessment_at": _aware(next_at).isoformat()}


def _configured_owner():
    values = [part.strip() for part in str(os.getenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS") or "").split(",") if part.strip()]
    return values[0] if values else ""


def _time(value, fallback):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return _aware(parsed)
    except (TypeError, ValueError): return _aware(fallback)


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
