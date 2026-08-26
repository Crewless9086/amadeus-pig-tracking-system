"""Preview-only bridge from durable manager cases to existing protected rails."""
from __future__ import annotations

import hashlib
import re

from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority


def build_retained_protected_preview(case):
    refs = tuple(str(value) for value in (case or {}).get("evidence_refs") or ())
    provider_ids = tuple(sorted({value.split(":", 1)[1] for value in refs
                                 if value.startswith("provider_message:") and ":" in value}))
    if not provider_ids:
        return _contained("retained_provider_identity_missing")
    if "litter-loss" in str((case or {}).get("dedupe_key") or ""):
        return _litter_loss(provider_ids, refs, str((case or {}).get("evidence_digest") or ""))
    if "expired-farrowing" in str((case or {}).get("dedupe_key") or ""):
        return _farrowing(provider_ids, str((case or {}).get("evidence_digest") or ""))
    if "retained-mortality" in str((case or {}).get("dedupe_key") or ""):
        return _mortality(provider_ids, refs)
    return _contained("retained_recovery_case_kind_unsupported")


def _litter_loss(provider_ids, refs, recovery_identity):
    incident = next((value.split(":", 1)[1] for value in refs
                     if value.startswith("incident_date:")), "")
    with connect_bounded_read() as connection:
        with connection.cursor() as cur:
            cur.execute("""select review_json->'herdmaster_health_loss'
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_herdmaster_health_loss_runtime'
                  and review_json->'herdmaster_health_loss'->>'provider_message_id'=any(%s)
                order by created_at""", (list(provider_ids),))
            rows = cur.fetchall()
            payloads = [dict(row[0] or {}) for row in rows if row and isinstance(row[0], dict)]
            principals = {(str(value.get("owner_user_id") or ""),
                           str(value.get("chat_id") or "")) for value in payloads}
            if len(principals) != 1:
                return _contained("retained_litter_loss_principal_unproven")
            owner, chat = next(iter(principals))
            if not owner or owner != chat:
                return _contained("retained_litter_loss_principal_unproven")
            texts = [str(value.get("owner_text_verbatim") or "") for value in payloads]
            counts = {int(match.group(1)) for text in texts
                      for match in [re.search(r"\b(\d+)\s+kleintjies\s+dood\b", text, re.I)]
                      if match}
            if len(counts) != 1 or not incident:
                return _contained("retained_litter_loss_exact_facts_unproven")
            cur.execute("""select l.litter_id
                from public.current_canonical_litters l
                join public.current_canonical_pigs s on s.pig_id=l.sow_pig_id
                where lower(s.pig_name)=lower(%s) and lower(coalesce(l.litter_status,''))='active'
                order by l.farrowing_date desc,l.litter_id desc limit 2""", ("Linda",))
            litters = cur.fetchall()
            piglets = []
            if len(litters) == 1:
                cur.execute("""select pig_id,coalesce(tag_number,''),coalesce(pig_name,''),
                    coalesce(sex,''),status,on_farm
                    from public.pigs where litter_id=%s
                    order by coalesce(tag_number,''),pig_id""", (str(litters[0][0]),))
                piglets = cur.fetchall()
    if len(litters) != 1:
        return _contained("retained_litter_loss_active_litter_unproven")
    litter_id, count = str(litters[0][0]), next(iter(counts))
    from modules.pig_weights.herdmaster_litter_loss_action import (
        prepare_litter_loss_preview, render_litter_loss_preview)
    male_count = next((int(str(value).split(":", 1)[1]) for value in refs
                       if str(value).startswith("male_count:")), None)
    female_count = next((int(str(value).split(":", 1)[1]) for value in refs
                         if str(value).startswith("female_count:")), None)
    sex_unknown = "sex_unknown:true" in refs
    canonical = {"animals": [{"pig_id": "LINDA", "name": "Linda"}],
        "litters": [{"litter_id": litter_id, "sow_pig_id": "LINDA",
            "litter_status": "Active", "detail": {"piglets": [
                {"pig_id": str(row[0]), "tag_number": str(row[1] or ""),
                 "name": str(row[2] or ""), "sex": str(row[3] or ""),
                 "status": str(row[4] or ""), "on_farm": row[5]}
                for row in piglets]}}]}
    prepared = prepare_litter_loss_preview({
        "sow_ref": "Linda", "litter_ref": litter_id, "event_date": incident,
        "count": count, "male_count": male_count, "female_count": female_count,
        "sex_unknown": sex_unknown, "source_event_ids": list(provider_ids),
    }, canonical)
    suffix = hashlib.sha256((recovery_identity + "|" + "|".join(provider_ids)).encode()).hexdigest()[:20].upper()
    mission = "OOM-HERDMASTER-LITTER-LOSS-" + suffix
    if prepared.get("success") is not True:
        question = str(prepared.get("question") or "")
        if question:
            return {"success": True, "handled": True, "status": "waiting_for_input",
                "answer": ("HERDMASTER retained Linda, the incident date "
                           f"{incident}, and exactly {count} deaths. {question}"),
                "clarification_question": question, "question_count": 1,
                "mission_id": mission, "card_mission_id": mission,
                "confirmation_required": False, "writes_farm_data": False}
        return {**_contained(str(prepared.get("status") or
                                "retained_litter_loss_selection_required")),
                "answer": "HERDMASTER retained Linda, the date and the deaths; "
                          "current active piglet membership conflicts with a safe preview."}
    payload = {**prepared["preview"], "owner_user_id": owner,
        "private_chat_id": chat}
    from modules.oom_sakkie.protected_action_claims import create_claim
    claim = create_claim(action_kind="herdmaster_record_litter_piglet_deaths",
        owner_user_id=owner, private_chat_id=chat, mission_id=mission,
        provider_message_id=provider_ids[0], evidence_generation=recovery_identity,
        preview_payload=payload)
    return _protected({"success": True, "status": "litter_piglet_deaths_preview_ready",
        "answer": render_litter_loss_preview(payload),
        "mission_id": mission, "card_mission_id": mission,
        "callback_token": claim["callback_token"], "preview_digest": claim["preview_digest"],
        "action_kind": "herdmaster_record_litter_piglet_deaths",
        "reply_markup": {"inline_keyboard": [[
            {"text": "Confirm and record", "callback_data": f"oompa:{claim['callback_token']}:confirm"},
            {"text": "Change", "callback_data": f"oompa:{claim['callback_token']}:change"},
            {"text": "Cancel", "callback_data": f"oompa:{claim['callback_token']}:cancel"}]]}})


