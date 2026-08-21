"""Scheduled Riversdale auction coordination for Anton's existing manager rail.

This module owns reminders and the operating/date decision only.  Candidate
selection remains read-only and the final Auction List mutation remains on its
existing owner-protected append-only rail.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import html
import os
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from modules.oom_sakkie.family_access import (
    FamilyRole, authorize_family_message, resolve_family_principal,
)
from modules.sales.riversdale_auction import next_auction_date

CALLBACK_PREFIX = "oomauction:"
LOCAL_ZONE = ZoneInfo("Africa/Johannesburg")


def reminder_window(now: datetime) -> dict[str, Any] | None:
    """Return only the latest reached 14/7-day window for the next auction."""
    local_day = _aware(now).astimezone(LOCAL_ZONE).date()
    auction_day = next_auction_date(local_day)
    reached = [days for days in (14, 7) if local_day >= auction_day - timedelta(days=days)]
    if not reached or local_day >= auction_day:
        return None
    days_before = min(reached)
    due_day = auction_day - timedelta(days=days_before)
    return {"auction_date": auction_day.isoformat(), "days_before": days_before,
            "due_date": due_day.isoformat(), "late": local_day > due_day,
            "observed_date": local_day.isoformat()}


def collect_auction_manager_case(now: datetime, *, cycle_loader=None,
                                 recommendation_loader=None, list_loader=None):
    """Build one canonical manager candidate; a missed run never fans out."""
    window = reminder_window(now)
    if not window:
        return []
    if cycle_loader is None:
        from modules.sales.riversdale_auction import load_owner_confirmed_cycle
        cycle_loader = load_owner_confirmed_cycle
    cycle = cycle_loader(today=date.fromisoformat(window["observed_date"]))
    if (isinstance(cycle, Mapping) and cycle.get("valid") is True
            and str(cycle.get("confirmed_date") or "") == window["auction_date"]):
        return _confirmed_cohort_case(now, window, recommendation_loader, list_loader)
    summary = _cohort_summary(window, recommendation_loader)
    phase = f"{window['days_before']}-day"
    return [{
        "dedupe_key": f"herdmaster:riversdale-auction:{window['auction_date']}",
        "specialist": "HERDMASTER", "urgency": "urgent" if window["late"] else "due",
        "evidence_refs": [f"auction_date:{window['auction_date']}",
            f"reminder_phase:{phase}", f"due_date:{window['due_date']}",
            f"observed:{_aware(now).isoformat()}", *summary["refs"]],
        "unknowns": ["anton_operating_and_date_confirmation", *summary["unknowns"]],
        "summary": (f"Riversdal-veiling {window['auction_date']}: "
                    f"{summary['current']} tans geskik, {summary['projected']} geprojekteer, "
                    f"{summary['excluded']} uitgesluit."),
        "next_action": ("Vra Anton een keer: Ja, dié datum / Nee / Datum verskil. "
                        "HERDMASTER herbereken daarna outomaties; finale presiese varklys-goedkeuring bly beskerm."),
        "next_reassessment_at": (_aware(now) + timedelta(minutes=5)).isoformat(),
        "message_family": "riversdale_auction_confirmation",
        "task_class": "protected_decision",
        "owner_question_eligible": True,
        "presentation_identity": {"familiar_meaning": "Riversdal-veiling",
                                  "stable_reference": window["auction_date"]},
    }]


def _confirmed_cohort_case(now, window, recommendation_loader, list_loader):
    try:
        if recommendation_loader is None:
            from modules.pig_weights.pig_weights_service import get_riversdale_auction_recommendation
            recommendation_loader = get_riversdale_auction_recommendation
        if list_loader is None:
            from modules.pig_weights.pig_weights_service import get_riversdale_auction_list
            list_loader = get_riversdale_auction_list
        packet = recommendation_loader(today=date.fromisoformat(window["observed_date"]))
        listing, status = list_loader()
        from modules.sales.riversdale_auction_list import eligibility_tokens
        tokens = eligibility_tokens(packet)
        cycle_id = str((packet.get("confirmation") or {}).get("auction_cycle_id") or "")
        if not cycle_id or status != 200 or str(listing.get("auction_cycle_id") or "") != cycle_id:
            raise ValueError("auction_list_current_cycle_unavailable")
        selected = sorted(tokens)
        current = sorted(str(row.get("pig_id") or "") for row in listing.get("items") or ())
        if selected == current:
            return []
        excluded = len(packet.get("excluded") or packet.get("excluded_preview") or ())
        refs = [f"auction_date:{window['auction_date']}", "reminder_phase:cohort-review",
            f"auction_cycle:{cycle_id}", f"cohort_ids:{','.join(selected)}",
            f"cohort_tokens_digest:{_digest(tokens)}", f"prior_heads_digest:{_digest(listing.get('causal_heads') or {})}",
            f"excluded_count:{excluded}", f"observed:{_aware(now).isoformat()}"]
        return [{"dedupe_key": f"herdmaster:riversdale-auction:{window['auction_date']}",
            "specialist": "HERDMASTER", "urgency": "due", "evidence_refs": refs,
            "unknowns": [],
            "summary": (f"Riversdal-veiling {window['auction_date']}: {len(selected)} presies "
                        f"bewys-geskikte varke; {excluded} uitgesluit."),
            "next_action": ("Gee Charl een beskermde presiese-groep-goedkeuring. By bevestiging "
                            "voeg die bestaande append-only Veilingslys-rail die groep presies een keer by."),
            "next_reassessment_at": (_aware(now) + timedelta(minutes=5)).isoformat(),
            "message_family": "riversdale_auction_exact_cohort", "task_class": "protected_decision",
            "owner_question_eligible": True,
            "presentation_identity": {"familiar_meaning": "Riversdal-veiling presiese groep",
                                      "stable_reference": cycle_id}}]
    except Exception as exc:
        return [{"dedupe_key": f"herdmaster:riversdale-auction:{window['auction_date']}",
            "specialist": "HERDMASTER", "urgency": "urgent",
            "evidence_refs": [f"auction_date:{window['auction_date']}",
                "reminder_phase:cohort-review", f"cohort:{exc.__class__.__name__}",
                f"observed:{_aware(now).isoformat()}"],
            "unknowns": ["current_exact_auction_cohort_or_list_heads"],
            "summary": "Die Riversdal-veiling is bevestig, maar die huidige presiese groep kon nie veilig saamgestel word nie.",
            "next_action": "HERDMASTER herprobeer die kanonieke aanbeveling en bestaande Veilingslys outomaties; geen vark word geraai of bygevoeg nie.",
            "next_reassessment_at": (_aware(now) + timedelta(minutes=5)).isoformat()}]


def build_anton_prompt(case: Mapping[str, Any], *, environ=None):
    source = environ if environ is not None else os.environ
    principal = _anton_principal(source)
    if principal is None:
        return {"success": False, "status": "auction_anton_binding_unavailable",
                "telegram_sends": 0, "writes_farm_data": False}
    auction_date = _ref(case, "auction_date:")
    phase = _ref(case, "reminder_phase:")
    if not auction_date or not phase:
        return {"success": False, "status": "auction_case_binding_invalid",
                "telegram_sends": 0, "writes_farm_data": False}
    answer = ("<b>RIVERSDAL-VEILING</b>\n\n" + html.escape(str(case.get("summary") or ""))
        + "\n\nIs die veiling aan op dié datum? Kies asseblief een opsie. "
          "Geen varke word deur hierdie antwoord by die Veilingslys gevoeg nie.")
    return {"success": True, "status": "auction_anton_confirmation_ready",
        "answer": answer, "specialist": "HERDMASTER", "auction_date": auction_date,
        "principal": principal, "writes_farm_data": False, "hardware_commands": 0,
        "protected_actions_performed": False,
        "reply_markup": {"inline_keyboard": [[
            {"text": "Ja, dié datum", "callback_data": f"{CALLBACK_PREFIX}{auction_date}:{phase}:yes"},
            {"text": "Nee", "callback_data": f"{CALLBACK_PREFIX}{auction_date}:{phase}:no"},
            {"text": "Datum verskil", "callback_data": f"{CALLBACK_PREFIX}{auction_date}:{phase}:change"},
        ]]}}


def build_owner_cohort_prompt(case: Mapping[str, Any], *, environ=None,
                              recommendation_loader=None, list_loader=None,
                              claim_creator=None):
    source = environ if environ is not None else os.environ
    owner = str(source.get("OOM_SAKKIE_TELEGRAM_OWNER_USER_ID") or "").strip()
    if not owner:
        owners = [value.strip() for value in str(source.get(
            "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS") or "").split(",") if value.strip()]
        owner = owners[0] if owners else ""
    if not owner:
        return {"success": False, "status": "auction_owner_binding_unavailable",
                "writes_farm_data": False}
    if recommendation_loader is None:
        from modules.pig_weights.pig_weights_service import get_riversdale_auction_recommendation
        recommendation_loader = get_riversdale_auction_recommendation
    if list_loader is None:
        from modules.pig_weights.pig_weights_service import get_riversdale_auction_list
        list_loader = get_riversdale_auction_list
    packet = recommendation_loader()
    listing, status = list_loader()
    from modules.sales.riversdale_auction_list import eligibility_tokens
    tokens = eligibility_tokens(packet)
    cycle_id = str((packet.get("confirmation") or {}).get("auction_cycle_id") or "")
    already_listed = {str(row.get("pig_id") or "").strip()
                      for row in listing.get("items") or () if isinstance(row, Mapping)}
    ids = sorted(pig_id for pig_id in tokens if pig_id not in already_listed)
    if (status != 200 or not cycle_id or listing.get("auction_cycle_id") != cycle_id or not ids):
        return {"success": False, "status": "auction_exact_cohort_unavailable",
                "writes_farm_data": False}
    heads = listing.get("causal_heads") or {}
    prior = {pig_id: str((heads.get(pig_id) or {}).get("event_id") or "") for pig_id in ids}
    incremental_tokens = {pig_id: tokens[pig_id] for pig_id in ids}
    preview = {"contract_version": "riversdale_auction_manager_cohort.v1",
        "auction_cycle_id": cycle_id, "pig_ids": ids,
        "eligibility_tokens": incremental_tokens,
        "prior_event_ids": prior,
        "cohort_digest": _digest({"ids": ids, "tokens": incremental_tokens, "prior": prior})}
    if claim_creator is None:
        from modules.oom_sakkie.protected_action_claims import create_claim
        claim_creator = create_claim
    mission_id = f"{case['case_id']}:G{int(case['generation'])}"
    claim = claim_creator(action_kind="riversdale_auction_list_add",
        owner_user_id=owner, private_chat_id=owner, mission_id=mission_id,
        provider_message_id="scheduled:" + mission_id,
        evidence_generation=preview["cohort_digest"], preview_payload=preview)
    from modules.oom_sakkie.protected_action_claims import build_buttons
    return {"success": True, "status": "auction_exact_cohort_approval_ready",
        "answer": (f"<b>RIVERSDAL-VEILING — PRESIESE GROEP</b>\n\n{len(ids)} varke: "
                   + ", ".join(html.escape(value) for value in ids)
                   + "\n\nBevestig om hierdie presiese groep een keer by die bestaande Veilingslys te voeg. "
                     "HERDMASTER sal veranderde bewyse eers weer bereken."),
        "callback_token": claim["callback_token"], "reply_markup": build_buttons(claim["callback_token"], grouped=True),
        "mission_id": mission_id, "card_mission_id": case["case_id"],
        "preview_digest": claim["preview_digest"], "writes_farm_data": False,
        "protected_actions_performed": False, "hardware_commands": 0}


def handle_anton_callback(parsed: Mapping[str, Any], principal, *, callback_data: str,
                          decision_writer=None, now=None):
    parts = str(callback_data or "").split(":")
    if (len(parts) != 4 or parts[0] != "oomauction"
            or parts[2] not in {"14-day", "7-day"}
            or parts[3] not in {"yes", "no", "change"}):
        return _hold("auction_callback_invalid"), 400
    try:
        auction_day = date.fromisoformat(parts[1])
    except ValueError:
        return _hold("auction_callback_invalid"), 400
    decision = authorize_family_message(principal, parsed,
        capability="herdmaster_management_input")
    if (not decision.allowed or principal.role is not FamilyRole.FARM_MANAGER
            or principal.family_key != "dad"):
        return _hold("auction_callback_unauthorized"), 403
    current = reminder_window(_aware(now or datetime.now(timezone.utc)))
    if not current or current["auction_date"] != auction_day.isoformat():
        return _hold("auction_callback_stale"), 409
    selected = parts[3]
    if decision_writer is None:
        from modules.sales.riversdale_auction import record_owner_auction_decision
        decision_writer = record_owner_auction_decision
    payload = {"operating": selected == "yes",
        "confirmed_date": auction_day.isoformat() if selected == "yes" else None,
        "idempotency_key": f"riversdale-auction:{auction_day.isoformat()}:{parts[2]}:anton-confirmation",
        "owner_note": ((f"PENDING_DATE_CORRECTION:{auction_day.isoformat()}:{parts[2]}"
                       if selected == "change" else
                       "Confirmed by authenticated farm_manager principal via Oom Sakkie."))}
    result, status = decision_writer(payload, actor_id=principal.telegram_user_id)
    if result.get("success") is not True:
        return {**_hold(str(result.get("status") or "auction_decision_contained")),
                "decision_result": result}, status
    if result.get("status") == "auction_decision_replayed":
        return {"success": True, "handled": True, "status": "auction_callback_replayed_noop",
            "answer": "", "suppress_owner_delivery": True, "decision_result": result,
            "writes_farm_data": False, "hardware_commands": 0,
            "protected_actions_performed": False}, status
    if selected == "change":
        return {"success": True, "handled": True, "status": "auction_date_correction_required",
            "answer": "Wat is die korrekte Riversdal-veilingdatum? Antwoord byvoorbeeld 09-09-2026. Ek behou die huidige saak.",
            "decision_result": result, "writes_farm_data": result.get("writes_auction_decision") is True,
            "hardware_commands": 0, "protected_actions_performed": False}, status
    answer = ("Dankie. HERDMASTER sal die huidige en geprojekteerde groep outomaties herbereken. "
              "Geen vark is by die Veilingslys gevoeg nie; die finale presiese groep vereis beskermde goedkeuring.")
    return {"success": True, "handled": True, "status": "auction_operating_decision_recorded",
        "answer": answer, "decision_result": result,
        "writes_farm_data": result.get("writes_auction_decision") is True,
        "hardware_commands": 0, "protected_actions_performed": False}, status


def handle_anton_date_reply(parsed: Mapping[str, Any], principal, *, cycle_loader=None,
                            decision_writer=None):
    """Complete a durable pending date-correction context from Anton's next reply."""
    decision = authorize_family_message(principal, parsed,
        capability="herdmaster_management_input")
    if (not decision.allowed or principal.role is not FamilyRole.FARM_MANAGER
            or principal.family_key != "dad"):
        return {"handled": False, "status": "auction_date_reply_not_applicable"}, 200
    if cycle_loader is None:
        from modules.sales.riversdale_auction import load_owner_confirmed_cycle
        cycle_loader = load_owner_confirmed_cycle
    cycle = cycle_loader()
    note = str((cycle or {}).get("owner_note") or "")
    if not note.startswith("PENDING_DATE_CORRECTION:"):
        return {"handled": False, "status": "auction_date_reply_not_applicable"}, 200
    fields = note.split(":")
    if len(fields) != 3 or fields[2] not in {"14-day", "7-day"}:
        return _hold("auction_date_correction_context_invalid"), 409
    corrected = _parse_date_reply(str(parsed.get("text") or ""))
    if corrected is None:
        return {**_hold("auction_date_correction_format_required", success=True),
            "answer": "Gee asseblief die korrekte datum as DD-MM-JJJJ, byvoorbeeld 09-09-2026."}, 200
    expected = date.fromisoformat(fields[1])
    if corrected < _aware(datetime.now(timezone.utc)).astimezone(LOCAL_ZONE).date():
        return _hold("auction_date_correction_past_date"), 409
    if decision_writer is None:
        from modules.sales.riversdale_auction import record_owner_auction_decision
        decision_writer = record_owner_auction_decision
    result, status = decision_writer({"operating": True,
        "confirmed_date": corrected.isoformat(),
        "idempotency_key": f"riversdale-auction:{expected.isoformat()}:{fields[2]}:anton-corrected:{corrected.isoformat()}",
        "owner_note": "Corrected date confirmed by authenticated farm_manager principal via Oom Sakkie."},
        actor_id=principal.telegram_user_id)
    if result.get("success") is not True:
        return {**_hold(str(result.get("status") or "auction_date_correction_contained")),
                "decision_result": result}, status
    return {"handled": True, "success": True, "status": "auction_corrected_date_recorded",
        "answer": (f"Dankie. Ek het {corrected.strftime('%d-%m-%Y')} as die bevestigde "
                   "Riversdal-veilingdatum vasgelê en HERDMASTER sal die groep herbereken."),
        "decision_result": result, "writes_farm_data": result.get("writes_auction_decision") is True,
        "hardware_commands": 0, "protected_actions_performed": False}, status


