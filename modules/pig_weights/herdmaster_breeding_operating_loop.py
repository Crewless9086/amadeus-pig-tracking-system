"""Agentic, plan-only Herdmaster breeding operating loop.

The loop reconciles existing canonical evidence into weekly owner tasks,
conversational observation previews, male recommendations, approval packets
and milestone reminders. It does not persist observations, matings, reminders
or animal state.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

CONTRACT_VERSION = "herdmaster_breeding_operating_loop_v1"
REPEAT_SERVICE_REVIEW_COUNT = 2
WEIGHT_FRESH_DAYS = 30


def build_breeding_operating_loop(
    attention,
    *,
    readiness,
    matings,
    litters,
    observations,
    generated_at=None,
    today=None,
):
    """Create one deterministic weekly breeding worklist and plan-only loop."""
    today = today or date.today()
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    if not _valid(attention, readiness, matings, litters, observations):
        return _unavailable(generated_at)
    week_start = today - timedelta(days=today.weekday())
    mating_by_female = _group(matings, "sow_pig_id", "mating_date")
    litter_by_female = _group(litters, "sow_pig_id", "farrowing_date")
    observations_by_pig = _group_observations(observations)
    readiness_by_pig = {
        _text(row.get("pig_id")): row for row in readiness["pigs"]
        if isinstance(row, dict)
    }
    females = {
        _text(row.get("pig_id")): row for row in attention["animals"]
        if isinstance(row, dict)
    }
    male_rows = [
        row for row in readiness["pigs"]
        if _norm(row.get("sex")) == "male"
        and _norm(row.get("status")) == "active"
        and _norm(row.get("on_farm")) in {"yes", "true", "1"}
    ]
    tasks = []
    cases = []
    for pig_id, attention_row in females.items():
        readiness_row = readiness_by_pig.get(pig_id, {})
        female_matings = mating_by_female.get(pig_id, [])
        female_litters = litter_by_female.get(pig_id, [])
        female_observations = observations_by_pig.get(pig_id, [])
        classification = _classify(
            attention_row, readiness_row, female_matings, female_litters,
            female_observations, today,
        )
        male_recommendation = _rank_males(
            readiness_row, male_rows, matings, classification
        )
        task = _task(
            attention_row, readiness_row, classification,
            female_observations, male_recommendation, week_start, generated_at,
        )
        if task and not task["completed"]:
            tasks.append(task)
        cases.append({
            "pig_id": pig_id,
            "tag_number": _text(attention_row.get("tag_number")) or pig_id,
            "animal_href": attention_row.get("animal_href") or f"/pig/{pig_id}",
            "classification": classification,
            "male_recommendation": male_recommendation,
            "mating_history": _mating_summary(female_matings, today),
            "litter_history": _litter_summary(female_litters, today),
            "observation_history": _observation_summary(female_observations),
            "evidence": {
                "missing": list(attention_row.get("missing_facts") or []),
                "conflicting": list(
                    attention_row.get("conflicting_facts") or []
                ),
                "observation_timestamp": attention_row.get(
                    "evidence_dates", {}
                ).get("observed_at"),
            },
            "approval_packet": _approval_packet(
                readiness_row, classification, male_recommendation,
                generated_at, today,
            ),
            "milestones": _milestones(female_matings, today),
            "owner_only": True,
        })
    tasks.sort(key=lambda item: (
        item["priority"], item["task_group"], item["tag_number"],
        item["pig_id"],
    ))
    cases.sort(key=lambda item: (
        next((
            task["priority"] for task in tasks
            if task["pig_id"] == item["pig_id"]
        ), 999),
        item["tag_number"], item["pig_id"],
    ))
    reminders = _reminder_plan(cases, today)
    counts = Counter(task["task_group"] for task in tasks)
    return {
        "success": True,
        "contract_version": CONTRACT_VERSION,
        "generated_at": generated_at,
        "week_start": week_start.isoformat(),
        "worklist_id": _stable_id(
            "HERD-WEEK", week_start.isoformat(),
            sorted(task["task_id"] for task in tasks),
        ),
        "worklist_status": "Available",
        "task_count": len(tasks),
        "task_counts": dict(sorted(counts.items())),
        "tasks": tasks,
        "cases": cases,
        "reminder_plan": reminders,
        "notification_delivery_operational": False,
        "mating_execution_enabled": False,
        "observation_recording_enabled": False,
        "owner_only": True,
        "writes_performed": False,
        "protected_actions_performed": False,
        "limitations": [
            "This deployment prepares the worklist, factual capture preview, "
            "recommendation, approval packet and reminder plan only.",
            "Observation append, mating execution and reminder delivery remain "
            "disabled until a separate supervised authorization.",
        ],
    }


def preview_conversational_inspection(loop, user_text):
    """Extract only directly stated facts and bind them to one current task."""
    if not isinstance(loop, dict) or loop.get("success") is not True:
        return _preview_error("worklist_unavailable")
    text = _text(user_text)
    matches = [
        task for task in loop.get("tasks", [])
        if _mentions(text, task.get("tag_number"))
        or _mentions(text, task.get("pig_id"))
        or _mentions(text, task.get("task_id"))
    ]
    if len(matches) != 1:
        return _preview_error(
            "animal_or_task_ambiguous",
            clarification=(
                "Please include exactly one animal tag from this week's "
                "breeding worklist."
            ),
        )
    task = matches[0]
    facts = _extract_facts(text)
    if not facts:
        return _preview_error(
            "no_direct_facts_found",
            clarification=(
                f"For {task['tag_number']}, state only what was physically "
                "seen or measured."
            ),
        )
    ambiguities = _ambiguities(text, facts)
    if ambiguities:
        return _preview_error(
            "inspection_fact_ambiguous",
            clarification=ambiguities[0],
            task_id=task["task_id"],
        )
    missing_after = [
        item for item in task.get("required_checks", [])
        if not _fact_resolves_check(facts, item)
    ]
    preview_id = _stable_id(
        "HERD-OBS-PREVIEW", task["task_id"], facts
    )
    return {
        "success": True,
        "status": "inspection_preview_ready",
        "preview_id": preview_id,
        "task_id": task["task_id"],
        "pig_id": task["pig_id"],
        "tag_number": task["tag_number"],
        "facts": facts,
        "interpretation": _interpretation(facts),
        "missing_after_preview": missing_after,
        "task_would_close": not missing_after,
        "provisional_reassessment": (
            "Ready for mating review"
            if not missing_after and facts.get("standing_heat") == "observed"
            else "Observe for heat"
            if facts.get("standing_heat") == "not_observed"
            else task["provisional_recommendation"]
        ),
        "recording_contract": {
            "existing_writer": "herdmaster_breeding_observation_v1",
            "exact_pig_binding": True,
            "exact_task_binding": True,
            "server_derived_owner_identity_required": True,
            "preview_required": True,
            "idempotency_key": _stable_id(
                "HERD-OBS-KEY", task["task_id"], facts
            ),
            "append_only": True,
            "recording_enabled": False,
        },
        "writes_performed": False,
        "protected_actions_performed": False,
    }


def oom_sakkie_worklist_summary(loop):
    """Return Telegram-safe ordinary-farm-language worklist copy."""
    if not isinstance(loop, dict) or loop.get("success") is not True:
        return "Monday breeding worklist is unavailable; do not treat this as zero."
    tasks = loop.get("tasks", [])
    if not tasks:
        return "No breeding animals require owner attention in the current evidence cut."
    lines = [f"Monday breeding round: {len(tasks)} animal(s) need attention."]
    for task in tasks[:8]:
        checks = ", ".join(task["required_checks"]) or "owner review"
        lines.append(
            f"{task['tag_number']}: {task['why']}. Check {checks}. "
            f"Provisional: {task['provisional_recommendation']}. "
            f"Delay: {task['delay_consequence']}."
        )
    if len(tasks) > 8:
        lines.append(f"{len(tasks) - 8} more task(s) remain on the owner board.")
    return "\n".join(lines)


def _classify(attention, readiness, matings, litters, observations, today):
    latest_mating = matings[0] if matings else {}
    latest_litter = litters[0] if litters else {}
    unsuccessful = [
        row for row in matings if _norm(row.get("pregnancy_check_result"))
        in {"not_pregnant", "negative"}
        or _norm(row.get("mating_status")) in {
            "repeat_service", "repeat_required"
        }
        or _norm(row.get("outcome")) in {
            "repeat_required", "not_pregnant", "unsuccessful"
        }
    ]
    mating_date = _date(latest_mating.get("mating_date"))
    days_since_mating = (
        (today - mating_date).days if mating_date and today >= mating_date
        else None
    )
    pregnancy = _norm(latest_mating.get("pregnancy_check_result"))
    latest_heat = _latest_measurement(observations, "standing_heat")
    latest_bcs = _latest_measurement(observations, "body_condition_score")
    observed_checks = {
        "body condition": latest_bcs is not None,
        "movement": _latest_measurement(
            observations, "feet_legs_movement"
        ) is not None,
        "visible concerns": _latest_measurement(
            observations, "visible_injury"
        ) is not None,
        "heat signs": latest_heat is not None,
    }
    medical = _norm(
        readiness.get("medical_status") or readiness.get("health_status")
    )
    withdrawal = _norm(readiness.get("withdrawal_evidence_state"))
    available = _norm(readiness.get("available_for_breeding"))
    family_complete = bool(
        _text(readiness.get("mother_id"))
        and _text(readiness.get("father_id"))
    )
    hold_reasons = []
    if medical not in {"clear", "eligible"}:
        hold_reasons.append("medical evidence")
    if withdrawal not in {"cleared", "not_applicable"}:
        hold_reasons.append("withdrawal evidence")
    if available not in {"available", "yes", "true"}:
        hold_reasons.append("breeding availability")
    if not family_complete:
        hold_reasons.append("family-tree evidence")
    litter_date = _date(
        latest_litter.get("farrowing_date") or latest_litter.get("birth_date")
    )
    days_since_litter = (
        (today - litter_date).days if litter_date and today >= litter_date
        else None
    )
    weight_age = readiness.get("days_since_weight")
    state = "Needs Data"
    action = "inspect for breeding readiness"
    priority = 60
    reason = "Required breeding evidence is incomplete."
    if any(value in {"hold", "medical_hold", "active"} for value in (
        medical, withdrawal, available,
    )):
        state, action, priority = (
            "Hold for medical/withdrawal evidence",
            "review medical or withdrawal hold", 5,
        )
        reason = "A current medical, withdrawal or availability hold is evidenced."
    elif len(unsuccessful) >= REPEAT_SERVICE_REVIEW_COUNT:
        state, action, priority = (
            "Repeat-service decision required", "repeat-service review", 10
        )
        reason = (
            f"{len(unsuccessful)} canonical unsuccessful/repeat-service "
            "events require an owner decision."
        )
    elif pregnancy in {"pregnant", "confirmed", "confirmed_pregnant"}:
        state, action, priority = (
            "Pregnancy evidence pending" if days_since_mating is None
            else "Pregnancy evidence pending",
            "monitor pregnancy and farrowing milestones", 35,
        )
        reason = "Canonical pregnancy evidence is present."
    elif mating_date and (
        pregnancy in {"not_pregnant", "negative"}
        or _norm(latest_mating.get("mating_status")) == "repeat_service"
    ):
        state, action, priority = (
            "Possible return to heat", "observe for standing heat", 15
        )
        reason = "Not-pregnant or repeat-service evidence follows a canonical mating."
    elif mating_date and (
        _norm(latest_mating.get("is_overdue_check")) == "yes"
        or (days_since_mating is not None and days_since_mating >= 28)
    ):
        state, action, priority = (
            "Pregnancy evidence pending", "pregnancy check due", 18
        )
        reason = f"The canonical mating was {days_since_mating} days ago."
    elif mating_date:
        state, action, priority = (
            "Pregnancy evidence pending", "monitor next milestone", 40
        )
        reason = "A canonical mating exists and pregnancy is not yet confirmed."
    elif (
        days_since_litter is not None
        and days_since_litter <= 56
        and not all(observed_checks.values())
    ):
        state, action, priority = (
            "Recovery incomplete", "post-litter recovery check", 20
        )
        reason = f"The latest litter was {days_since_litter} days ago."
    elif weight_age is None or weight_age > WEIGHT_FRESH_DAYS:
        state, action, priority = (
            "Weigh or inspect again", "weigh before breeding decision", 25
        )
        reason = "Current weight evidence is missing or stale."
    elif latest_bcs is None:
        state, action, priority = (
            "Weigh or inspect again", "inspect for breeding readiness", 30
        )
        reason = "Current body-condition evidence is missing."
    elif hold_reasons:
        state, action, priority = (
            "Needs Data", "resolve evidence before mating review", 22
        )
        reason = "Missing: " + ", ".join(hold_reasons) + "."
    elif latest_heat == "observed":
        state, action, priority = (
            "Ready for mating review", "prepare for mating", 28
        )
        reason = "Fresh standing heat and baseline readiness evidence are present."
    else:
        state, action, priority = (
            "Observe for heat", "observe for standing heat", 32
        )
        reason = "No fresh affirmative standing-heat observation is present."
    return {
        "state": state,
        "task_group": action,
        "priority": priority,
        "reason": reason,
        "canonical_mating_exists": bool(
            _text(latest_mating.get("mating_id"))
        ),
        "latest_mating_date": _date_text(mating_date),
        "days_since_mating": days_since_mating,
        "expected_pregnancy_check": _text(
            latest_mating.get("expected_pregnancy_check_date")
        ) or None,
        "expected_farrowing": _text(
            latest_mating.get("expected_farrowing_date")
        ) or None,
        "latest_litter_date": _date_text(litter_date),
        "days_since_litter": days_since_litter,
        "unsuccessful_service_count": len(unsuccessful),
        "current_heat": latest_heat or "unknown",
        "body_condition": latest_bcs,
        "observed_checks": observed_checks,
        "hold_reasons": hold_reasons,
        "missing": list(attention.get("missing_facts") or []),
        "conflicting": list(attention.get("conflicting_facts") or []),
        "confidence": attention.get("confidence") or "Limited",
    }


def _task(
    attention, readiness, classification, observations, male_recommendation,
    week_start, generated_at,
):
    if classification["task_group"] == "monitor next milestone":
        return None
    if (
        classification["state"] == "Pregnancy evidence pending"
        and classification["task_group"]
        == "monitor pregnancy and farrowing milestones"
    ):
        return None
    required = _required_checks(classification)
    observed_this_week = [
        row for row in observations
        if (_date(row.get("observed_at")) or date.min) >= week_start
    ]
    completed = (
        bool(observed_this_week)
        and not required
        and classification["task_group"] in {
            "post-litter recovery check",
            "weigh before breeding decision",
            "inspect for breeding readiness",
            "observe for standing heat",
        }
    )
    evidence = {
        "state": classification["state"],
        "missing": classification["missing"],
        "conflicting": classification["conflicting"],
        "latest_weight_date": readiness.get("latest_weight_date"),
        "latest_mating_date": classification["latest_mating_date"],
        "latest_litter_date": classification["latest_litter_date"],
        "male_recommendation_state": male_recommendation["status"],
    }
    task_id = _stable_id(
        "HERD-TASK", week_start.isoformat(), attention.get("pig_id"), evidence
    )
    return {
        "task_id": task_id,
        "week_start": week_start.isoformat(),
        "pig_id": _text(attention.get("pig_id")),
        "tag_number": _text(attention.get("tag_number"))
        or _text(attention.get("pig_id")),
        "animal_href": attention.get("animal_href"),
        "priority": classification["priority"],
        "task_group": classification["task_group"],
        "why": classification["reason"],
        "known_evidence": _known_evidence(classification, readiness),
        "required_checks": required,
        "provisional_recommendation": classification["state"],
        "delay_consequence": _delay_consequence(classification["task_group"]),
        "male_recommendation": male_recommendation,
        "evidence_generation": generated_at,
        "evidence_digest": _digest(evidence),
        "completed": completed,
        "completed_by_existing_evidence": completed,
        "notification": {
            "deduplication_key": _stable_id("HERD-NOTIFY", task_id),
            "send_required": True,
            "sent": False,
            "delivery_operational": False,
        },
        "writes_performed": False,
    }


def _rank_males(female, males, all_matings, classification):
    if classification["state"] != "Ready for mating review":
        return {
            "status": "Not yet applicable",
            "recommended": None,
            "alternatives": [],
            "blockers": ["Female readiness review is incomplete."],
        }
    ranked = []
    female_parents = {
        _text(female.get("mother_id")), _text(female.get("father_id"))
    } - {""}
    for male in males:
        blockers = []
        if _norm(male.get("purpose")) != "breeding":
            blockers.append("purpose is not affirmatively Breeding")
        if _norm(male.get("medical_status") or male.get("health_status")) not in {
            "clear", "eligible",
        }:
            blockers.append("medical evidence is not clear")
        if _norm(male.get("withdrawal_evidence_state")) not in {
            "cleared", "not_applicable",
        }:
            blockers.append("withdrawal evidence is incomplete")
        if _norm(male.get("available_for_breeding")) not in {
            "available", "yes", "true",
        }:
            blockers.append("breeding availability is not affirmative")
        male_parents = {
            _text(male.get("mother_id")), _text(male.get("father_id"))
        } - {""}
        if not female_parents or not male_parents:
            blockers.append("family-tree comparison is incomplete")
        elif female_parents & male_parents:
            blockers.append("shared parent evidence")
        prior_pairings = sum(
            1 for row in all_matings
            if _text(row.get("sow_pig_id")) == _text(female.get("pig_id"))
            and _text(row.get("boar_pig_id")) == _text(male.get("pig_id"))
        )
        if not blockers:
            ranked.append({
                "pig_id": _text(male.get("pig_id")),
                "tag_number": _text(male.get("tag_number"))
                or _text(male.get("pig_id")),
                "score": 100 - min(prior_pairings * 10, 30),
                "reasoning": [
                    "Active breeding-purpose male.",
                    "Medical and withdrawal evidence are affirmative.",
                    "No shared parent is present in the bounded comparison.",
                    f"Previous pairing count: {prior_pairings}.",
                ],
            })
    ranked.sort(key=lambda row: (
        -row["score"], row["tag_number"], row["pig_id"]
    ))
    if not ranked:
        return {
            "status": "Unavailable",
            "recommended": None,
            "alternatives": [],
            "blockers": [
                "No male has complete affirmative compatibility evidence."
            ],
        }
    tied = len(ranked) > 1 and ranked[0]["score"] == ranked[1]["score"]
    return {
        "status": "Owner choice required" if tied else "Available",
        "recommended": None if tied else ranked[0],
        "alternatives": ranked[:3],
        "blockers": (
            ["Evidence cannot distinguish the top compatible males."]
            if tied else []
        ),
    }


def _approval_packet(
    female, classification, male_recommendation, generated_at, today
):
    male = male_recommendation.get("recommended")
    if classification["state"] != "Ready for mating review" or not male:
        return {
            "status": "Not ready",
            "approval_required": True,
            "execution_enabled": False,
        }
    proposed = {
        "female_pig_id": _text(female.get("pig_id")),
        "female_tag": _text(female.get("tag_number")),
        "male_pig_id": male["pig_id"],
        "male_tag": male["tag_number"],
        "proposed_mating_date": today.isoformat(),
        "mating_method": "Natural",
        "evidence_generation": generated_at,
        "recommendation_state": classification["state"],
    }
    return {
        "status": "Awaiting explicit owner decision",
        "approval_packet_id": _stable_id("HERD-MATING-PLAN", proposed),
        "proposed_record": proposed,
        "existing_governed_writer": "save_new_mating",
        "known_fields_autofilled": True,
        "stale_approval_rejected": True,
        "exact_replay_withheld": True,
        "approval_required": True,
        "execution_enabled": False,
    }


def _milestones(matings, today):
    if not matings:
        return []
    latest = matings[0]
    mating_date = _date(latest.get("mating_date"))
    if not mating_date:
        return []
    values = [
        ("Return-to-heat observation window", mating_date + timedelta(days=18)),
        ("Pregnancy-check window", _date(
            latest.get("expected_pregnancy_check_date")
        ) or mating_date + timedelta(days=28)),
        ("Expected farrowing window", _date(
            latest.get("expected_farrowing_date")
        ) or mating_date + timedelta(days=114)),
    ]
    return [{
        "name": name,
        "date": value.isoformat(),
        "state": "Due" if value <= today else "Scheduled",
        "days_from_today": (value - today).days,
        "reminder_key": _stable_id(
            "HERD-MILESTONE", latest.get("mating_id"), name, value.isoformat()
        ),
    } for name, value in values]


def _reminder_plan(cases, today):
    due = []
    for case in cases:
        for milestone in case["milestones"]:
            if milestone["state"] == "Due":
                due.append({
                    "reminder_key": milestone["reminder_key"],
                    "tag_number": case["tag_number"],
                    "milestone": milestone["name"],
                    "due_date": milestone["date"],
                    "delivery_status": "not_sent",
                })
    return {
        "status": "Prepared" if due else "No due reminders",
        "due_count": len(due),
        "items": due,
        "deduplicated": True,
        "delivery_operational": False,
        "sent_count": 0,
    }


def _required_checks(classification):
    group = classification["task_group"]
    checks = {
        "post-litter recovery check": [
            "body condition", "movement", "visible concerns", "heat signs"
        ],
        "weigh before breeding decision": [
            "current weight", "body condition", "movement"
        ],
        "inspect for breeding readiness": [
            "body condition", "movement", "visible concerns", "heat signs"
        ],
        "observe for standing heat": ["heat signs"],
        "pregnancy check due": ["governed pregnancy check result"],
        "repeat-service review": [
            "service chronology", "body condition", "owner decision"
        ],
        "review medical or withdrawal hold": [
            "medical or withdrawal evidence"
        ],
        "resolve evidence before mating review": list(
            classification.get("hold_reasons") or ["missing evidence"]
        ),
        "prepare for mating": [],
    }
    required = list(checks.get(group, ["owner review"]))
    observed_checks = classification.get("observed_checks") or {}
    required = [
        item for item in required
        if not observed_checks.get(item, False)
    ]
    return required


def _extract_facts(text):
    lower = text.lower()
    facts = {}
    bcs = re.search(
        r"(?:body condition|condition|bcs)(?:\s+(?:is|about|around))?\s*"
        r"([1-5](?:\.[05])?)", lower
    )
    if bcs:
        facts["body_condition_score"] = float(bcs.group(1))
    weight = re.search(r"\b(\d{1,3}(?:\.\d+)?)\s*kg\b", lower)
    if weight:
        facts["weight_kg"] = float(weight.group(1))
    if re.search(r"\b(moving well|walking well|movement good|no limp)\b", lower):
        facts["feet_legs_movement"] = "no_visible_concern"
    elif re.search(r"\b(limp|lameness|struggling to move|movement concern)\b", lower):
        facts["feet_legs_movement"] = "concern"
    if re.search(r"\b(no injury|no injuries|no visible concern|looks good)\b", lower):
        facts["visible_injury"] = "none_observed"
    elif re.search(r"\b(injury|wound|swelling|visible concern)\b", lower):
        facts["visible_injury"] = "concern"
    if re.search(r"\b(no heat|not in heat|no standing heat)\b", lower):
        facts["standing_heat"] = "not_observed"
    elif re.search(r"\b(standing heat|in heat|heat signs present)\b", lower):
        facts["standing_heat"] = "observed"
    if re.search(r"\b(calm|easy to handle)\b", lower):
        facts["temperament"] = "calm"
    elif re.search(r"\b(difficult to handle|aggressive)\b", lower):
        facts["temperament"] = "difficult"
    return facts


def _ambiguities(text, facts):
    lower = text.lower()
    issues = []
    if "maybe heat" in lower or "might be in heat" in lower:
        issues.append("Were standing-heat signs directly observed: yes or no?")
    if "looks okay" in lower and not any(
        key in facts for key in (
            "body_condition_score", "feet_legs_movement", "visible_injury"
        )
    ):
        issues.append(
            "Please state body condition, movement, or visible concern "
            "separately rather than only saying 'okay'."
        )
    return issues


def _interpretation(facts):
    labels = {
        "body_condition_score": "body condition",
        "weight_kg": "measured weight",
        "feet_legs_movement": "movement",
        "visible_injury": "visible injury",
        "standing_heat": "standing heat",
        "temperament": "temperament",
    }
    return [
        {"fact": labels[key], "value": value, "directly_stated": True}
        for key, value in facts.items()
    ]


def _fact_resolves_check(facts, check):
    mapping = {
        "body condition": "body_condition_score",
        "current weight": "weight_kg",
        "movement": "feet_legs_movement",
        "visible concerns": "visible_injury",
        "heat signs": "standing_heat",
    }
    return mapping.get(check) in facts


def _known_evidence(classification, readiness):
    return {
        "state": classification["state"],
        "latest_weight_kg": readiness.get("latest_weight_kg"),
        "latest_weight_date": readiness.get("latest_weight_date") or None,
        "latest_mating_date": classification["latest_mating_date"],
        "latest_litter_date": classification["latest_litter_date"],
        "medical": _display(
            readiness.get("medical_status") or readiness.get("health_status")
        ),
        "withdrawal": _display(
            readiness.get("withdrawal_evidence_state")
        ),
        "family_tree": (
            "Available"
            if readiness.get("mother_id") and readiness.get("father_id")
            else "Incomplete"
        ),
    }


def _delay_consequence(group):
    return {
        "post-litter recovery check": "Recovery readiness remains uncertain.",
        "weigh before breeding decision": "Weight-based readiness remains unsupported.",
        "inspect for breeding readiness": "Mating consideration remains blocked.",
        "observe for standing heat": "The current heat window may be missed.",
        "pregnancy check due": "Pregnancy and farrowing planning remain uncertain.",
        "repeat-service review": "Another unsupported service may be attempted.",
        "review medical or withdrawal hold": "Breeding remains on hold.",
        "resolve evidence before mating review": "The unsupported conclusion remains blocked.",
        "prepare for mating": "The observed heat opportunity may pass.",
    }.get(group, "The evidence gap remains unresolved.")


def _mating_summary(rows, today):
    return [{
        "mating_id": _text(row.get("mating_id")),
        "date": _text(row.get("mating_date")) or None,
        "boar_tag": _text(row.get("boar_tag_number"))
        or _text(row.get("boar_pig_id")) or None,
        "status": _display(row.get("mating_status")),
        "pregnancy_result": _display(row.get("pregnancy_check_result")),
        "outcome": _display(row.get("outcome")),
        "canonical_mating": True,
    } for row in rows]


def _litter_summary(rows, today):
    return [{
        "litter_id": _text(row.get("litter_id")),
        "farrowing_date": _text(
            row.get("farrowing_date") or row.get("birth_date")
        ) or None,
        "born_alive": row.get("born_alive"),
        "weaned_count": row.get("weaned_count"),
        "wean_date": _text(row.get("wean_date")) or None,
        "status": _display(row.get("litter_status")),
    } for row in rows]


def _observation_summary(rows):
    return [{
        "observation_event_id": row["observation_event_id"],
        "observed_at": row["observed_at"],
        "categories": sorted(
            key for key in row["measurements"]
            if key != "contract_version"
        ),
        "immutable": True,
    } for row in rows]


def _group(rows, key, date_key):
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        identity = _text(row.get(key))
        if identity:
            result.setdefault(identity, []).append(row)
    for values in result.values():
        values.sort(
            key=lambda row: (
                _text(row.get(date_key)),
                _text(row.get("mating_id") or row.get("litter_id")),
            ),
            reverse=True,
        )
    return result


def _group_observations(rows):
    result = {}
    for row in rows:
        if isinstance(row, dict):
            pig_id = _text(row.get("pig_id"))
            observed = row.get("observed_at")
            measurements = row.get("measurements_json")
            event_id = row.get("observation_event_id")
        else:
            pig_id, observed, _category, measurements, event_id = row[:5]
            pig_id = _text(pig_id)
        if not pig_id:
            continue
        result.setdefault(pig_id, []).append({
            "pig_id": pig_id,
            "observed_at": (
                observed.isoformat()
                if isinstance(observed, datetime) else _text(observed)
            ),
            "measurements": (
                measurements if isinstance(measurements, dict) else {}
            ),
            "observation_event_id": _text(event_id),
        })
    for values in result.values():
        values.sort(
            key=lambda row: (
                row["observed_at"], row["observation_event_id"]
            ),
            reverse=True,
        )
    return result


def _latest_measurement(rows, key):
    for row in rows:
        value = row["measurements"].get(key)
        if value not in (None, "", "not_recorded"):
            return value
    return None


def _mentions(text, value):
    value = _text(value)
    return bool(value) and value.lower() in text.lower()


def _stable_id(prefix, *parts):
    digest = hashlib.sha256(json.dumps(
        parts, sort_keys=True, separators=(",", ":"), default=str
    ).encode()).hexdigest()[:32].upper()
    return f"{prefix}-{digest}"


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()).hexdigest()


def _preview_error(status, clarification=None, **extra):
    return {
        "success": False,
        "status": status,
        "needs_clarification": bool(clarification),
        "clarification": clarification,
        "writes_performed": False,
        "protected_actions_performed": False,
        **extra,
    }


def _valid(attention, readiness, matings, litters, observations):
    return (
        isinstance(attention, dict) and attention.get("success") is True
        and isinstance(attention.get("animals"), list)
        and isinstance(readiness, dict) and readiness.get("success") is True
        and isinstance(readiness.get("pigs"), list)
        and all(isinstance(value, list) for value in (
            matings, litters, observations,
        ))
    )


def _unavailable(generated_at):
    return {
        "success": False,
        "contract_version": CONTRACT_VERSION,
        "generated_at": generated_at,
        "worklist_status": "Unavailable",
        "task_count": None,
        "tasks": [],
        "cases": [],
        "notification_delivery_operational": False,
        "mating_execution_enabled": False,
        "observation_recording_enabled": False,
        "owner_only": True,
        "writes_performed": False,
        "protected_actions_performed": False,
        "limitations": ["Canonical breeding evidence is unavailable."],
    }


def _text(value):
    return str(value or "").strip()


def _norm(value):
    return _text(value).lower().replace(" ", "_").replace("-", "_")


def _display(value):
    value = _text(value)
    return value.replace("_", " ") if value else "Unknown"


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_text(value)[:10])
    except ValueError:
        return None


def _date_text(value):
    value = _date(value)
    return value.isoformat() if value else None
