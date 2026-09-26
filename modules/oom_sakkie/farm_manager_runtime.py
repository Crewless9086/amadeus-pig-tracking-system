"""Authenticated entrypoint for one consolidated Oom Sakkie manager round."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import os
from typing import Any, Callable
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
import html

from modules.oom_sakkie.farm_manager_loop import (
    Authority, Provenance, SpecialistAvailability, SpecialistResult,
    SpecialistWorkItem, WorkState, build_family_brief,
)
from modules.oom_sakkie.gateway_authority import bind_gateway_owner_authority
from modules.oom_sakkie.herdmaster_management_runtime import _load_active_lifecycles, _load_observations
from modules.pig_weights.herdmaster_whole_herd_packet import build_whole_herd_packet
from modules.pig_weights.mating_routes import load_current_breeding_operating_loop
from modules.telemetry.rootline_specialist_result import build_current_rootline_specialist_result
from modules.pig_weights.herdmaster_daily_manager_evidence import load_daily_manager_evidence
from modules.oom_sakkie.herdmaster_daily_manager_adapter import consume_daily_manager_evidence
from modules.oom_sakkie.bounded_postgres_read import connect_bounded_postgres, connect_bounded_read
from modules.oom_sakkie.herdmaster_mortality_runtime import consume_current_mortality_packet
from zoneinfo import ZoneInfo

CONTRACT_VERSION = "oom_sakkie_farm_manager_round_v5"
EVENT_SOURCE = "oom_sakkie_farm_manager_round"
SPECIALIST_BUDGET_SECONDS = 12.0
_SPECIALIST_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="oom-manager")
_HERD_EVIDENCE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="oom-herd-evidence")
_ROOTLINE_REFRESH_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="oom-rootline-refresh")
_MANAGER_PHRASES = (
    "what needs our attention", "what needs attention", "farm status",
    "farm priorities", "morning brief", "management plan", "today's work",
    "todays work", "farm-management brief", "farm management brief",
)
_DOMAINS = {
    "herd": ("pig", "herd", "welfare", "breed", "mating", "weigh"),
    "rootline": ("irrigation", "water", "energy", "power", "solar"),
    "sales": ("sale", "sales", "customer", "enquir"),
    "marketing": ("marketing", "facebook", "media", "post"),
}
ZERO_AUTHORITY = {
    "writes_farm_data": False, "writes_weights": False, "writes_mating": False,
    "sends_customers": False, "publishes": False, "hardware_commands": False,
    "protected_actions_performed": False,
}


def is_farm_manager_round(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    if any(phrase in normalized for phrase in _MANAGER_PHRASES):
        return True
    mentioned = sum(any(term in normalized for term in terms) for terms in _DOMAINS.values())
    return mentioned >= 2


def handle_farm_manager_round(parsed: dict[str, Any], authority: Any, *, now=None,
                              loaders: dict[str, Callable] | None = None,
                              event_store=None, weighing_loader=None,
                              specialist_budget_seconds=SPECIALIST_BUDGET_SECONDS,
                              clock=None, case_loader=None):
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), dict) else {}
    query = semantic.get("read_query") or {}
    if query.get("kind") == "farm_brief":
        query = {}
    if query.get("kind") == "animal_status":
        return {"handled": False}, 200
    if (semantic and semantic.get("needs_clarification")
            and not (query and _enquiry_clarification(query, str(semantic.get("language") or "en")))):
        return {"handled": False}, 200
    if query and (semantic.get("message_kind") not in {"question", "request"}
                  or float(semantic.get("confidence") or 0) < .8):
        return {"handled": False}, 200

    if semantic:
        if semantic.get("domain") != "manager_round":
            return {"handled": False}, 200
    elif not is_farm_manager_round(parsed.get("text", "")):
        return {"handled": False}, 200
    # The durable manager lifecycle is provider-bound. Legacy/local callers
    # without Telegram chronology continue through the existing read-only tool.
    if not parsed.get("provider_message_id") or not parsed.get("provider_timestamp"):
        return {"handled": False}, 200
    explicit_now = now is not None
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = (now or clock()).astimezone(timezone.utc)
    owner = str(parsed.get("telegram_user_id") or "")
    chat = str(parsed.get("telegram_chat_id") or "")
    bound = bind_gateway_owner_authority(authority, "farm_manager_round")
    if not bound or bound.owner_user_id != owner or bound.private_chat_id != chat:
        return {"handled": False}, 200
    if query and bound.principal_role != "owner":
        return {"handled": False}, 200
    binding = {
        "owner": owner, "chat": chat,
        "provider_message_id": str(parsed.get("provider_message_id") or ""),
        "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "content_digest": _digest(str(parsed.get("text") or "")),
        "contract_version": CONTRACT_VERSION,
    }
    mission_id = "OOM-FARM-ROUND-" + _digest({"owner": owner, "chat": chat,
        "provider_message_id": binding["provider_message_id"]}).upper()[:24]
    store = event_store or _event_store
    try:
        prior = store("load", mission_id, None)
    except Exception:
        return {"handled": True, "success": False,
            "status": "farm_manager_round_persistence_unavailable",
            "mission_id": mission_id, **ZERO_AUTHORITY}, 503
    material_recomposition = None
    if prior:
        prior_binding = prior.get("binding") or {}
        if prior_binding != binding and not _material_recomposition_allowed(prior, binding):
            return {"handled": True, "success": False,
                "status": "farm_manager_provider_binding_conflict",
                "mission_id": mission_id, **ZERO_AUTHORITY}, 409
        if prior_binding != binding:
            material_recomposition = {
                "from_contract": str(prior_binding.get("contract_version") or ""),
                "to_contract": CONTRACT_VERSION,
                "provider_binding_digest": _digest(binding),
            }
        if prior_binding == binding:
            preserved = prior.get("result") or {}
            if prior.get("mortality_packet") and not _append_mortality_receipt(
                    prior["mortality_packet"], authority, owner, now,
                    str(semantic.get("language") or "en")):
                return {"handled": True, "success": False,
                    "status": "farm_manager_mortality_receipt_unavailable",
                    "mission_id": mission_id, **ZERO_AUTHORITY}, 503
            return {**preserved, "status": "farm_manager_round_replay_suppressed"}, 200
    clarification = _enquiry_clarification(query, str(semantic.get("language") or "en")) if query else ""
    providers = loaders or {
        "herdmaster": lambda: _load_herdmaster(authority, owner, now,
            language=str(semantic.get("language") or "en")),
        "rootline": lambda: _load_rootline(now, str(semantic.get("language") or "en")),
        "sam": lambda: _missing("sam", now),
        "beacon": lambda: _missing("beacon", now),
    }
    if clarification:
        providers = {name: (lambda name=name: _missing(name, now)) for name in ("herdmaster", "rootline", "sam", "beacon")}
    results = []
    exceptions = {}
    specialists = ((str(query["specialist"]).lower(),)
        if query.get("kind") == "specialist_detail" and query.get("specialist")
        else ("herdmaster", "rootline", "sam", "beacon"))
    # Independent specialist evidence loads run concurrently so one slow source
    # cannot consume the synchronous Telegram delivery budget. HERDMASTER may
    # append only its existing idempotent internal consumption audit trace.
    futures = {specialist: _SPECIALIST_EXECUTOR.submit(providers[specialist]) for specialist in specialists}
    done, pending = wait(tuple(futures.values()), timeout=max(0.01, float(specialist_budget_seconds)))
    try:
        for specialist in specialists:
            future = futures[specialist]
            try:
                if future not in done:
                    raise TimeoutError("specialist_delivery_budget_exceeded")
                result = future.result()
                if not isinstance(result, SpecialistResult):
                    raise ValueError("malformed specialist result")
            except Exception:
                result = _missing(specialist, now, SpecialistAvailability.CONTAINED)
                exceptions[specialist] = "specialist_result_unavailable"
            results.append(result)
    finally:
        for future in pending:
            future.cancel()
    if (material_recomposition
            and material_recomposition["from_contract"] == "oom_sakkie_farm_manager_round_v4"
            and not _mortality_recomposition_supported(prior, results[0])):
        return {"handled": True, "success": False,
            "status": "farm_manager_material_recomposition_evidence_unavailable",
            "mission_id": mission_id, **ZERO_AUTHORITY}, 409
    # HERDMASTER's typed daily evidence owns production cohort eligibility.
    # The retired argument remains API-compatible but is never consulted.
    weighing_worklist = ()
    # A live specialist result is normally generated after manager invocation.
    # Validate freshness against composition time, not the earlier inbound or
    # invocation instant. Explicit test/replay clocks remain deterministic.
    composition_now = now if explicit_now else clock().astimezone(timezone.utc)
    brief = build_family_brief(results, now=composition_now)
    try:
        answer = (_render_enquiry(brief, query,
                    language=str(semantic.get("language") or "en"), now=composition_now,
                    case_loader=case_loader)
                  if query else _render(brief, language=str(semantic.get("language") or "en")))
    except ValueError:
        return {"handled": True, "success": False,
            "status": "farm_manager_round_render_contained",
            "mission_id": mission_id, **ZERO_AUTHORITY}, 503
    result_digest = _digest({
        "binding": binding, "answer": answer,
        "specialists": [(r.specialist, r.result_id, r.observed_at.isoformat(), r.availability.value) for r in results],
    })
    output = {
        "handled": True, "success": True, "status": "farm_manager_round_ready",
        "specialist_identity": "OOM_SAKKIE", "mission_id": mission_id,
        "card_mission_id": mission_id, "answer": answer, "binding": binding,
        "result_digest": result_digest, "specialist_exceptions": exceptions,
        "specialist_gaps": dict(brief.specialist_gaps),
        "action_count": min(3, len(brief.queue)),
        "question_count": (int(bool(clarification)) if query else min(1, sum(len(values) for values in brief.questions.values()))),
        "clarification_question": (clarification if query else next((q for values in brief.questions.values() for q in values), "")),
        "read_only": True, "writes_performed": False,
        "recipient_render_contract": "canonical_read_answer_v1",
        "recipient_language": str(semantic.get("language") or "en"),
        "reassessment_triggers": [f.follow_up_id for f in brief.follow_ups],
        "weighing_worklist": weighing_worklist,
        "material_recomposition_authority": material_recomposition,
        "herdmaster_mortality_fingerprints": _mortality_fingerprints(brief),
        **ZERO_AUTHORITY,
    }
    mortality_packet = None if query else _mortality_packet(brief)
    recorded = store("record", mission_id, {"binding": binding, "result": output,
        "mortality_packet": mortality_packet})
    if not isinstance(recorded, dict) or recorded.get("success") is not True:
        return _persistence_failure(parsed, mission_id), 503
    if recorded.get("created") is False:
        winner = store("load", mission_id, None) or {}
        if (winner.get("binding") or {}) != binding:
            return {"handled": True, "success": False,
                "status": "farm_manager_provider_binding_conflict",
                "mission_id": mission_id, **ZERO_AUTHORITY}, 409
        if winner.get("mortality_packet") and not _append_mortality_receipt(
                winner["mortality_packet"], authority, owner, composition_now,
                str(semantic.get("language") or "en")):
            return {"handled": True, "success": False,
                "status": "farm_manager_mortality_receipt_unavailable",
                "records_audit_trace": True, "mission_id": mission_id, **ZERO_AUTHORITY}, 503
        return {**(winner.get("result") or {}),
                "status": "farm_manager_round_replay_suppressed"}, 200
    if mortality_packet and not _append_mortality_receipt(mortality_packet,
            authority, owner, composition_now, str(semantic.get("language") or "en")):
        return {"handled": True, "success": False,
            "status": "farm_manager_mortality_receipt_unavailable",
            "records_audit_trace": True, "mission_id": mission_id, **ZERO_AUTHORITY}, 503
    return output, 200


def _load_herdmaster(authority, owner, now, language="en"):
    return _project_herdmaster_snapshot(
        _load_herdmaster_snapshot(owner, now), authority, owner, now, language)


def _load_herdmaster_snapshot(owner, now):
    """Read one immutable canonical HERDMASTER evidence snapshot."""
    owners = tuple(dict.fromkeys(str(value) for value in
        (owner if isinstance(owner, (tuple, list, set)) else (owner,)) if str(value)))
    futures = {
        "canonical": _HERD_EVIDENCE_EXECUTOR.submit(load_current_breeding_operating_loop),
        "daily": _HERD_EVIDENCE_EXECUTOR.submit(load_daily_manager_evidence,
            analysis_date=now.astimezone(ZoneInfo("Africa/Johannesburg")).date(),
            owner_user_ids=owners),
    }
    for actor in owners:
        futures["observations:" + actor] = _HERD_EVIDENCE_EXECUTOR.submit(_load_observations, actor)
        futures["active:" + actor] = _HERD_EVIDENCE_EXECUTOR.submit(_load_manager_lifecycles, actor)
    base_names = ("canonical", *["observations:" + actor for actor in owners],
                  *["active:" + actor for actor in owners])
    done, pending = wait(tuple(futures.values()), timeout=9.0)
    try:
        if any(futures[name] not in done for name in base_names):
            raise TimeoutError("herd_evidence_deadline")
        canonical = futures["canonical"].result()
        observations = _provenance_union(
            (actor, futures["observations:" + actor].result()) for actor in owners)
        active = _provenance_union(
            (actor, futures["active:" + actor].result()) for actor in owners)
        active_current = tuple(row for row in active if str(row.get("state") or "").casefold()
            not in {"completed", "closed", "handled"})
        # Reproductive and welfare evidence remains in the existing whole-herd
        # result. Weekly cohort biology comes only from the versioned producer.
        snapshot = {"canonical": canonical, "observations": observations,
                    "active": tuple(active), "active_current": active_current}
    except Exception:
        try:
            active = _provenance_union((actor,
                futures["active:" + actor].result(timeout=0)
                if futures["active:" + actor] in done else ()) for actor in owners)
        except Exception:
            active = ()
        active_current = tuple(row for row in active if str(row.get("state") or "").casefold()
            not in {"completed", "closed", "handled"})
        return {"failed": True, "active": tuple(active), "active_current": active_current}
    else:
        try:
            packet = futures["daily"].result() if futures["daily"] in done else None
        except Exception:
            packet = None
        snapshot["daily_packet"] = packet
        return snapshot
    finally:
        for future in pending:
            future.cancel()


def _provenance_union(actor_rows):
    """Deduplicate identical actor-scoped rows without losing attribution."""
    values = {}
    for actor, rows in actor_rows:
        for raw in rows or ():
            row = dict(raw) if isinstance(raw, dict) else raw
            digest = _digest(row)
            if digest not in values:
                if isinstance(row, dict):
                    row = {**row, "attributable_actor_ids": [str(actor)]}
                values[digest] = row
            elif isinstance(values[digest], dict):
                actors = set(values[digest].get("attributable_actor_ids") or ())
                actors.add(str(actor)); values[digest]["attributable_actor_ids"] = sorted(actors)
    return tuple(values[key] for key in sorted(values))


def _project_herdmaster_snapshot(snapshot, authority, owner, now, language="en"):
    if snapshot.get("failed"):
        return _active_welfare_result(snapshot.get("active_current") or (), now, language)
    active = snapshot.get("active") or ()
    herd = _whole_herd_specialist_result(snapshot["canonical"],
        snapshot["observations"], snapshot.get("active_current") or (), now, language)
    daily = consume_daily_manager_evidence(snapshot.get("daily_packet"), observed_at=now,
        active_lifecycles=active, language=language)
    combined_id = herd.result_id + ":" + daily.result_id
    items = tuple(replace(item, provenance=replace(item.provenance,
                  result_id=combined_id))
                  for item in tuple(daily.work_items) + tuple(herd.work_items))
    return replace(herd, work_items=items, result_id=combined_id)


def _augment_herd_with_mortality(*,herd,mortality_future,mortality_done,authority,owner,
                                 now,active,language):
    """Add the optional mortality section without weakening the base herd round."""
    if not mortality_done:
        return herd
    try:
        packet=build_oom_sakkie_mortality_packet(mortality_future.result(),
            analysis_end=now.astimezone(ZoneInfo("Africa/Johannesburg")).date())
        mortality,meta=consume_current_mortality_packet(packet=packet,authority=authority,
            owner_user_id=owner,observed_at=now,active_lifecycles=active,language=language)
    except Exception:
        return herd
    # `notify_owner` controls standalone refresh noise. A new authenticated
    # manager request must still receive current unchanged specialist truth;
    # exact inbound replay is suppressed by the outer provider lifecycle.
    if mortality and mortality.availability is SpecialistAvailability.AVAILABLE:
        combined_id=herd.result_id+":"+mortality.result_id
        items=tuple(replace(item,provenance=replace(item.provenance,result_id=combined_id))
                    for item in tuple(mortality.work_items)+tuple(herd.work_items))
    return replace(herd,work_items=items,result_id=combined_id)


def _load_manager_lifecycles(owner):
    """Retain terminal closure evidence without breaking injected legacy loaders."""
    try:
        return _load_active_lifecycles(owner, include_terminal=True)
    except TypeError as exc:
        if "include_terminal" not in str(exc):
            raise
        return _load_active_lifecycles(owner)


def _mortality_fingerprints(brief):
    fingerprints = {}
    for item in brief.queue:
        values = item.metadata.get("mortality_fingerprints") if item.metadata else None
        if isinstance(values, dict):
            fingerprints.update({str(key): str(value) for key, value in values.items()
                                 if key and value})
    return dict(sorted(fingerprints.items()))


def _mortality_packet(brief):
    for item in brief.queue:
        packet = item.metadata.get("mortality_packet") if item.metadata else None
        if isinstance(packet, dict):
            # Excluded historical diagnostics remain in canonical history. They
            # are not consumed by the current assessment and must not become
            # new actionable references to superseded animal identities.
            return {key: value for key, value in packet.items()
                    if key != "excluded_dated_or_superseded"}
    return None


def _persistence_failure(parsed, mission_id):
    language = str(parsed.get("output_language") or
                   (parsed.get("semantic") or {}).get("language") or "en")
    is_af = language.casefold().startswith("af")
    answer = ("<b>OOM SAKKIE — PLAASVERSLAG TERUGGEHOU</b>\n\n"
        "Ek kon nie bevestig dat vandag se plaasverslag veilig gestoor is nie. "
        "Ek het geen plaashandelinge uitgevoer nie. Hierdie versoek is nog nie voltooi nie."
        if is_af else "<b>OOM SAKKIE — FARM REPORT NOT CONFIRMED</b>\n\n"
        "I couldn’t confirm that today’s farm report was saved. "
        "I haven’t carried out any farm actions. This request is not complete.")
    return {"handled": True, "success": False,
        "status": "farm_manager_round_persistence_unproven", "mission_id": mission_id,
        "card_mission_id": mission_id + "-PERSISTENCE-FAILURE",
        "specialist_identity": "OOM_SAKKIE", "answer": answer,
        "recipient_render_contract": "specialist_structured_recipient_v1",
        "recipient_language": "af" if is_af else "en",
        "requires_visible_notification": True, "records_audit_trace": False,
        "audit_trace_status": "unproven", "do_not_retry_automatically": True, **ZERO_AUTHORITY}


def _append_mortality_receipt(packet, authority, owner, observed_at, language):
    try:
        _, meta = consume_current_mortality_packet(packet=packet,
            authority=authority, owner_user_id=owner, observed_at=observed_at,
            active_lifecycles=(), language=language)
        return meta.get("success") is True
    except Exception:
        return False
    return herd


def _active_welfare_result(active, now, language="en"):
    is_af = str(language).casefold().startswith("af")
    items = []
    for row in active or ():
        question = str(row.get("current_question") or "").strip()
        reported_dead = row.get("reported_dead") is True
        if not question and not reported_dead:
            continue
        tag = str(row.get("tag_number") or row.get("pig_id") or "the pig")
        label = str(row.get("tag_number") or row.get("pig_id") or ("die vark" if is_af else "the pig"))
        observed = _time(row.get("provider_timestamp"), now)
        result_id = "herdmaster-active-welfare-" + str(row.get("lifecycle_id") or tag)
        provenance = Provenance("herdmaster", result_id,
            (str(row.get("lifecycle_id") or "active_welfare_lifecycle"),
             "telegram-card-" + str(row.get("card_message_id") or "unknown")), observed, 1.0)
        if reported_dead:
            question = ""
            title = f"Vark {label} se sterfterekordopvolging" if is_af else f"Pig {tag} mortality record follow-up"
            why = ("Die eienaar het aangemeld dat hierdie vark dood is; die beheerde sterftelewensiklus bly die enigste huidige opvolg." if is_af else
                   "The owner reported this pig dead; the governed mortality lifecycle remains the only current follow-up.")
            next_action = ("Hersien die behoue sterftevoorskou en bevestig slegs wanneer die voorgestelde gevolge korrek is." if is_af else
                           "Review the retained mortality preview and confirm only when its proposed effects are correct.")
        else:
            title = f"Vark {label} se welstandsopvolging" if is_af else f"Pig {tag} welfare follow-up"
            why = ("'n Bestaande welstandsaak wag op een fisiese waarneming voordat HERDMASTER die rekordvoorskou kan voorberei." if is_af else
                   "An existing welfare case is waiting for one physical observation before HERDMASTER can prepare the record preview.")
            # This is retained specialist evidence. Do not replace an unknown
            # question with a generic translated observation or change its facts.
            next_action = question
        items.append(SpecialistWorkItem(
            item_id=result_id + ":follow-up", dedupe_key="herdmaster:" + str(row.get("pig_id")),
            domain="herd", title=title, why=why,
            next_action=next_action, assignee="charl", state=WorkState.URGENT,
            authority=Authority.ADVISORY, provenance=provenance, business_value=120,
            genuine_question=question, question_for="charl",
            metadata={"notification_decision_identity": str(row.get("lifecycle_id") or "")}))
    result_id = "herdmaster-active-welfare-" + _digest([
        (item.item_id, item.provenance.observed_at.isoformat()) for item in items])[:20]
    rebound = tuple(replace(item, provenance=replace(item.provenance, result_id=result_id)) for item in items)
    return SpecialistResult("herdmaster", result_id, now,
        SpecialistAvailability.AVAILABLE if rebound else SpecialistAvailability.CONTAINED,
        work_items=rebound)


def _whole_herd_specialist_result(canonical, observations, active, now, language="en"):
    from modules.pig_weights.herdmaster_management_round import _pregnancy_planning
    is_af = str(language).casefold().startswith("af")
    tasks = _canonical_tasks_with_current_mating(canonical)
    observations = _current_cycle_observations(
        tasks, observations, _time(canonical.get("generated_at"), now))
    active_packet = [{
        "pig_id": row["pig_id"], "tag_number": row.get("tag_number") or row["pig_id"],
        "lifecycle_id": row["lifecycle_id"], "state": row["state"],
        "specialist_owner": "HERDMASTER", "current_evidence": ["Existing authenticated welfare lifecycle."],
        "existing_question_or_card_id": row["card_message_id"],
        "reassessment_trigger": "authenticated reply on the existing lifecycle card",
    } for row in active]
    reproductive = []
    expired = []
    for observation in observations:
        pig_id = str(observation.get("pig_id") or "")
        task = tasks.get(pig_id) or {}
        known = task.get("known_evidence") or {}
        status = str(observation.get("operational_result") or "")
        if status not in {"Assumed Pregnant", "Inconclusive"}:
            continue
        row = {"pig_id": pig_id, "tag_number": str(task.get("tag_number") or pig_id),
            "operational_status": status,
            "current_evidence": [f"Authenticated owner observation: {status}; {observation.get('observed_signs') or 'no additional sign supplied'}."],
            "observed_at": observation.get("observed_at"), "source_identity": observation.get("source_identity"),
            "mating_id": observation.get("mating_id") or known.get("current_mating_id"),
            "smallest_next_observation": ("Watch appetite, comfort and any labour sign; clinical scanning remains optional."
                if status == "Assumed Pregnant" else "Reassess only if new heat, condition or clinical evidence appears."),
            "clinical_confirmation": "Optional higher-confidence fact; not clinically confirmed.",
            "current_applicability": status == "Assumed Pregnant"}
        if status == "Assumed Pregnant":
            try:
                planning = _pregnancy_planning(status, observation, known, now)
            except (TypeError, ValueError):
                continue
            if planning.get("current_applicability") is not True:
                expired.append({**row, **planning})
                continue
            window = planning["projected_farrowing_range"]
            preparation = planning["farrowing_pen_preparation_window"]
            row.update({"mating_id": observation.get("mating_id") or known.get("current_mating_id"),
                "mating_date": planning["mating_date"], "observed_signs": observation.get("observed_signs"),
                "projected_farrowing_range": {"start": window["earliest"],
                    "end": window["latest"], "uncertainty": window["uncertainty"]},
                "preparation_window": {"start": preparation["start"],
                    "end": preparation["complete_by"], "uncertainty": "prepare proportionally"},
                "change_triggers": ["return to heat", "illness", "early labour", "farrowing"],
                "prohibited_without_more_evidence": ["clinical-confirmation claim", "mating", "movement", "farm write"]})
        reproductive.append(row)
    packet = build_whole_herd_packet({"success": True, "writes_performed": False,
        "evidence_generation": canonical["generated_at"], "evidence_identity": canonical["worklist_id"]},
        active_lifecycles=active_packet, monday_weighing_candidates=(),
        reproductive_reviews=reproductive)
    result_id = packet["packet_identity"]
    observed = _time(packet["evidence_generation"], now)
    provenance = Provenance("herdmaster", result_id,
        (packet["source_evidence_identity"], packet["packet_identity"]), observed, 1.0)
    items = list(_active_welfare_result(active, now, language).work_items)
    assumed = [row for row in packet["reproductive_reviews"]
               if row["operational_status"] == "Assumed Pregnant"]
    groups = {}
    for row in assumed:
        groups.setdefault((row["projected_farrowing_range"]["start"], row["projected_farrowing_range"]["end"]), []).append(row)
    for group in groups.values():
        labels = (" en " if is_af else " and ").join(str(row["tag_number"]) for row in group)
        window = group[0]["projected_farrowing_range"]
        prep = group[0]["preparation_window"]
        key = "herdmaster:farrowing-preparation:" + ":".join(sorted(row["pig_id"] for row in group))
        items.append(SpecialistWorkItem(
            item_id=result_id + ":" + key, dedupe_key=key,
            domain="herd", title=f"Berei {labels} voor" if is_af else f"Prepare {labels}",
            why=((f"{labels} word vir plaasbeplanning steeds as dragtig aanvaar, maar dit is nie klinies bevestig nie; verwagte werping is ongeveer "
                  f"{window['start']} tot {window['end']}, met gepaste voorbereiding {prep['start']} tot {prep['end']}.") if is_af else
                 (f"{labels} remain operationally Assumed Pregnant, not clinically confirmed; farrowing is approximately "
                  f"{window['start']} to {window['end']}, with proportional preparation {prep['start']} to {prep['end']}.")),
            next_action="Berei hul werpareas in gepaste mate voor." if is_af else "Prepare their farrowing areas proportionally.",
            assignee="charl", state=WorkState.DUE_TODAY, authority=Authority.ADVISORY,
            provenance=provenance, business_value=110,
            metadata={"owner_followup": (f"HERDMASTER volg {labels} op wanneer nuwe werp- of dragtigheidsbewyse inkom."
                if is_af else f"HERDMASTER will follow up on {labels} when new farrowing or pregnancy evidence arrives.")}))
    expired_groups = {}
    for row in expired:
        window = row.get("historical_projected_farrowing_range") or {}
        expired_groups.setdefault((window.get("earliest"), window.get("latest")), []).append(row)
    for (start, end), group in expired_groups.items():
        labels = (" en " if is_af else " and ").join(str(row["tag_number"]) for row in group)
        key = "herdmaster:reproductive-status:" + ":".join(sorted(row["pig_id"] for row in group))
        question = (f"Wat is {labels} se huidige status: reeds gewerp, weer op hitte, of nog geen duidelike verandering nie?"
                    if is_af else f"What is the current status of {labels}: already farrowed, returned to heat, or no clear change yet?")
        items.append(SpecialistWorkItem(item_id=result_id + ":" + key, dedupe_key=key,
            domain="herd", title=(f"Huidige werpstatus — {labels}" if is_af else f"Current farrowing status — {labels}"),
            why=(f"Die verwagte tydperk {start} tot {end} is verby. Die huidige rekords bevestig nie die uitkoms van hierdie parings nie."
                 if is_af else f"The projected window {start} to {end} has passed. Current records do not confirm the outcome of these matings."),
            next_action=("Gee die huidige uitkoms; as daar 'n werpsel was, sal ek die datum en geboortetellings vra en die bevestiging voorberei."
                if is_af else "Tell me the current outcome; if there was a litter, I will ask for its date and birth counts and prepare the confirmation."),
            assignee="charl", state=WorkState.DUE_TODAY, authority=Authority.ADVISORY,
            provenance=provenance, business_value=110, genuine_question=question, question_for="charl",
            metadata={"notification_decision_identity": "matings:" + ":".join(
                sorted(str(row["mating_id"]) for row in group)) if all(row.get("mating_id") for row in group) else ""}))
    rebound = tuple(replace(item, provenance=provenance) for item in items)
    return SpecialistResult("herdmaster", result_id, observed,
        SpecialistAvailability.AVAILABLE, work_items=rebound)


def _canonical_tasks_with_current_mating(canonical):
    tasks = {str(row.get("pig_id") or ""): dict(row) for row in canonical.get("tasks") or ()}
    cases = {str(row.get("pig_id") or ""): row for row in canonical.get("cases") or ()}
    for pig_id, task in tasks.items():
        known = dict(task.get("known_evidence") or {})
        if known.get("current_mating_id") and known.get("current_mating_date"):
            task["known_evidence"] = known
            continue
        latest_date = str(known.get("latest_mating_date") or "")
        matching = [row for row in (cases.get(pig_id) or {}).get("mating_history") or ()
                    if row.get("canonical_mating") is True
                    and str(row.get("date") or "") == latest_date
                    and str(row.get("mating_id") or "")]
        if len(matching) == 1:
            known["current_mating_id"] = str(matching[0]["mating_id"])
            known["current_mating_date"] = latest_date
        task["known_evidence"] = known
    return tasks


def _current_cycle_observations(tasks, observations, generated_at):
    """Select one current, canonical-mating-bound owner observation per pig."""
    candidates = {}
    conflicted = set()
    for observation in observations or ():
        pig_id = str(observation.get("pig_id") or "")
        task = tasks.get(pig_id) or {}
        known = task.get("known_evidence") or {}
        # A later canonical litter settles this mating's old pregnancy watch.
        # The next litter lifecycle owns any remaining nursing/weaning work.
        if (str(known.get("latest_litter_date") or "")[:10]
                > str(known.get("current_mating_date") or "")[:10]
                and known.get("latest_litter_date") and known.get("current_mating_date")):
            continue
        current_mating_id = str(known.get("current_mating_id") or "")
        current_mating_date = str(known.get("current_mating_date") or "")
        if (not current_mating_id or not current_mating_date
                or str(observation.get("mating_id") or "") != current_mating_id
                or str(observation.get("mating_date") or "") != current_mating_date):
            continue
        try:
            raw_observed_at = observation.get("observed_at")
            if not isinstance(raw_observed_at, str) or not raw_observed_at.strip():
                continue
            observed_at = datetime.fromisoformat(raw_observed_at.replace("Z", "+00:00"))
            if observed_at.tzinfo is None:
                continue
            mating_date = datetime.fromisoformat(current_mating_date).date()
        except (TypeError, ValueError):
            continue
        if observed_at > generated_at or observed_at.date() < mating_date:
            continue
        prior = candidates.get(pig_id)
        if prior is None or observed_at > prior[0]:
            candidates[pig_id] = (observed_at, observation)
            conflicted.discard(pig_id)
        elif observed_at == prior[0] and _digest(observation) != _digest(prior[1]):
            conflicted.add(pig_id)
    return [row for pig_id, (_, row) in sorted(candidates.items()) if pig_id not in conflicted]


def _load_rootline(now, language="en"):
    return _project_rootline_snapshot(_load_rootline_snapshot(now), now, language)


def _load_rootline_snapshot(now):
    future = _ROOTLINE_REFRESH_EXECUTOR.submit(
        build_current_rootline_specialist_result,
        operating_date=now.date().isoformat(), now=now)
    try:
        raw = future.result(timeout=7.0)
    except Exception:
        future.cancel()
        provenance = Provenance("rootline", "rootline-current-reassessment-needed",
            ("canonical_rootline_refresh_not_available_within_manager_deadline",), now, 1.0)
        item = SpecialistWorkItem(
            item_id="rootline-current-reassessment-needed",
            dedupe_key="rootline:current-reassessment-needed", domain="water_energy",
            title="Refresh today's irrigation decision",
            why="The current power, forecast and water readings could not all be refreshed in time for a safe irrigation recommendation.",
            next_action="Oom Sakkie will reassess when fresh ROOTLINE readings are available; do not start irrigation or commissioning from this brief.",
            assignee="charl", state=WorkState.WAITING_EVIDENCE, authority=Authority.ADVISORY,
            provenance=provenance, business_value=90,
            genuine_question="", question_for="")
        return {"failed_result": SpecialistResult("rootline", provenance.result_id, now,
            SpecialistAvailability.AVAILABLE, work_items=(item,))}
    return {"raw": raw}


def _project_rootline_snapshot(snapshot, now, language="en"):
    if snapshot.get("failed_result"):
        result = snapshot["failed_result"]
        if (str(language).lower().startswith("af")
                and result.result_id == "rootline-current-reassessment-needed"):
            # The shared snapshot retains its evidence and authority; localize
            # only this generated fallback for each recipient's daily brief.
            result = replace(result, work_items=tuple(
                replace(item,
                    title="Werk vandag se besproeiingsbesluit by",
                    why=("Die huidige krag-, weervoorspelling- en waterlesings kon nie almal betyds "
                         "bygewerk word om besproeiing veilig aan te beveel nie."),
                    next_action=("Oom Sakkie sal die besluit heroorweeg wanneer nuwe ROOTLINE-lesings "
                                 "beskikbaar is; moenie besproeiing of ingebruikneming vanuit hierdie "
                                 "opsomming begin nie."))
                if item.dedupe_key == "rootline:current-reassessment-needed" else item
                for item in result.work_items))
        return result
    raw = snapshot["raw"]
    observed = _time(((raw.get("evidence") or {}).get("generated_at") or raw.get("generated_at")), now)
    result_id = str(raw.get("result_id") or raw.get("plan_id") or "rootline-current")
    provenance = Provenance("rootline", result_id, ("canonical_rootline_specialist_result",), observed, 1.0)
    from modules.oom_sakkie.rootline_daily_presentation import compose_daily_rootline_manager_item
    projection = compose_daily_rootline_manager_item(raw, language=language)
    state = WorkState.WAITING_EVIDENCE if "needs data" in projection["title"].lower() else WorkState.PLANNED
    item = SpecialistWorkItem(
        item_id=result_id + "-plan", dedupe_key="rootline:daily-plan", domain="water_energy",
        title=projection["title"], why=projection["why"],
        next_action=projection["next_action"],
        assignee="charl", state=state, authority=Authority.ADVISORY, provenance=provenance,
        business_value=80, genuine_question=projection["question"],
        question_for="charl" if projection["question"] else "",
        metadata={"owner_followup": projection["next_action"],
                  "notification_decision_identity": projection.get("notification_decision_identity", "")},
    )
    return SpecialistResult("rootline", result_id, observed,
        SpecialistAvailability.AVAILABLE if raw.get("success") else SpecialistAvailability.CONTAINED,
        work_items=(item,))


def _missing(name, now, availability=SpecialistAvailability.MISSING):
    return SpecialistResult(name, f"{name}-unavailable", now, availability)


def _material_recomposition_allowed(prior, binding):
    prior_binding = prior.get("binding") if isinstance(prior, dict) else {}
    prior_result = prior.get("result") if isinstance(prior, dict) else {}
    same_provider = all(prior_binding.get(key) == binding.get(key) for key in (
        "owner", "chat", "provider_message_id", "provider_timestamp", "content_digest"))
    if not same_provider or binding.get("contract_version") != CONTRACT_VERSION:
        return False
    prior_version = prior_binding.get("contract_version")
    if prior_version == "oom_sakkie_farm_manager_round_v1":
        return (int((prior_result or {}).get("action_count") or 0) == 0
            and "BOUNDED WAITING" in str((prior_result or {}).get("answer") or ""))
    if prior_version == "oom_sakkie_farm_manager_round_v2":
        gaps = (prior_result or {}).get("specialist_gaps") or {}
        return (gaps.get("herdmaster") == "invalid_future_evidence"
            and "Pig 127" not in str((prior_result or {}).get("answer") or ""))
    if prior_version == "oom_sakkie_farm_manager_round_v3":
        answer = str((prior_result or {}).get("answer") or "")
        defective_weighing = re.search(r"Weigh these[^\n]*(?:None|…|\.\.\.)", answer)
        return "Pig 127" in answer and defective_weighing is not None
    if prior_version == "oom_sakkie_farm_manager_round_v4":
        answer = str((prior_result or {}).get("answer") or "")
        # A mortality lifecycle may become authoritative after the original
        # manager round. Permit one contract-version material correction only
        # when the preserved brief still asks an obsolete breathing question.
        return "breathing" in answer.casefold()
    return False


def _mortality_recomposition_supported(prior, herd_result):
    if not isinstance(herd_result, SpecialistResult):
        return False
    if herd_result.specialist != "herdmaster" or herd_result.availability is not SpecialistAvailability.AVAILABLE:
        return False
    prior_answer = str(((prior or {}).get("result") or {}).get("answer") or "")
    prior_animals = {value.casefold() for value in re.findall(
        r"\bPig\s+([A-Za-z0-9-]+)", prior_answer, flags=re.IGNORECASE)}
    if not prior_animals:
        return False
    for item in herd_result.work_items:
        title = str(item.title or "")
        current = {value.casefold() for value in re.findall(
            r"\bPig\s+([A-Za-z0-9-]+)", title, flags=re.IGNORECASE)}
        if "mortality record follow-up" in title.casefold() and prior_animals.intersection(current):
            return True
    return False


def _render(brief, language="en"):
    from modules.oom_sakkie.owner_response_composer import compose_manager_brief
    return compose_manager_brief(brief, language="af" if language.lower().startswith("af") else "en")


def _render_legacy(brief):
    labels = {
        WorkState.URGENT: "DO NOW", WorkState.DUE_TODAY: "DO TODAY",
        WorkState.PLANNED: "PLANNED / RECOMMENDED",
        WorkState.WAITING_EVIDENCE: "WAITING FOR EVIDENCE",
        WorkState.PROTECTED_OWNER_DECISION: "PROTECTED DECISION",
    }
    lines = ["<b>OOM SAKKIE — TODAY'S FARM BRIEF</b>"]
    questions = [question for values in brief.questions.values() for question in values]
    selected_question = questions[0] if questions else ""
    for item in brief.queue[:3]:
        next_action = ("Reply to the one question below."
            if selected_question and item.genuine_question == selected_question
            and item.next_action == selected_question else item.next_action)
        lines += ["", f"<b>{labels[item.state]}</b> — {_clip(item.title, 120)}",
                  _clip(item.why, 300), f"Next: {_clip(next_action, 450)}",
                  f"Owner: {_clip(item.assignee.title(), 30)} · Specialist: {_clip(item.provenance.specialist.upper(), 40)}"]
    if not brief.queue:
        lines += ["", "No supported family action is due from the current farm evidence. Oom Sakkie will reassess when a specialist result or farm observation changes."]
    if questions:
        lines += ["", "<b>ONE QUESTION</b>", _clip(questions[0], 300)]
    lines += ["", "No weight, mating, farm, customer, publication or hardware action was performed. Weights require an exact tag/Pig ID/weight preview and confirmation; mating and irrigation execution remain separately governed."]
    rendered = "\n".join(lines)
    if len(rendered) > 3900:
        raise ValueError("farm_manager_render_budget_exceeded")
    return rendered


def _clip(value, limit):
    text = " ".join(str(value or "").split())
    escaped = []
    used = 0
    for character in text:
        entity = html.escape(character, quote=False)
        if used + len(entity) > limit:
            return "".join(escaped).rstrip() + "…"
        escaped.append(entity)
        used += len(entity)
    return "".join(escaped)


def _digest(value):
    payload = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _time(value, fallback):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return fallback


def _event_store(action, identity, payload):
    from modules.sales.sam_live_stock_launch_control import (
        build_sam_live_stock_review_event, record_sam_live_stock_review_event,
    )
    if action == "load":
        with connect_bounded_read() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'farm_manager_round'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s and chatwoot_conversation_id=%s
                    order by created_at desc,review_event_id desc limit 1""",
                    (EVENT_SOURCE, identity))
                row = cursor.fetchone()
        return row[0] if row and isinstance(row[0], dict) else None
    event = build_sam_live_stock_review_event({"conversation_id": identity}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "internal_farm_manager_round"},
        event_source=EVENT_SOURCE)
    # The revision claim is provider/contract scoped, not result scoped. Two
    # concurrent recompositions must contend for the same durable identity;
    # only the inserted winner may reach family delivery.
    revision_id = identity + "-REV-" + _digest({
        "binding": payload.get("binding")})[:20].upper()
    event.update({"review_event_id": revision_id, "chatwoot_conversation_id": identity,
        "review_json": {"farm_manager_round": payload}, "decision_json": {}, "facts_json": {},
        "customer_message_excerpt": "", "sam_reply_excerpt": ""})
    saved, status = record_sam_live_stock_review_event(event,
        connect_factory=lambda: connect_bounded_postgres(read_only=False))
    return {"success": status < 400 and saved.get("success") is True,
            "created": saved.get("created")}


