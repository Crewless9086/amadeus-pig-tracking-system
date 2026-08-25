"""Scheduler-owned, read-only Daily Farm Manager coordination lifecycle."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace
from hashlib import sha256
import html
import json
import os
from urllib import error as urllib_error, request as urllib_request
from zoneinfo import ZoneInfo
from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read

from modules.oom_sakkie.farm_manager_loop import (
    Authority, Provenance, SpecialistAvailability, SpecialistResult,
    SpecialistWorkItem, WorkState,
)

SAST = ZoneInfo("Africa/Johannesburg")
CONTRACT_VERSION = "oom_sakkie_daily_farm_manager.v2"
EVENT_SOURCE = "oom_sakkie_daily_farm_manager"
MORNING_HOUR = 6
MORNING_MINUTE = 45
ZERO = {"hardware_commands": 0, "writes_farm_data": False,
        "customer_sends": 0, "protected_actions_performed": False}


def run_daily_farm_manager(*, owner_user_id, chat_id, specialist_results,
                           litter_rows, sale_rows=(), deliver, store=None, now=None,
                           language="en", semantic_prioritizer=None,
                           replace_brief=None):
    now = _aware(now or datetime.now(timezone.utc))
    local = now.astimezone(SAST)
    identity = f"OOM-DAILY-FARM-MANAGER-{local.date().isoformat()}"
    if str(owner_user_id) != str(chat_id) or not str(owner_user_id):
        return {"success": False, "status": "daily_manager_owner_binding_denied", **ZERO}
    store = store or daily_farm_manager_store
    projection_identity = _owner_projection_identity(identity, owner_user_id, chat_id)
    prior = store("load_daily", identity, {"owner_user_id": str(owner_user_id),
        "chat_id": str(chat_id)}) or {}
    if not prior and (local.hour, local.minute) < (MORNING_HOUR, MORNING_MINUTE):
        return {"success": True, "status": "daily_manager_not_due",
                "next_due_at": local.replace(hour=MORNING_HOUR, minute=MORNING_MINUTE,
                    second=0, microsecond=0).isoformat(), "telegram_sends": 0,
                "telegram_edits": 0, **ZERO}
    litter = build_litter_watch_result(litter_rows, now=now, language=language)
    sales = build_sale_watch_result(sale_rows, now=now, language=language)
    results = [row for row in specialist_results if isinstance(row, SpecialistResult)] + [litter, sales]
    answered = store("load_answered_questions", identity, {
        "owner_user_id": str(owner_user_id), "chat_id": str(chat_id),
        "daily_identity": identity}) or ()
    results = _retire_answered_questions(results, answered)
    packet = build_daily_management_packet(results, now=now, language=language,
        semantic_prioritizer=semantic_prioritizer)
    digest = packet["material_digest"]
    if prior.get("material_digest") == digest and prior.get("status") in {
            "presented", "unchanged"}:
        return {"success": True, "status": "daily_manager_unchanged_silent",
                "daily_identity": identity, "material_digest": digest,
                "telegram_sends": 0, "telegram_edits": 0,
                "next_due_at": _next_check(local), **ZERO}
    # One scheduled date owns one provider effect.  The material digest is
    # evidence carried by the claim, not part of its identity: evidence may
    # change while another worker starts or a process restarts.
    replacement = bool(prior.get("status") in {"presented", "unchanged"}
                       and prior.get("material_digest") != digest
                       and str(prior.get("telegram_message_id") or ""))
    claim_id = (projection_identity + ":GENERATION:" + digest[:20].upper()
                if replacement else projection_identity + ":DELIVERY")
    retry_proven = bool(prior.get("status") == "provider_ambiguous"
                        and prior.get("delivery_definitely_not_sent") is True
                        and prior.get("material_digest") == digest)
    claim = store("claim_daily", claim_id, {"daily_identity": identity,
        "material_digest": digest, "status": "detected", "observed_at": now.isoformat(),
        "task_identities": [row["task_id"] for row in packet["all_tasks"]],
        "contract_version": CONTRACT_VERSION})
    if not isinstance(claim, dict) or claim.get("success") is not True:
        return {"success": False, "status": "daily_manager_claim_unproven",
                "telegram_sends": 0, "telegram_edits": 0, **ZERO}
    # A duplicate claim may be a restart before the provider attempt. Continue
    # into the family lifecycle: its attempt claim safely sends when no attempt
    # exists and fails ambiguous without retry after any possible provider call.
    if claim.get("created") is False and store is not daily_farm_manager_store and not retry_proven:
        return {"success": True, "status": "daily_manager_replay_suppressed",
                "daily_identity": identity, "material_digest": digest,
                "telegram_sends": 0, "telegram_edits": 0, **ZERO}
    for task in packet["all_tasks"]:
        detected = store("record_task", task["task_id"], {**task, "daily_identity": identity,
            "lifecycle_state": "detected", "detected_at": now.isoformat()})
        if not isinstance(detected, dict) or detected.get("success") is not True:
            return {"success": False, "status": "daily_manager_task_receipt_unavailable",
                "daily_identity": identity, "material_digest": digest,
                "telegram_sends": 0, "telegram_edits": 0, **ZERO}
    parsed = {"telegram_user_id": str(owner_user_id), "telegram_chat_id": str(chat_id),
        "telegram_chat_type": "private", "output_language": str(language),
        "provider_message_id": "scheduled:" + claim_id,
        "provider_timestamp": now.isoformat(), "text": "Daily Farm Manager"}
    result = {"success": True, "status": "daily_farm_manager_ready",
        "answer": packet["answer"], "result_digest": digest,
        "recipient_render_contract": "specialist_structured_recipient_v1",
        "recipient_language": str(language),
        "rolling_brief_replacement": replacement,
        "hardware_commands": 0, "writes_farm_data": False}
    retry_authority = None
    if retry_proven:
        from modules.oom_sakkie.delivery_retry_authority import issue_delivery_retry_authority
        retry_authority = issue_delivery_retry_authority(mission_id=claim_id,
            card_mission_id=projection_identity, text=packet["answer"],
            proof_identity=projection_identity + ":PROVIDER-DEFINITELY-NOT-SENT")
    if replacement:
        if replace_brief is None:
            from modules.oom_sakkie.family_message_lifecycle import replace_current_brief
            replace_brief = replace_current_brief
        delivery = replace_brief(parsed, result, mission_id=claim_id,
            card_mission_id=projection_identity,
            previous_message_id=str(prior.get("telegram_message_id") or ""),
            generation_digest=digest)
    else:
        delivery = deliver(parsed, result, specialist="OOM_SAKKIE",
            mission_id=claim_id, card_mission_id=projection_identity,
            delivery_retry_authority=retry_authority)
    message_id = str((delivery or {}).get("telegram_message_id") or "")
    provider_confirmed = bool(message_id and ((delivery or {}).get("success") is True
        or (delivery or {}).get("provider_delivery_confirmed") is True))
    if not provider_confirmed:
        store("record_daily", claim_id + ":OUTCOME", {"daily_identity": identity,
            "material_digest": digest, "status": "provider_ambiguous",
            "observed_at": now.isoformat(), "telegram_sends": 0,
            "owner_user_id": str(owner_user_id), "chat_id": str(chat_id),
            "delivery_definitely_not_sent":
                (delivery or {}).get("delivery_definitely_not_sent") is True})
        return {"success": False, "status": "daily_manager_delivery_ambiguous",
                "daily_identity": identity, "material_digest": digest,
                "telegram_sends": 0, "telegram_edits": 0, **ZERO}
    if delivery.get("success") is not True:
        store("record_daily", claim_id + ":OUTCOME", {"daily_identity": identity,
            "material_digest": digest, "status": "provider_confirmed_receipt_unavailable",
            "observed_at": now.isoformat(), "telegram_message_id": message_id,
            "telegram_sends": int(delivery.get("telegram_sends") or 1)})
        return {"success": False,
            "status": "daily_manager_provider_confirmed_receipt_unavailable",
            "daily_identity": identity, "material_digest": digest,
            "telegram_message_id": message_id,
            "telegram_sends": int(delivery.get("telegram_sends") or 1),
            "telegram_edits": int(delivery.get("telegram_edits") or 0), **ZERO}
    task_receipts_proven = True
    for task in packet["all_tasks"]:
        receipt = store("record_task", task["task_id"] + ":PRESENTED:" + digest[:16],
            {**task, "daily_identity": identity, "lifecycle_state": "presented",
             "presented_at": now.isoformat(),
             "telegram_message_id": str(delivery.get("telegram_message_id"))})
        task_receipts_proven = task_receipts_proven and isinstance(receipt, dict) \
            and receipt.get("success") is True
    outcome = store("record_daily", claim_id + ":OUTCOME", {"daily_identity": identity,
        "material_digest": digest, "status": "presented", "observed_at": now.isoformat(),
        "owner_user_id": str(owner_user_id), "chat_id": str(chat_id),
        "question": packet["question"], "question_binding": packet["question_binding"],
        "telegram_message_id": str(delivery.get("telegram_message_id")),
        "telegram_sends": int(delivery.get("telegram_sends") or 0),
        "previous_telegram_message_id": str(prior.get("telegram_message_id") or "")
            if replacement else "",
        "generation_replaced": replacement})
    if not task_receipts_proven or not isinstance(outcome, dict) or outcome.get("success") is not True:
        return {"success": False, "status": "daily_manager_provider_confirmed_lifecycle_unavailable",
            "daily_identity": identity, "material_digest": digest,
            "telegram_message_id": message_id,
            "telegram_sends": int(delivery.get("telegram_sends") or 1),
            "telegram_edits": int(delivery.get("telegram_edits") or 0), **ZERO}
    return {"success": True, "status": "daily_manager_presented",
        "daily_identity": identity, "material_digest": digest,
        "telegram_message_id": str(delivery.get("telegram_message_id")),
        "telegram_sends": int(delivery.get("telegram_sends") or 0),
        "telegram_edits": int(delivery.get("telegram_edits") or 0),
        "task_count": len(packet["all_tasks"]), "priority_count": len(packet["priorities"]),
        "next_due_at": _next_check(local), **ZERO}


def build_litter_watch_result(rows, *, now=None, language="en"):
    now = _aware(now or datetime.now(timezone.utc)); today = now.astimezone(SAST).date()
    rows = [dict(row) for row in rows or () if isinstance(row, dict)]
    items = []
    active_by_sow = {}
    for row in rows:
        status = _text(row, "Litter_Status", "litter_status").lower()
        if status != "active":
            continue
        litter_id = _text(row, "Litter_ID", "litter_id")
        sow_id = _text(row, "Sow_Pig_ID", "sow_pig_id")
        sow_tag = _text(row, "Sow_Tag_Number", "sow_tag_number") or sow_id
        active_by_sow.setdefault(sow_id, []).append(row)
    conflicting_sows = {sow_id for sow_id, active in active_by_sow.items()
        if len({_text(row, "Litter_ID", "litter_id") for row in active}) > 1}
    for row in rows:
        status = _text(row, "Litter_Status", "litter_status").lower()
        if status != "active":
            continue
        litter_id = _text(row, "Litter_ID", "litter_id")
        sow_id = _text(row, "Sow_Pig_ID", "sow_pig_id")
        sow_tag = _text(row, "Sow_Tag_Number", "sow_tag_number") or sow_id
        expected = _date(_text(row, "Wean_Date", "wean_date"))
        weaned = row.get("Weaned_Count", row.get("weaned_count"))
        if sow_id not in conflicting_sows and expected and expected <= today and weaned in (None, ""):
            overdue = (today - expected).days
            af = str(language).lower().startswith("af")
            result_id = "HERD-LITTER-WATCH-" + sha256(
                f"{litter_id}|{expected.isoformat()}|{status}|{weaned}".encode()).hexdigest()[:20]
            provenance = Provenance("herdmaster", result_id,
                ("canonical_litter:" + litter_id,), now, 1.0)
            why = ((f"{sow_tag} se werpsel moes op {expected.isoformat()} gespeen word en is "
                    f"{overdue} dae laat; die huidige werpsel is steeds Aktief en geen gespeende telling bewys voltooiing nie.")
                   if af else (f"{sow_tag}'s litter was due for weaning on {expected.isoformat()} and is "
                    f"{overdue} day{'s' if overdue != 1 else ''} overdue; the canonical litter "
                    "is still Active and no weaned count proves completion."))
            items.append(SpecialistWorkItem(item_id=result_id, dedupe_key="weaning:"+litter_id,
                domain="herd", title=(f"Speenwerk laat — {sow_tag}" if af else f"Weaning overdue — {sow_tag}"), why=why,
                next_action=("Berei die presiese varkie-, merk-, gewig- en skuifvoorskou voor; teken speen eers ná bevestiging aan."
                    if af else "Prepare the exact piglet, tag, weight and movement preview; record weaning only after confirmation."),
                assignee="charl", state=WorkState.URGENT if overdue > 1 else WorkState.DUE_TODAY,
                authority=Authority.OWNER_DECISION, provenance=provenance,
                business_value=130, due_at=datetime.combine(expected, datetime.min.time(), SAST)))
    for sow_id, active in active_by_sow.items():
        identities = {_text(row, "Litter_ID", "litter_id") for row in active}
        if len(identities) <= 1:
            continue
        sow_tag = _text(active[0], "Sow_Tag_Number", "sow_tag_number") or sow_id
        result_id = "HERD-LITTER-CONFLICT-" + sha256(
            f"{sow_id}|{'|'.join(sorted(identities))}".encode()).hexdigest()[:20]
        provenance = Provenance("herdmaster", result_id,
            tuple("canonical_litter:"+value for value in sorted(identities)), now, 1.0)
        af = str(language).lower().startswith("af")
        items.append(SpecialistWorkItem(item_id=result_id, dedupe_key="litter-conflict:"+sow_id,
            domain="herd", title=(f"Huidige-werpsel-konflik — {sow_tag}" if af else f"Current-litter conflict — {sow_tag}"),
            why=(f"{sow_tag} het {len(identities)} huidige werpsels as Aktief gemerk; dit is 'n bronrekordkonflik."
                if af else f"{sow_tag} has {len(identities)} canonical litters marked Active; this is a source-record conflict."),
            next_action=("Los die duplikaat huidige-werpsel-skakel deur die beheerde datakwaliteitspad op; geen fisiese waarneming is nodig nie."
                if af else "Resolve the duplicate current-litter linkage through the governed data-quality path; no physical observation is needed."),
            assignee="charl", state=WorkState.WAITING_EVIDENCE,
            authority=Authority.READ_ONLY, provenance=provenance, business_value=105))
    result_id = "HERD-LITTER-ROUND-" + sha256("|".join(sorted(
        item.item_id for item in items)).encode()).hexdigest()[:20]
    rebound = tuple(SpecialistWorkItem(**{**item.__dict__, "provenance": Provenance(
        "herdmaster", result_id, item.provenance.source_refs, now, 1.0)}) for item in items)
    return SpecialistResult("herdmaster", result_id, now,
        SpecialistAvailability.AVAILABLE, work_items=rebound)


def build_sale_watch_result(rows, *, now=None, language="en"):
    """Project current sale readiness without creating a commitment or write."""
    now = _aware(now or datetime.now(timezone.utc)); today = now.astimezone(SAST).date()
    items = []
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        sale_id = _text(row, "sale_id"); sale_date = _date(_text(row, "sale_date"))
        if not sale_id or not sale_date or sale_date > today:
            continue
        sale_status = _text(row, "sale_status").casefold()
        payment = _text(row, "payment_status").casefold()
        if sale_status == "cancelled" or (sale_status == "completed"
                and payment in {"paid", "settled", "not_applicable", "not applicable"}):
            continue
        missing = []
        if sale_status != "completed" and int(row.get("item_count") or 0) <= 0:
            missing.append("selected animal/items")
        if sale_status != "completed" and not _text(row, "external_reference"):
            missing.append("paperwork/reference")
        if payment not in {"paid", "settled"}: missing.append("payment/settlement follow-up")
        label = (_text(row, "buyer_name") or _text(row, "destination")
                 or _text(row, "sale_channel") or "Farm sale")
        stream = _text(row, "sale_stream") or _text(row, "sale_channel") or "Sale"
        amount = row.get("net_settlement_payable")
        amount_kind = "settlement payable"
        if amount in (None, ""):
            amount = row.get("net_total")
            amount_kind = "amount due"
        amount_text = _money(amount)
        action_url = "/sales/transactions/" + sale_id
        result_id = "SALE-WATCH-" + sha256(f"{sale_id}|{sale_status}|{payment}|{amount}|{'|'.join(missing)}".encode()).hexdigest()[:20]
        provenance = Provenance("sam", result_id, ("canonical_sale:" + sale_id,), now, 1.0)
        due = "today" if sale_date == today else f"since {sale_date.isoformat()}"
        af = str(language).lower().startswith("af")
        items.append(SpecialistWorkItem(item_id=result_id, dedupe_key="sale:" + sale_id,
            domain="sales", title=(f"Betaling — {label}" if af else f"Payment — {label}"),
            why=((f"{stream}: {amount_text} {amount_kind}; betaling is {payment or 'Onbekend'} {due}. "
                  f"Uitstaande: {', '.join(missing) or 'finale verifikasie'}.")
                if af else (f"{stream}: {amount_text} {amount_kind}; payment is {payment or 'Unknown'} {due}. "
                            f"Outstanding: {', '.join(missing) or 'final verification'}.")),
            next_action=((f"Hersien betalingsbewys; slegs voorskou eerste: {action_url}")
                if af else f"Review payment evidence; preview only first: {action_url}"),
            assignee="charl", state=WorkState.DUE_TODAY,
            authority=Authority.OWNER_DECISION, provenance=provenance,
            business_value=115, due_at=datetime.combine(sale_date, datetime.min.time(), SAST)))
    result_id = "SALE-ROUND-" + sha256("|".join(sorted(item.item_id for item in items)).encode()).hexdigest()[:20]
    rebound = tuple(SpecialistWorkItem(**{**item.__dict__, "provenance": Provenance(
        "sam", result_id, item.provenance.source_refs, now, 1.0)}) for item in items)
    return SpecialistResult("sam", result_id, now, SpecialistAvailability.AVAILABLE,
        work_items=rebound)


def build_daily_management_packet(results, *, now=None, language="en",
                                  semantic_prioritizer=None):
    now = _aware(now or datetime.now(timezone.utc))
    by_key = {}
    for result in results:
        if not isinstance(result, SpecialistResult) or result.availability not in {
                SpecialistAvailability.AVAILABLE, SpecialistAvailability.STALE}:
            continue
        for item in result.work_items:
            if item.state in {WorkState.COMPLETED, WorkState.HANDLED}:
                continue
            key = item.dedupe_key
            prior = by_key.get(key)
            if prior is None or _priority(item) < _priority(prior):
                by_key[key] = item
    ordered = sorted(by_key.values(), key=_priority)
    selected = (semantic_prioritizer or _semantic_prioritize)(ordered, language=language)
    ordered = _validated_semantic_order(ordered, selected)
    priorities = ordered[:3]; watch = ordered[3:6]
    question = next((item.genuine_question for item in ordered
                     if item.genuine_question.strip()), "")
    tasks = [_task(row) for row in ordered]
    material = {"priorities": [_material(row) for row in priorities],
        "watch": [_material(row) for row in watch], "question": question}
    digest = sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    question_item = next((item for item in ordered
                          if item.genuine_question.strip() == question), None)
    pig_refs = ([str(value).removeprefix("pig:")
                 for value in question_item.provenance.source_refs
                 if str(value).startswith("pig:") and str(value).removeprefix("pig:")]
                if question_item else [])
    question_binding = ({"task_id": question_item.item_id,
        "dedupe_key": question_item.dedupe_key, "domain": question_item.domain,
        "question": question,
        **({"pig_id": pig_refs[0]} if len(set(pig_refs)) == 1 else {})}
        if question_item else {})
    return {"contract_version": CONTRACT_VERSION, "material_digest": digest,
        "priorities": priorities, "watch": watch, "all_tasks": tasks,
        "question": question, "question_binding": question_binding,
        "answer": _render(priorities, watch, question, now, language)}


def daily_farm_manager_store(action, identity, payload):
    if action == "load_daily":
        return _load_daily(identity, payload or {})
    if action == "load_answered_questions":
        return _load_answered_questions(payload or {})
    from modules.sales.sam_live_stock_launch_control import (
        build_sam_live_stock_review_event, record_sam_live_stock_review_event)
    body = dict(payload or {})
    event_id = identity
    event = build_sam_live_stock_review_event({"conversation_id": identity}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "daily_farm_manager"},
        event_source=EVENT_SOURCE)
    event.update({"review_event_id": event_id, "chatwoot_conversation_id": identity,
        "review_json": {"daily_farm_manager": {**body, "event_id": event_id,
            "event_kind": action}}, "decision_json": {}, "facts_json": {},
        "customer_message_excerpt": "", "sam_reply_excerpt": ""})
    result, status = record_sam_live_stock_review_event(event)
    return {**result, "success": status < 400 and result.get("success") is True,
        "created": result.get("created", status < 300)}


def _load_daily(identity, binding):
    with connect_bounded_read() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'daily_farm_manager'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'daily_farm_manager'->>'daily_identity'=%s
                  and review_json->'daily_farm_manager'->>'owner_user_id'=%s
                  and review_json->'daily_farm_manager'->>'chat_id'=%s
                  and review_json->'daily_farm_manager'->>'status' in
                      ('presented','unchanged','provider_ambiguous')
                order by created_at desc, review_event_id desc limit 1""",
                (EVENT_SOURCE, identity, str(binding.get("owner_user_id") or ""),
                 str(binding.get("chat_id") or "")))
            row = cursor.fetchone(); return row[0] if row else None


