"""Telegram purpose views and exact confirmation over existing canonical rails."""
from __future__ import annotations
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import hashlib
from html import escape
import json
import math
import re
import time
from zoneinfo import ZoneInfo
from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
from modules.oom_sakkie import protected_action_claims as claims

PREFIX = "oompur:"
CONTRACT = "herdmaster.telegram_purpose.v1"
REVIEW, CORRECTION = "herdmaster_purpose_review", "herdmaster_purpose_correction"
KINDS = frozenset({REVIEW, CORRECTION})
PAGE_SIZE = 6
OVERVIEW_SIZE = 8
FARM_ZONE = ZoneInfo("Africa/Johannesburg")
PURPOSES = ("Breeding", "Grow_Out", "Meat", "Sale", "Slaughter")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _connect():
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_postgres
    return connect_bounded_postgres(read_only=False)


def applicable(parsed, semantic=None):
    from modules.oom_sakkie.semantic_front_door import purpose_review_intent
    from modules.oom_sakkie.semantic_front_door import SemanticInterpretation
    typed = (isinstance(semantic,SemanticInterpretation) and semantic.domain == "herd_management"
        and semantic.intent == "purpose_review_telegram" and semantic.message_kind in {"question","request"}
        and semantic.requested_action == "open_current_purpose_review")
    return str(parsed.get("callback_data") or "").startswith(PREFIX) or purpose_review_intent(parsed) is not None or typed


def _owner(parsed, authority):
    owner = str(parsed.get("telegram_user_id") or "")
    if (not validates_gateway_owner_authority(authority) or authority.principal_role != "owner"
            or not owner or owner != str(parsed.get("telegram_chat_id") or "")
            or parsed.get("telegram_chat_type") != "private"
            or authority.owner_user_id != owner or authority.private_chat_id != owner
            or not str(parsed.get("provider_message_id") or "")):
        raise ValueError("purpose_owner_private_authority_required")
    return owner


def _word(payload, en, af):
    return af if payload.get("language") == "af" else en


def _refusal(reason, status=409, *, language="en"):
    af = language == "af"
    return {"handled": True, "success": False, "status": reason if str(reason).startswith("purpose_") else "purpose_"+str(reason),
        "reason":reason,"specialist":"HERDMASTER","purpose_presentation_contract":CONTRACT,
        "recipient_language":"af" if af else "en", "recipient_render_contract":"specialist_structured_recipient_v1",
        "answer": ("Ek kon hierdie doelhersiening nie verifieer nie. Niks is aangeteken nie. Vra my om die doelbesluite weer te hersien." if af else
            "I could not verify this purpose review. Nothing was recorded. Ask me to review the purpose decisions again."),
        "writes_farm_data":False,"hardware_commands":0},status


def recommendation_rows(snapshot, now):
    from modules.pig_weights.pig_weights_service import (get_pig_allocation_readiness,
        _purpose_review_row, get_herdmaster_pig_allocation_alerts)
    allocation = get_pig_allocation_readiness(today=now.astimezone(FARM_ZONE).date(), allow_sheet_fallback=False, canonical_inputs=snapshot)
    if allocation.get("success") is not True:
        raise ValueError("purpose_recommendation_source_unavailable")
    # Supplied inputs prevent additional broad breeding/litter reads. Missing
    # breeding evidence remains missing in the existing numeric reasoning rule.
    packet = get_herdmaster_pig_allocation_alerts(today=now.astimezone(FARM_ZONE).date(), allocation=allocation,
        litter_attention={}, breeding_analytics=snapshot.get("breeding_analytics") or {})
    reasoning = {r["pig_id"]: r for r in packet.get("decisions", [])}
    return {str(r["pig_id"]): {**_purpose_review_row(r), "reasoning": reasoning.get(r["pig_id"], {})}
        for r in allocation.get("pigs", [])}


def load_context(*, now, connect=None, connection=None):
    from modules.pig_weights.herdmaster_purpose_work import load_purpose_work_snapshot
    from modules.oom_sakkie.herdmaster_purpose_membership import list_current_review_cases
    with (nullcontext(connection) if connection is not None else (connect or _connect)()) as db:
        if connection is None:
            db.execute("set transaction isolation level repeatable read read only")
        deadline = time.monotonic()+10
        snapshot = load_purpose_work_snapshot(analysis_date=now.astimezone(FARM_ZONE).date(), connection=db, deadline=deadline)
        snapshot["snapshot_observed_at"] = datetime.now(timezone.utc).isoformat()
        if (snapshot.get("purpose_work") or {}).get("state") != "checked":
            raise ValueError("purpose_work_unavailable")
        observed_now = datetime.now(timezone.utc)
        cases = list_current_review_cases(snapshot, now=observed_now, connect=lambda: nullcontext(db), transaction_managed=True, deadline_monotonic=deadline)
        return {"snapshot": snapshot, "cases": cases["cases"], "recommendations": recommendation_rows(snapshot, now)}


