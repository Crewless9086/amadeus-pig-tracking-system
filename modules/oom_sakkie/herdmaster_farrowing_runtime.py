"""Oom Sakkie -> HERDMASTER protected farrowing/litter action."""

from __future__ import annotations

import html
import os
from typing import Mapping

from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
from modules.oom_sakkie.protected_action_claims import canonical_preview_digest, create_claim
from modules.pig_weights.farm_supabase_write_service import create_governed_farrowing_litter
from modules.pig_weights.herdmaster_farrowing_litter_intake import (
    ACTION_KIND, FarrowingEvidenceError, prepare_farrowing_litter_preview,
)


def handle_farrowing_litter_message(parsed: Mapping, authority, *, connect_factory=None,
                                    evidence_loader=None, claim_creator=None):
    parsed = dict(parsed or {})
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), Mapping) else {}
    facts = semantic.get("farrowing_litter")
    if semantic.get("intent") != "record_farrowing_litter" or not isinstance(facts, Mapping):
        return {"handled": False, "status": "farrowing_litter_not_applicable"}, 200
    owner, chat = str(parsed.get("telegram_user_id") or ""), str(parsed.get("telegram_chat_id") or "")
    if not validates_gateway_owner_authority(authority) or not owner or owner != chat:
        return {"handled": True, "success": False, "status": "farrowing_owner_authority_required",
                "writes_farm_data": False}, 403
    try:
        canonical = (evidence_loader or load_canonical_farrowing_evidence)(connect_factory=connect_factory)
        result = prepare_farrowing_litter_preview({
            "authenticated": True, "authenticated_principal_id": owner,
            "provider_message_id": str(parsed.get("provider_message_id") or ""),
            "language": str(semantic.get("language") or parsed.get("output_language") or "en"),
            "farrowing_litter": facts,
        }, canonical)
    except (FarrowingEvidenceError, RuntimeError, OSError, ValueError):
        return {"handled": True, "success": False, "status": "farrowing_evidence_unavailable",
                "answer": "HERDMASTER could not safely refresh the litter evidence. Nothing was recorded.",
                "writes_farm_data": False}, 503
    if result.get("success") is not True:
        question = str(result.get("question") or "")
        return {"handled": True, **result, "answer": question or _hold_answer(result),
                "question_count": 1 if question else 0}, 409 if not question else 200
    preview = result["preview"]
    mission_id = "OOM-" + result["operation_id"]
    creator = claim_creator or create_claim
    claim = creator(action_kind=ACTION_KIND, owner_user_id=owner, private_chat_id=chat,
                    mission_id=mission_id, provider_message_id=str(parsed.get("provider_message_id") or ""),
                    evidence_generation=str(preview["evidence_generation"]), preview_payload=preview,
                    connect_factory=connect_factory)
    answer = _preview_answer(result)
    return {"handled": True, "success": True, "status": "farrowing_litter_preview_ready",
            "answer": answer, "question_count": 0, "mission_id": mission_id,
            "card_mission_id": mission_id, "callback_token": claim["callback_token"],
            "preview_digest": claim["preview_digest"], "action_kind": ACTION_KIND,
            "reply_markup": {"inline_keyboard": [[
                {"text": "Confirm and record", "callback_data": f"oompa:{claim['callback_token']}:confirm"},
                {"text": "Change", "callback_data": f"oompa:{claim['callback_token']}:change"},
                {"text": "Cancel", "callback_data": f"oompa:{claim['callback_token']}:cancel"},
            ]]}, "writes_farm_data": False, "protected_actions_performed": False}, 200