def _load_answered_questions(binding):
    if not str(os.environ.get("DATABASE_URL") or "").strip():
        return ()
    with connect_bounded_read() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'manager_question_reply'
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_manager_question_reply'
                  and review_json->'manager_question_reply'->>'owner_user_id'=%s
                  and review_json->'manager_question_reply'->>'chat_id'=%s
                  and review_json->'manager_question_reply'->>'status'='recorded'
                order by created_at, review_event_id""",
                (str(binding.get("owner_user_id") or ""),
                 str(binding.get("chat_id") or "")))
            values = []
            current_identity = str(binding.get("daily_identity") or "")
            for row in cursor.fetchall():
                if not row or not isinstance(row[0], dict):
                    continue
                value = dict(row[0])
                value["durable_concern_receipt"] = bool(
                    current_identity and str(value.get("daily_identity") or "") != current_identity)
                values.append(value)
            return tuple(values)


def _render(priorities, watch, question, now, language):
    af = str(language).lower().startswith("af")
    visible = list(priorities) + list(watch)
    owner_work = [row for row in visible if _owner_action_required(row)]
    automatic_work = [row for row in visible if not _owner_action_required(row)]
    lines = ["<b>VANDAG SE PLAASPLAN</b>" if af
             else "<b>TODAY'S FARM PLAN</b>"]
    if owner_work:
        lines.append("<b>AKSIE NODIG</b>" if af else "<b>ACTION NEEDED</b>")
        lines.extend(f"{index}. <b>{html.escape(_compact(row.title, 110))}</b> "
                     f"{html.escape(_compact(row.next_action, 170))}"
                     for index, row in enumerate(owner_work, 1))
    if automatic_work:
        lines.extend(("", "<b>OOM SAKKIE KONTROLEER OUTOMATIES</b>" if af
                      else "<b>OOM SAKKIE IS CHECKING AUTOMATICALLY</b>"))
        lines.extend(f"• <b>{html.escape(_compact(row.title, 110))}</b>"
                     for row in automatic_work)
    if not owner_work and not automatic_work:
        lines.append("Geen nuwe werk nie." if af else "No new work.")
    if question:
        lines.extend(("", "<b>EEN VRAAG</b>" if af else "<b>ONE QUESTION</b>",
                      html.escape(question)))
    elif not owner_work:
        lines.extend(("", "Geen aksie word nou van jou benodig nie."
                      if af else "No action required from you."))
    return "\n".join(lines)


def _owner_action_required(item):
    """Keep specialist-owned reconciliation out of the owner's action list."""
    return (bool(item.genuine_question.strip())
            or item.authority is Authority.OWNER_DECISION
            or item.metadata.get("physical_work_ready") is True)