def _farrowing(provider_ids, recovery_identity):
    with connect_bounded_read() as connection:
        with connection.cursor() as cur:
            cur.execute("""select owner_user_id,private_chat_id,provider_message_id,preview_payload,
                callback_token,mission_id,preview_digest,status,preview_card_message_id
                from app_private.oom_protected_action_claims
                where action_kind='herdmaster_record_farrowing_litter'
                  and provider_message_id=any(%s) order by created_at desc limit 1""",
                (list(provider_ids),))
            row = cur.fetchone()
    if not row or str(row[0] or "") != str(row[1] or ""):
        return _contained("retained_farrowing_principal_unproven")
    owner, chat, provider, preview = str(row[0]), str(row[1]), str(row[2]), dict(row[3] or {})
    if str(row[7] or "") == "active" and not str(row[8] or ""):
        counts = dict(preview.get("counts") or {})
        return _protected({"success": True, "status": "farrowing_litter_preview_ready",
            "answer": (f"HERDMASTER protected preview: {counts.get('total_born')} total born; "
                       f"{counts.get('stillborn')} stillborn on {preview.get('farrowing_date')}. "
                       "Confirm only if correct."),
            "mission_id": str(row[5]), "card_mission_id": str(row[5]),
            "callback_token": str(row[4]), "preview_digest": str(row[6]),
            "action_kind": "herdmaster_record_farrowing_litter",
            "reply_markup": {"inline_keyboard": [[
                {"text": "Confirm and record", "callback_data": f"oompa:{row[4]}:confirm"},
                {"text": "Change", "callback_data": f"oompa:{row[4]}:change"},
                {"text": "Cancel", "callback_data": f"oompa:{row[4]}:cancel"}]]}})
    counts = dict(preview.get("counts") or {})
    parsed = {"telegram_user_id": owner, "telegram_chat_id": chat,
        "provider_message_id": provider, "output_language": preview.get("language") or "af",
        "semantic": {"intent": "record_farrowing_litter",
            "language": preview.get("language") or "af", "farrowing_litter": {
                "sow_ref": preview.get("sow_pig_id"),
                "farrowing_date": preview.get("farrowing_date"),
                "total_born": counts.get("total_born"), "born_alive": counts.get("born_alive"),
                "stillborn": counts.get("stillborn"), "mummified": counts.get("mummified"),
                "mating_ref": preview.get("requested_mating_ref"),
                "father_ref": preview.get("requested_father_ref")}}}
    from modules.oom_sakkie.herdmaster_farrowing_runtime import handle_farrowing_litter_message
    from modules.oom_sakkie.protected_action_claims import create_claim
    recovery_suffix = hashlib.sha256(
        (recovery_identity + "|" + provider).encode()).hexdigest()[:12].upper()
    created = {}
    def recovery_claim(**kwargs):
        created["mission_id"] = str(kwargs["mission_id"]) + "-RECOVERY-" + recovery_suffix
        return create_claim(**{**kwargs, "mission_id": created["mission_id"]})
    result, _status = handle_farrowing_litter_message(
        parsed, issue_gateway_owner_authority(owner, chat), claim_creator=recovery_claim)
    if created.get("mission_id") and result.get("callback_token"):
        result = {**result, "mission_id": created["mission_id"],
                  "card_mission_id": created["mission_id"]}
    return _protected(result)