def _load_enquiry_cases(query=None):
    """Bounded read of the existing manager, never a second work queue."""
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    columns = ("case_id", "dedupe_key", "specialist", "status", "summary", "next_action",
               "unknowns", "next_reassessment_at", "lease_until", "last_heartbeat_at")
    query = query or {}
    prefixes = _CASE_PREFIXES.get(query.get("case_kind"), ())
    with connect_bounded_rootline_postgres() as connection, connection.cursor() as cursor:
        cursor.execute("""select case_id,dedupe_key,specialist,status,summary,next_action,
                   unknowns,next_reassessment_at,lease_until,last_heartbeat_at
            from app_private.oom_manager_cases where status <> 'completed'
              and (%s or dedupe_key like any(%s))
            order by next_reassessment_at,case_id limit 65""",
            (not bool(prefixes), [prefix + '%' for prefix in prefixes]))
        rows = cursor.fetchall()
    return {"cases": [dict(zip(columns, row)) for row in rows[:64]], "truncated": len(rows) > 64}


def _render_enquiry(brief, query, *, language, now, case_loader=None):
    af = language.casefold().startswith("af")
    kind = query.get("kind")
    clarification = _enquiry_clarification(query, language)
    if clarification:
        return clarification
    lines = ["<b>OOM SAKKIE — OPVOLG</b>" if af else "<b>OOM SAKKIE — FOLLOW-UP</b>"]
    if kind in {"work_split", "case_status"}:
        try:
            cases = (case_loader or _load_enquiry_cases)(query)
        except Exception:
            cases = None
        lines += ["", "<b>Aangetekende opvolgwerk</b>" if af else "<b>Recorded follow-up work</b>"]
        if cases is None:
            lines.append("Huidige saakstatus is nie beskikbaar nie; ek kan nie bevestig wat aan die gang is nie." if af else
                         "Current case status is unavailable; I cannot verify what is running.")
        else:
            truncated = bool(cases.get("truncated")) if isinstance(cases, dict) else False
            selected = cases.get("cases", []) if isinstance(cases, dict) else cases
            for row in selected[:6]:
                state = str(row.get("status") or "unknown")
                lease = _time(row.get("lease_until"), datetime.min.replace(tzinfo=timezone.utc))
                if state == "delegated":
                    label = ("aktiewe werkerhuur" if af else "active worker lease") if lease > now else ("werkerhuur verstryk; uitvoering onbevestig" if af else "worker lease expired; execution unconfirmed")
                else:
                    label = ({"open": "in die tou", "waiting_reassessment": "wag op herbeoordeling", "exception": "tegnies geblokkeer", "contained": "beperk"}.get(state, state) if af else
                             {"open": "queued", "waiting_reassessment": "waiting for reassessment", "exception": "technical exception", "contained": "contained"}.get(state, state))
                summary = (_case_label_af(str(row.get("dedupe_key") or "")) if af else _clip(row.get("summary"), 220))
                lines.append(f"• {_clip(row.get('specialist'), 30)}: {summary} — {_clip(label, 100)}.")
            if truncated:
                lines.append("Hierdie is 'n begrensde deel van die saakregister." if af else "This is a bounded partial case snapshot.")
            if not selected and not truncated:
                lines.append("Geen passende oop saak in hierdie huidige saakregister nie; dit bewys nie 'n fisiese uitkoms nie." if af else
                             "No matching open case in this current case register; this does not prove a physical outcome.")
            if len(selected) > 6:
                lines.append((f"Nog {len(selected)-6} sake is aangeteken." if af else f"Another {len(selected)-6} cases are recorded."))
    items = list(brief.queue)
    if kind == "specialist_detail":
        lines += ["", "<b>Huidige spesialisbevindinge</b>" if af else "<b>Current specialist findings</b>"]
        for item in items[:5]:
            finding = f"{item.title}. {item.why} " + ("Volgende stap: " if af else "Next step: ") + item.next_action
            lines.append("• " + _read_text(finding, 660, af))
        if not items:
            lines.append("Geen ondersteunde aksie in die huidige spesialispakket nie." if af else "No supported action in the current specialist packet.")
    if kind == "work_split":
        lines += ["", "<b>Wat ek kan hanteer</b>" if af else "<b>What I can handle</b>",
            "Ek lees en vergelyk spesialisbewyse. Die saakstatus hierbo onderskei beplande opvolg van werk wat werklik aan 'n werker toegewys is." if af else
            "I read and compare specialist evidence. The case status above distinguishes queued follow-up from work actually assigned to a worker."]
    questions = [q for values in brief.questions.values() for q in values]
    if kind != "case_status":
        lines += ["", "<b>Wat ek van jou nodig het</b>" if af else "<b>What I need from you</b>"]
        owner_steps = list(dict.fromkeys(questions + [item.next_action for item in items
            if not item.genuine_question and item.metadata.get("physical_work_ready") is True]))
        lines.extend("• " + _read_text(step, 260, af) for step in owner_steps[:4])
        if not owner_steps:
            lines.append("Geen bewys-gesteunde nuwe vraag in die huidige pakket nie." if af else "No supported new owner question in the current packet.")
    for specialist, gap in brief.specialist_gaps.items():
        lines.append(("Bewysgaping: " if af else "Evidence gap: ") + _clip(specialist, 30) + " — " + ("nie beskikbaar nie" if af else _clip(gap, 80)))
    lines += ["", "Hierdie is 'n leesantwoord; geen plaasrekord, sluiting of fisiese handeling is uitgevoer nie." if af else
              "This is a read-only answer; no farm record, case closure or physical action was performed."]
    answer = "\n".join(lines)
    if len(answer) > 3900:
        raise ValueError("enquiry_render_budget_exceeded")
    return answer