def _task(item):
    return {"task_id": item.item_id, "dedupe_key": item.dedupe_key,
        "domain": item.domain, "title": item.title, "why": item.why,
        "next_action": item.next_action, "state": item.state.value,
        "authority": item.authority.value,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "source_refs": list(item.provenance.source_refs)}


def _material(item):
    material = {"dedupe_key": item.dedupe_key, "title": item.title, "why": item.why,
        "state": item.state.value, "authority": item.authority.value}
    if _owner_action_required(item):
        material.update({"next_action": item.next_action,
            "due_at": item.due_at.isoformat() if item.due_at else None})
    return material


def _owner_projection_identity(daily_identity, owner_user_id, chat_id):
    scope = sha256(f"{owner_user_id}|{chat_id}".encode()).hexdigest()[:16].upper()
    return f"{daily_identity}:OWNER:{scope}"


def _priority(item):
    rank = {WorkState.URGENT: 0, WorkState.DUE_TODAY: 1,
        WorkState.PROTECTED_OWNER_DECISION: 2, WorkState.PLANNED: 3,
        WorkState.WAITING_EVIDENCE: 4}.get(item.state, 9)
    return (rank, -item.business_value,
            item.due_at or datetime.max.replace(tzinfo=timezone.utc), item.item_id)


def _semantic_prioritize(items, *, language="en"):
    """Ask the approved read-only LLM to rank supported task identities only."""
    from modules.oom_sakkie.llm_router import API_KEY_ENV, API_URL_ENV, DEFAULT_API_URL, MODEL_ENV
    if str(os.environ.get("OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED") or "").lower() not in {
            "1", "true", "yes", "on"}:
        return None
    model = str(os.environ.get(MODEL_ENV) or "").strip()
    key = str(os.environ.get(API_KEY_ENV) or "").strip()
    if not model or not key or not items:
        return None
    tasks = [{"task_id": row.item_id, "title": row.title, "why": row.why,
              "next_action": row.next_action, "state": row.state.value,
              "due_at": row.due_at.isoformat() if row.due_at else None,
              "authority": row.authority.value} for row in items]
    payload = {"model": model, "temperature": 0, "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": (
            "You are Oom Sakkie's farm-management prioritizer. Rank only supplied task_id values. "
            "Put urgent welfare, overdue work, today's protected readiness, and time-critical farm work first. "
            "Missing evidence blocks only its dependent conclusion. Never invent facts, tasks, completion or authority. "
            "Return JSON with ordered_task_ids containing every supplied identity exactly once.")},
            {"role": "user", "content": json.dumps({"language": language, "tasks": tasks},
                separators=(",", ":"))}]}
    request = urllib_request.Request(str(os.environ.get(API_URL_ENV) or DEFAULT_API_URL),
        data=json.dumps(payload).encode(), headers={"Authorization": "Bearer " + key,
        "Content-Type": "application/json"}, method="POST")
    try:
        with urllib_request.urlopen(request, timeout=8) as response:
            envelope = json.loads(response.read().decode())
        content = json.loads(str(envelope["choices"][0]["message"]["content"]))
        return content.get("ordered_task_ids")
    except (KeyError, IndexError, TypeError, ValueError, OSError, TimeoutError,
            json.JSONDecodeError, urllib_error.URLError, urllib_error.HTTPError):
        return None