def execute_owner_cohort_claim(claimed: Mapping[str, Any], *, actor_id: str,
                               list_loader=None, list_writer=None):
    preview = claimed.get("preview_payload") if isinstance(claimed.get("preview_payload"), Mapping) else {}
    if preview.get("contract_version") != "riversdale_auction_manager_cohort.v1":
        return _hold("auction_cohort_claim_binding_mismatch"), 409
    if list_loader is None:
        from modules.pig_weights.pig_weights_service import get_riversdale_auction_list
        list_loader = get_riversdale_auction_list
    if list_writer is None:
        from modules.pig_weights.pig_weights_service import update_riversdale_auction_list
        list_writer = update_riversdale_auction_list
    listing, status = list_loader()
    ids = sorted(str(value) for value in preview.get("pig_ids") or () if str(value))
    heads = listing.get("causal_heads") or {} if isinstance(listing, Mapping) else {}
    current_prior = {pig_id: str((heads.get(pig_id) or {}).get("event_id") or "") for pig_id in ids}
    current_tokens = listing.get("eligibility_tokens") or {} if isinstance(listing, Mapping) else {}
    if (status != 200 or listing.get("auction_cycle_id") != preview.get("auction_cycle_id")
            or current_prior != preview.get("prior_event_ids")
            or {pig_id: str(current_tokens.get(pig_id) or "") for pig_id in ids}
                != preview.get("eligibility_tokens")
            or _digest({"ids": ids, "tokens": preview.get("eligibility_tokens"),
                        "prior": preview.get("prior_event_ids")}) != preview.get("cohort_digest")):
        return _hold("auction_cohort_evidence_changed"), 409
    result, result_status = list_writer({"action": "add", "pig_ids": ids,
        "auction_cycle_id": preview["auction_cycle_id"],
        "eligibility_tokens": preview["eligibility_tokens"],
        "prior_event_ids": preview["prior_event_ids"],
        "idempotency_key": "oom-auction-list:" + str(preview["cohort_digest"]),
        "owner_note": "Exact cohort approved through protected Oom Sakkie manager rail."},
        actor_id=actor_id)
    if result.get("success") is not True:
        return {**_hold(str(result.get("status") or "auction_list_update_contained")),
                "list_result": result}, result_status
    return {"success": True, "handled": True, "status": "auction_exact_cohort_added",
        "answer": (f"Die presiese groep van {len(ids)} varke is een keer by die Veilingslys gevoeg. "
                   "HERDMASTER hou latere bewysveranderings en herbeoordeling dop."),
        "reply_markup": {"inline_keyboard": []}, "list_result": result,
        "writes_farm_data": result.get("status") == "auction_list_updated",
        "hardware_commands": 0, "protected_actions_performed": True}, result_status