def _mortality(provider_ids, refs):
    with connect_bounded_read() as connection:
        with connection.cursor() as cur:
            cur.execute("""select review_json->'herdmaster_health_loss'
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_herdmaster_health_loss_runtime'
                  and review_json->'herdmaster_health_loss'->>'provider_message_id'=any(%s)
                order by created_at desc limit 1""", (list(provider_ids),))
            row = cur.fetchone()
    payload = dict(row[0] or {}) if row and isinstance(row[0], dict) else {}
    owner, chat = str(payload.get("owner_user_id") or ""), str(payload.get("chat_id") or "")
    if not owner or owner != chat:
        return _contained("retained_mortality_principal_unproven")
    target = next((value.split(":", 1)[1] for value in refs
                   if value.startswith("pig:") and ":" in value), "")
    from modules.oom_sakkie.herdmaster_health_loss_preview import (
        prepare_health_loss_owner_preview,
    )
    from modules.oom_sakkie.herdmaster_health_loss_runtime import (
        load_canonical_health_loss_evidence,
    )
    evidence = load_canonical_health_loss_evidence()
    provider = str(payload.get("provider_message_id") or "")
    preview = prepare_health_loss_owner_preview({
        "gateway_authority": issue_gateway_owner_authority(owner, chat),
        "provider_message_id": provider,
        "provider_timestamp": str(payload.get("provider_timestamp") or ""),
        "provider_timezone": "Africa/Johannesburg",
        "output_language": payload.get("output_language") or "af",
        "text": str(payload.get("owner_text_verbatim") or ""),
    }, evidence)
    identity = dict((preview.get("evaluator") or {}).get("identity") or {})
    if not target or str(identity.get("pig_id") or "") != target:
        return _contained("retained_mortality_exact_identity_unproven")
    if int(preview.get("question_count") or 0):
        return {**_contained("retained_mortality_removed_disposal_required"),
                "missing_facts": ["removed_disposal"],
                "answer": str(preview.get("owner_text") or "")}
    binding = dict(preview.get("confirmation_binding") or {})
    operation = str(binding.get("operation_id") or "")
    if preview.get("success") is not True or not operation:
        return _contained("retained_mortality_preview_unproven")
    mission = "OOM-HERDMASTER-MORTALITY-" + hashlib.sha256(
        (provider + "|" + target + "|" + operation).encode()).hexdigest()[:24].upper()
    from modules.oom_sakkie.protected_action_claims import create_claim
    claim = create_claim(action_kind="mortality", owner_user_id=owner,
        private_chat_id=chat, mission_id=mission, provider_message_id=provider,
        evidence_generation=str(evidence.get("evidence_generation") or ""),
        preview_payload={"operation_id": operation,
            "preview_sha256": str(binding.get("preview_sha256") or ""),
            "identity": identity,
            "event_family": str((preview.get("evaluator") or {}).get("event_family") or ""),
            "effect_kind": "mortality"})
    return _protected({"success": True, "status": "mortality_preview_ready",
        "answer": str(preview.get("owner_text") or ""), "mission_id": mission,
        "card_mission_id": mission, "callback_token": claim["callback_token"],
        "preview_digest": claim["preview_digest"], "action_kind": "mortality",
        "reply_markup": {"inline_keyboard": [[
            {"text": "Confirm and record", "callback_data": f"oompa:{claim['callback_token']}:confirm"},
            {"text": "Change", "callback_data": f"oompa:{claim['callback_token']}:change"},
            {"text": "Cancel", "callback_data": f"oompa:{claim['callback_token']}:cancel"}]]}})