def _validated_semantic_order(items, selected):
    """Deterministic code rejects additions, omissions, duplication and stale IDs."""
    if not isinstance(selected, list):
        return list(items)
    identities = [row.item_id for row in items]
    proposed = [str(value) for value in selected]
    if len(proposed) != len(set(proposed)) or set(proposed) != set(identities):
        return list(items)
    by_id = {row.item_id: row for row in items}
    ordered = [by_id[value] for value in proposed]
    deterministic_classes = [_priority(row)[0] for row in ordered]
    if deterministic_classes != sorted(deterministic_classes):
        return list(items)
    return ordered


def _retire_answered_questions(results, answered):
    receipts = tuple(value for value in answered or () if isinstance(value, dict))
    if not receipts:
        return results
    projected = []
    for result in results:
        if not isinstance(result, SpecialistResult):
            projected.append(result)
            continue
        if result.specialist == "herdmaster":
            from modules.oom_sakkie.herdmaster_daily_manager_adapter import (
                reconcile_manager_question_answer)
            for receipt in receipts:
                result = reconcile_manager_question_answer(result, receipt)
        projected.append(result)
    return projected


def _compact(value, limit):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    clipped = text[:max(1, limit - 1)].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return clipped + "…"


def _money(value):
    try:
        return f"R{float(value):,.2f}"
    except (TypeError, ValueError):
        return "Amount unknown"


def _text(row, *keys):
    return next((str(row.get(key) or "").strip() for key in keys if row.get(key) not in (None, "")), "")


def _date(value):
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _next_check(local):
    rounded = local.replace(second=0, microsecond=0)
    return (rounded + timedelta(minutes=15 - rounded.minute % 15)).isoformat()


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