def _cohort_summary(window, loader):
    if loader is None:
        try:
            from modules.pig_weights.pig_weights_service import get_riversdale_auction_recommendation
            loader = get_riversdale_auction_recommendation
        except Exception:
            loader = None
    if loader is None:
        return {"current": "Onbekend", "projected": "Onbekend", "excluded": "Onbekend",
                "refs": ["cohort:unavailable"], "unknowns": ["current_projected_excluded_cohort"]}
    try:
        packet = loader(today=date.fromisoformat(window["observed_date"]),
            confirmation={"operating": True, "confirmed_date": window["auction_date"], "valid": True})
        excluded = list(packet.get("excluded") or packet.get("excluded_preview") or ())
        from modules.sales.riversdale_auction_list import eligibility_tokens
        current = len(eligibility_tokens(packet))
        # Candidate preview rows are not evidence that an animal will become
        # eligible.  Until a canonical projection with its own provenance exists,
        # keep this dimension explicitly unknown.
        projected = "Onbekend"
        refs = [f"cohort_digest:{packet.get('packet_digest') or packet.get('evidence_digest') or 'unavailable'}"]
        unknowns = ["projected_cohort_evidence"]
        if refs[0] == "cohort_digest:unavailable":
            unknowns.append("cohort_evidence_digest")
        return {"current": current, "projected": projected, "excluded": len(excluded),
                "refs": refs, "unknowns": unknowns}
    except Exception as exc:
        return {"current": "Onbekend", "projected": "Onbekend", "excluded": "Onbekend",
                "refs": [f"cohort:{exc.__class__.__name__}"],
                "unknowns": ["current_projected_excluded_cohort"]}


