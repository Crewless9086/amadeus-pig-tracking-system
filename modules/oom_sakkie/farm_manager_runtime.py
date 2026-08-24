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
                              clock=None):
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), dict) else {}
    if not (semantic.get("domain") == "manager_round"
            and not semantic.get("needs_clarification")) \
            and not is_farm_manager_round(parsed.get("text", "")):
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
    providers = loaders or {
        "herdmaster": lambda: _load_herdmaster(authority, owner, now,
            language=str(semantic.get("language") or "en")),
        "rootline": lambda: _load_rootline(now, str(semantic.get("language") or "en")),
        "sam": lambda: _missing("sam", now),
        "beacon": lambda: _missing("beacon", now),
    }
    results = []
    exceptions = {}
    specialists = ("herdmaster", "rootline", "sam", "beacon")
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
        answer = _render(brief, language=str(semantic.get("language") or "en"))
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
        "question_count": sum(len(values) for values in brief.questions.values()),
        "reassessment_triggers": [f.follow_up_id for f in brief.follow_ups],
        "weighing_worklist": weighing_worklist,
        "material_recomposition_authority": material_recomposition,
        "herdmaster_mortality_fingerprints": _mortality_fingerprints(brief),
        **ZERO_AUTHORITY,
    }
    mortality_packet = _mortality_packet(brief)
    recorded = store("record", mission_id, {"binding": binding, "result": output,
        "mortality_packet": mortality_packet})
    if not isinstance(recorded, dict) or recorded.get("success") is not True:
        return {"handled": True, "success": False,
            "status": "farm_manager_round_persistence_unproven",
            "mission_id": mission_id, **ZERO_AUTHORITY}, 503
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
                "mission_id": mission_id, **ZERO_AUTHORITY}, 503
        return {**(winner.get("result") or {}),
                "status": "farm_manager_round_replay_suppressed"}, 200
    if mortality_packet and not _append_mortality_receipt(mortality_packet,
            authority, owner, composition_now, str(semantic.get("language") or "en")):
        return {"handled": True, "success": False,
            "status": "farm_manager_mortality_receipt_unavailable",
            "mission_id": mission_id, **ZERO_AUTHORITY}, 503
    return output, 200


def _load_herdmaster(authority, owner, now, language="en"):
    futures = {
        "canonical": _HERD_EVIDENCE_EXECUTOR.submit(load_current_breeding_operating_loop),
        "observations": _HERD_EVIDENCE_EXECUTOR.submit(_load_observations, owner),
        "active": _HERD_EVIDENCE_EXECUTOR.submit(_load_manager_lifecycles, owner),
        "daily": _HERD_EVIDENCE_EXECUTOR.submit(load_daily_manager_evidence,
            analysis_date=now.astimezone(ZoneInfo("Africa/Johannesburg")).date(),
            owner_user_id=owner),
    }
    base_names=("canonical","observations","active")
    done, pending = wait(tuple(futures.values()), timeout=9.0)
    try:
        if any(futures[name] not in done for name in base_names):
            raise TimeoutError("herd_evidence_deadline")
        canonical = futures["canonical"].result()
        observations = futures["observations"].result()
        active = futures["active"].result()
        active_current = tuple(row for row in active if str(row.get("state") or "").casefold()
            not in {"completed", "closed", "handled"})
        # Reproductive and welfare evidence remains in the existing whole-herd
        # result. Weekly cohort biology comes only from the versioned producer.
        herd = _whole_herd_specialist_result(canonical, observations, active_current, now)
    except Exception:
        try:
            active = futures["active"].result(timeout=0) if futures["active"] in done else ()
        except Exception:
            active = ()
        active_current = tuple(row for row in active if str(row.get("state") or "").casefold()
            not in {"completed", "closed", "handled"})
        return _active_welfare_result(active_current, now)
    else:
        try:
            packet = futures["daily"].result() if futures["daily"] in done else None
        except Exception:
            packet = None
        daily = consume_daily_manager_evidence(packet, observed_at=now,
            active_lifecycles=active, language=language)
        combined_id = herd.result_id + ":" + daily.result_id
        items = tuple(replace(item, provenance=replace(item.provenance,
                      result_id=combined_id))
                      for item in tuple(daily.work_items) + tuple(herd.work_items))
        return replace(herd, work_items=items, result_id=combined_id)
    finally:
        for future in pending:
            future.cancel()


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
            return packet
    return None