_CASE_PREFIXES = {
    "farrowing": ("herdmaster:expired-farrowing:", "herdmaster:farrowing-", "herdmaster:herdmaster:farrowing-"),
    "mortality": ("herdmaster:retained-mortality:", "herdmaster:retained-litter-loss:", "herdmaster:mortality", "herdmaster:herdmaster:mortality"),
    "welfare": ("herdmaster:welfare:", "herdmaster:health:")}


def _enquiry_clarification(query, language):
    af = language.casefold().startswith("af")
    if query.get("subject") and query.get("kind") in {"specialist_detail", "case_status"}:
        return (f"Ek kan dier {_clip(query['subject'], 100)} se huidige status of die hele saakgroep wys. Ek kan nog nie een individuele saak veilig aan die dier koppel nie. Watter aansig verkies jy?" if af else
                f"I can show animal {_clip(query['subject'], 100)}'s current status or the whole case family, but cannot yet bind an individual case to this animal. Which view would you like?")
    if query.get("kind") == "case_status" and not query.get("case_kind"):
        return ("Ek wil die regte saak bevestig. Bedoel jy 'n werpsaak, 'n sterfte-/afskeidsaak, of 'n ander spesifieke saak?" if af else
                "Do you mean a farrowing case, an animal death/farewell case, or another specific case?")
    if query.get("kind") == "specialist_detail" and not query.get("specialist"):
        return "Watter spesialis se bevindinge bedoel jy?" if af else "Which specialist's findings do you mean?"
    return ""


def _read_text(value, limit, af):
    if af:
        from modules.oom_sakkie.family_message_lifecycle import _looks_afrikaans
        if not _looks_afrikaans(str(value)):
            return "Die besonderhede is nog nie in jou taal beskikbaar nie; geen gevolgtrekking word bygevoeg nie."
    return _clip(value, limit)


def _case_label_af(key):
    if key.startswith(_CASE_PREFIXES["farrowing"]): return "Werp-opvolg"
    if key.startswith(_CASE_PREFIXES["mortality"]): return "Sterfte-opvolg"
    if key.startswith(_CASE_PREFIXES["welfare"]): return "Welstandsopvolg"
    if key.startswith(("herdmaster:bulk-weight-", "herdmaster:weight", "herdmaster:herdmaster:weight")): return "Gewigsversoening"
    return "Aangetekende opvolgsaak"
