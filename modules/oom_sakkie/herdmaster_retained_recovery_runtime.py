"""Preview-only bridge from durable manager cases to existing protected rails."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import html
import time
import json
import re

from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority


REPORT_READ_LIMIT = 1024
REPORT_ID_LIMIT = 128
REPORT_SOURCE = "oom_sakkie_herdmaster_health_loss_runtime"


def read_retained_health_reports(cursor, provider_ids):
    """Bounded canonical chronology, including later replies under another ID.

    Provider IDs are chat-local. They select evidence, never authenticate it.
    No status or age filter may precede the mission's latest-state selection.
    """
    ids = sorted(set(provider_ids))
    if not ids or len(ids) > REPORT_ID_LIMIT or any(not str(v).isdigit() for v in ids):
        raise ValueError("retained_report_identity_read_bound_invalid")
    cursor.execute("""select review_json->'herdmaster_health_loss'
        from public.sam_live_stock_conversation_review_events
        where event_source=%s
          and review_json->'herdmaster_health_loss'->>'provider_message_id'=any(%s)
        order by created_at desc,review_event_id desc limit %s""",
        (REPORT_SOURCE, ids, REPORT_READ_LIMIT + 1))
    reports = cursor.fetchall()
    if len(reports) > REPORT_READ_LIMIT:
        raise ValueError("retained_report_read_bound_exceeded")
    payloads = [row[0] for row in reports if row and isinstance(row[0], dict)]
    missions = sorted({str(row.get("mission_id") or "") for row in payloads} - {""})
    if not missions:
        return {"reports": payloads, "lifecycle": [], "claims": []}
    cursor.execute("""select review_json->'herdmaster_health_loss'
        from public.sam_live_stock_conversation_review_events
        where event_source=%s and (
          review_json->'herdmaster_health_loss'->>'mission_id'=any(%s)
          or review_json->'herdmaster_health_loss'->'consumed_context_missions' ?| %s
          or exists (select 1 from jsonb_array_elements(coalesce(
            review_json->'herdmaster_health_loss'->'superseded_duplicate_bindings',
            '[]'::jsonb)) b where b->>'mission_id'=any(%s)))
        order by created_at desc,review_event_id desc limit %s""",
        (REPORT_SOURCE, missions, missions, missions, REPORT_READ_LIMIT + 1))
    lifecycle = cursor.fetchall()
    if len(lifecycle) > REPORT_READ_LIMIT:
        raise ValueError("retained_report_lifecycle_read_bound_exceeded")
    cursor.execute("""select owner_user_id,private_chat_id,mission_id,
        provider_message_id,status,action_kind,preview_payload,
        jsonb_build_object('callback_token',callback_token,'preview_digest',preview_digest,
          'evidence_generation',evidence_generation,'expires_at',expires_at,
          'preview_card_message_id',preview_card_message_id,'delivery_state',delivery_state,
          'delivery_attempt_id',delivery_attempt_id,'delivery_attempted_at',delivery_attempted_at,
          'provider_accepted_at',provider_accepted_at,'delivery_confirmed_at',delivery_confirmed_at,
          'delivery_ambiguous_at',delivery_ambiguous_at,'delivery_result',delivery_result,
          'result_payload',result_payload,'confirmation_provider_message_id',confirmation_provider_message_id,
          'confirmation_provider_timestamp',confirmation_provider_timestamp,'completed_at',completed_at) as delivery
        from app_private.oom_protected_action_claims
        where mission_id=any(%s) or provider_message_id=any(%s)
          or preview_payload->'provider_message_ids' ?| %s
        order by created_at desc limit %s""",
        (missions, ids, ids, REPORT_READ_LIMIT + 1))
    claims = cursor.fetchall()
    if len(claims) > REPORT_READ_LIMIT:
        raise ValueError("retained_report_claim_read_bound_exceeded")
    return {"reports": payloads,
        "lifecycle": [row[0] for row in lifecycle if row and isinstance(row[0], dict)],
        "claims": claims}


def resolve_retained_health_reports(evidence, provider_ids, *, retain_existing_attempts=False):
    """Return only unchanged, uniquely owned, still-unresolved original reports.

    Existing protected attempts are left to their own callback/recovery rail.
    An expired/cancelled/completed/ambiguous claim never licenses a new digest.
    This function neither retires a report nor infers farm completion.
    """
    ids = set(provider_ids)
    if not ids:
        return [], "retained_provider_identity_missing"
    selected = []
    for provider in sorted(ids):
        rows = [row for row in evidence["reports"]
                if str(row.get("provider_message_id") or "") == provider]
        bindings = {(str(row.get("owner_user_id") or ""), str(row.get("chat_id") or ""),
                     str(row.get("mission_id") or "")) for row in rows}
        if len(bindings) != 1:
            return [], "retained_report_principal_or_mission_unproven"
        owner, chat, mission = next(iter(bindings))
        if not owner or owner != chat or not mission:
            return [], "retained_report_principal_or_mission_unproven"
        current = [row for row in evidence["lifecycle"] if row.get("mission_id") == mission]
        if not current or any((row.get("owner_user_id"), row.get("chat_id")) != (owner, chat)
                              for row in current):
            return [], "retained_report_lifecycle_unproven"
        latest = current[0]
        original = rows[-1]
        bridge = latest.get("retained_repreview") or {}
        recovered = (retain_existing_attempts and latest.get("status") == "preview_ready"
            and str(latest.get("event_phase") or "").startswith("retained_preview_generated:")
            and bridge.get("contract_version") == "retained_health_preview_v1"
            and bridge.get("source_binding") == retained_report_binding([original])
            and bool(bridge.get("claim_mission_id")) and bool(bridge.get("claim_preview_digest"))
            and latest.get("operation_id") == (latest.get("preview") or {}).get("confirmation_binding", {}).get("operation_id"))
        if (latest.get("status") != "waiting_for_input" and not recovered
                or latest.get("provider_message_id") != provider
                or latest.get("owner_text_verbatim") != original.get("owner_text_verbatim")
                or latest.get("correction_digest")
                or latest.get("invalidated_operation_ids")):
            return [], "retained_report_no_longer_unresolved"
        selected.append(latest)
    principals = {(row["owner_user_id"], row["chat_id"]) for row in selected}
    if len(principals) != 1:
        return [], "retained_report_principal_or_mission_unproven"
    owner, chat = next(iter(principals))
    missions = {row["mission_id"] for row in selected}
    for row in evidence["lifecycle"]:
        if (row.get("owner_user_id"), row.get("chat_id")) != (owner, chat):
            continue
        # A reference is enough to stop re-preview; it is never completion proof.
        # Even an incomplete supersession binding requires canonical reconciliation.
        if (missions.intersection(row.get("consumed_context_missions") or ())
                or any(isinstance(binding, dict) and binding.get("mission_id") in missions
                       for binding in row.get("superseded_duplicate_bindings") or ())):
            return [], "retained_report_correction_requires_reconciliation"
    for claim in evidence["claims"]:
        c_owner, c_chat, mission, provider, _status, _kind, payload = claim[:7]
        members = set((payload or {}).get("provider_message_ids") or ())
        if (str(mission) in missions or ((str(c_owner), str(c_chat)) == (owner, chat)
                and (str(provider) in ids or members.intersection(ids)))):
            if not retain_existing_attempts:
                return [], "retained_report_existing_protected_attempt"
            # Keep the exact retained case observable. This permits no delivery:
            # the preview boundary must compare current canonical evidence with
            # the existing claim, and terminal/uncertain attempts remain contained.
    return selected, ""



def retained_mortality_tag(row):
    """Use the retained specialist assessment, including identity-bound short replies.

    Historical reports without a typed assessment retain their existing legacy
    eligibility. Prose must never override a present contrary assessment.
    """
    if (row.get("semantic_interpretation") or {}).get("recording_prohibited"):
        return ""
    evaluator = (row.get("preview") or {}).get("evaluator") or {}
    if evaluator:
        identity = evaluator.get("identity") or {}
        if (evaluator.get("event_family") == "found_dead"
                and identity.get("resolved") is True and identity.get("pig_id")):
            return str(identity.get("tag_number") or "")
        return ""
    text = str(row.get("owner_text_verbatim") or "")
    match = re.search(r"\b(?:vark|pig)\s*(?:nr)?\s*(\d+)\b", text, re.I)
    return match.group(1) if match and "dood" in text.casefold() else ""


def retained_identity_reassessment_needed(row):
    """An unresolved old identity may be reevaluated; contrary facts may not."""
    evaluator = (row.get("preview") or {}).get("evaluator") or {}
    identity = evaluator.get("identity") or {}
    return (row.get("status") == "waiting_for_input"
        and not (row.get("semantic_interpretation") or {}).get("recording_prohibited")
        and evaluator.get("status") == "identity_required"
        and evaluator.get("event_family") == "unknown"
        and identity.get("resolved") is False and not identity.get("pig_id")
        and not row.get("correction_digest") and not row.get("invalidated_operation_ids"))


def _prepare_retained_report(payload, evidence):
    from modules.oom_sakkie.herdmaster_health_loss_preview import prepare_health_loss_owner_preview
    return prepare_health_loss_owner_preview({
        "gateway_authority": issue_gateway_owner_authority(payload["owner_user_id"], payload["chat_id"]),
        "provider_message_id": str(payload.get("provider_message_id") or ""),
        "provider_timestamp": str(payload.get("provider_timestamp") or ""),
        "provider_timezone": "Africa/Johannesburg",
        "output_language": payload.get("output_language") or "af",
        "text": str(payload.get("combined_text") or payload.get("owner_text_verbatim") or ""),
        **({"report_parts": payload["report_parts"]} if payload.get("report_parts") else {}),
        **{key: value for key, value in (payload.get("semantic_interpretation") or {}).items()
           if key in {"mortality_observation", "welfare_observation", "clinical_observation"}},
    }, evidence)


def reassess_retained_mortality_identity(row, evidence):
    if not retained_identity_reassessment_needed(row):
        return {}
    if not retained_recipient_authorized(_delivery_context(row)):
        return {}
    evaluated = _prepare_retained_report(row, evidence).get("evaluator") or {}
    identity = evaluated.get("identity") or {}
    if (evaluated.get("event_family") != "found_dead" or identity.get("resolved") is not True
            or not identity.get("pig_id") or not identity.get("tag_number")):
        return {}
    return identity


def retained_report_binding(rows):
    """Stable source identity, not a claim that the report facts are current."""
    identities = sorted({(str(row.get("provider_message_id") or ""),
                          str(row.get("owner_user_id") or ""),
                          str(row.get("chat_id") or ""),
                          str(row.get("mission_id") or "")) for row in rows})
    return "retained_report_binding:" + hashlib.sha256(
        json.dumps(identities, separators=(",", ":")).encode()).hexdigest()


def _validated_report_case(case, provider_ids, *, claims_out=None):
    with connect_bounded_read() as connection:
        with connection.cursor() as cursor:
            evidence = read_retained_health_reports(cursor, provider_ids)
    rows, failure = resolve_retained_health_reports(evidence, provider_ids, retain_existing_attempts=True)
    if failure:
        return [], failure
    refs = tuple(str(v) for v in case.get("evidence_refs") or ())
    bindings = {value for value in refs if value.startswith("retained_report_binding:")}
    if bindings != {retained_report_binding(rows)}:
        return [], "retained_report_source_binding_unproven"
    key = str(case.get("dedupe_key") or "")
    if key.startswith("herdmaster:retained-mortality:"):
        tags = {v.split(":", 1)[1] for v in refs if v.startswith("tag:")}
        reported = {retained_mortality_tag(row) for row in rows} - {""}
        reassess = ("retained_identity_reassessment:required" in refs and len(rows) == 1
                    and retained_identity_reassessment_needed(rows[0]))
        if (len(provider_ids) != 1 or key != "herdmaster:retained-mortality:" + provider_ids[0]
                or len(tags) != 1 or (tags != reported and not reassess)):
            return [], "retained_mortality_exact_identity_unproven"
    else:
        incidents = {v.split(":", 1)[1] for v in refs if v.startswith("incident_date:")}
        dates = {f"2026-08-{int(match.group(1)):02d}" for row in rows for match in
                 [re.search(r"\b(\d{1,2})\s+aug\b", str(row.get("owner_text_verbatim") or ""), re.I)] if match}
        if (len(incidents) != 1 or dates != incidents or key !=
                "herdmaster:retained-litter-loss:" + provider_ids[0] + ":" + next(iter(incidents))):
            return [], "retained_litter_loss_exact_facts_unproven"
    if not all(retained_recipient_authorized(_delivery_context(row)) for row in rows):
        return [], "retained_recipient_not_currently_authorized"
    if claims_out is not None:
        claims_out.extend(evidence["claims"])
    return rows, ""


def build_retained_protected_preview(case, *, deadline_monotonic=None):
    refs = tuple(str(value) for value in (case or {}).get("evidence_refs") or ())
    provider_ids = tuple(sorted({value.split(":", 1)[1] for value in refs
                                 if value.startswith("provider_message:") and ":" in value}))
    if not provider_ids:
        return _contained("retained_provider_identity_missing")
    if "litter-loss" in str((case or {}).get("dedupe_key") or ""):
        return _litter_loss(provider_ids, refs, str((case or {}).get("evidence_digest") or ""), case, deadline_monotonic)
    if "expired-farrowing" in str((case or {}).get("dedupe_key") or ""):
        return _contained("retained_farrowing_owner_review_required")
    if "retained-mortality" in str((case or {}).get("dedupe_key") or ""):
        return _mortality(provider_ids, refs, case, deadline_monotonic)
    return _contained("retained_recovery_case_kind_unsupported")


def _litter_loss(provider_ids, refs, recovery_identity, case, deadline_monotonic=None):
    claims = []
    payloads, failure = _validated_report_case(case, provider_ids, claims_out=claims)
    if failure:
        return _contained(failure)
    incident = next(value.split(":", 1)[1] for value in refs if value.startswith("incident_date:"))
    owner, chat = payloads[0]["owner_user_id"], payloads[0]["chat_id"]
    texts = [str(value.get("owner_text_verbatim") or "") for value in payloads]
    counts = {int(match.group(1)) for text in texts
              for match in [re.search(r"\b(\d+)\s+kleintjies\s+dood\b", text, re.I)] if match}
    identities = [(value.get("preview") or {}).get("evaluator", {}).get("identity", {})
                  for value in payloads]
    sows = {str(value.get("pig_id")) for value in identities
            if value.get("resolved") is True and value.get("pig_id")}
    if len(counts) != 1 or len(sows) != 1:
        return _contained("retained_litter_loss_exact_facts_unproven")
    with connect_bounded_read() as connection:
        with connection.cursor() as cur:
            cur.execute("""select l.litter_id
                from public.current_canonical_litters l
                join public.current_canonical_pigs s on s.pig_id=l.sow_pig_id
                where s.pig_id=%s
                  and lower(coalesce(l.litter_status,''))='active'
                  and l.farrowing_date<=%s::date
                order by l.farrowing_date desc,l.litter_id desc limit 2""",
                (next(iter(sows)), incident))
            litters = cur.fetchall()
    if len(litters) != 1:
        return _contained("retained_litter_loss_active_litter_unproven")
    litter_id, count = str(litters[0][0]), next(iter(counts))
    from modules.pig_weights.pig_weights_service import mark_litter_piglets_dead
    preview, status = mark_litter_piglets_dead(
        litter_id, incident, "Unknown", count=count, changed_by="oom_sakkie", dry_run=True)
    if status >= 400 or preview.get("success") is not True:
        return {**_contained("retained_litter_loss_selection_required"),
                "answer": "HERDMASTER retained the resolved sow, incident date and reported loss count. "
                          + " ".join(str(value) for value in preview.get("errors") or ())}
    operation_id = "HERD-LITTER-LOSS-" + hashlib.sha256(
        (recovery_identity + "|" + "|".join(provider_ids) + "|" + litter_id
         + "|" + incident + "|" + str(count)).encode()).hexdigest()[:24].upper()
    payload = {"contract_version": "herdmaster_litter_piglet_deaths_v1",
        "litter_id": litter_id, "event_date": incident, "reason": "Unknown",
        "count": count, "pig_ids": list(preview.get("pig_ids") or ()),
        "operation_id": operation_id,
        "provider_message_ids": list(provider_ids), "owner_user_id": owner,
        "private_chat_id": chat, "selected_piglets": preview.get("selected_piglets") or []}
    suffix = hashlib.sha256((recovery_identity + "|" + "|".join(provider_ids)).encode()).hexdigest()[:20].upper()
    mission = "OOM-HERDMASTER-LITTER-LOSS-" + suffix
    claim, failure = _same_or_new_claim(payloads, claims, deadline_monotonic,
        action_kind="herdmaster_record_litter_piglet_deaths",
        owner_user_id=owner, private_chat_id=chat, mission_id=mission,
        provider_message_id=provider_ids[0], evidence_generation=recovery_identity,
        preview_payload=payload)
    if failure:
        return _contained(failure)
    return _protected({"success": True, "status": "litter_piglet_deaths_preview_ready",
        "answer": _litter_preview_text(payload, payloads[0].get("output_language") or "af"),
        "recipient_render_contract": "specialist_structured_recipient_v1",
        "recipient_language": payloads[0].get("output_language") or "af",
        "retained_delivery_context": _delivery_context(payloads[0]),
        "mission_id": mission, "card_mission_id": mission,
        "callback_token": claim["callback_token"], "preview_digest": claim["preview_digest"],
        "action_kind": "herdmaster_record_litter_piglet_deaths",
        "reply_markup": {"inline_keyboard": [[
            {"text": "Confirm and record", "callback_data": f"oompa:{claim['callback_token']}:confirm"},
            {"text": "Change", "callback_data": f"oompa:{claim['callback_token']}:change"},
            {"text": "Cancel", "callback_data": f"oompa:{claim['callback_token']}:cancel"}]]}})


FARROWING_KEY = "herdmaster:expired-farrowing:"
FARROWING_REVIEW_FAMILY = "retained_farrowing_owner_review"
FARROWING_KIND = "herdmaster_record_farrowing_litter"


def read_retained_farrowing_reviews(cur, now, retained, *, discovery=False):
    """Attribute an informational owner handoff to the original stored claim.

    This is not a protected preview or claim succession. Legacy claims are the
    retained report source; absent conversation receipts grant no owner authority.
    """
    from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
    from modules.oom_sakkie.manager_case_sources import _candidate
    owned = {key: (refs, status) for key, refs, status in retained if key.startswith(FARROWING_KEY)}
    missions = [key[len(FARROWING_KEY):] for key in owned]
    if not discovery and not missions:
        return []
    cur.execute("""select case when octet_length(c.preview_payload::text)<=32768
          then to_jsonb(c)-'callback_token' end
        from app_private.oom_protected_action_claims c
        where c.action_kind=%s and (c.mission_id=any(%s) or (%s
          and c.status='active' and c.expires_at<%s
          and c.preview_card_message_id is not null
          and position('-RECOVERY-' in c.mission_id)=0))
        order by c.mission_id,c.created_at,c.callback_token limit 65""",
        (FARROWING_KIND, missions, discovery, now))
    originals = [row[0] for row in cur.fetchall()]
    if len(originals)>64 or any(not isinstance(c, dict) or not isinstance(c.get('preview_payload'), dict) for c in originals):
        raise ValueError("retained_farrowing_source_read_bound")
    if not originals:
        return []
    missions = [c['mission_id'] for c in originals]
    providers = list({c['provider_message_id'] for c in originals})
    sows = list({str(c['preview_payload'].get('sow_pig_id') or '') for c in originals})
    cur.execute("""select case when octet_length(c.preview_payload::text)<=32768
          then to_jsonb(c)-'callback_token' end
        from app_private.oom_protected_action_claims c
        where c.action_kind=%s and (c.mission_id=any(%s)
          or c.provider_message_id=any(%s) or c.preview_payload->>'sow_pig_id'=any(%s))
        order by c.mission_id,c.created_at,c.callback_token limit 129""", (FARROWING_KIND, missions, providers, sows))
    claims = [row[0] for row in cur.fetchall()]
    if len(claims)>128 or any(not isinstance(c, dict) or not isinstance(c.get('preview_payload'), dict) for c in claims):
        raise ValueError("retained_farrowing_claim_read_bound")
    cur.execute("""select pig_id,tag_number,status,on_farm,pig_name from public.current_canonical_pigs
        where pig_id=any(%s) order by pig_id limit 129""", (sows,))
    pigs = cur.fetchall()
    cur.execute("""select litter_id,sow_pig_id,farrowing_date from public.litters
        where sow_pig_id=any(%s) order by litter_id limit 129""", (sows,))
    litters = cur.fetchall()
    if len(pigs)>128 or len(litters)>128:
        raise ValueError("retained_farrowing_canonical_read_bound")
    aliases = sorted(set(sows + [str(p[1]) for p in pigs if p[1]]
        + [str(p[4]) for p in pigs if p[4]]
        + [str(c['preview_payload'].get('sow_display_name')) for c in originals
           if c['preview_payload'].get('sow_display_name')]))
    cur.execute("""select review_json->'farrowing_litter'
        from public.sam_live_stock_conversation_review_events
        where event_source='oom_sakkie_farrowing_litter' and (
          review_json->'farrowing_litter'->>'provider_message_id'=any(%s)
          or review_json->'farrowing_litter'->>'context_id'=any(%s)
          or review_json->'farrowing_litter'->'sow_refs' ?| %s)
        order by created_at,review_event_id limit 129""", (providers, missions, aliases))
    conversations = [row[0] for row in cur.fetchall()]
    if len(conversations)>128:
        raise ValueError('retained_farrowing_conversation_read_bound')
    result = []
    for original in originals:
        mission, provider = original['mission_id'], original['provider_message_id']
        key = FARROWING_KEY + mission
        if sum(c['mission_id'] == mission for c in originals) != 1:
            continue
        refs, status = owned.get(key, ([], 'open'))
        if status not in {'open','delegated','waiting_reassessment','exception'}:
            continue
        preview = original['preview_payload']
        owner, chat = original['owner_user_id'], original['private_chat_id']
        sow, event_date = str(preview.get('sow_pig_id') or ''), str(preview.get('farrowing_date') or '')
        expected = {f'mission:{mission}', f'provider_message:{provider}', f'sow:{sow}'}
        prior = {r for r in refs if r.startswith(('mission:', 'provider_message:', 'sow:'))}
        if owned.get(key) and prior != expected:
            continue
        try:
            expired = datetime.fromisoformat(original['expires_at']) < now
            event_day = datetime.fromisoformat(event_date).date()
        except (ValueError, TypeError):
            continue
        binding = 'retained_farrowing_source:' + _farrowing_digest(original)
        previous = {r for r in refs if r.startswith('retained_farrowing_source:')}
        def park(reason, evidence):
            if key not in owned:
                return
            lineage = sorted(expected | (previous or {binding}))
            result.append(_candidate(key, 'HERDMASTER', 'watch',
                lineage + ['farrowing_reconciliation:' + reason,
                    'farrowing_current_evidence:' + _farrowing_digest(evidence)], [],
                'The retained farrowing report needs reconciliation with current owning evidence: '
                    + reason.replace('_', ' ') + '. The historical report is not an owner confirmation.',
                'Follow the current birth conversation or canonical birth result. Preserve the old '
                    'report and claims; do not replay or confirm them automatically.',
                now + timedelta(minutes=30), task_class='status_reconciliation',
                message_family='herdmaster_disposition'))
        if (not owner or owner != chat or not str(provider).isdigit() or not sow
                or event_day > now.date() or '-RECOVERY-' in mission
                or preview.get('principal_id') not in (None, owner)
                or preview.get('provider_message_id') not in (None, provider)
                or original['preview_digest'] != canonical_preview_digest(FARROWING_KIND, preview)):
            continue
        if previous and previous != {binding}:
            park('retained_source_changed', original)
            continue
        if original['status'] != 'active':
            park('original_claim_' + original['status'], original)
            continue
        if (not expired or not original.get('preview_card_message_id')
                or original.get('delivery_state') != 'delivery_confirmed'
                or not original.get('provider_accepted_at') or not original.get('delivery_confirmed_at')
                or original.get('delivery_ambiguous_at') or original.get('result_payload') is not None
                or original.get('completed_at') or original.get('confirmation_provider_message_id')
                or original.get('confirmation_provider_timestamp')):
            continue
        conversations_for_birth = [r for r in conversations if isinstance(r, dict) and (
                r.get('context_id') == mission or r.get('provider_message_id') == provider
                or (set(r.get('sow_refs') or ()) & {sow, str(preview.get('sow_display_name') or ''),
                     *[str(p[i]) for p in pigs for i in (1,4) if p[0] == sow and p[i]]}
                    and (r.get('facts') or {}).get('farrowing_date') in (None, '', event_date)))]
        if conversations_for_birth:
            if all(r.get('owner_user_id') and r.get('owner_user_id') == r.get('private_chat_id')
                    and r.get('context_id') and r.get('provider_message_id')
                    for r in conversations_for_birth):
                park('current_birth_conversation_present', conversations_for_birth)
            continue
        same_pigs = [p for p in pigs if p[0] == sow]
        if len(same_pigs)!=1 or same_pigs[0][2] != 'Active' or same_pigs[0][3] is not True:
            continue
        current_births = [p for p in litters if p[1] == sow and str(p[2]) == event_date]
        if current_births:
            park('canonical_birth_present', current_births)
            continue
        related = [c for c in claims if c['mission_id'] == mission or c['provider_message_id'] == provider
            or (c['preview_payload'].get('sow_pig_id') == sow
                and str(c['preview_payload'].get('farrowing_date') or '') == event_date)]
        successors = [c for c in related if c != original]
        # One old, never-attempted duplicate recovery may be reported alongside
        # its source. It is preserved, never selected as a new actionable claim.
        if len([c for c in related if c == original]) != 1 or len(successors)>1:
            continue
        if any(not (c['mission_id'].startswith(mission + '-RECOVERY-')
                and c['owner_user_id']==owner and c['private_chat_id']==chat
                and c['provider_message_id']==provider and c['preview_payload']==preview
                and c['preview_digest']==original['preview_digest'] and c['status']=='active'
                and c['created_at'] >= original['created_at']
                and datetime.fromisoformat(c['expires_at']) < now
                and c.get('delivery_state') in (None, 'claim_created')
                and all(c.get(k) is None for k in (
                    'preview_card_message_id','delivery_attempt_id','delivery_attempted_at',
                    'provider_accepted_at','delivery_confirmed_at','delivery_ambiguous_at',
                    'delivery_result','confirmation_provider_message_id',
                    'confirmation_provider_timestamp','completed_at','result_payload')))
                for c in successors):
            # A uniquely attributable later claim transfers attention to its
            # owning journey; a foreign/ambiguous claim cannot grant a handoff.
            current_owner = current_farrowing_review_owner()
            if len(successors)==1:
                successor = successors[0]
                if (successor['owner_user_id'] in {owner, current_owner}
                        and successor['private_chat_id'] == successor['owner_user_id']
                        and successor['preview_payload'].get('sow_pig_id') == sow
                        and str(successor['preview_payload'].get('farrowing_date') or '') == event_date
                        and successor['preview_digest'] == canonical_preview_digest(
                            FARROWING_KIND, successor['preview_payload'])
                        and successor['created_at'] >= original['created_at']):
                    park('later_claim_requires_owning_reconciliation', successor)
            continue
        counts = preview.get('counts') or {}
        names = ('total_born','born_alive','stillborn','mummified','died_after_live_birth')
        if not isinstance(counts, dict) or any(type(counts.get(n)) is not int or not 0 <= counts[n] <= 100 for n in names):
            continue
        if (counts['total_born'] != counts['born_alive'] + counts['stillborn'] + counts['mummified']
                or counts['died_after_live_birth'] > counts['born_alive']):
            continue
        label = str(same_pigs[0][4] or preview.get('sow_display_name') or sow)
        if len(label)>120:
            continue
        candidate = _candidate(key, 'HERDMASTER', 'due',
            sorted(expected) + [binding, 'retained_farrowing_context:' + _farrowing_digest(related),
                'canonical_effect:none', 'owner_authorization:fresh_farrowing_report_required'],
            ['fresh_authenticated_owner_farrowing_report'],
            f'Historical UNCONFIRMED farrowing report for {label} on {event_date}: '
            f"total born {counts['total_born']}, born alive {counts['born_alive']}, "
            f"stillborn {counts['stillborn']}, mummified {counts['mummified']}, "
            f"died after live birth {counts['died_after_live_birth']}. "
            'The older report from the farm reporter is retained. This birth has not been recorded.',
            'Owner review required: send the verified sow, date and birth counts, or corrections, '
            'here. Then review the confirmation before saving. This notice has no approval buttons '
            'and does not record the birth.',
            now + timedelta(minutes=30), task_class='protected_owner_decision',
            message_family=FARROWING_REVIEW_FAMILY, owner_question_eligible=True,
            irreducible_owner_exception=True)
        candidate['_farrowing_review'] = {'label':label,'date':event_date,'counts':counts}
        result.append(candidate)
    return result


def _farrowing_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def current_farrowing_review_owner():
    """Resolve the configured owner, never the first allowlisted recipient."""
    import os
    from modules.oom_sakkie.family_access import _owner_id, resolve_family_principal
    owner = _owner_id(os.environ)
    allowed = {s.strip() for s in os.getenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS', '').split(',')}
    parsed = {'telegram_user_id':owner,'telegram_chat_id':owner,'telegram_chat_type':'private'}
    return owner if owner and owner in allowed and resolve_family_principal(parsed, os.environ).is_owner else ''


def build_retained_farrowing_owner_review(case, *, now=None, deadline_monotonic=None):
    """Revalidate the durable exact case immediately before informational delivery."""
    from modules.oom_sakkie.manager_case_sources import _retained_herd_report_recovery_candidates
    from modules.oom_sakkie.general_manager_worker import normalize_candidate
    if deadline_monotonic is not None and time.monotonic()+6 >= deadline_monotonic:
        return _contained('manager_cycle_deadline_deferred')
    now = now or datetime.now(timezone.utc)
    try:
        candidates = _retained_herd_report_recovery_candidates(now, claimed_cases=[dict(case)],
            deadline_monotonic=deadline_monotonic, delivery_case=case)
        normalized = [normalize_candidate(c, now=now) for c in candidates]
        if (len(normalized)!=1 or normalized[0]['evidence_digest'] != case.get('evidence_digest')
                or normalized[0].get('message_family') != FARROWING_REVIEW_FAMILY
                or not current_farrowing_review_owner()):
            return _contained('retained_farrowing_owner_review_binding_changed')
        row = normalized[0]
        import os
        from modules.oom_sakkie.family_access import resolve_family_principal
        owner = current_farrowing_review_owner()
        principal = resolve_family_principal({'telegram_user_id':owner,
            'telegram_chat_id':owner,'telegram_chat_type':'private'}, os.environ)
        language = principal.language
        facts = candidates[0]['_farrowing_review']
        counts, label, day = facts['counts'], html.escape(facts['label']), facts['date']
        if language == 'af':
            answer = (f'<b>HERDMASTER — EIENAAR SE HERSIENING</b>\n\n'
                f'Historiese ONBEVESTIGDE werpselverslag vir {label} op {day}: '
                f"totaal gebore {counts['total_born']}, lewend gebore {counts['born_alive']}, "
                f"doodgebore {counts['stillborn']}, gemummifiseer {counts['mummified']}, "
                f"dood na lewende geboorte {counts['died_after_live_birth']}.\n\n"
                'Die ouer verslag van die plaasverslaggewer is behou. Geen geboorte is hiermee aangeteken nie.\n\n'
                'Stuur asseblief die geverifieerde sog, datum en geboortegetalle, of regstellings, hier. '
                'Hersien daarna die bevestiging voordat dit gestoor word. Hierdie kennisgewing het '
                'geen goedkeuringsknoppies nie en teken nie die geboorte aan nie.')
        else:
            answer = ('<b>HERDMASTER — OWNER REVIEW</b>\n\n' + html.escape(row['summary'])
                + '\n\n' + html.escape(row['next_action']))
        return {'success':True, 'status':'retained_farrowing_owner_attention',
            'answer':answer, 'recipient_language':language,
            'recipient_render_contract':'specialist_structured_recipient_v1',
            'result_digest':row['evidence_digest'], 'writes_farm_data':False}
    except Exception as exc:
        from modules.oom_sakkie.bounded_postgres_read import is_database_unavailable
        if isinstance(exc, (ValueError, RuntimeError, OSError)) or is_database_unavailable(exc):
            return _contained('retained_farrowing_owner_review_unavailable')
        raise


def _mortality(provider_ids, refs, case, deadline_monotonic=None):
    claims = []
    payloads, failure = _validated_report_case(case, provider_ids, claims_out=claims)
    if failure:
        return _contained(failure)
    payload = payloads[0]
    owner, chat = payload["owner_user_id"], payload["chat_id"]
    if (payload.get("retained_repreview") or {}).get("owner_requested_continuation") is True:
        from modules.oom_sakkie.retained_mortality_continuation import resume_requested_preview
        return resume_requested_preview(payload, case)
    from modules.oom_sakkie import retained_mortality_orphan_recovery as orphan
    from modules.oom_sakkie.herdmaster_source_transaction import SourceConflict
    orphan_checked = orphan.prefer_transactional_preparation(payload, claims)
    if orphan_checked:
        try:
            return orphan.prepare(payload, case, deadline_monotonic=deadline_monotonic)
        except orphan.ExactClaimRequiresReuse:
            # Its read-only attempt rolled back. Rebuild normally and use the
            # existing audited renewal; never retry replacement from this path.
            pass
        except SourceConflict as exc:
            return _contained(str(exc))
    target = next((value.split(":", 1)[1] for value in refs
                   if value.startswith("pig:") and ":" in value), "")
    from modules.oom_sakkie.herdmaster_health_loss_runtime import (
        load_canonical_health_loss_evidence,
    )
    bridge = payload.get("retained_repreview") or {}
    prepared = (payload.get("status") == "preview_ready"
        and str(payload.get("event_phase") or "").startswith("retained_preview_generated:")
        and bridge.get("contract_version") == "retained_health_preview_v1")
    provider = str(payload.get("provider_message_id") or "")
    if prepared:
        # A rendering hint only. The one fresh canonical rebuild moves to the
        # protected provider gate; no stored evidence can admit a send.
        preview = deepcopy(payload["preview"])
        evidence = {"evidence_generation": bridge.get("claim_evidence_generation")}
    else:
        evidence = load_canonical_health_loss_evidence()
        provider = str(payload.get("provider_message_id") or "")
        preview = _prepare_retained_report(payload, evidence)
    identity = dict((preview.get("evaluator") or {}).get("identity") or {})
    reassessed = "retained_identity_reassessment:required" in refs
    if reassessed and (identity.get("resolved") is not True
            or (preview.get("evaluator") or {}).get("event_family") != "found_dead"
            or {v for v in refs if v.startswith("tag:")} != {"tag:" + str(identity.get("tag_number") or "")}):
        return _contained("retained_mortality_exact_identity_unproven")
    if not target or str(identity.get("pig_id") or "") != target:
        return _contained("retained_mortality_exact_identity_unproven")
    if int(preview.get("question_count") or 0):
        return {**_contained("retained_mortality_removed_disposal_required"),
                "missing_facts": ["removed_disposal"],
                "answer": str(preview.get("owner_text") or "")}
    preview = _unchanged_retained_preview(payload, preview,
        evidence_generation=str(evidence.get("evidence_generation") or ""))
    binding = dict(preview.get("confirmation_binding") or {})
    operation = str(binding.get("operation_id") or "")
    if preview.get("success") is not True or not operation:
        return _contained("retained_mortality_preview_unproven")
    mission = "OOM-HERDMASTER-MORTALITY-" + hashlib.sha256(
        (provider + "|" + target + "|" + operation).encode()).hexdigest()[:24].upper()
    request = dict(action_kind="mortality", owner_user_id=owner,
        private_chat_id=chat, mission_id=mission, provider_message_id=provider,
        evidence_generation=str(evidence.get("evidence_generation") or ""),
        preview_payload={"operation_id": operation,
            "preview_sha256": str(binding.get("preview_sha256") or ""),
            "identity": identity,
            "event_family": str((preview.get("evaluator") or {}).get("event_family") or ""),
            "effect_kind": "mortality"})
    from modules.oom_sakkie.herdmaster_source_transaction import SourceConflict
    try:
        claim, failure = _same_or_new_claim(payloads, claims, deadline_monotonic, staged_mortality=prepared, **request)
    except SourceConflict as exc:
        return _contained(str(exc))
    if failure:
        if (failure == "retained_claim_current_preview_mismatch" and not orphan_checked
                and retained_identity_reassessment_needed(payload)):
            from modules.oom_sakkie.retained_mortality_orphan_recovery import prepare
            from modules.oom_sakkie.herdmaster_source_transaction import SourceConflict
            try:
                return prepare(payload, case, deadline_monotonic=deadline_monotonic)
            except SourceConflict as exc:
                return _contained(str(exc))
        return _contained(failure)
    from modules.oom_sakkie.herdmaster_health_loss_runtime import persist_retained_health_loss_preview
    if not prepared:
        persisted = persist_retained_health_loss_preview(payload, preview,
            source_binding=retained_report_binding(payloads), claim=claim, claim_request=request)
        if persisted.get("success") is not True:
            return _contained(persisted.get("status") or "retained_preview_lifecycle_unproven")
        # Creating a new preview consumes its fresh validation budget. A later
        # normal cycle stages it and validates once at the actual effect gate.
        return {"success": True, "status": "retained_mortality_prepared_not_presented",
            "suppress_owner_delivery": True, "telegram_sends": 0, "telegram_edits": 0,
            "writes_farm_data": False, "protected_actions_performed": False}
    from modules.oom_sakkie.retained_mortality_presentation import stage
    policy = stage(payload, request, claim, case) if claim.get("presentation_window_pending") else None
    persisted = {"_retained_mortality_policy": policy} if policy is not None else {}
    from modules.oom_sakkie.protected_action_claims import protected_card_mission_id
    return _protected({**persisted, "success": True, "status": "preview_ready",
        "tool_used": "herdmaster_health_loss_preview",
        "answer": str(preview.get("owner_text") or ""), "mission_id": mission,
        "recipient_render_contract": "herdmaster_health_loss_recipient_v1",
        "recipient_language": payload.get("output_language") or "af",
        "retained_delivery_context": _delivery_context(payload),
        "card_mission_id": protected_card_mission_id(mission, claim["preview_digest"]),
        "callback_token": claim["callback_token"],
        "preview_digest": claim["preview_digest"], "action_kind": "mortality",
        "reply_markup": {"inline_keyboard": [[
            {"text": "Confirm and record", "callback_data": f"oompa:{claim['callback_token']}:confirm"},
            {"text": "Change", "callback_data": f"oompa:{claim['callback_token']}:change"},
            {"text": "Cancel", "callback_data": f"oompa:{claim['callback_token']}:cancel"}]]}})



def _unchanged_retained_preview(source, current, *, evidence_generation):
    """Keep an existing exact preview across the legacy clock-hash correction.

    Fresh evaluation must reproduce the *whole* stored preview after replacing
    only its generated operation identity and recomputing its preview digest.
    No claim, expiry, lifecycle or confirmation is changed here. The caller must
    still pass the existing exact claim, delivery and lifecycle readback gates.
    Missing retained previews cannot recover a legacy claim this way.
    """
    prior = source.get("preview") or {}
    bridge = source.get("retained_repreview") or {}
    operation = str(source.get("operation_id") or "")
    if (source.get("status") != "preview_ready"
            or not str(source.get("event_phase") or "").startswith("retained_preview_generated:")
            or bridge.get("contract_version") != "retained_health_preview_v1"
            or not evidence_generation or bridge.get("claim_evidence_generation") != evidence_generation
            or not operation or current.get("success") is not True
            or current.get("confirmation_ready") is not True
            or (prior.get("confirmation_binding") or {}).get("operation_id") != operation):
        return current
    candidate = deepcopy(current)
    evaluated = candidate["evaluator"]
    evaluated["operation_id"] = operation
    evaluated["preview"]["operation_id"] = operation
    digest = hashlib.sha256(json.dumps(evaluated["preview"], sort_keys=True,
        separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
    evaluated["preview_sha256"] = digest
    for binding in (evaluated["confirmation_binding"], candidate["confirmation_binding"]):
        binding["operation_id"] = operation
        binding["preview_sha256"] = digest
    return prior if candidate == prior else current


def _litter_preview_text(payload, language):
    af = str(language).casefold().startswith("af")
    litter = html.escape(str(payload["litter_id"]))
    piglets = ", ".join(html.escape(str(value)) for value in payload["pig_ids"])
    date = html.escape(str(payload["event_date"]))
    if af:
        return (f"<b>HERDMASTER - BESKERMDE VOORSKOU</b>\nWerpsel {litter}; "
            f"{payload['count']} kleintjies dood op {date}.\nPresiese kleintjies: {piglets}. "
            "Rede: Onbekend. Bevestig slegs indien korrek. Niks is nog aangeteken nie.")
    return (f"<b>HERDMASTER - PROTECTED PREVIEW</b>\nLitter {litter}; "
        f"{payload['count']} piglets died on {date}.\nExact piglets: {piglets}. "
        "Reason: Unknown. Confirm only if correct. Nothing has been recorded yet.")


def _delivery_context(row):
    return {"telegram_user_id": str(row["owner_user_id"]),
        "telegram_chat_id": str(row["chat_id"]),
        "telegram_chat_type": "private",
        "provider_message_id": str(row["provider_message_id"]),
        "provider_timestamp": str(row.get("provider_timestamp") or ""),
        "output_language": row.get("output_language") or "af"}


def retained_recipient_authorized(parsed):
    """Apply the existing gateway/family policy to the exact retained recipient."""
    import os
    from modules.oom_sakkie.telegram_gateway import _allowed_user_ids
    from modules.oom_sakkie.family_access import resolve_family_principal, authorize_family_message
    allowed = _allowed_user_ids(os.environ)
    if not allowed or str(parsed.get("telegram_user_id") or "") not in allowed:
        return False
    principal = resolve_family_principal(parsed, os.environ)
    return authorize_family_message(principal, parsed, capability="mortality_confirmation").allowed


def _same_or_new_claim(rows, claims, deadline_monotonic, *, staged_mortality=False, **requested):
    """Reuse the exact claim; a never-attempted expiry may renew once with audit."""
    from modules.oom_sakkie.protected_action_claims import create_claim, canonical_preview_digest
    if not all(retained_recipient_authorized(_delivery_context(row)) for row in rows):
        return None, "retained_recipient_not_currently_authorized"
    ids = {str(row["provider_message_id"]) for row in rows}
    missions = {str(row["mission_id"]) for row in rows}
    owner, chat = requested["owner_user_id"], requested["private_chat_id"]
    related = [claim for claim in claims if str(claim[2]) in missions or
        ((str(claim[0]), str(claim[1])) == (owner, chat) and
         (str(claim[3]) in ids or ids.intersection((claim[6] or {}).get("provider_message_ids") or ())))]
    if len(rows) == 1 and (rows[0].get("retained_repreview") or {}).get("orphan_predecessor"):
        from modules.oom_sakkie import herdmaster_source_transaction as source_tx
        from modules.oom_sakkie import retained_mortality_orphan_recovery as orphan
        with connect_bounded_read() as db, db.cursor() as cur:
            history_rows = source_tx.read_history(cur, [rows[0]["mission_id"]])
            source_tx.require_current(history_rows, rows[0])
            full = orphan.read_claims(cur, rows[0])
            current = [c for c in full if c["preview_digest"] == rows[0]["retained_repreview"]["claim_preview_digest"]]
            source_tx.require(len(current) == 1, "retained_orphan_current_claim_missing")
            cur.execute("select clock_timestamp()")
            active, _audit = orphan.validate_lineage(cur, rows[0], full, current[0], cur.fetchone()[0], history_rows)
            source_tx.require(active == current, "retained_orphan_competing_claim")
            related = [c for c in related if (c[7] or {}).get("callback_token") == current[0]["callback_token"]]
    if deadline_monotonic is not None:
        from modules.oom_sakkie.family_message_lifecycle import PROVIDER_DELIVERY_RESERVE_SECONDS
        if time.monotonic() + PROVIDER_DELIVERY_RESERVE_SECONDS >= deadline_monotonic:
            return None, "manager_cycle_deadline_deferred"
    if not related:
        if staged_mortality:
            return None, "retained_mortality_original_claim_missing"
        return create_claim(**requested), ""
    if len(related) != 1 or len(related[0]) != 8:
        return None, "retained_claim_identity_or_delivery_unproven"
    c_owner, c_chat, mission, provider, status, kind, payload, delivery = related[0]
    if not isinstance(delivery, dict):
        return None, "retained_claim_identity_or_delivery_unproven"
    try:
        expires = datetime.fromisoformat(str(delivery.get("expires_at") or "").replace("Z", "+00:00"))
        if expires.tzinfo is None:
            raise ValueError()
    except (ValueError, TypeError):
        return None, "retained_claim_expiry_unproven"
    if status not in {"active", "expired"}:
        return None, "retained_claim_terminal_requires_current_review"
    digest = canonical_preview_digest(kind, payload)
    if ((str(c_owner), str(c_chat), str(mission), str(provider), str(kind)) !=
            (owner, chat, requested["mission_id"], requested["provider_message_id"], requested["action_kind"])
            or payload != requested["preview_payload"]
            or delivery.get("evidence_generation") != requested["evidence_generation"]
            or delivery.get("preview_digest") != digest
            or not delivery.get("callback_token")):
        return None, "retained_claim_current_preview_mismatch"
    if staged_mortality:
        unattempted = (kind == "mortality" and payload.get("effect_kind") == "mortality"
            and delivery.get("delivery_state") in (None, "claim_created", "expired")
            and all(key in delivery and delivery[key] is None for key in _RENEWAL_MARKERS))
        if unattempted:
            # No TTL update here. Full durable histories and canonical facts are
            # reloaded under the source/claim locks by the provider gate.
            return {"callback_token": delivery["callback_token"], "preview_digest": digest,
                "presentation_window_pending": True}, ""
        if status == "expired" or expires <= datetime.now(timezone.utc):
            return None, "retained_claim_attempt_or_terminal_requires_review"
    if status == "expired" or expires <= datetime.now(timezone.utc):
        return _renew_unattempted_claim(rows, delivery, requested)
    state, card = delivery.get("delivery_state"), delivery.get("preview_card_message_id")
    unattempted = state in (None, "claim_created") and not card and all(
        delivery.get(key) is None for key in ("delivery_attempt_id", "delivery_attempted_at",
            "provider_accepted_at", "delivery_confirmed_at", "delivery_ambiguous_at", "delivery_result",
            "result_payload", "confirmation_provider_message_id", "confirmation_provider_timestamp", "completed_at"))
    confirmed = (state == "delivery_confirmed" and bool(card)
        and bool(delivery.get("delivery_attempt_id")) and bool(delivery.get("delivery_attempted_at"))
        and bool(delivery.get("provider_accepted_at")) and bool(delivery.get("delivery_confirmed_at"))
        and delivery.get("delivery_ambiguous_at") is None
        and isinstance(delivery.get("delivery_result"), dict)
        and delivery["delivery_result"].get("success") is True
        and str(delivery["delivery_result"].get("telegram_message_id") or "") == str(card))
    if not (unattempted or confirmed):
        return None, "retained_claim_delivery_outcome_unproven"
    # The existing protected lifecycle owns the final locked check, one provider
    # attempt and binding; an already bound card is only a no-send replay.
    return {"callback_token": delivery["callback_token"], "preview_digest": digest}, ""



_RENEWAL_EVENT = "retained_protected_preview_expiry_renewed"
_RENEWAL_AGGREGATE = "protected_action_claim"
_RENEWAL_MARKERS = ("preview_card_message_id", "delivery_attempt_id", "delivery_attempted_at",
    "provider_accepted_at", "delivery_confirmed_at", "delivery_ambiguous_at", "delivery_result",
    "confirmation_provider_message_id", "confirmation_provider_timestamp", "result_payload", "completed_at")


def _renew_unattempted_claim(rows, delivery, requested):
    """One audited TTL extension, atomically locked; never a provider-attempt retry.

    The caller rebuilt the same preview from current canonical evidence. Recheck
    exact source rows and the complete claim under its lock. A source correction
    versus this transaction is not atomically serialized; lifecycle persistence
    and the genuine callback retain their separate current-binding gates.
    """
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
    from modules.charlie.operational_events import build_event
    from modules.charlie.mission_store import _insert_operational_event
    if not all(retained_recipient_authorized(_delivery_context(row)) for row in rows):
        return None, "retained_recipient_not_currently_authorized"
    token = str(delivery.get("callback_token") or "")
    aggregate = hashlib.sha256(token.encode()).hexdigest()
    source_binding = retained_report_binding(rows)
    failure = "retained_claim_expired_requires_current_review"
    if not token or requested.get("action_kind") not in {"mortality", "herdmaster_record_litter_piglet_deaths"}:
        return None, failure
    try:
        with connect_bounded_rootline_postgres(read_only=False) as db, db.cursor() as cur:
            cur.execute("""select to_jsonb(c),clock_timestamp()
                from app_private.oom_protected_action_claims c where callback_token=%s for update""", (token,))
            value = cur.fetchone()
            if not value:
                return None, failure
            claim, observed_at = value
            digest = canonical_preview_digest(requested["action_kind"], requested["preview_payload"])
            if (not isinstance(claim, dict) or any(claim.get(key) != requested[key] for key in (
                    "action_kind", "owner_user_id", "private_chat_id", "mission_id",
                    "provider_message_id", "evidence_generation", "preview_payload"))
                    or claim.get("preview_digest") != digest or digest != delivery.get("preview_digest")
                    or claim.get("status") not in {"active", "expired"}
                    or claim.get("delivery_state") not in {None, "claim_created", "expired"}
                    or any(claim.get(key) is not None for key in _RENEWAL_MARKERS)):
                return None, failure
            expires = datetime.fromisoformat(str(claim.get("expires_at") or "").replace("Z", "+00:00"))
            prior_expiry = datetime.fromisoformat(str(delivery.get("expires_at") or "").replace("Z", "+00:00"))
            if expires.tzinfo is None or expires != prior_expiry or expires > observed_at:
                return None, failure
            cur.execute("""select event_id from public.operational_events
                where aggregate_type=%s and aggregate_id=%s limit 1""", (_RENEWAL_AGGREGATE, aggregate))
            if cur.fetchone():
                return None, "retained_claim_renewal_already_consumed"
            cur.execute("""select callback_token from app_private.oom_protected_action_claims
                where mission_id=%s and status='active' and callback_token<>%s limit 1""",
                (requested["mission_id"], token))
            if cur.fetchone():
                return None, "retained_claim_other_active_attempt"
            current = read_retained_health_reports(cur, [row["provider_message_id"] for row in rows])
            resolved, reason = resolve_retained_health_reports(current,
                [row["provider_message_id"] for row in rows], retain_existing_attempts=True)
            if reason or resolved != rows or retained_report_binding(resolved) != source_binding:
                return None, "retained_claim_source_changed_before_renewal"
            if not all(retained_recipient_authorized(_delivery_context(row)) for row in rows):
                return None, "retained_recipient_not_currently_authorized"
            cur.execute("""update app_private.oom_protected_action_claims
                set expires_at=clock_timestamp()+interval '30 minutes',status='active',delivery_state='claim_created'
                where callback_token=%s and expires_at=%s and status=%s
                returning expires_at""", (token, expires, claim["status"]))
            renewed = cur.fetchone()
            if cur.rowcount != 1 or not renewed:
                raise RuntimeError("retained_claim_renewal_compare_and_set_failed")
            event_key = "retained-preview-renewal:" + aggregate + ":" + expires.isoformat()
            audit = {"contract_version": "retained_preview_renewal_v1", "claim_hash": aggregate,
                "source_binding": source_binding, "mission_id": requested["mission_id"],
                "preview_digest": digest, "evidence_generation": requested["evidence_generation"],
                "old_expires_at": expires.isoformat(), "new_expires_at": renewed[0].isoformat(),
                "old_status": claim["status"], "old_delivery_state": claim.get("delivery_state"),
                "new_status": "active", "new_delivery_state": "claim_created",
                "provider_attempts": 0, "farm_writes": 0, "one_time_only": True}
            ready = build_event({"event_id": "OOM-RETAINED-RENEWAL-" + aggregate[:32].upper(),
                "idempotency_key": event_key, "event_type": _RENEWAL_EVENT, "domain": "approvals",
                "aggregate_type": _RENEWAL_AGGREGATE, "aggregate_id": aggregate,
                "source_system": "oom_sakkie", "authority_tier": "bounded_auto",
                "privacy_class": "owner_private", "actor_type": "system",
                "actor_id": "retained_preview_recovery", "correlation_id": requested["mission_id"],
                "occurred_at": observed_at.isoformat(), "recorded_at": observed_at.isoformat(),
                "payload": audit, "provenance": {"source_ref": source_binding}})
            if ready.get("accepted") is not True or not _insert_operational_event(cur, ready["event"]):
                raise RuntimeError("retained_claim_renewal_audit_unproven")
            cur.execute("""select c.expires_at,c.status,c.delivery_state,e.payload_json
                from app_private.oom_protected_action_claims c join public.operational_events e
                  on e.idempotency_key=%s where c.callback_token=%s""", (event_key, token))
            if cur.fetchone() != (renewed[0], "active", "claim_created", audit):
                raise RuntimeError("retained_claim_renewal_readback_unproven")
        return {"callback_token": token, "preview_digest": digest,
                "retained_unattempted_expiry_renewed": True}, ""
    except Exception:
        # Transaction context rolls back the expiry CAS and audit together.
        return None, "retained_claim_renewal_persistence_unproven"


def _protected(result):
    value = dict(result or {})
    if value.get("success") is True and value.get("callback_token"):
        return {**value, "confirmation_required": True, "writes_farm_data": False}
    return _contained(str(value.get("status") or "retained_protected_repreview_unproven"))


def execute_claimed_litter_piglet_deaths(claimed, parsed):
    """Execute only an already callback-claimed, exact piglet selection."""
    preview = dict(claimed.get("preview_payload") or {})
    if preview.get("contract_version") != "herdmaster_litter_piglet_deaths_v1":
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
        return {"success": True, "status": "litter_piglet_deaths_recovered_from_canonical",
            "piglet_count": len(preview.get("pig_ids") or ()),
            "pig_ids": list(preview.get("pig_ids") or ()), "rows_updated": 0,
            "answer": "The exact piglet deaths were already recorded; protected completion was recovered without another mutation.",
            "writes_farm_data": False, "reply_markup": {"inline_keyboard": []}}, 200
    if readback == "partial":
        return {"success": False, "status": "litter_piglet_deaths_partial_readback_recovery_required",
                "writes_farm_data": False, "recovery_required": True}, 503
    result, status = service.mark_litter_piglets_dead(preview.get("litter_id"),
        preview.get("event_date"), preview.get("reason"), pig_ids=preview.get("pig_ids") or (),
        changed_by="oom_sakkie:" + operation_id, dry_run=False)
    if result.get("success") is True:
        result = {**result, "answer": f"Recorded {result.get('piglet_count')} piglet deaths for Linda's litter exactly once.",
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


def _contained(status):
    return {"success": False, "status": status, "suppress_owner_delivery": True,
            "telegram_sends": 0, "writes_farm_data": False, "recovery_required": True}