def _case(context, binding):
    rows = [r for r in context["cases"] if r["case_id"] == binding["case_id"]]
    if len(rows) != 1 or not rows[0].get("available"):
        raise ValueError("purpose_current_membership_unavailable")
    current = rows[0]["membership"]
    keys = ("case_id", "generation", "evidence_digest", "cohort_key", "material_digest", "member_ids", "membership_digest")
    if any(current.get(k) != binding.get(k) for k in keys):
        raise ValueError("purpose_current_generation_or_membership_changed")
    return current


def _recommendations(context, binding):
    rows = []
    for pig in binding["member_ids"]:
        r = context["recommendations"].get(pig)
        if not r:
            raise ValueError("purpose_recommendation_identity_missing")
        rows.append({k: r.get(k) for k in ("pig_id", "tag_number", "proposed_purpose", "suggested_purpose",
            "suggested_purpose_confidence", "suggested_purpose_reason", "review_status", "readiness_reason",
            "latest_weight_date", "latest_weight_kg", "growth_class", "litter_quality", "reasoning")})
    return rows


def _proposable(row):
    reasoning = row.get("reasoning") or {}
    value = reasoning.get("confidence")
    return (type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
        and row.get("suggested_purpose_confidence") in {"High", "Medium"}
        and reasoning.get("outcome") != "ask_charl" and not reasoning.get("missing_data")
        and not reasoning.get("contradictions") and row.get("proposed_purpose") in PURPOSES
        and row.get("review_status") != "needs_data")


def purpose_label(value, payload):
    en = {"Breeding":"Breeding","Grow_Out":"Grow out","Meat":"Meat","Sale":"Live sale","Slaughter":"Slaughter"}
    af = {"Breeding":"Teling","Grow_Out":"Uitgroei","Meat":"Vleis","Sale":"Lewende verkoop","Slaughter":"Slagting"}
    return (af if payload.get("language")=="af" else en).get(value,str(value).replace("_"," "))


def _button(token, label, action):
    data = PREFIX + token + ":" + action
    if len(data.encode()) > 64:
        raise ValueError("purpose_callback_too_long")
    return {"text": label[:64], "callback_data": data}