def _append_mortality_receipt(packet, authority, owner, observed_at, language):
    try:
        _, meta = consume_current_mortality_packet(packet=packet,
            authority=authority, owner_user_id=owner, observed_at=observed_at,
            active_lifecycles=(), language=language)
        return meta.get("success") is True
    except Exception:
        return False
    return herd


def _active_welfare_result(active, now):
    items = []
    for row in active or ():
        question = str(row.get("current_question") or "").strip()
        reported_dead = row.get("reported_dead") is True
        if not question and not reported_dead:
            continue
        tag = str(row.get("tag_number") or row.get("pig_id") or "the pig")
        observed = _time(row.get("provider_timestamp"), now)
        result_id = "herdmaster-active-welfare-" + str(row.get("lifecycle_id") or tag)
        provenance = Provenance("herdmaster", result_id,
            (str(row.get("lifecycle_id") or "active_welfare_lifecycle"),
             "telegram-card-" + str(row.get("card_message_id") or "unknown")), observed, 1.0)
        if reported_dead:
            question = ""
            title = f"Pig {tag} mortality record follow-up"
            why = "The owner reported this pig dead; the governed mortality lifecycle remains the only current follow-up."
            next_action = "Review the retained mortality preview and confirm only when its proposed effects are correct."
        else:
            title = f"Pig {tag} welfare follow-up"
            why = "An existing welfare case is waiting for one physical observation before HERDMASTER can prepare the record preview."
            next_action = question
        items.append(SpecialistWorkItem(
            item_id=result_id + ":follow-up", dedupe_key="herdmaster:" + str(row.get("pig_id")),
            domain="herd", title=title, why=why,
            next_action=next_action, assignee="charl", state=WorkState.URGENT,
            authority=Authority.ADVISORY, provenance=provenance, business_value=120,
            genuine_question=question, question_for="charl"))
    result_id = "herdmaster-active-welfare-" + _digest([
        (item.item_id, item.provenance.observed_at.isoformat()) for item in items])[:20]
    rebound = tuple(replace(item, provenance=replace(item.provenance, result_id=result_id)) for item in items)
    return SpecialistResult("herdmaster", result_id, now,
        SpecialistAvailability.AVAILABLE if rebound else SpecialistAvailability.CONTAINED,
        work_items=rebound)


def _whole_herd_specialist_result(canonical, observations, active, now):
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
            "smallest_next_observation": ("Watch appetite, comfort and any labour sign; clinical scanning remains optional."
                if status == "Assumed Pregnant" else "Reassess only if new heat, condition or clinical evidence appears."),
            "clinical_confirmation": "Optional higher-confidence fact; not clinically confirmed.",
            "current_applicability": status == "Assumed Pregnant"}
        if status == "Assumed Pregnant":
            mating_date = datetime.fromisoformat(str(observation.get("mating_date"))).date()
            row.update({"mating_id": observation.get("mating_id") or known.get("current_mating_id"),
                "mating_date": mating_date.isoformat(), "observed_signs": observation.get("observed_signs"),
                "projected_farrowing_range": {"start": (mating_date + timedelta(days=112)).isoformat(),
                    "end": (mating_date + timedelta(days=116)).isoformat(), "uncertainty": "approximately 114 +/- 2 days"},
                "preparation_window": {"start": (mating_date + timedelta(days=98)).isoformat(),
                    "end": (mating_date + timedelta(days=105)).isoformat(), "uncertainty": "prepare proportionally"},
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
    items = list(_active_welfare_result(active, now).work_items)
    assumed = [row for row in packet["reproductive_reviews"]
               if row["operational_status"] == "Assumed Pregnant"]
    if assumed:
        labels = " and ".join(str(row["tag_number"]) for row in assumed)
        window = assumed[0]["projected_farrowing_range"]
        prep = assumed[0]["preparation_window"]
        items.append(SpecialistWorkItem(
            item_id=result_id + ":farrowing-round", dedupe_key="herdmaster:farrowing-preparation",
            domain="herd", title=f"Prepare {labels}",
            why=(f"{labels} remain operationally Assumed Pregnant, not clinically confirmed; farrowing is approximately "
                 f"{window['start']} to {window['end']}, with proportional preparation {prep['start']} to {prep['end']}."),
            next_action="Prepare their farrowing areas proportionally.",
            assignee="charl", state=WorkState.DUE_TODAY, authority=Authority.ADVISORY,
            provenance=provenance, business_value=110))
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
        return SpecialistResult("rootline", provenance.result_id, now,
            SpecialistAvailability.AVAILABLE, work_items=(item,))
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
