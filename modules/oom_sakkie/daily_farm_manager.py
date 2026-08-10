"""Scheduler-owned, read-only Daily Farm Manager coordination lifecycle."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import html
import json
import os
from urllib import error as urllib_error, request as urllib_request
from zoneinfo import ZoneInfo

from modules.oom_sakkie.farm_manager_loop import (
    Authority, Provenance, SpecialistAvailability, SpecialistResult,
    SpecialistWorkItem, WorkState,
)

SAST = ZoneInfo("Africa/Johannesburg")
CONTRACT_VERSION = "oom_sakkie_daily_farm_manager.v1"
EVENT_SOURCE = "oom_sakkie_daily_farm_manager"
MORNING_HOUR = 6
MORNING_MINUTE = 45
ZERO = {"hardware_commands": 0, "writes_farm_data": False,
        "customer_sends": 0, "protected_actions_performed": False}


def run_daily_farm_manager(*, owner_user_id, chat_id, specialist_results,
                           litter_rows, sale_rows=(), deliver, store=None, now=None,
                           language="en", semantic_prioritizer=None):
    now = _aware(now or datetime.now(timezone.utc))
    local = now.astimezone(SAST)
    identity = f"OOM-DAILY-FARM-MANAGER-{local.date().isoformat()}"
    if str(owner_user_id) != str(chat_id) or not str(owner_user_id):
        return {"success": False, "status": "daily_manager_owner_binding_denied", **ZERO}
    store = store or daily_farm_manager_store
    prior = store("load_daily", identity, None) or {}
    if not prior and (local.hour, local.minute) < (MORNING_HOUR, MORNING_MINUTE):
        return {"success": True, "status": "daily_manager_not_due",
                "next_due_at": local.replace(hour=MORNING_HOUR, minute=MORNING_MINUTE,
                    second=0, microsecond=0).isoformat(), "telegram_sends": 0,
                "telegram_edits": 0, **ZERO}
    litter = build_litter_watch_result(litter_rows, now=now, language=language)
    sales = build_sale_watch_result(sale_rows, now=now, language=language)
    results = [row for row in specialist_results if isinstance(row, SpecialistResult)] + [litter, sales]
    packet = build_daily_management_packet(results, now=now, language=language,
        semantic_prioritizer=semantic_prioritizer)
    digest = packet["material_digest"]
    if prior.get("material_digest") == digest and prior.get("status") in {
            "presented", "unchanged"}:
        return {"success": True, "status": "daily_manager_unchanged_silent",
                "daily_identity": identity, "material_digest": digest,
                "telegram_sends": 0, "telegram_edits": 0,
                "next_due_at": _next_check(local), **ZERO}
    claim_id = identity + ":" + digest[:24]
    claim = store("claim_daily", claim_id, {"daily_identity": identity,
        "material_digest": digest, "status": "detected", "observed_at": now.isoformat(),
        "task_identities": [row["task_id"] for row in packet["all_tasks"]],
        "contract_version": CONTRACT_VERSION})
    if not isinstance(claim, dict) or claim.get("success") is not True:
        return {"success": False, "status": "daily_manager_claim_unproven",
                "telegram_sends": 0, "telegram_edits": 0, **ZERO}
    if claim.get("created") is False:
        return {"success": True, "status": "daily_manager_replay_suppressed",
                "daily_identity": identity, "material_digest": digest,
                "telegram_sends": 0, "telegram_edits": 0, **ZERO}
    for task in packet["all_tasks"]:
        store("record_task", task["task_id"], {**task, "daily_identity": identity,
            "lifecycle_state": "detected", "detected_at": now.isoformat()})
    parsed = {"telegram_user_id": str(owner_user_id), "telegram_chat_id": str(chat_id),
        "provider_message_id": "scheduled:" + claim_id,
        "provider_timestamp": now.isoformat(), "text": "Daily Farm Manager"}
    result = {"success": True, "status": "daily_farm_manager_ready",
        "answer": packet["answer"], "result_digest": digest,
        "hardware_commands": 0, "writes_farm_data": False}
    delivery = deliver(parsed, result, specialist="OOM_SAKKIE",
        mission_id=claim_id, card_mission_id=identity)
    if not isinstance(delivery, dict) or delivery.get("success") is not True \
            or not str(delivery.get("telegram_message_id") or ""):
        store("record_daily", claim_id + ":OUTCOME", {"daily_identity": identity,
            "material_digest": digest, "status": "provider_ambiguous",
            "observed_at": now.isoformat(), "telegram_sends": 0})
        return {"success": False, "status": "daily_manager_delivery_ambiguous",
                "daily_identity": identity, "material_digest": digest,
                "telegram_sends": 0, "telegram_edits": 0, **ZERO}
    for task in packet["all_tasks"]:
        store("record_task", task["task_id"] + ":PRESENTED:" + digest[:16],
            {**task, "daily_identity": identity, "lifecycle_state": "presented",
             "presented_at": now.isoformat(),
             "telegram_message_id": str(delivery.get("telegram_message_id"))})
    store("record_daily", claim_id + ":OUTCOME", {"daily_identity": identity,
        "material_digest": digest, "status": "presented", "observed_at": now.isoformat(),
        "telegram_message_id": str(delivery.get("telegram_message_id")),
        "telegram_sends": int(delivery.get("telegram_sends") or 0)})
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
                and payment in {"paid", "settled"}):
            continue
        missing = []
        if int(row.get("item_count") or 0) <= 0: missing.append("selected animal/items")
        if not _text(row, "external_reference"): missing.append("paperwork/reference")
        if payment not in {"paid", "settled"}: missing.append("payment/settlement follow-up")
        result_id = "SALE-WATCH-" + sha256(f"{sale_id}|{sale_status}|{payment}|{'|'.join(missing)}".encode()).hexdigest()[:20]
        provenance = Provenance("sam", result_id, ("canonical_sale:" + sale_id,), now, 1.0)
        due = "today" if sale_date == today else f"since {sale_date.isoformat()}"
        af = str(language).lower().startswith("af")
        items.append(SpecialistWorkItem(item_id=result_id, dedupe_key="sale:" + sale_id,
            domain="sales", title=(f"Verkoopgereedheid — {sale_id}" if af else f"Sale readiness — {sale_id}"),
            why=(f"Die huidige verkoop is {due} betaalbaar; uitstaande: {', '.join(missing) or 'finale oorhandigingsverifikasie'}."
                if af else f"The canonical sale is due {due}; outstanding: {', '.join(missing) or 'final handover verification'}."),
            next_action=("Berei die ondersteunde oorhandigings- en vereffeningsbewyse voor; vra Charl net vir enige beskermde verbintenis wat nog ontbreek."
                if af else "Prepare the supported handover and settlement evidence; ask Charl only for any protected commitment still missing."),
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
    priorities = ordered[:3]; watch = ordered[3:7]
    question = next((item.genuine_question for item in ordered
                     if item.genuine_question.strip()), "")
    tasks = [_task(row) for row in ordered]
    material = {"priorities": [_material(row) for row in priorities],
        "watch": [_material(row) for row in watch], "question": question}
    digest = sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"contract_version": CONTRACT_VERSION, "material_digest": digest,
        "priorities": priorities, "watch": watch, "all_tasks": tasks,
        "question": question, "answer": _render(priorities, watch, question, now, language)}


def daily_farm_manager_store(action, identity, payload):
    if action == "load_daily":
        return _load_daily(identity)
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


def _load_daily(identity):
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'daily_farm_manager'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'daily_farm_manager'->>'daily_identity'=%s
                  and review_json->'daily_farm_manager'->>'status' in
                      ('presented','unchanged','provider_ambiguous')
                order by created_at desc, review_event_id desc limit 1""",
                (EVENT_SOURCE, identity))
            row = cursor.fetchone(); return row[0] if row else None