def render(p, token):
    mode, page = p["mode"], p.get("page", 0)
    size = OVERVIEW_SIZE if mode == "overview" else PAGE_SIZE
    rows, buttons = [], []
    if mode == "overview":
        items = p["cases"]
        rows = [_word(p, "🐷 Purpose decisions", "🐷 Doelbesluite"), "",
            _word(p, f"{len(items)} groups to review. Opening a group approves nothing.", f"{len(items)} groepe om te hersien. Oopmaak keur niks goed nie.")]
        for i, item in enumerate(items[page*size:(page+1)*size], page*size):
            label, count = item.get("label") or item["case_id"], item.get("member_count") or "?"
            rows.append(f"• {escape(str(label))}: {count}" + ("" if item["available"] else _word(p, " — evidence unavailable", " — bewyse ontbreek")))
            if item["available"]: buttons.append([_button(token, f"{label} · {count}", f"group{i}")])
        revisits = p.get("purpose_overview_revisit") or []
        if revisits:
            dates = ", ".join(sorted({datetime.fromisoformat(r["review_at"]).astimezone(FARM_ZONE).strftime("%d %b %Y") for r in revisits}))
            rows.append(_word(p, f"As requested, here is your review for {dates} at 08:00 SAST.", f"Soos gevra, hier is jou hersiening vir {dates} om 08:00 SAST."))
        if not items: rows.append(_word(p, "No current purpose review was found in this bounded view.", "Geen huidige doelhersiening is in hierdie begrensde aansig gevind nie."))
        total = len(items)
    else:
        count, label = len(p["selected"]), p.get("label") or _word(p, "Selected group", "Gekose groep")
        rows = [_word(p, "🐷 Purpose review — ", "🐷 Doelhersiening — ")+escape(label), ""]
        total = 0
        if mode == "defer":
            rows += [_word(p, f"Review this group on {p['review_date']} at 08:00 SAST?", f"Hersien hierdie groep op {p['review_date']} om 08:00 SAST?"),
                _word(p, "Only the review date changes. No animal purpose changes.", "Net die hersieningsdatum verander. Geen dier se doel verander nie.")]
            buttons.append([_button(token, _word(p, "Confirm review date", "Bevestig hersieningsdatum"), "confirm")])
        elif mode == "preview":
            effects = p["batch_preview"]["effects"]
            total = len(effects)
            rows.append(_word(p, f"Exact proposal: {total} animals, page {page+1}/{(total+PAGE_SIZE-1)//PAGE_SIZE}.", f"Presiese voorstel: {total} diere, bladsy {page+1}/{(total+PAGE_SIZE-1)//PAGE_SIZE}."))
            for e in effects[page*PAGE_SIZE:(page+1)*PAGE_SIZE]:
                rows.append(f"• {escape(e['tag_number'])}: {escape(e['old_purpose'])} → {escape(purpose_label(e['new_purpose'],p))}")
            if set(p.get("seen_pages", [])) == set(range((total+PAGE_SIZE-1)//PAGE_SIZE)):
                buttons.append([_button(token, _word(p, f"Confirm {total} purposes", f"Bevestig {total} doele"), "confirm")])
            else: rows.append(_word(p, "Review every page before Confirm becomes available.", "Hersien elke bladsy voordat Bevestig beskikbaar word."))
            rows.append(_word(p, "Nothing is recorded until you confirm this exact preview.", "Niks word aangeteken voordat jy hierdie presiese voorskou bevestig nie."))
            buttons.append([_button(token, _word(p, f"Change {count} selected", f"Verander {count} gekies"), "change")])
        elif mode == "dates":
            rows.append(_word(p, "Choose an explicit review date:", "Kies 'n presiese hersieningsdatum:"))
            for day in p["review_dates"]:
                buttons.append([_button(token, _word(p, "Review ", "Hersien ")+day, "date"+day.replace("-", ""))])
        elif mode == "why":
            recs=p["recommendations"];total=len(recs)
            rows.append(_word(p,f"Why — page {page+1}/{(total+PAGE_SIZE-1)//PAGE_SIZE}",f"Waarom — bladsy {page+1}/{(total+PAGE_SIZE-1)//PAGE_SIZE}"))
            for r in recs[page*PAGE_SIZE:(page+1)*PAGE_SIZE]:
                rows.append("• "+escape(str(r["tag_number"]))+": "+escape(str(r.get("suggested_purpose_reason") or r.get("readiness_reason") or "Evidence unavailable")))
                gaps=(r.get("reasoning") or {}).get("missing_data") or []
                contradictions=(r.get("reasoning") or {}).get("contradictions") or []
                if gaps or contradictions: rows.append(_word(p,"Missing/conflicting: ","Ontbreek/bots: ")+escape(", ".join(gaps+contradictions)))
            if p.get("language")=="af":rows.append("Bronredes hierbo is aangehaalde oorspronklike rekordteks.")
            buttons.append([_button(token,_word(p,"Back to group review","Terug na groephersiening"),"back")])
        elif mode == "group":
            recs = p["recommendations"]
            summary = {}
            for r in recs:
                purpose = str(r.get("proposed_purpose") or r.get("suggested_purpose") or "Unknown")
                summary.setdefault(purpose, []).append(str(r["tag_number"]))
            rows.append(_word(p, f"{len(recs)} animals ready for owner review.", f"{len(recs)} diere gereed vir eienaarhersiening."))
            for purpose, tags in sorted(summary.items()):
                shown = ", ".join(tags[:6])
                more = _word(p, f"; {len(tags)-6} more", f"; nog {len(tags)-6}") if len(tags)>6 else ""
                rows.append(f"• {escape(purpose_label(purpose,p))}: {len(tags)} ({escape(shown+more)})")
                group_reason = next((str(r.get("suggested_purpose_reason") or r.get("readiness_reason") or "") for r in recs if str(r.get("proposed_purpose") or r.get("suggested_purpose") or "Unknown")==purpose), "")
                rows.append(_word(p, "Reason: ", "Bronrede (oorspronklike teks): ")+escape(group_reason[:180]))
            reasons = list(dict.fromkeys(str(r.get("suggested_purpose_reason") or r.get("readiness_reason") or "Evidence incomplete") for r in recs))

            rows.append(_word(p, "Advisory proposal: review the exact animals and purposes before confirming. No purpose is recorded yet.", "Adviserende voorstel: hersien die presiese diere en doele voor bevestiging. Geen doel is nog aangeteken nie."))
            if all(_proposable(r) for r in recs):
                buttons.append([_button(token, _word(p, f"Review suggestions ({len(recs)})", f"Hersien voorstelle ({len(recs)})"), "recommend")])
            else:
                rows.append(_word(p, "Some recommendation evidence is missing or contradictory. Choose and review your own purpose through Change.", "Sommige aanbevelingsbewyse ontbreek of bots. Kies en hersien jou eie doel via Verander."))
            buttons += [[_button(token, _word(p, f"Change selection / purpose ({len(recs)})", f"Verander keuse / doel ({len(recs)})"), "change")],
                [_button(token, _word(p, f"Why this group ({len(recs)})?", f"Waarom dié groep ({len(recs)})?"), "why")],
                [_button(token, _word(p, "Review later — choose date", "Hersien later — kies datum"), "later")]]
        else:
            recs = p["recommendations"]
            total = len(recs)
            rows += [_word(p, f"{count} of {total} selected. Below 96% confidence, suggestions remain advisory; choose a purpose explicitly.", f"{count} van {total} gekies. Onder 96% vertroue bly voorstelle adviserend; kies 'n doel uitdruklik.")]
            for i, r in enumerate(recs[page*PAGE_SIZE:(page+1)*PAGE_SIZE], page*PAGE_SIZE):
                confidence = (r.get("reasoning") or {}).get("confidence")
                confidence = f"{confidence:.0%}" if type(confidence) in (int, float) and math.isfinite(confidence) else "Unknown"
                rows.append(f"• {escape(str(r['tag_number']))}: {escape(str(r.get('proposed_purpose') or r.get('suggested_purpose') or 'Unknown'))} ({confidence})")
                buttons.append([_button(token, ("✓ " if r["pig_id"] in p["selected"] else "○ ")+str(r["tag_number"]), f"pick{i}")])
            buttons.append([_button(token, _word(p, f"Select all {total}", f"Kies al {total}"), "all"), _button(token, _word(p, "Clear selection", "Maak keuse skoon"), "none")])
            if count:
                for i, value in enumerate(PURPOSES):
                    buttons.append([_button(token, _word(p, f"Preview {purpose_label(value,p)}: {count}", f"Voorskou {purpose_label(value,p)}: {count}"), f"set{i}")])
                if all(_proposable(r) for r in recs if r["pig_id"] in p["selected"]):
                    buttons.append([_button(token, _word(p, f"Preview recommendations: {count}", f"Voorskou aanbevelings: {count}"), "recommend")])
            buttons += [[_button(token, _word(p, f"Why this group ({total})?", f"Waarom dié groep ({total})?"), "why")],
                [_button(token, _word(p, "Review later — choose date", "Hersien later — kies datum"), "later")]]
    if mode in {"overview", "selection", "preview", "why"}:
        navigation = []
        if page > 0: navigation.append(_button(token, _word(p, "Previous page", "Vorige bladsy"), f"page{page-1}"))
        if (page+1)*size < total: navigation.append(_button(token, _word(p, "Next page", "Volgende bladsy"), f"page{page+1}"))
        if navigation: buttons.append(navigation)
    if mode != "overview": buttons.append([_button(token, _word(p, "All purpose groups", "Alle doelgroepe"), "overview")])
    buttons.append([_button(token, _word(p, "Close this review", "Sluit hierdie hersiening"), "cancel")])
    if rows: rows[0] = "<b>"+rows[0]+"</b>"
    return "\n".join(rows), {"inline_keyboard": buttons}


def _issue(payload, parsed, *, connect=None):
    kind = CORRECTION if payload["mode"] == "preview" else REVIEW
    claim = claims.create_claim(action_kind=kind, owner_user_id=parsed["telegram_user_id"],
        private_chat_id=parsed["telegram_chat_id"], mission_id=payload["mission_id"],
        provider_message_id=str(parsed["provider_message_id"]), evidence_generation=str(payload.get("binding", {}).get("generation", "overview")),
        preview_payload=payload, connect_factory=connect,
        reuse_active_provider_identity=payload.get("scheduled_overview") is True,
        supersede_active=not (payload.get("continuation_once") and not payload.get("parent_transition")),
        purpose_parent_transition=payload.get("parent_transition"))
    if not claim.get("success") or not claim.get("callback_token"): raise ValueError("purpose_preview_claim_unavailable")
    answer, keyboard = render(payload, claim["callback_token"])
    return {"handled": True, "success": True, "status": "purpose_telegram_"+payload["mode"], "specialist": "HERDMASTER",
        "answer": answer, "reply_markup": keyboard, "callback_token": claim["callback_token"], "preview_digest": claim["preview_digest"], "action_kind": kind,
        "purpose_presentation_contract": CONTRACT, "mission_id": payload["mission_id"],
        "card_mission_id": payload["mission_id"]+":TELEGRAM",
        "purpose_transition": payload.get("parent_transition"),
        "recipient_language": payload["language"], "recipient_render_contract": "specialist_structured_recipient_v1",
        "writes_farm_data": False, "hardware_commands": 0}, 200


def _overview(context, parsed, *, mission=None):
    items = []
    for row in context["cases"]:
        b = row.get("membership") or {}
        # A known display label does not grant unavailable membership authority.
        cohorts = (context.get("snapshot", {}).get("purpose_work") or {}).get("cohorts", [])
        matches = [c for c in cohorts if c.get("label") and (
            (b.get("cohort_key") and c.get("cohort_key") == b["cohort_key"])
            or (not b and row.get("dedupe_key") and c.get("case_key") == row["dedupe_key"]))]
        label = matches[0]["label"] if len(matches) == 1 else "Group "+str(len(items)+1)
        items.append({"case_id": row["case_id"], "generation": row["generation"], "evidence_digest": row["evidence_digest"],
            "available": row["available"], "label": label,
            "member_count": b.get("member_count"), "membership": b})
    return {"contract": CONTRACT, "mode": "overview", "page": 0, "cases": items,
        "language": "af" if parsed.get("output_language") == "af" else "en",
        "mission_id": mission or "OOM-PURPOSE-"+digest([parsed["telegram_user_id"], parsed["provider_message_id"]])[:32]}


def handle_purpose_message(parsed, authority, *, now=None, connect=None, context_loader=None, semantic=None):
    if not applicable(parsed,semantic): return {"handled": False}, 200
    now, loader = now or datetime.now(timezone.utc), context_loader or load_context
    try:
        owner = _owner(parsed, authority)
        data = str(parsed.get("callback_data") or "")
        if not data: return _issue(_overview(loader(now=now, connect=connect), parsed), parsed, connect=connect)
        if len(data.encode()) > 64 or data.count(":") != 2: raise ValueError("purpose_callback_invalid")
        _, token, action = data.split(":")
        if action == "remaining":
            return _remaining_overview(token, parsed, now=now, connect=connect, loader=loader)
        claimed, status = claims.claim_callback("oompa:"+token+":"+(action if action in {"confirm", "cancel"} else "details"),
            owner_user_id=owner, private_chat_id=owner, provider_message_id=str(parsed["provider_message_id"]),
            provider_timestamp=str(parsed.get("provider_timestamp") or ""), source_card_message_id=str(parsed.get("reply_to_message_id") or ""),
            connect_factory=connect, allowed_action_kinds=KINDS, purpose_callback=True)
        if claimed.get("status") == "purpose_completed_delivery_recovery":
            result = claimed.get("result") or {}
            if result.get("status") not in {"purpose_recorded_verified", "purpose_review_date_recorded", "purpose_review_date_replayed"}:
                return _refusal("purpose_completion_receipt_invalid", language=parsed.get("output_language"))
            return {"handled":True, **result, "writes_farm_data":False,
                "delivery_recovery_required":True, "delivery_callback_binding":claimed["delivery_callback_binding"]},200
        if claimed.get("status") == "protected_callback_replayed_noop":
            return {"handled": True, **claimed, "suppress_owner_delivery": True, "writes_farm_data": False}, 200
        if status >= 400: return _refusal(str(claimed.get("status")), status, language=parsed.get("output_language"))
        p = claimed.get("preview_payload") or {}
        if p.get("contract") != CONTRACT or claims.canonical_preview_digest(claimed.get("action_kind"), p) != claimed.get("preview_digest"):
            raise ValueError("purpose_preview_digest_mismatch")
        if action == "cancel":
            return {"handled": True, "success": True, "status": "purpose_review_closed", "specialist": "HERDMASTER",
                "purpose_presentation_contract":CONTRACT,"recipient_language":p["language"],
                "answer": _word(p, "Review closed. No purpose was recorded.", "Hersiening gesluit. Geen doel is aangeteken nie."), "writes_farm_data": False}, 200
        if action == "confirm":
            if claimed.get("status") not in {"protected_callback_claimed", "protected_callback_recovered"}: raise ValueError("purpose_confirmation_not_current")
            try:
                result, code = execute_claimed_purpose(claimed, parsed, now=now, connect=connect)
                if result.get("success"):
                    result.update(mission_id=p["mission_id"], card_mission_id=p["mission_id"]+":TELEGRAM",
                        owner_visible_completion_policy="verified_edit_or_new_message",
                        recipient_language=p["language"], recipient_render_contract="specialist_structured_recipient_v1",
                        purpose_presentation_contract=CONTRACT,
                        delivery_callback_binding={"owner_user_id":owner,"chat_id":owner,
                            "provider_message_id":str(parsed["provider_message_id"]),
                            "provider_timestamp":str(parsed["provider_timestamp"]),
                            "reply_to_message_id":str(parsed["reply_to_message_id"])})
                    result["reply_markup"] = {"inline_keyboard":[[_button(token,
                        _word(p,"Review remaining groups","Hersien oorblywende groepe"),"remaining")]]}
                    completion = claims.complete_claim(token, result, connect_factory=connect)
                    if not (completion.get("completed") or completion.get("replayed")) or completion.get("result") != result:
                        raise RuntimeError("purpose_completion_receipt_unproven")
                return {"handled": True, **result}, code
            except Exception:
                return {"handled":True,"success":False,"status":"purpose_confirmation_recovery_pending",
                    "specialist":"HERDMASTER","purpose_presentation_contract":CONTRACT,"recipient_language":p["language"],"answer":_word(p,
                        "The save may have completed. Its acknowledgement needs checking; do not submit a second decision.",
                        "Die stooraksie kon voltooi het. Die erkenning moet nagegaan word; moenie 'n tweede besluit indien nie."),
                    "writes_farm_data":None,"recovery_required":True},503
        if claimed.get("status") != "protected_preview_details": raise ValueError("purpose_navigation_stale")
        context = loader(now=now, connect=connect)
        if action == "overview":
            updated = _overview(context, parsed, mission=p["mission_id"])
        else:
            if p["mode"] != "overview":
                binding = _case(context, p["binding"])
                recs = _recommendations(context, binding)
                if recs != p["recommendations"]: raise ValueError("purpose_recommendation_changed")
            updated = {**p}
            if action.startswith("group") and p["mode"] == "overview":
                index = int(action[5:])
                if not 0 <= index < len(p["cases"]) or not p["cases"][index]["available"]: raise ValueError("purpose_group_invalid")
                binding = _case(context, p["cases"][index]["membership"])
                updated.update(mode="group", label=p["cases"][index]["label"], binding=binding, selected=list(binding["member_ids"]), recommendations=_recommendations(context, binding), page=0)
                updated.pop("cases", None)
            elif action.startswith("page") and p["mode"] in {"overview", "selection", "preview", "why"}:
                page = int(action[4:])
                total = len(p["cases"]) if p["mode"] == "overview" else len(p["batch_preview"]["effects"]) if p["mode"] == "preview" else len(p["recommendations"])
                size = OVERVIEW_SIZE if p["mode"] == "overview" else PAGE_SIZE
                if not 0 <= page < (total+size-1)//size: raise ValueError("purpose_page_invalid")
                updated["page"] = page
                if p["mode"] == "preview": updated["seen_pages"] = sorted(set(p["seen_pages"]) | {page})
            elif action == "why" and p["mode"] in {"group", "selection"}:
                updated.update(mode="why",page=0)
            elif action == "back" and p["mode"] == "why":
                updated.update(mode="group",page=0)
            elif action in {"all", "none"} and p["mode"] == "selection": updated["selected"] = list(binding["member_ids"]) if action == "all" else []
            elif action.startswith("pick") and p["mode"] == "selection":
                index = int(action[4:])
                if not 0 <= index < len(recs): raise ValueError("purpose_selection_invalid")
                chosen = set(p["selected"]); chosen.symmetric_difference_update({recs[index]["pig_id"]}); updated["selected"] = sorted(chosen)
            elif action == "change" and p["mode"] in {"group", "preview"}:
                updated.update(mode="selection", page=0); updated.pop("batch_preview", None); updated.pop("seen_pages", None)
            elif action == "later" and p["mode"] in {"group", "selection"}:
                day = (now+timedelta(hours=2)).date()
                updated.update(mode="dates", review_dates=[(day+timedelta(days=n)).isoformat() for n in (1, 3, 7)])
            elif action.startswith("date") and p["mode"] == "dates":
                raw = action[4:]; day = raw[:4]+"-"+raw[4:6]+"-"+raw[6:]
                if day not in p["review_dates"]: raise ValueError("purpose_review_date_invalid")
                updated.update(mode="defer", review_date=day)
            elif ((action.startswith("set") and p["mode"] == "selection") or (action == "recommend" and p["mode"] in {"group", "selection"})):
                selected = p["selected"]
                if not selected or not set(selected) <= set(binding["member_ids"]): raise ValueError("purpose_selection_invalid")
                if action == "recommend":
                    chosen = [r for r in recs if r["pig_id"] in selected]
                    if not all(_proposable(r) for r in chosen): raise ValueError("purpose_recommendation_advisory_only")
                    purposes = {r["pig_id"]: r["proposed_purpose"] for r in chosen}
                else:
                    index = int(action[3:])
                    if not 0 <= index < len(PURPOSES): raise ValueError("purpose_choice_invalid")
                    purposes = {pig: PURPOSES[index] for pig in selected}
                from modules.pig_weights.purpose_correction_batch_service import preview_correction_batch
                decisions = [{"pig_id": pig, "purpose": purposes[pig], "reason": "Owner selected in Telegram exact preview", "note": ""} for pig in selected]
                preview, code = preview_correction_batch(decisions, actor_id=owner, now=now, connect_factory=(lambda _url: connect()) if connect else None)
                if code >= 400 or not preview.get("success"): raise ValueError("purpose_canonical_preview_unavailable")
                updated.update(mode="preview", batch_preview=preview, page=0, seen_pages=[0])
            else: raise ValueError("purpose_callback_invalid")
        updated["interaction"] = str(parsed["provider_message_id"])
        updated["parent_transition"] = {"callback_token":token,"preview_digest":claimed["preview_digest"],
            "source_card_message_id":str(parsed["reply_to_message_id"]),
            "provider_message_id":str(parsed["provider_message_id"])}
        return _issue(updated, parsed, connect=connect)
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        return _refusal(str(exc) if isinstance(exc, ValueError) else "purpose_contract_invalid", language=parsed.get("output_language"))
    except Exception:
        return _refusal("purpose_store_or_source_unavailable", 503, language=parsed.get("output_language"))


def _remaining_overview(token, parsed, *, now, connect, loader):
    """One read-only continuation from a verified completed owner card."""
    from modules.oom_sakkie.family_presentation import envelope
    from modules.oom_sakkie.family_message_lifecycle import EVENT_SOURCE
    mission = "OOM-PURPOSE-CONT-"+digest([parsed["telegram_user_id"],token])[:32]
    with (connect or _connect)() as db, db.cursor() as cur:
        cur.execute("set transaction isolation level repeatable read read only")
        cur.execute("set local statement_timeout='5000ms'")
        cur.execute("""select action_kind,owner_user_id,private_chat_id,preview_digest,
            preview_payload,status,expires_at,result_payload from app_private.oom_protected_action_claims
            where callback_token=%s""",(token,))
        row = cur.fetchone()
        if (not row or row[0] not in KINDS or row[1] != str(parsed["telegram_user_id"])
                or row[2] != str(parsed["telegram_chat_id"]) or row[5] != "completed" or row[6] <= now
                or canonical_digest_invalid(row[0],row[4],row[3])):
            raise ValueError("purpose_completed_review_binding_invalid")
        result = row[7] or {}
        if (result.get("status") not in {"purpose_recorded_verified","purpose_review_date_recorded","purpose_review_date_replayed"}
                or result.get("purpose_presentation_contract") != CONTRACT):
            raise ValueError("purpose_completed_review_binding_invalid")
        cur.execute("""select review_json->'family_message_lifecycle' from public.sam_live_stock_conversation_review_events
            where event_source=%s and review_json->'family_message_lifecycle'->>'card_mission_id'=%s
              and review_json->'family_message_lifecycle'->>'state' in ('delivered','updated')
            order by created_at desc,review_event_id desc limit 1""",(EVENT_SOURCE,result["card_mission_id"]))
        receipt = cur.fetchone();receipt = receipt[0] if receipt else {}
        if (any(str(receipt.get(k) or "") != str(v) for k,v in {
                "owner_user_id":parsed["telegram_user_id"],"chat_id":parsed["telegram_chat_id"],
                "telegram_message_id":parsed.get("reply_to_message_id"),"specialist_identity":"HERDMASTER",
                "task_state":result["status"],"mission_id":result["mission_id"]}.items())
                or receipt.get("text_sha256") != hashlib.sha256(envelope(result["answer"]).encode()).hexdigest()
                or receipt.get("purpose_keyboard_sha256") != digest(result["reply_markup"])):
            raise ValueError("purpose_completed_card_receipt_invalid")
        cur.execute("""select preview_payload,status,provider_message_id from app_private.oom_protected_action_claims
            where mission_id=%s and owner_user_id=%s and private_chat_id=%s order by created_at limit 2""",
            (mission,str(parsed["telegram_user_id"]),str(parsed["telegram_chat_id"])))
        existing = cur.fetchall()
    if existing:
        if len(existing) == 1 and existing[0][1] == "active" and existing[0][2] == str(parsed["provider_message_id"]):
            payload = existing[0][0]
        else:
            return {"handled":True,"success":True,"status":"purpose_continuation_replayed_noop",
                "suppress_owner_delivery":True,"writes_farm_data":False},200
    else:
        payload = _overview(loader(now=now,connect=connect),parsed,mission=mission)
        payload.update(continuation_once=True,completed_parent_token=token)
    return _issue(payload,parsed,connect=connect)


def canonical_digest_invalid(kind,payload,expected):
    return not isinstance(payload,dict) or payload.get("contract") != CONTRACT or claims.canonical_preview_digest(kind,payload) != expected


def execute_claimed_purpose(claimed, parsed, *, now, connect=None):
    p, token = claimed["preview_payload"], claimed.get("callback_token")
    if not token: raise ValueError("purpose_confirmation_token_missing")
    if p["mode"] == "defer":
        from modules.oom_sakkie.herdmaster_purpose_deferment import record_deferral
        result = record_deferral(claimed, parsed, now=now, connect=connect)
        return {**result, "specialist": "HERDMASTER", "answer": _word(p,
            f"I'll review this group on {p['review_date']} at 08:00 SAST. No purpose was changed.",
            f"Ek sal hierdie groep op {p['review_date']} om 08:00 SAST hersien. Geen doel is verander nie.")}, 200
    if p["mode"] != "preview" or claimed["action_kind"] != CORRECTION: raise ValueError("purpose_exact_correction_preview_required")
    preview = p["batch_preview"]
    if set(p.get("seen_pages", [])) != set(range((len(preview["effects"])+PAGE_SIZE-1)//PAGE_SIZE)):
        raise ValueError("purpose_all_effect_pages_required")
    from modules.pig_weights import purpose_correction_batch_service as batches
    owner = str(parsed["telegram_user_id"])
    key = "telegram-purpose:"+digest([token, claimed["preview_digest"]])
    factory = (lambda _url: connect()) if connect else None
    with (connect or _connect)() as db, db.cursor() as cur:
        cur.execute("set transaction read only"); cur.execute("set local statement_timeout='5000ms'")
        cur.execute("select batch_id,status,decisions_json,created_by,decision_hash from public.pig_purpose_correction_batches where idempotency_key=%s", (key,))
        prior = cur.fetchone()
    expected = {"contract_version": preview["contract_version"], "decisions": preview["decisions"], "effects": preview["effects"], "preview_digest": preview["preview_digest"], "return_to": preview.get("return_to")}
    if prior:
        if prior[2] != expected or prior[3] != owner or prior[4] != batches._decision_hash(preview["decisions"]): raise ValueError("purpose_batch_recovery_binding_mismatch")
        batch_id, state = prior[:2]
    else:
        current = load_context(now=now, connect=connect)
        binding = _case(current, p["binding"])
        if _recommendations(current, binding) != p["recommendations"]: raise ValueError("purpose_recommendation_changed")
        created, code = batches.create_correction_batch(preview["decisions"], idempotency_key=key, actor_id=owner,
            confirmation_binding=preview["confirmation_binding"], connect_factory=factory)
        if code >= 400 or not created.get("success"): return _refusal(created.get("status", "purpose_batch_failed"), code, language=p["language"])
        batch_id, state = created["batch_id"], created["batch_status"]
    if state == "draft":
        approved, code = batches.approve_correction_batch(batch_id, actor_id=owner, connect_factory=factory)
        if code >= 400 or not approved.get("success"): return _refusal(approved.get("status", "purpose_approval_failed"), code, language=p["language"])
    def validate_current(connection, envelope):
        from modules.oom_sakkie.herdmaster_purpose_membership import load_current_membership
        current = load_context(now=now, connection=connection)
        binding = _case(current, p["binding"])
        load_current_membership(binding["case_id"], current["snapshot"], now=datetime.now(timezone.utc), expected_generation=binding["generation"],
            expected_evidence_digest=binding["evidence_digest"], connect=lambda: nullcontext(connection), transaction_managed=True, lock_case=True)
        if _recommendations(current, binding) != p["recommendations"] or envelope != expected: raise ValueError("purpose_current_preview_changed")
    result, code = batches.execute_correction_batch(batch_id, actor_id=owner, connect_factory=factory, today=now.astimezone(FARM_ZONE).date(), validate_current=validate_current)
    if code >= 500:
        raise RuntimeError("purpose_execution_outcome_uncertain")
    if code >= 400 or not result.get("success"): return _refusal(result.get("status", "purpose_execution_failed"), code, language=p["language"])
    readback, wanted = result.get("canonical_readback") or [], {d["pig_id"]: d["purpose"] for d in preview["decisions"]}
    if (len(readback) != len(wanted) or {r["pig_id"]: r["purpose"] for r in readback} != wanted
            or any(r["status"] != "Active" or r["on_farm"] is not True for r in readback)):
        raise ValueError("purpose_executed_readback_unproven")
    return {**result, "specialist": "HERDMASTER", "status": "purpose_recorded_verified", "answer": _word(p,
        f"Recorded and verified the purposes for {len(wanted)} animals. I'll reassess the same group from the updated records.",
        f"Die doele van {len(wanted)} diere is aangeteken en nagegaan. Ek sal dieselfde groep uit die bygewerkte rekords hersien."),
        "writes_farm_data": result.get("rows_updated", 0) > 0, "reply_markup": {"inline_keyboard": []}}, 200


def build_telegram_purpose_overview(context, parsed, *, mission, connect=None):
    """Read-only navigation builder; caller owns existing family delivery proof."""
    payload = _overview(context, parsed, mission=mission)
    payload["scheduled_overview"] = True
    payload["purpose_overview_revisit"] = context.get("purpose_overview_revisit") or []
    return _issue(payload, parsed, connect=connect)



def verify_card_transition(parsed, result, latest, *, connect=None):
    """A typed authenticated parent card may be edited to its exact successor."""
    parent = result.get("purpose_transition") or {}
    owner = str(parsed.get("telegram_user_id") or "")
    if (result.get("purpose_presentation_contract") != CONTRACT or result.get("action_kind") not in KINDS
            or parsed.get("telegram_chat_type") != "private" or owner != str(parsed.get("telegram_chat_id") or "")
            or not parent or parent.get("source_card_message_id") != str(parsed.get("reply_to_message_id") or "")
            or parent.get("provider_message_id") != str(parsed.get("provider_message_id") or "")
            or latest.get("telegram_message_id") != parent.get("source_card_message_id")
            or latest.get("purpose_callback_token") != parent.get("callback_token")
            or latest.get("purpose_preview_digest") != parent.get("preview_digest")
            or any(str(latest.get(k) or "") != str(v) for k,v in {
                "owner_user_id":owner,"chat_id":owner,"specialist_identity":"HERDMASTER",
                "mission_id":result.get("mission_id"),"card_mission_id":result.get("card_mission_id")}.items())):
        return False
    with (connect or _connect)() as db, db.cursor() as cur:
        cur.execute("set transaction read only")
        cur.execute("set local statement_timeout='3000ms'")
        cur.execute("""select callback_token,status,action_kind,owner_user_id,private_chat_id,mission_id,
            preview_digest,preview_payload,preview_card_message_id,expires_at
            from app_private.oom_protected_action_claims where callback_token=any(%s) limit 3""",
            ([parent["callback_token"], result["callback_token"]],))
        rows = {r[0]:r for r in cur.fetchall()}
    old,new = rows.get(parent["callback_token"]), rows.get(result["callback_token"])
    return bool(old and new and old[1] == "changed" and new[1] == "active"
        and all(r[2] in KINDS and r[3] == owner and r[4] == owner and r[5] == result["mission_id"] for r in (old,new))
        and old[6] == parent["preview_digest"] and old[8] == parent["source_card_message_id"]
        and new[6] == result["preview_digest"] and not new[8] and new[9] > datetime.now(timezone.utc)
        and new[7].get("parent_transition") == parent
        and claims.canonical_preview_digest(new[2],new[7]) == new[6]
        and claims.canonical_preview_digest(old[2],old[7]) == old[6])