def _anton_principal(source):
    import json
    try:
        rows = json.loads(str(source.get("OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON") or "[]"))
    except (TypeError, ValueError):
        return None
    for row in rows if isinstance(rows, list) else ():
        if isinstance(row, Mapping) and str(row.get("family_key") or "").casefold() == "dad":
            user = str(row.get("telegram_user_id") or "").strip()
            principal = resolve_family_principal({"telegram_user_id": user,
                "telegram_chat_id": user, "telegram_chat_type": "private"}, source)
            if principal.role is FamilyRole.FARM_MANAGER:
                return principal
    return None


def _ref(case, prefix):
    return next((str(value)[len(prefix):] for value in case.get("evidence_refs") or ()
                 if str(value).startswith(prefix)), "")


def _hold(status, *, success=False):
    return {"success": success, "handled": True, "status": status, "answer": "",
            "writes_farm_data": False, "hardware_commands": 0,
            "protected_actions_performed": False}


def _digest(value):
    import hashlib, json
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        default=str).encode()).hexdigest()


def _parse_date_reply(text):
    import re
    match = re.search(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?!\d)", text)
    if not match:
        return None
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def _aware(value):
    if value.tzinfo is None:
        raise ValueError("timezone_required")
    return value.astimezone(timezone.utc)