def _render(priorities, watch, question, now, language):
    af = str(language).lower().startswith("af")
    lines = ["<b>🌅 OOM SAKKIE — VANDAG SE PLAASPLAN</b>" if af
             else "<b>🌅 OOM SAKKIE — TODAY'S FARM PLAN</b>", "",
             "<b>DOEN NOU / VANDAG</b>" if af else "<b>DO NOW / DO TODAY</b>"]
    if priorities:
        next_label = "Volgende" if af else "Next"
        lines.extend(f"• <b>{html.escape(row.title)}</b> — {html.escape(row.why)} "
                     f"<i>{next_label}:</i> {html.escape(row.next_action)}"
                     for row in priorities)
    else:
        lines.append("• Geen nuwe aksie nodig nie." if af else "• No new action is required.")
    if watch:
        lines.extend(("", "<b>KOMENDE / HOU DOP</b>" if af else "<b>COMING UP / WATCH</b>"))
        lines.extend(f"• {html.escape(row.title)} — {html.escape(row.why)}" for row in watch)
    if question:
        lines.extend(("", "<b>EEN VRAAG</b>" if af else "<b>ONE QUESTION</b>",
                      html.escape(question)))
    else:
        lines.extend(("", "Geen aksie word nou van jou benodig nie."
                      if af else "No action required from you."))
    lines.extend(("", ("Volgende outomatiese kontrole: binne 15 minute of wanneer kernbewyse verander."
                       if af else "Next automatic check: within 15 minutes or when material evidence changes.")))
    return "\n".join(lines)


def _task(item):
    return {"task_id": item.item_id, "dedupe_key": item.dedupe_key,
        "domain": item.domain, "title": item.title, "why": item.why,
        "next_action": item.next_action, "state": item.state.value,
        "authority": item.authority.value,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "source_refs": list(item.provenance.source_refs)}


def _material(item):
    return {"dedupe_key": item.dedupe_key, "title": item.title, "why": item.why,
        "next_action": item.next_action, "state": item.state.value,
        "authority": item.authority.value,
        "due_at": item.due_at.isoformat() if item.due_at else None}


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
