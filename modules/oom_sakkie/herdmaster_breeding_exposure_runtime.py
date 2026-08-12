"""Authenticated adapter for grouped HERDMASTER breeding facts.

The adapter owns no parser, Telegram transport, or persistence model.  It
accepts already-resolved semantic rows, creates the existing protected claim,
and delegates confirmed execution to the HERDMASTER grouped contract.
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import html
import json
import re

from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
from modules.oom_sakkie.protected_action_claims import build_buttons, create_claim
from modules.pig_weights.herdmaster_breeding_exposure_recovery import (
    build_grouped_preview,
    execute_grouped_preview,
    planned_exposure_removal_on,
)


ACTION_KIND = "herdmaster_breeding_grouped"
EXPOSURE_DAYS = 17


def handle_grouped_breeding_message(parsed, authority, *, claim_creator=None, evidence_loader=None):
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), dict) else {}
    parsed_rows = parse_grouped_exposure_reply(
        str(parsed.get("text") or ""), provider_timestamp=str(parsed.get("provider_timestamp") or "")
    )
    semantic_rows = semantic.get("breeding_actions")
    # Deterministic parsing repairs a demonstrably incomplete semantic packet;
    # it must not replace a complete compound packet or reinterpret sow-first
    # lines as the boar-first recovery format.
    raw_rows = (parsed_rows if len(parsed_rows) > len(semantic_rows or ()) else semantic_rows)
    if semantic.get("domain") != "herd_management" or not isinstance(raw_rows, (list, tuple)) or not raw_rows:
        return {"handled": False}, 200
    owner = str(parsed.get("telegram_user_id") or "")
    chat = str(parsed.get("telegram_chat_id") or "")
    if not validates_gateway_owner_authority(authority) or owner != chat or authority.owner_user_id != owner:
        return {"handled": True, "success": False, "status": "breeding_group_owner_required", **_zero()}, 403
    provider_message_id = str(parsed.get("provider_message_id") or "").strip()
    provider_timestamp = _provider_timestamp(parsed.get("provider_timestamp"))
    if not provider_message_id or not provider_timestamp:
        return {"handled": True, "success": False, "status": "breeding_provider_provenance_required",
                "answer": ("I could not verify this message's provider identity and time safely. "
                           "Nothing was recorded."), **_zero()}, 422
    if evidence_loader is None:
        from modules.pig_weights.farm_supabase_read_service import get_breeding_attention_source_snapshot
        evidence_loader = get_breeding_attention_source_snapshot
    try:
        evidence = evidence_loader()
    except Exception:
        return {"handled": True, "success": False, "status": "breeding_evidence_unavailable",
                "answer": "I could not verify the current animals safely. Nothing was recorded.", **_zero()}, 503
    rows, resolution_errors = _resolve_rows(raw_rows, evidence,
        provider_timestamp=provider_timestamp)
    if resolution_errors:
        return {"handled": True, "success": False, "status": "breeding_identity_clarification_required",
                "errors": resolution_errors, "question_count": 1,
                "answer": "Please identify only these ambiguous animals once: " + "; ".join(resolution_errors),
                **_zero()}, 200
    generation = hashlib.sha256(json.dumps(evidence, sort_keys=True, default=str,
                                separators=(",", ":")).encode()).hexdigest()
    preview = build_grouped_preview({"rows": rows}, evidence_generation=generation)
    mission = "OOM-HERD-BREED-" + hashlib.sha256(
        f"{owner}|{provider_message_id}|{json.dumps(rows, sort_keys=True)}".encode()
    ).hexdigest()[:24].upper()
    if preview.get("success") is not True:
        return {"handled": True, "success": False, "status": preview["status"],
                "errors": preview["errors"], "question_count": 1,
                "answer": "I could not bind the complete group. Please correct the listed facts once; nothing was recorded.",
                **_zero()}, 200
    creator = claim_creator or create_claim
    try:
        claim = creator(action_kind=ACTION_KIND, owner_user_id=owner, private_chat_id=chat,
                        mission_id=mission, provider_message_id=provider_message_id,
                        evidence_generation=generation, preview_payload=preview)
    except Exception:
        return {"handled": True, "success": False, "status": "breeding_group_claim_unavailable",
                "answer": ("I understood the complete group, but could not store its protected preview safely. "
                           "Nothing was recorded. The original provider-bound message remains the recovery source."),
                **_zero()}, 503
    if claim.get("status") == "protected_claim_existing" and claim.get("preview_card_message_id"):
        return {"handled": True, "success": True, "status": "breeding_group_preview_replay_suppressed",
                "mission_id": mission, "card_mission_id": mission, "answer": "",
                "suppress_owner_delivery": True, "replay_suppressed": True, **_zero()}, 200
    return {"handled": True, "success": True, "status": "breeding_grouped_preview_ready",
            "mission_id": mission, "card_mission_id": mission,
            "preview": preview["preview"], "preview_sha256": preview["preview_sha256"],
            "confirmation_required": True, "callback_token": claim["callback_token"],
            "reply_markup": build_buttons(claim["callback_token"], grouped=True),
            "answer": _summary(preview["preview"]["rows"]), **_zero()}, 200


def execute_claimed_group(claimed, *, actor_id, connect_factory):
    if connect_factory is None:
        connect_factory = _production_connect
    preview = claimed.get("preview_payload") or {}
    return execute_grouped_preview(preview,
        confirmed_preview_sha256=str(preview.get("preview_sha256") or ""),
        actor_id=actor_id, connect_factory=connect_factory)


def _production_connect():
    """Open the governed production store when the live callback supplies no test factory."""
    import os
    import psycopg

    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10)


def _summary(rows):
    lines = ["<b>HERDMASTER — GROUPED BREEDING PREVIEW</b>", ""]
    for row in rows:
        label = html.escape(str(row.get("label") or row.get("pig_id")))
        if row.get("action") == "exposure":
            boar = html.escape(str(row.get("boar_label") or row.get("boar_pig_id")))
            lines.append(f"• <b>{label}</b> — with {boar} from {row['exposure_started_on']} "
                         f"to {row['planned_removal_on']} (exposure only).")
        elif row.get("action") == "exposure_removal":
            boar = html.escape(str(row.get("boar_label") or row.get("boar_pig_id")))
            lines.append(f"• <b>{label}</b> — remove from {boar} on {row['actual_removed_on']}; "
                         f"possible service window {row['service_window_start']} to {row['service_window_end']}; "
                         f"expected farrowing window {row['expected_farrowing_window_start']} to "
                         f"{row['expected_farrowing_window_end']}. Exact service and conception remain Unknown.")
        elif row.get("action") == "recovery_hold":
            lines.append(f"• <b>{label}</b> — recovery hold; body condition "
                         f"{float(row['body_condition_score']):g}.")
        elif row.get("action") == "near_farrowing":
            lines.append(f"• <b>{label}</b> — appears close to farrowing; previous mating date "
                         "and father Unknown.")
        else:
            lines.append(f"• <b>{label}</b> — {html.escape(str(row.get('action') or 'review'))}.")
    lines += ["", "Nothing has been recorded yet. Confirm this complete group to record it once.",
              "This does not record mating, conception, pregnancy, movement or a litter."]
    return "\n".join(lines)


def _resolve_rows(raw_rows, evidence, *, provider_timestamp=""):
    master = ((evidence or {}).get("allocation_inputs") or {}).get("pig_master_rows") or []
    index = {}
    labels = {}
    for row in master:
        pig_id = str(row.get("Pig_ID") or row.get("pig_id") or "").strip()
        if not pig_id:
            continue
        label = str(row.get("Name") or row.get("Tag_Number") or row.get("tag_number") or pig_id).strip()
        labels[pig_id] = label
        for value in (pig_id, row.get("Name"), row.get("Tag_Number"), row.get("tag_number")):
            key = str(value or "").strip().casefold()
            if key:
                index.setdefault(key, []).append(pig_id)
    def exact(reference):
        matches = list(dict.fromkeys(index.get(str(reference or "").strip().casefold(), [])))
        return matches[0] if len(matches) == 1 else None
    resolved, errors = [], []
    exposure_rows = list((evidence or {}).get("exposure_rows") or ())
    for raw in raw_rows:
        row = dict(raw) if isinstance(raw, dict) else dict(raw or {})
        sow = exact(row.pop("animal_ref", None) or row.get("pig_id"))
        if not sow:
            errors.append(f"{row.get('pig_id') or raw.get('animal_ref')}: exact sow identity")
            continue
        boar_ref = row.pop("boar_ref", None)
        if boar_ref:
            boar = exact(boar_ref)
            if not boar:
                errors.append(f"{boar_ref}: exact boar identity")
                continue
            row["boar_pig_id"] = boar
            row["boar_label"] = labels.get(boar, boar)
        if row.get("action") == "exposure_removal":
            active=[]
            for candidate in exposure_rows:
                if str(candidate.get("sow_pig_id") or "") != sow or candidate.get("event_kind") != "started":
                    continue
                identity=str(candidate.get("exposure_identity") or "")
                removed=any(str(other.get("exposure_identity") or "") == identity
                    and other.get("event_kind") == "removed" for other in exposure_rows)
                if not removed and (not row.get("boar_pig_id")
                        or str(candidate.get("boar_pig_id") or "") == row.get("boar_pig_id")):
                    active.append(candidate)
            if len(active) != 1:
                errors.append(f"{labels.get(sow, sow)}: one active exposure required")
                continue
            active_row=active[0]
            row["boar_pig_id"]=str(active_row.get("boar_pig_id") or "")
            row["boar_label"]=labels.get(row["boar_pig_id"],row["boar_pig_id"])
            row["exposure_identity"]=str(active_row.get("exposure_identity") or "")
            row["exposure_group_identity"]=str(active_row.get("exposure_group_identity") or "") or None
            row["exposure_started_on"]=str(active_row.get("occurred_on") or "")
        planned_days = row.pop("planned_days", None)
        if planned_days is not None:
            try:
                days = int(planned_days)
                calculated = planned_exposure_removal_on(row.get("exposure_started_on"), days)
            except (TypeError, ValueError):
                errors.append(f"{labels.get(sow, sow)}: exact exposure duration")
                continue
            if row.get("planned_removal_on") and str(row["planned_removal_on"]) != calculated:
                errors.append(f"{labels.get(sow, sow)}: exposure duration conflicts with removal date")
                continue
            row["planned_removal_on"] = calculated
        prior_known = row.pop("prior_mating_known", None)
        father_known = row.pop("father_known", None)
        if row.get("action") == "recovery_hold":
            row["observed_at"] = provider_timestamp
            row["factual_note"] = str(row.get("factual_note") or
                "Owner reports body condition and directs recovery hold.")
        if row.get("action") == "near_farrowing":
            if prior_known is True or father_known is True:
                errors.append(f"{labels.get(sow, sow)}: previous mating date and father must remain Unknown")
                continue
            row["factual_note"] = str(row.get("factual_note") or
                "Owner reports she appears close to farrowing; previous mating date and father are unknown.")
            row["observed_at"] = provider_timestamp
        row["pig_id"] = sow
        row["label"] = labels.get(sow, sow)
        resolved.append(row)
    return resolved, errors


def _provider_timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return ""
    return parsed.isoformat()


def parse_grouped_exposure_reply(text, *, provider_timestamp=""):
    """Parse bounded boar-first grouped exposure phrasing without identities.

    This recognizes structure only. Canonical animal identity and ambiguity
    remain the responsibility of `_resolve_rows` against current evidence.
    """
    source = str(text or "").strip()
    if not source:
        return ()
    shared_date = _shared_date(source, provider_timestamp)
    if not shared_date:
        return ()
    rows, seen = [], set()
    for raw_line in source.splitlines():
        line = raw_line.strip().strip("•*- ")
        if not line or re.search(
            r"\b(?:not\s+(?:placed|exposed)|nie\s+geplaas|was\s+nie\s+geplaas)\b", line, re.I
        ):
            continue
        match = re.fullmatch(r"([^:–—-]{1,80})\s*(?::|\s[-–—]\s)\s*(.{1,500})", line)
        if not match:
            continue
        boar = match.group(1).strip()
        females = re.split(r"\s*(?:,|\band\b|\ben\b|&)\s*", match.group(2), flags=re.I)
        females = [item.strip(" .") for item in females if item.strip(" .")]
        if not boar or not females:
            return ()
        for female in females:
            key = female.casefold()
            if key in seen:
                return ()
            seen.add(key)
            rows.append({"action": "exposure", "animal_ref": female, "boar_ref": boar,
                         "exposure_started_on": shared_date, "planned_days": EXPOSURE_DAYS})
    return tuple(rows) if rows else ()


def _shared_date(text, provider_timestamp):
    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if iso:
        try:
            return date.fromisoformat(iso.group(1)).isoformat()
        except ValueError:
            return None
    months = {"january":1,"januarie":1,"february":2,"februarie":2,"march":3,"maart":3,
              "april":4,"may":5,"mei":5,"june":6,"junie":6,"july":7,"julie":7,
              "august":8,"augustus":8,"september":9,"october":10,"oktober":10,
              "november":11,"december":12,"desember":12}
    named = re.search(r"\b(\d{1,2})\s+(" + "|".join(months) + r")\s+(20\d{2})\b", text, re.I)
    if named:
        try:
            return date(int(named.group(3)), months[named.group(2).casefold()], int(named.group(1))).isoformat()
        except ValueError:
            return None
    if re.search(r"\b(?:today|vandag)\b", text, re.I):
        try:
            return date.fromisoformat(str(provider_timestamp)[:10]).isoformat()
        except ValueError:
            return None
    return None


def _zero():
    return {"writes_farm_data": False, "writes_matings": False, "writes_movements": False,
            "sends_telegram": False, "protected_actions_performed": False}