def execute_claimed_farrowing_litter(claimed, parsed, *, connect_factory=None):
    preview = dict(claimed.get("preview_payload") or {})
    fresh = load_canonical_farrowing_evidence(connect_factory=connect_factory)
    # Recompose from the exact typed preview against fresh canonical truth. This
    # is the mandatory duplicate/mating check immediately before mutation.
    report = {"authenticated": True,
              "authenticated_principal_id": str(parsed.get("telegram_user_id") or ""),
              "provider_message_id": str(preview.get("provider_message_id") or ""),
              "language": str(preview.get("language") or "en"),
              "farrowing_litter": {"sow_ref": preview.get("sow_pig_id"),
                  "farrowing_date": preview.get("farrowing_date"), **dict(preview.get("counts") or {}),
                  "mating_ref": preview.get("requested_mating_ref"),
                  "father_ref": preview.get("requested_father_ref"),
                  "correction_of_litter_id": preview.get("correction_of_litter_id"),
                  "correction_reason": preview.get("correction_reason")}}
    refreshed = prepare_farrowing_litter_preview(report, fresh)
    if (refreshed.get("success") is not True
            or canonical_preview_digest(ACTION_KIND, refreshed.get("preview") or {}) != claimed.get("preview_digest")):
        return {"success": False, "status": "farrowing_evidence_changed_repreview_required",
                "writes_farm_data": False}, 409
    result = create_governed_farrowing_litter(
        preview, actor_id=str(parsed.get("telegram_user_id") or ""), connect_factory=connect_factory)
    readback = load_litter_readback(result["litter_id"], connect_factory=connect_factory)
    if not readback or int(readback.get("total_born") or -1) != int(preview["counts"]["total_born"]):
        return {**result, "success": False, "status": "farrowing_readback_recovery_required",
                "recovery_required": True}, 503
    label = _sow_label(preview)
    af = str(preview.get("language") or "").startswith("af")
    if af:
        answer = (f"{label} se werpsel is aangeteken: {preview['counts']['born_alive']} lewend gebore, "
                  f"{preview['counts']['mummified']} gemummifiseer op {preview['farrowing_date']}. "
                  + ("Paring en vader bly Onbekend. " if not preview.get("mating_id") else "Die toepaslike paring is as Gekry gemerk. ")
                  + "HERDMASTER volg nou die gewone werpselsorg, merk, weeg en speen op.")
    else:
        answer = (f"Litter recorded for {label}: {preview['counts']['born_alive']} born alive, "
                  f"{preview['counts']['mummified']} mummified on {preview['farrowing_date']}. "
                  + ("Mating and father remain Unknown. " if not preview.get("mating_id") else "The attributable mating was marked Farrowed. ")
                  + "HERDMASTER now owns the normal litter-care, tagging, weighing and weaning follow-up.")
    return {**result, "answer": answer, "canonical_readback": readback,
            "follow_up_owner": "HERDMASTER", "reply_markup": {"inline_keyboard": []}}, 201


def load_canonical_farrowing_evidence(*, connect_factory=None):
    with _connect(connect_factory) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("select pig_id,tag_number,pig_name as name,status,on_farm,sex,animal_type from public.current_canonical_pigs")
            animals = _rows(cursor)
            cursor.execute("""select mating_id,sow_pig_id,boar_pig_id,mating_date,outcome,
                (expected_farrowing_date - interval '10 days')::date as expected_farrowing_window_start,
                (expected_farrowing_date + interval '10 days')::date as expected_farrowing_window_end,
                related_litter_id as linked_litter_id
                from public.mating_events order by mating_date,mating_id""")
            matings = _rows(cursor)
            cursor.execute("select litter_id,sow_pig_id,boar_pig_id,farrowing_date,total_born,born_alive from public.current_canonical_litters")
            litters = _rows(cursor)
    generation = f"farrowing:{len(animals)}:{len(matings)}:{len(litters)}:" + \
        str(max([str(row.get('litter_id') or '') for row in litters] or ['none']))
    return {"evidence_generation": generation, "animals": animals, "matings": matings, "litters": litters}


def load_litter_readback(litter_id, *, connect_factory=None):
    with _connect(connect_factory) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select litter_id,sow_pig_id,boar_pig_id,farrowing_date,total_born,
                born_alive,stillborn_count,mummified_count,litter_status from public.current_canonical_litters
                where litter_id=%s""", (litter_id,))
            rows = _rows(cursor)
    return rows[0] if len(rows) == 1 else None


def _connect(factory):
    if factory:
        return factory()
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10)


def _rows(cursor):
    names = [item.name if hasattr(item, "name") else item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _hold_answer(result):
    if result.get("status") == "canonical_litter_already_exists":
        return "A litter already exists for this sow and date. Nothing new was recorded."
    return "The litter facts were retained, but the disputed or incomplete part needs safe reconciliation. Nothing was recorded."


def _preview_answer(result):
    p, c = result["preview"], result["counts"]
    label = _sow_label(p)
    af = str(p.get("language") or "").startswith("af")
    linkage = (f"Mating {p['mating_id']} and father {p['father_pig_id']} will be linked."
               if p.get("mating_id") else "Mating and father will remain Unknown; neither will be invented.")
    if af:
        linkage = (f"Paring {p['mating_id']} en vader {p['father_pig_id']} sal gekoppel word."
                   if p.get("mating_id") else "Paring en vader bly Onbekend; niks word uitgedink nie.")
        return (f"HERDMASTER werpselvoorskou: {label}, {p['farrowing_date']}; "
                f"totaal {c['total_born']}, lewend gebore {c['born_alive']}, doodgebore {c['stillborn']}, "
                f"gemummifiseer {c['mummified']}. {linkage} Bevestig die presiese beskermde rekord.")
    return (f"HERDMASTER litter preview: {label}, {p['farrowing_date']}; "
            f"total {c['total_born']}, born alive {c['born_alive']}, stillborn {c['stillborn']}, "
            f"mummified {c['mummified']}. {linkage} Confirm the exact protected record.")


def _sow_label(preview):
    pig_id = html.escape(str(preview.get("sow_pig_id") or "").strip())
    name = html.escape(str(preview.get("sow_display_name") or "").strip())
    return f"{name} ({pig_id})" if name and name.casefold() != pig_id.casefold() else pig_id
