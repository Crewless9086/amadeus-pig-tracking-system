"""Canonical, read-only candidate collectors for the general manager worker."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read


def collect_manager_candidates(*, now: datetime, collectors=None):
    selected = collectors or (_rootline, _herdmaster, _auction, _sam, _beacon, _delivery_gaps, _runtime)
    selected = tuple(selected)

    def collect(collector):
        try:
            rows = collector(now)
            return [dict(row) for row in rows or ()]
        except Exception as exc:
            name = getattr(collector, "__name__", "collector").strip("_") or "collector"
            return [_candidate(
                dedupe_key=f"runtime:collector:{name}", specialist="RUNTIME", urgency="urgent",
                refs=[f"collector:{name}:{exc.__class__.__name__}"],
                unknowns=[f"current_{name}_specialist_evidence"],
                summary=f"Oom Sakkie could not load current {name} evidence.",
                next_action=f"Retry the canonical {name} collector; retain the case until evidence loads or one precise dependency is recorded.",
                next_at=now + timedelta(minutes=5))]

    if len(selected) <= 1:
        groups = [collect(value) for value in selected]
    else:
        with ThreadPoolExecutor(max_workers=min(6, len(selected)),
                                thread_name_prefix="oom-manager-read") as executor:
            groups = list(executor.map(collect, selected))
    result = []
    for group in groups:
        result.extend(group)
    return result


def collect_manager_candidate(*, now: datetime, dedupe_key: str, specialist: str,
                              collectors=None):
    """Refresh one case from only its canonical owning collector."""
    dedupe_key = str(dedupe_key or "")
    prefix = ("auction" if dedupe_key.startswith("herdmaster:riversdale-auction:")
              else dedupe_key.split(":", 1)[0].casefold())
    configured = {
        "rootline": (_rootline, "ROOTLINE"),
        "herdmaster": (_herdmaster, "HERDMASTER"),
        "auction": (_auction, "HERDMASTER"),
        "sam": (_sam, "SAM"), "beacon": (_beacon, "BEACON"),
        "delivery": (_delivery_gaps, None), "runtime": (_runtime, "RUNTIME"),
    }
    selected = configured.get(prefix)
    claimed_specialist = str(specialist or "").upper()
    if selected is None or (selected[1] and selected[1] != claimed_specialist):
        return None
    if prefix == "delivery":
        parts = str(dedupe_key).split(":", 2)
        if len(parts) < 3 or parts[1].upper() != claimed_specialist:
            return None
    collector = selected[0]
    if collectors is not None:
        expected_name = ("delivery_gaps" if prefix == "delivery" else
                         "auction" if prefix == "auction" else prefix)
        collector = next((value for value in collectors
            if getattr(value, "__name__", "").strip("_").casefold() == expected_name), None)
        if collector is None:
            return None
    rows = collect_manager_candidates(now=now, collectors=(collector,))
    return next((row for row in rows
                 if str(row.get("dedupe_key") or "") == str(dedupe_key)
                 and str(row.get("specialist") or "").upper() == claimed_specialist), None)


def _auction(now):
    from modules.oom_sakkie.riversdale_auction_manager import collect_auction_manager_case
    return collect_auction_manager_case(now)


def _rootline(now):
    local_date = _aware(now).astimezone(ZoneInfo("Africa/Johannesburg")).date().isoformat()
    with connect_bounded_read() as connection:
        with connection.cursor() as cur:
            cur.execute("""select review_event_id,created_at,
                    review_json->'rootline_reassessment'
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_rootline_reassessment'
                  and review_json->'rootline_reassessment'->>'delivery_state'='observation_only'
                  and review_json->'rootline_reassessment'->>'operating_date'=%s
                order by created_at desc,review_event_id desc limit 1""", (local_date,))
            observation_row = cur.fetchone()
            delivered_row = None
            if observation_row:
                observation = observation_row[2] or {}
                cur.execute("""select review_event_id,created_at,
                        review_json->'rootline_reassessment'
                    from public.sam_live_stock_conversation_review_events
                    where event_source='oom_sakkie_rootline_reassessment'
                      and review_json->'rootline_reassessment'->>'delivery_state'='delivered'
                      and review_json->'rootline_reassessment'->>'operating_date'=%s
                      and review_json->'rootline_reassessment'->>'material_digest'=%s
                      and review_json->'rootline_reassessment'->>'result_id'=%s
                      and review_json->'rootline_reassessment'->>'evidence_generation'=%s
                      and review_json->'rootline_reassessment'->>'owner_user_id'=%s
                      and review_json->'rootline_reassessment'->>'chat_id'=%s
                      and coalesce(review_json->'rootline_reassessment'->>'provider_message_id','')<>''
                    order by created_at desc,review_event_id desc limit 1""",
                    (local_date, str(observation.get("material_digest") or ""),
                     str(observation.get("result_id") or ""),
                     str(observation.get("evidence_generation") or ""),
                     str(observation.get("owner_user_id") or ""),
                     str(observation.get("chat_id") or "")))
                delivered_row = cur.fetchone()
    retry_at = now + timedelta(minutes=5)
    retry_text = retry_at.astimezone(ZoneInfo("Africa/Johannesburg")).strftime("%Y-%m-%d %H:%M SAST")
    if not observation_row:
        return [_candidate("rootline:current-plan", "ROOTLINE", "urgent",
            [f"operating_date:{local_date}", "canonical:rootline_observation:none"],
            ["current_date_canonical_rootline_observation"],
            f"ROOTLINE current-plan delivery exception: the current-date canonical ROOTLINE observation for {local_date} is missing.",
            ("Automatic acquisition owner: the existing Oom Sakkie ROOTLINE schedule must load "
             f"and persist the canonical observation; retry at {retry_text}. No hardware action is permitted."),
            retry_at, presentation_identity={"familiar_meaning": "Current water and energy plan",
                "stable_reference": local_date})]
    event_id, observed, payload = observation_row; payload = payload or {}
    if delivered_row:
        return []
    identities = {"material": str(payload.get("material_digest") or ""),
        "result": str(payload.get("result_id") or ""),
        "generation": str(payload.get("evidence_generation") or "")}
    missing = ["provider_confirmed_family_delivery_bound_to_current_plan"]
    missing.extend(f"current_plan_{key}_identity" for key, value in identities.items() if not value)
    return [_candidate("rootline:current-plan", "ROOTLINE", "urgent",
        [f"event:{event_id}", f"operating_date:{local_date}",
         f"material:{identities['material'] or 'missing'}",
         f"result:{identities['result'] or 'missing'}",
         f"generation:{identities['generation'] or 'missing'}",
         f"observed:{observed.isoformat()}"], missing,
        "ROOTLINE current-plan delivery exception: provider-confirmed family delivery is missing for the exact current-date material, result and generation.",
        ("Automatic acquisition owner: the existing Oom Sakkie ROOTLINE delivery lifecycle must "
         f"obtain and persist exact Telegram provider confirmation; retry at {retry_text}. "
         "Do not infer delivery or actuate hardware."), retry_at,
        presentation_identity={"familiar_meaning": "Current water and energy plan",
                               "stable_reference": local_date})]


def _herdmaster(now):
    owner = _configured_owner()
    if not owner:
        raise ValueError("owner_binding_unavailable")
    from modules.oom_sakkie.farm_manager_runtime import _load_herdmaster
    result = _load_herdmaster(None, owner, now)
    candidates = []
    from modules.pig_weights.pig_welfare_case_runtime import (
        load_open_welfare_attention_cases,
        project_welfare_case_attention,
        welfare_case_runtime_enabled,
    )
    if welfare_case_runtime_enabled():
        for welfare in load_open_welfare_attention_cases():
            projected = project_welfare_case_attention(welfare)
            case_id = projected["case_identity"]
            presentation_identity = _welfare_presentation_identity(welfare)
            pig_label = (presentation_identity.get("human_name") or
                         presentation_identity.get("familiar_meaning") or "Name unavailable")
            observed = str(welfare.get("welfare_case_observed_at") or now.isoformat())
            due = _time(welfare.get("welfare_case_next_check_at"), now)
            state = str(welfare.get("welfare_case_state") or "open")
            escalation = str(welfare.get("welfare_case_escalation_reason") or "").strip()
            action = ("Physically weigh now and record the weight through the governed rail."
                      if projected["task_class"] == "physical_action_due"
                      else "HERDMASTER retains the case and must reconcile current canonical welfare, lifecycle and status evidence at the next check.")
            candidates.append(_candidate(
                f"herdmaster:welfare:{case_id}", "HERDMASTER",
                str(welfare.get("welfare_case_urgency") or "due"),
                [f"welfare_case:{case_id}", f"pig:{welfare.get('pig_id')}",
                 f"case_state:{state}", f"observed:{observed}",
                 "attention:welfare_priority"],
                ([] if projected["task_class"] == "physical_action_due"
                 else ["current_welfare_and_lifecycle_status"]),
                f"{pig_label} has an active {state} welfare case"
                + (f": {escalation}" if escalation else "."),
                action, due, task_class=projected["task_class"], welfare_priority=True,
                physical_work_ready=projected["task_class"] == "physical_action_due",
                presentation_identity=presentation_identity))
    for item in tuple(getattr(result, "work_items", ()) or ()):
        metadata = getattr(item, "metadata", {}) or {}
        welfare_priority = bool(metadata.get("welfare_exception")
                                or metadata.get("mortality_packet"))
        unknowns = [item.genuine_question] if str(item.genuine_question or "").strip() else []
        due = item.due_at or now
        urgency = {"urgent": "urgent", "due_today": "due", "planned": "planned",
                   "waiting_for_evidence": "urgent", "protected_owner_decision": "due"}.get(item.state.value, "watch")
        exact_owner_question = bool(
            str(item.genuine_question or "").strip()
            and str(item.assignee or "").casefold() == "charl"
            and str(item.question_for or "").casefold() == "charl"
            and item.state.value in {"urgent", "due_today", "protected_owner_decision"}
            and item.authority.value in {"advisory", "owner_decision"})
        task_class = ("protected_decision" if (
                          item.state.value == "protected_owner_decision" or exact_owner_question)
                      else ("status_reconciliation" if unknowns or item.state.value == "waiting_for_evidence"
                      else ("physical_action_due" if any(term in item.next_action.casefold()
                            for term in ("record weight", "weigh now", "physical weighing"))
                            else "informational_watch")))
        candidates.append(_candidate(
            "herdmaster:" + str(item.dedupe_key), "HERDMASTER", urgency,
            [f"result:{result.result_id}",
             f"observed:{item.provenance.observed_at.isoformat()}",
             *(["attention:welfare_priority"] if welfare_priority else []),
             *item.provenance.source_refs], unknowns,
            item.title + ": " + item.why, item.next_action, due,
            task_class=task_class, welfare_priority=welfare_priority,
            physical_work_ready=(task_class == "physical_action_due"
                                 and metadata.get("physical_work_ready") is True
                                 and not unknowns),
            routine_weekly_weighing=metadata.get("routine_weekly_weighing") is True,
            exceptional_weighing_due_now=metadata.get("exceptional_weighing_due_now") is True,
            physical_assignee=(item.assignee if task_class == "physical_action_due" else None),
            owner_question_eligible=exact_owner_question or (
                task_class == "protected_decision" and not unknowns)))
    from modules.pig_weights.farm_supabase_read_service import get_allocation_input_rows
    farm_today = _aware(now).astimezone(ZoneInfo("Africa/Johannesburg")).date()
    try:
        snapshot = get_allocation_input_rows(today=farm_today)
    except TypeError as exc:
        # Preserve narrow dependency-injected adapters that predate the
        # optional deterministic date argument; production uses the canonical
        # adapter above.
        if "today" not in str(exc):
            raise
        snapshot = get_allocation_input_rows()
    snapshot_observed = _time(snapshot.get("snapshot_observed_at"), now)
    candidates.extend(_purpose_review_candidates(
        snapshot, now=now, today=farm_today, observed_at=snapshot_observed,
    ))
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
                now + timedelta(minutes=5), presentation_identity={
                    "familiar_meaning": "Pig 151",
                    "stable_reference": str(row.get("Pig_ID") or "tag 151")}))
    for row in snapshot.get("litter_rows") or ():
        sow = str(row.get("Sow_Tag_Number") or "").strip()
        status = str(row.get("Litter_Status") or "").strip().casefold()
        if sow.casefold() == "molly" and status not in {"completed", "closed", "weaned"}:
            litter_id = str(row.get("Litter_ID") or "unknown")
            farrowing = str(row.get("Farrowing_Date") or "unknown")
            wean = str(row.get("Wean_Date") or "unknown")
            weaned = row.get("Weaned_Count")
            treatment_state = str(row.get("first_treatment_evidence_state") or "unknown").casefold()
            treatment_due = (treatment_state == "due"
                             and row.get("first_treatment_attention_due") is True
                             and int(row.get("Active_Pig_Count") or 0) > 0)
            treatment_date = str(row.get("first_treatment_attention_date") or "unknown")
            candidates.append(_candidate("herdmaster:molly-active-litter", "HERDMASTER", "due",
                [f"litter:{litter_id}", f"status:{status or 'unknown'}",
                 f"farrowing:{farrowing}", f"wean_due:{wean}",
                 f"weaned_count:{weaned if weaned is not None else 'unknown'}",
                 f"first_treatment_due:{str(treatment_due).lower()}",
                 f"first_treatment_state:{treatment_state}",
                 f"first_treatment_attention_date:{treatment_date}",
                 f"observed:{snapshot_observed.isoformat()}"],
                ([] if treatment_due or treatment_state in {"not_due", "completed", "skipped"}
                 else [f"first_treatment_{treatment_state}_reconciliation"]),
                ("Molly's litter first treatment is due and ready."
                 if treatment_due else
                 f"Molly's litter {litter_id} is Active; farrowed {farrowing}, planned weaning {wean}, and recorded weaned count is {weaned if weaned is not None else 'Unknown'}."),
                ("Molly's litter — perform the first treatment now in the existing litter treatment journey."
                 if treatment_due else
                 "HERDMASTER retains care ownership now; prepare the exact piglet, tag, weight and movement preview at the planned weaning boundary, and record nothing without confirmation."),
                now + timedelta(minutes=30),
                task_class=("physical_action_due" if treatment_due else
                            ("informational_watch" if treatment_state in {
                                "not_due", "completed", "skipped"}
                             else "status_reconciliation")),
                welfare_priority=treatment_due,
                physical_work_ready=treatment_due,
                physical_assignee=("Farm team" if treatment_due else None),
                message_family=("litter_first_treatment" if treatment_due else "litter_care"),
                presentation_identity={"human_name": "Molly",
                                       "stable_reference": litter_id}))
    return candidates


def _purpose_review_candidates(snapshot, *, now, today, observed_at):
    """Project one governed purpose-work identity per canonical litter/cohort."""
    from modules.pig_weights.pig_weights_service import get_pig_allocation_readiness

    allocation = get_pig_allocation_readiness(
        today=today, allow_sheet_fallback=False, canonical_inputs=snapshot,
    )
    if allocation.get("success") is not True:
        return []

    grouped = {}
    for row in allocation.get("pigs") or ():
        purpose = str(row.get("purpose") or "").strip().casefold()
        if (str(row.get("status") or "").casefold() != "active"
                or str(row.get("on_farm") or "").casefold() != "yes"
                or purpose not in {"", "unknown", "unallocated", "not allocated", "not_allocated"}):
            continue
        if row.get("purpose_review_eligible") is not True:
            continue
        litter_id = str(row.get("litter_id") or "").strip()
        cohort_key = litter_id or str(row.get("pig_id") or "").strip()
        if not cohort_key:
            continue
        grouped.setdefault(cohort_key, {"litter_id": litter_id, "rows": []})["rows"].append(row)

    result = []
    for cohort_key, cohort in sorted(grouped.items()):
        rows = cohort["rows"]
        missing = [row for row in rows if row.get("purpose_review_state") == "weight_due"]
        sow_name = next((str(row.get("sow_tag_number") or "").strip()
                         for row in rows if str(row.get("sow_tag_number") or "").strip()), "")
        row_names = [str(row.get("tag_number") or "").strip() or "Name unavailable"
                     for row in rows]
        animal_names = [name for name in row_names if name != "Name unavailable"]
        label = sow_name or (animal_names[0] if len(animal_names) == 1 else "Purpose review cohort")
        stable_reference = cohort["litter_id"] or str(rows[0].get("pig_id") or cohort_key)
        refs = [f"litter:{cohort['litter_id']}" if cohort["litter_id"] else f"pig:{stable_reference}",
                f"purpose_work:{cohort_key}", f"rule_day:{rows[0].get('purpose_review_due_after_days') or 14}",
                f"observed:{observed_at.isoformat()}"]
        detail = "/pig-allocation?mode=purpose-review"
        if cohort["litter_id"] and _safe_detail_identifier(cohort["litter_id"]):
            detail += f"&litter_id={cohort['litter_id']}"
        if missing:
            names = [str(row.get("tag_number") or "Name unavailable") for row in missing]
            result.append(_candidate(
                f"herdmaster:purpose-review:{cohort_key}", "HERDMASTER", "due", refs + [
                    "phase:post_wean_weight", *[f"pig:{row.get('pig_id')}" for row in missing]], [],
                f"{label}'s purpose cohort needs {len(missing)} qualifying post-wean weight"
                f"{'s' if len(missing) != 1 else ''} before one grouped decision.",
                "Physically weigh and record through the existing grouped weighing rail: "
                + ", ".join(names) + ".", now,
                task_class="physical_action_due", physical_work_ready=True,
                physical_assignee="Farm team", exceptional_weighing_due_now=True,
                message_family="purpose_review", detail_target=detail,
                presentation_identity={"human_name": sow_name,
                    "familiar_meaning": "Purpose review cohort" if not sow_name else "",
                    "stable_reference": stable_reference}))
            continue
        suggestions = [str(row.get("suggested_purpose") or "Manual Review") for row in rows]
        result.append(_candidate(
            f"herdmaster:purpose-review:{cohort_key}", "HERDMASTER", "due",
            refs + ["phase:owner_decision", *[f"pig:{row.get('pig_id')}" for row in rows]], [],
            f"{label}'s purpose cohort has qualifying day-{rows[0].get('purpose_review_due_after_days') or 14} evidence for {len(rows)} animal"
            f"{'s' if len(rows) != 1 else ''}.",
            "Review one grouped HERDMASTER recommendation in Pig Allocation: "
            + ", ".join(f"{name} — {suggestion}"
                        for name, suggestion in zip(row_names, suggestions))
            + ". Purpose approval does not allocate, reserve, sell, or publish an animal.",
            now, task_class="protected_decision", owner_question_eligible=True,
            message_family="purpose_review", detail_target=detail,
            presentation_identity={"human_name": sow_name,
                "familiar_meaning": "Purpose review cohort" if not sow_name else "",
                "stable_reference": stable_reference}))
    return result


def _safe_detail_identifier(value):
    text = str(value or "")
    return bool(text) and len(text) <= 120 and all(
        character.isalnum() or character in "-_." for character in text
    )
def _sam(now):
    with connect_bounded_read() as connection:
        with connection.cursor() as cur:
            cur.execute("""select review_event_id,created_at,decision_json from (
                    select distinct on (decision_json->'inbound'->>'conversation_id')
                        review_event_id,created_at,decision_json
                    from public.sam_live_stock_conversation_review_events
                    where event_source='sam_live_stock_direct_inbound'
                      and coalesce(decision_json->'inbound'->>'conversation_id','')<>''
                    order by decision_json->'inbound'->>'conversation_id',
                             created_at desc,review_event_id desc
                ) latest
                where coalesce((decision_json->>'customer_send_confirmed')::boolean,false)=false
                  and coalesce((decision_json->'routine_reply_delivery'->>'sent')::boolean,false)=false
                  and coalesce((decision_json->>'no_reply_recommended')::boolean,false)=false
                order by created_at desc,review_event_id desc""")
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
            now + timedelta(minutes=5), presentation_identity={
                "familiar_meaning": "Customer name unavailable",
                "stable_reference": f"conversation {digest}"}))
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
        now, presentation_identity={"familiar_meaning": "Current sales opportunity",
                                    "stable_reference": str(packet["packet_id"])})]


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
            now + timedelta(minutes=5), presentation_identity={
                "familiar_meaning": f"{specialist.title()} owner result",
                "stable_reference": digest}))
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
        now + timedelta(minutes=5), presentation_identity={
            "familiar_meaning": "Oom Sakkie scheduled operation",
            "stable_reference": "scheduled-worker-health"})]


def _candidate(dedupe_key, specialist, urgency, refs, unknowns, summary, next_action, next_at,
               *, task_class=None, welfare_priority=False, presentation_identity=None,
               message_family=None, physical_work_ready=False,
               physical_assignee=None, owner_question_eligible=False,
               irreducible_owner_exception=False, routine_weekly_weighing=False,
               exceptional_weighing_due_now=False, detail_target=None):
    result = {"dedupe_key": dedupe_key, "specialist": specialist, "urgency": urgency,
        "evidence_refs": list(refs), "unknowns": list(unknowns), "summary": summary,
        "next_action": next_action, "next_reassessment_at": _aware(next_at).isoformat()}
    if task_class:
        result["task_class"] = task_class
    if welfare_priority:
        result["welfare_priority"] = True
    if presentation_identity:
        result["presentation_identity"] = dict(presentation_identity)
    if message_family:
        result["message_family"] = str(message_family)
    if physical_work_ready:
        result["physical_work_ready"] = True
    if physical_assignee:
        result["physical_assignee"] = str(physical_assignee)
    if owner_question_eligible:
        result["owner_question_eligible"] = True
    if irreducible_owner_exception:
        result["irreducible_owner_exception"] = True
    if routine_weekly_weighing:
        result["routine_weekly_weighing"] = True
    if exceptional_weighing_due_now:
        result["exceptional_weighing_due_now"] = True
    if detail_target:
        result["detail_target"] = str(detail_target)
    return result


def _configured_owner():
    values = [part.strip() for part in str(os.getenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS") or "").split(",") if part.strip()]
    return values[0] if values else ""


def _welfare_presentation_identity(row):
    provenance = row.get("welfare_case_provenance") or {}
    context = provenance.get("intake_context") if isinstance(provenance, dict) else {}
    preview = context.get("preview") if isinstance(context, dict) else {}
    evaluator = preview.get("evaluator") if isinstance(preview, dict) else {}
    identity = evaluator.get("identity") if isinstance(evaluator, dict) else {}
    for key in ("display_name", "name"):
        value = str(identity.get(key) or "").strip() if isinstance(identity, dict) else ""
        if value:
            return {"human_name": value,
                    "stable_reference": str(identity.get("tag_number") or row.get("pig_id") or "")}
    return {"familiar_meaning": "Animal name unavailable",
            "stable_reference": str(identity.get("tag_number") or row.get("pig_id") or "")}


def _time(value, fallback):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return _aware(parsed)
    except (TypeError, ValueError): return _aware(fallback)


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