def _protected(result):
    value = dict(result or {})
    if value.get("success") is True and value.get("callback_token"):
        return {**value, "confirmation_required": True, "writes_farm_data": False}
    return _contained(str(value.get("status") or "retained_protected_repreview_unproven"))


def execute_claimed_litter_piglet_deaths(claimed, parsed):
    """Execute only an already callback-claimed, exact piglet selection."""
    preview = dict(claimed.get("preview_payload") or {})
    if preview.get("contract_version") not in {
            "herdmaster_litter_piglet_deaths_v1",
            "herdmaster_litter_piglet_deaths_v2"}:
        return {"success": False, "status": "litter_piglet_deaths_binding_invalid",
                "writes_farm_data": False}, 409
    if str(preview.get("owner_user_id") or "") != str(parsed.get("telegram_user_id") or ""):
        return {"success": False, "status": "litter_piglet_deaths_principal_mismatch",
                "writes_farm_data": False}, 403
    operation_id = str(preview.get("operation_id") or "")
    if not operation_id:
        return {"success": False, "status": "litter_piglet_deaths_operation_missing",
                "writes_farm_data": False}, 409
    from modules.pig_weights import pig_weights_service as service
    readback = _litter_loss_operation_readback(service, preview, operation_id)
    if readback == "complete":
        remaining = _remaining_active_litter_piglets(service, preview)
        return {"success": True, "status": "litter_piglet_deaths_recovered_from_canonical",
            "piglet_count": len(preview.get("pig_ids") or ()),
            "pig_ids": list(preview.get("pig_ids") or ()), "rows_updated": 0,
            "remaining_active_count": len(remaining),
            "remaining_active_pig_ids": remaining,
            "answer": "The exact piglet deaths were already recorded; protected completion was recovered without another mutation.",
            "writes_farm_data": False, "reply_markup": {"inline_keyboard": []}}, 200
    if readback == "partial":
        return {"success": False, "status": "litter_piglet_deaths_partial_readback_recovery_required",
                "writes_farm_data": False, "recovery_required": True}, 503
    result, status = service.mark_litter_piglets_dead(preview.get("litter_id"),
        preview.get("event_date"), preview.get("reason"), pig_ids=preview.get("pig_ids") or (),
        changed_by="oom_sakkie:" + operation_id, dry_run=False)
    if result.get("success") is True:
        sow = str(preview.get("sow_name") or preview.get("sow_tag_number") or "the sow")
        remaining = _remaining_active_litter_piglets(service, preview)
        result = {**result, "answer": f"Recorded {result.get('piglet_count')} piglet deaths for {sow}'s litter exactly once.",
                  "remaining_active_count": len(remaining),
                  "remaining_active_pig_ids": remaining,
                  "reply_markup": {"inline_keyboard": []}}
    return result, status


def _litter_loss_operation_readback(service, preview, operation_id):
    wanted = {str(value) for value in preview.get("pig_ids") or ()}
    if not wanted:
        return "mismatch"
    columns = service.PIG_WEIGHTS_CONFIG["columns"]
    matched = []
    for row in service._get_pig_master_rows():
        if str(row.get(columns["pig_id"], "")) not in wanted:
            continue
        notes = str(row.get("General_Notes") or "")
        exact = (str(row.get(columns["status"], "")).casefold() == "dead"
            and str(row.get(columns["on_farm"], "")).casefold() == "no"
            and operation_id in notes)
        matched.append(exact)
    if len(matched) == len(wanted) and all(matched):
        return "complete"
    # Once any exact operation marker exists, absence or mixed state is not a
    # safe invitation to run the mutation again. Keep the claimed receipt in
    # recovery until the entire bound selection can be proved canonically.
    return "partial" if any(matched) else "mismatch"


def _remaining_active_litter_piglets(service, preview):
    columns = service.PIG_WEIGHTS_CONFIG["columns"]
    litter_id = str(preview.get("litter_id") or "")
    return sorted(
        str(row.get(columns["pig_id"], ""))
        for row in service._get_pig_master_rows()
        if str(row.get("Litter_ID") or "") == litter_id
        and str(row.get(columns["status"], "")).casefold() == "active"
        and str(row.get(columns["on_farm"], "")).casefold() == "yes"
        and str(row.get(columns["pig_id"], ""))
    )


def _contained(status):
    return {"success": False, "status": status, "suppress_owner_delivery": True,
            "telegram_sends": 0, "writes_farm_data": False, "recovery_required": True}
