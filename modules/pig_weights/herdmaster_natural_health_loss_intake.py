"""Pure HERDMASTER natural health/loss intake evaluator.

The caller supplies authenticated report metadata and complete canonical
evidence.  This module performs no I/O and grants no write authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo


CONTRACT_VERSION = "herdmaster_natural_health_loss_intake_v1"
RESULT_FAMILIES = {
    "sick", "injured", "found_dead", "farrowing_complication",
    "piglet_loss", "compound_event",
}
AUTHORITY = {
    "zero_io": True,
    "writes_performed": False,
    "farm_write_authority": False,
    "medical_authority": False,
    "lifecycle_authority": False,
    "mating_authority": False,
    "litter_authority": False,
    "movement_authority": False,
    "availability_authority": False,
    "customer_authority": False,
    "confirmation_received": False,
}
TRANSACTION_POLICY = {
    "execution_authorized": False,
    "future_write_mode": "atomic_all_supported_effects",
    "confirmation_binding": "exact_operation_id_and_evidence_generation",
    "partial_write_allowed": False,
    "replay_requirement": "zero_rows_changed",
}


class IntakeEvidenceError(ValueError):
    """The supplied authenticated/canonical packet is unsafe to evaluate."""


def evaluate_health_loss_intake(report: Mapping, canonical: Mapping) -> dict:
    """Return a complete zero-write interpretation and consolidated preview."""
    report = _mapping(report, "report")
    canonical = _mapping(canonical, "canonical")
    if report.get("authenticated") is not True:
        raise IntakeEvidenceError("authenticated_report_required")
    text = _clean(report.get("text"), 4000)
    if not text:
        raise IntakeEvidenceError("report_text_required")
    provider_time = _provider_time(report)
    if not _clean(report.get("provider_message_id"), 200):
        raise IntakeEvidenceError("provider_message_id_required")
    if not _clean(report.get("authenticated_principal_id"), 200):
        raise IntakeEvidenceError("authenticated_principal_required")
    if not _clean(canonical.get("evidence_generation"), 120):
        raise IntakeEvidenceError("evidence_generation_required")
    as_of = _strict_datetime(canonical.get("as_of_timestamp"), "as_of_timestamp")
    if provider_time > as_of + timedelta(minutes=5):
        raise IntakeEvidenceError("provider_timestamp_future_or_skewed")
    animals = [_mapping(row, "animal") for row in canonical.get("animals", [])]
    pig_ids = [_clean(row.get("pig_id"), 80) for row in animals]
    if any(not pig_id for pig_id in pig_ids) or len(pig_ids) != len(set(pig_ids)):
        raise IntakeEvidenceError("canonical_animal_identity_invalid_or_duplicate")
    matches = _identity_matches(text, animals)
    identity = _identity_result(matches)
    if not identity["resolved"]:
        return _result(
            status="identity_required",
            identity=identity,
            family="unknown",
            question=identity["question"],
            provider_time=provider_time,
        )

    animal = matches[0]
    parsed = _parse_report(text, provider_time)
    if parsed["family"] == "unknown":
        return _result(
            status="event_details_required", identity=identity, family="unknown",
            question=f"What exactly did you observe about {_display(animal)}?",
            provider_time=provider_time,
        )
    chronology = _chronology(animal, parsed, canonical)
    if chronology["conflicts"]:
        return _result(
            status="chronology_conflict",
            identity=identity,
            family=parsed["family"],
            question=chronology["question"],
            provider_time=provider_time,
            observed=parsed["observed"],
            suspected=parsed["suspected"],
            veterinary=parsed["veterinary"],
            inference=parsed["inference"],
            conflicts=chronology["conflicts"],
        )

    effects, confirmations, missing = _effects(
        animal, parsed, canonical, chronology
    )
    question = _smallest_question(parsed, missing, animal)
    before = _before(animal, chronology)
    operation_id = _operation_identity(
        report, animal, parsed, chronology, effects, canonical,
        confirmations, missing, before,
    )
    preview = {
        "title": "Natural health and loss intake preview",
        "operation_id": operation_id,
        "animal": _animal_identity(animal),
        "event_family": parsed["family"],
        "event_date": parsed["event_date"],
        "owner_report_text": text,
        "before": before,
        "after": _after(before, effects),
        "observed_facts": parsed["observed"],
        "owner_suspected_cause": parsed["suspected"],
        "veterinary_evidence": parsed["veterinary"],
        "agent_inference": parsed["inference"],
        "proposed_canonical_effects": effects,
        "intentionally_unchanged": _unchanged(effects),
        "required_confirmations": confirmations,
        "transaction_policy": TRANSACTION_POLICY,
        "confirmation_prompt": (
            "Confirm this exact consolidated preview before any governed "
            "recording. Confirmation must bind the operation identity and "
            "canonical evidence generation."
        ),
    }
    preview_sha256 = _digest(preview)
    return {
        "success": True,
        "status": "preview_ready" if not missing else "partial_preview_ready",
        "contract_version": CONTRACT_VERSION,
        "provider_report_time": provider_time.isoformat(),
        "identity": identity,
        "event_family": parsed["family"],
        "owner_report_text": text,
        "observed_facts": parsed["observed"],
        "owner_suspected_cause": parsed["suspected"],
        "veterinary_evidence": parsed["veterinary"],
        "agent_inference": parsed["inference"],
        "immediate_welfare_priority": _welfare(parsed),
        "smallest_missing_follow_up_question": question,
        "missing_evidence": missing,
        "canonical_effects": effects,
        "preview": preview,
        "required_confirmations": confirmations,
        "operation_id": operation_id,
        "preview_sha256": preview_sha256,
        "confirmation_binding": {
            "operation_id": operation_id,
            "preview_sha256": preview_sha256,
            "evidence_generation": _clean(canonical.get("evidence_generation"), 120),
            "required_confirmations": confirmations,
        },
        "evidence_generation": _clean(canonical.get("evidence_generation"), 120),
        "transaction_policy": TRANSACTION_POLICY,
        **AUTHORITY,
    }


def _mapping(value, label):
    if not isinstance(value, Mapping):
        raise IntakeEvidenceError(f"{label}_mapping_required")
    return dict(value)


def _provider_time(report):
    raw = _clean(report.get("provider_timestamp"), 120)
    if not raw:
        raise IntakeEvidenceError("provider_timestamp_required")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntakeEvidenceError("provider_timestamp_invalid") from exc
    if value.tzinfo is None:
        raise IntakeEvidenceError("provider_timestamp_timezone_required")
    zone_name = _clean(report.get("provider_timezone"), 80) or "Africa/Johannesburg"
    try:
        return value.astimezone(ZoneInfo(zone_name))
    except Exception as exc:
        raise IntakeEvidenceError("provider_timezone_invalid") from exc


def _identity_matches(text, animals):
    lower = text.casefold()
    exact_ids = set(re.findall(r"\bPIG-\d{4}-[A-Z0-9]{4}\b", text.upper()))
    tag_matches = set(re.findall(r"\b(?:tag|pig)\s*#?([A-Za-z0-9-]+)\b", text, re.I))
    matches = []
    for animal in animals:
        pig_id = _clean(animal.get("pig_id"), 80)
        tag = _clean(animal.get("tag_number"), 120)
        name = _clean(animal.get("name") or tag, 120)
        selected = pig_id in exact_ids
        selected = selected or bool(tag and tag.casefold() in {x.casefold() for x in tag_matches})
        selected = selected or bool(
            name and re.search(rf"(?<!\w){re.escape(name.casefold())}(?!\w)", lower)
        )
        if selected:
            matches.append(animal)
    return sorted(matches, key=lambda row: _clean(row.get("pig_id"), 80))


def _identity_result(matches):
    if len(matches) == 1:
        return {"resolved": True, **_animal_identity(matches[0]), "question": ""}
    if not matches:
        return {
            "resolved": False, "pig_id": "", "tag_number": "",
            "question": "Which exact pig is this—please give its Pig ID or tag?",
            "candidate_pig_ids": [],
        }
    candidates = [_animal_identity(row) for row in matches]
    labels = ", ".join(
        f"{row['tag_number']} ({row['pig_id']})" for row in candidates
    )
    return {
        "resolved": False, "pig_id": "", "tag_number": "",
        "question": f"Which one do you mean: {labels}?",
        "candidate_pig_ids": [row["pig_id"] for row in candidates],
    }


def _parse_report(text, provider_time):
    lower = text.casefold()
    reported_died = bool(re.search(
        r"\bdied\b|\b(?:is|was) dead(?=\s*(?:[.!?,;:]|$)|\s+(?:and\s+)?"
        r"(?:(?:was\s+)?buried|(?:was\s+)?removed|gone|no longer alive)\b)",
        lower,
    ))
    found_dead = bool(
        re.search(r"\bfound(?:\s+.+?)?\s+dead\b", lower)
        or re.search(r"\bwas dead(?:\s+when|\s+in|\s+at|[.!?]|$)", lower)
    )
    dead = reported_died or found_dead
    farrowing = bool(re.search(r"\b(farrow|farrowing|gave birth)\b", lower))
    stillborn_match = re.search(r"(all\s+)?(\d+)\s+piglets?\s+(?:were\s+)?stillborn", lower)
    later_death_match = re.search(
        r"(\d+)\s+piglets?\s+(?:were\s+)?born alive(?:\s+but)?\s+(?:then\s+)?died", lower
    )
    total_match = re.search(r"(?:total(?: born)?|in total)\s*(?:was|were|of|:)?\s*(\d+)", lower)
    def latest_positive(positive_pattern, negative_pattern, subject):
        negative_matches = list(re.finditer(negative_pattern, subject))
        positive = [
            match.end()
            for match in re.finditer(positive_pattern, subject)
            if not any(
                match.start() < negative.end() and negative.start() < match.end()
                for negative in negative_matches
            )
        ]
        negative = [match.end() for match in negative_matches]
        if not positive:
            return False
        return not negative or max(positive) > max(negative)

    def latest_negative(positive_pattern, negative_pattern, subject):
        negative_matches = list(re.finditer(negative_pattern, subject))
        positive_matches = [
            match
            for match in re.finditer(positive_pattern, subject)
            if not any(
                match.start() < negative.end() and negative.start() < match.end()
                for negative in negative_matches
            )
        ]
        if not negative_matches:
            return False
        return not positive_matches or max(match.end() for match in negative_matches) > max(
            match.end() for match in positive_matches
        )

    def welfare_evidence(positive_pattern, negative_pattern):
        if latest_negative(positive_pattern, negative_pattern, lower):
            return "no"
        if latest_positive(positive_pattern, negative_pattern, lower):
            return "yes"
        return "unknown"

    def current_sign(pattern):
        return latest_positive(
            rf"\b(?:{pattern})\w*\b",
            rf"\b(?:no|not|without)\s+(?:any\s+)?(?:(?:\w+)\s*(?:,\s*(?:and\s+|or\s+)?|and\s+|or\s+)){{0,4}}(?:{pattern})\w*\b",
            lower,
        )

    injured = current_sign(r"injur|limp|wound|bleed|broken|swollen")
    eating_positive = r"\b(?:is|was)?\s*eating(?: food|normally|again|now)?\b|\bappetite (?:is )?(?:normal|back)\b"
    eating_negative = r"\b(?:not|no longer|isn't|wasn't|without) eating\b|\b(?:cannot|can't|unable to|stopped|barely|hardly|scarcely) eat(?:ing)?\b|\b(?:no|poor|reduced) appetite\b"
    drinking_positive = r"\bdrinking(?: water)?\b"
    drinking_negative = r"\b(?:not|no longer|isn't|wasn't|without) drinking\b|\bdrinking no water\b|\b(?:cannot|can't|unable to|stopped|barely|hardly|scarcely) drink(?:ing)?\b"
    not_eating = latest_negative(eating_positive, eating_negative, lower)
    not_drinking = latest_negative(drinking_positive, drinking_negative, lower)
    other_sick = current_sign(r"sick|ill|vomit|diarrh|cough|fever")
    sick = not_eating or not_drinking or other_sick
    severe_sick = not_drinking or other_sick
    complications = bool(re.search(r"\bcomplication\w*\b", lower))
    families = []
    if dead:
        families.append("found_dead")
    if farrowing or complications:
        families.append("farrowing_complication")
    if stillborn_match or later_death_match:
        families.append("piglet_loss")
    if injured:
        families.append("injured")
    if sick:
        families.append("sick")
    family = families[0] if len(set(families)) == 1 else "compound_event" if families else "unknown"
    event_date = provider_time.date()
    if "yesterday" in lower:
        event_date -= timedelta(days=1)
    observed = []
    if dead:
        observed.append({"fact": "animal_reported_dead", "value": True})
    if complications:
        observed.append({"fact": "farrowing_complications_reported", "value": True})
    stillborn_count = int(stillborn_match.group(2)) if stillborn_match else 0
    later_death_count = int(later_death_match.group(1)) if later_death_match else 0
    explicit_total = int(total_match.group(1)) if total_match else None
    complete_outcomes = bool(
        (stillborn_match and stillborn_match.group(1))
        or (explicit_total is not None and explicit_total == stillborn_count + later_death_count)
    )
    if stillborn_match or later_death_match:
        if complete_outcomes:
            observed.extend([
                {"fact": "total_born", "value": stillborn_count + later_death_count},
                {"fact": "born_alive", "value": later_death_count},
                {"fact": "stillborn", "value": stillborn_count},
                {"fact": "later_deaths", "value": later_death_count},
            ])
        else:
            if stillborn_match:
                observed.append({"fact": "reported_stillborn_count", "value": stillborn_count})
            if later_death_match:
                observed.extend([
                    {"fact": "reported_born_alive_count", "value": later_death_count},
                    {"fact": "reported_later_deaths", "value": later_death_count},
                ])
    if not_eating:
        observed.append({"fact": "not_eating", "value": True})
    if not_drinking:
        observed.append({"fact": "not_drinking", "value": True})
    if current_sign(r"limp"):
        observed.append({"fact": "limping", "value": True})
    if current_sign(r"bleed"):
        observed.append({"fact": "bleeding", "value": True})
    welfare_checks = {
        "standing": latest_positive(
            r"\b(?:can|able to) stand\b|\b(?:is|was) standing\b",
            r"\b(?:not|no longer|cannot|can't|isn't|wasn't|without)\s+(?:being\s+|able to\s+)?(?:stand|standing)\b|\b(?:unable to|stopped|barely|hardly|scarcely)(?: able to)? stand(?:ing)?\b",
            lower,
        ),
        "moving": latest_positive(
            r"\bmoving(?: around)?\b",
            r"\b(?:not|no longer|isn't|wasn't|without) moving\b|\b(?:cannot|can't|unable to|stopped|barely|hardly|scarcely) mov(?:e|ing)\b",
            lower,
        ),
        "breathing": latest_positive(
            r"\bbreath(?:ing|es) normal(?:ly)?\b",
            r"\b(?:not|no longer|isn't|wasn't|without) breathing normal(?:ly)?\b|\b(?:cannot|can't|unable to|stopped|barely|hardly|scarcely) breath(?:e|ing)(?: normal(?:ly)?)?\b|\b(?:breathing abnormally|struggling to breathe)\b",
            lower,
        ),
        "drinking": latest_positive(
            drinking_positive,
            drinking_negative,
            lower,
        ),
    }
    welfare_check_evidence = {
        "standing": welfare_evidence(
            r"\b(?:can|able to) stand\b|\b(?:is|was) standing\b",
            r"\b(?:not|no longer|cannot|can't|isn't|wasn't|without)\s+(?:being\s+|able to\s+)?(?:stand|standing)\b|\b(?:unable to|stopped|barely|hardly|scarcely)(?: able to)? stand(?:ing)?\b|\bnot able to do anything\b"),
        "moving": welfare_evidence(r"\bmoving(?: around)?\b",
            r"\b(?:not|no longer|isn't|wasn't|without) moving\b|\b(?:cannot|can't|unable to|stopped|barely|hardly|scarcely) mov(?:e|ing)\b|\bnot able to do anything\b"),
        "breathing": welfare_evidence(r"\bbreath(?:ing|es) normal(?:ly)?\b",
            r"\b(?:not|no longer|isn't|wasn't|without) breathing normal(?:ly)?\b|\b(?:cannot|can't|unable to|stopped|barely|hardly|scarcely) breath(?:e|ing)(?: normal(?:ly)?)?\b|\b(?:breathing abnormally|struggling to breathe)\b"),
        "drinking": welfare_evidence(drinking_positive,
            drinking_negative + r"|\bnot able to do anything\b"),
    }
    if re.search(r"\bnot able to do anything\b", lower):
        observed.extend([
            {"fact": "unable_to_stand", "value": True, "attribution": "owner_reported"},
            {"fact": "not_drinking", "value": True, "attribution": "owner_reported_apparent"},
            {"fact": "unable_to_function_normally", "value": True, "attribution": "owner_reported_apparent"},
        ])
    if re.search(r"\b(?:last breath|last breathe|not going to make it)\b", lower):
        observed.append({"fact": "apparently_close_to_death", "value": True,
                         "attribution": "owner_reported_not_diagnosis"})
    for fact, supplied in welfare_checks.items():
        if supplied:
            observed.append({"fact": f"{fact}_reported", "value": True})
    time_context = r"(?:today|yesterday|(?:this\s+)?morning|(?:this\s+)?afternoon|(?:this\s+)?evening|(?:last\s+)?night|\d{1,2}[:.]\d{2})"
    last_seen = re.search(rf"\b(?:last\s+)?seen alive(?:\s+(?P<when>{time_context}))?\b", lower)
    found_words = list(re.finditer(r"\bfound\b", lower))
    time_words = list(re.finditer(rf"\b(?P<when>{time_context})\b", lower))
    found_time = min(
        (time for time in time_words for found in found_words
         if min(abs(time.end() - found.start()), abs(found.end() - time.start())) <= 100),
        key=lambda time: min(abs(time.end() - found.start()) for found in found_words),
        default=None,
    )
    last_seen_supplied = bool(last_seen)
    found_time_supplied = bool(found_time)
    removal_supplied = bool(re.search(r"\b(?:removed from (?:the )?pen|buried|disposed|cremated)\b", lower))
    removal_outcome = (
        "removed and buried" if re.search(r"\bremoved\b.{0,40}\bburied\b", lower)
        else "buried" if re.search(r"\bburied\b", lower)
        else "cremated" if re.search(r"\bcremated\b", lower)
        else "disposed" if re.search(r"\bdisposed\b", lower)
        else "removed from pen" if removal_supplied else ""
    )
    if last_seen_supplied:
        observed.append({"fact": "last_seen_alive_context_reported",
                         "value": (last_seen.group("when") if last_seen and last_seen.group("when") else True)})
    if found_time_supplied:
        observed.append({"fact": "body_found_time_context_reported",
                         "value": (found_time.group("when") if found_time and found_time.group("when") else True)})
    biosecurity_plan = re.search(r"\bgoing to\s+(spray\b[^.!?]*)", text, re.I)
    if biosecurity_plan:
        observed.append({"fact": "future_biosecurity_intention_reported",
                         "value": biosecurity_plan.group(1).strip(),
                         "classification": "unverified_owner_wording_not_canonical_effect"})
    if removal_supplied:
        observed.append({"fact": "removal_or_disposal_context_reported", "value": True})
    observed.append({"fact": "event_date", "value": event_date.isoformat()})
    suspected = []
    suspect = re.search(r"(?:believe|think|suspect)(?:\s+that)?\s+(?:she|he|it)?\s*(?:had|has|was)?\s+([^.!?]+)", lower)
    if suspect:
        suspected.append({
            "cause": suspect.group(1).strip(),
            "classification": "owner_suspected_not_diagnosed",
        })
    veterinary = []
    vet = re.search(r"(?:vet|veterinarian)\s+(?:confirmed|diagnosed)\s+([^.!?]+)", lower)
    if vet:
        veterinary.append({"diagnosis": vet.group(1).strip(), "attribution": "owner_reported_veterinary_evidence"})
    return {
        "family": family, "families": sorted(set(families)),
        "event_date": event_date.isoformat(), "observed": observed,
        "suspected": suspected, "veterinary": veterinary, "inference": [],
        "dead": dead, "reported_died": reported_died, "found_dead": found_dead,
        "farrowing": farrowing or complications,
        "stillborn_count": stillborn_count if stillborn_match else None,
        "later_death_count": later_death_count if later_death_match else None,
        "complete_birth_outcomes": complete_outcomes,
        "welfare_checks": welfare_checks,
        "welfare_check_evidence": welfare_check_evidence,
        "last_seen_supplied": last_seen_supplied,
        "found_time_supplied": found_time_supplied,
        "removal_supplied": removal_supplied,
        "removal_outcome": removal_outcome,
        "current_signs": sick or injured,
        "severe_signs": injured or severe_sick or complications,
    }


def _chronology(animal, parsed, canonical):
    event_date = datetime.fromisoformat(parsed["event_date"]).date()
    conflicts = []
    status_date = _clean(animal.get("lifecycle_effective_date"), 20)
    if status_date:
        try:
            governed_status_date = datetime.fromisoformat(status_date).date()
        except ValueError:
            conflicts.append("canonical lifecycle effective date is malformed")
        else:
            if governed_status_date > event_date:
                conflicts.append("newer lifecycle chronology conflicts with reported event date")
    birth_date = _clean(animal.get("birth_date"), 20)
    if birth_date:
        try:
            if datetime.fromisoformat(birth_date).date() > event_date:
                conflicts.append("reported event predates canonical birth date")
        except ValueError:
            conflicts.append("canonical birth date is malformed")
    lifecycle = _clean(animal.get("lifecycle_status"), 80).casefold()
    if parsed["dead"] and lifecycle in {"dead", "deceased", "sold", "removed", "retired"}:
        conflicts.append("canonical lifecycle is already terminal")
    matings = [row for row in canonical.get("matings", [])
               if row.get("sow_pig_id") == animal.get("pig_id") and row.get("is_open") is True]
    if len(matings) > 1:
        conflicts.append("multiple open mating cycles")
    mating = matings[0] if len(matings) == 1 else None
    if parsed["farrowing"] and mating:
        try:
            mating_date = datetime.fromisoformat(str(mating.get("date"))).date()
            days = (event_date - mating_date).days
        except ValueError:
            conflicts.append("current mating date is malformed")
        else:
            if days < 0 or days > 125:
                conflicts.append("current mating is outside the governed farrowing cycle boundary")
    if parsed["farrowing"]:
        matching_litters = [row for row in canonical.get("litters", [])
                            if row.get("sow_pig_id") == animal.get("pig_id")
                            and _clean(row.get("farrowing_date"), 20) == event_date.isoformat()]
        if matching_litters:
            conflicts.append("canonical litter already exists for this sow and farrowing date")
    question = ""
    if conflicts:
        question = "The canonical chronology conflicts with this report; which event date or cycle is correct?"
    return {"mating": mating, "conflicts": conflicts, "question": question}


def _effects(animal, parsed, canonical, chronology):
    effects, confirmations, missing = [], [], []
    def add(area, action, facts, confirmation, supported=True):
        effects.append({"area": area, "action": action, "facts": facts, "supported": supported})
        if confirmation and supported:
            confirmations.append(confirmation)

    if parsed["dead"]:
        add("lifecycle", "record_death", {
            "date": parsed["event_date"], "time": "Unknown",
            "evidence_basis": "owner_reported_found_dead_or_died",
            "discovery_context_is_not_exact_time_of_death": True,
            "resulting_status": "Deceased", "resulting_on_farm": False,
        }, "confirm_lifecycle_death")
    if parsed["dead"]:
        add("availability", "remove_from_current_active_sale_and_breeding_projections", {
            "current_availability": False, "historical_sales_and_breeding_records_preserved": True,
        }, "confirm_availability_effect")
        add("downstream_work", "close_or_replace_future_animal_tasks", {
            "preserve_mortality_follow_up": True, "reassess_herd_counts": True,
        }, "confirm_downstream_work_effect")
        if parsed["removal_supplied"]:
            add("movement_pen", "record_reported_removal_or_disposal_context", {
                "owner_reported_context": True, "current_pen_occupancy": "remove animal",
                "historical_movements_preserved": True,
                "owner_reported_outcome": parsed["removal_outcome"],
            }, "confirm_movement_pen_context")
        else:
            add("movement_pen", "leave_physical_removal_and_disposal_unknown", {}, "", supported=False)
            missing.append("physical removal/disposal evidence")
    if parsed["farrowing"]:
        mating = chronology["mating"]
        if mating:
            add("mating", "close_current_cycle_as_farrowed", {"mating_id": mating.get("mating_id")}, "confirm_mating_cycle_closure")
        else:
            add("mating", "no_change_without_exact_current_cycle", {}, "", supported=False)
            missing.append("exact current mating cycle")
        if parsed["complete_birth_outcomes"]:
            stillborn = parsed["stillborn_count"] or 0
            later_deaths = parsed["later_death_count"] or 0
            add("litter", "create_and_close_farrowing_litter", {
                "farrowing_date": parsed["event_date"],
                "total_born": stillborn + later_deaths,
                "born_alive": later_deaths, "stillborn": stillborn,
                "later_deaths": later_deaths,
                "generated_identity_disposition": "stillborn_not_live_birth; later_deaths_require_distinct_live_birth_identity",
            }, "confirm_litter_and_stillborn_effects")
        else:
            add("litter", "no_count_change_until_birth_outcomes_known", {}, "", supported=False)
            missing.append("piglet birth outcome counts")
    if parsed["current_signs"] or parsed["suspected"] or parsed["veterinary"] or parsed["farrowing"]:
        add("medical_observation", "record_reported_observation_context", {
            "observed": parsed["observed"], "owner_suspected": parsed["suspected"],
            "veterinary_evidence": parsed["veterinary"], "diagnosis_inferred": False,
        }, "confirm_medical_observation_effect")
    if not any(row["area"] == "movement_pen" for row in effects):
        add("movement_pen", "unchanged_without_reported_movement", {}, "", supported=False)
    return effects, sorted(set(confirmations)), sorted(set(missing))


def _smallest_question(parsed, missing, animal):
    if "piglet birth outcome counts" in missing:
        return "In total, how many were born alive, stillborn, mummified, or died after live birth?"
    if parsed["dead"] and "physical removal/disposal evidence" in missing:
        return f"Has {_display(animal)} been removed from the pen; if yes, when and what was the disposal/removal outcome?"
    if "exact current mating cycle" in missing:
        return f"Which exact current mating cycle applies to {_display(animal)}?"
    unknown = [key for key in ("standing", "breathing", "drinking")
               if parsed.get("welfare_check_evidence", {}).get(key) == "unknown"]
    if parsed["current_signs"] and unknown:
        if unknown == ["breathing"]:
            return f"Is {_display(animal)} breathing now, and does it look normal or distressed?"
        return f"Is {_display(animal)} able to stand, breathe normally and drink water right now?"
    return ""


def _welfare(parsed):
    if parsed["farrowing"] and not parsed["complete_birth_outcomes"]:
        return {"level": "emergency", "action": "Check immediately for a surviving sow or piglets and continuing farrowing; obtain experienced or veterinary assistance before record work."}
    if parsed["dead"]:
        return {"level": "urgent_follow_up", "action": "Check the pen, any surviving animals and biosecurity needs now; veterinary/mortality review may be required."}
    if parsed["farrowing"]:
        return {"level": "emergency", "action": "If the sow or any piglet is alive or farrowing is continuing, obtain immediate experienced or veterinary assistance before record work."}
    if (parsed["current_signs"] and not parsed.get("severe_signs")
            and all(parsed["welfare_checks"].get(key) for key in ("standing", "breathing", "drinking"))):
        return {"level": "monitor_closely", "action": "The immediate standing, breathing and drinking checks are reassuring; keep monitoring appetite and seek experienced or veterinary help if signs worsen or eating does not resume."}
    if parsed["current_signs"]:
        return {"level": "urgent_assessment", "action": "Physically assess breathing, standing, water intake, bleeding and distress now; seek veterinary help for serious signs."}
    return {"level": "review", "action": "Verify the animal and observable welfare state."}


def _before(animal, chronology):
    return {
        "lifecycle_status": animal.get("lifecycle_status", "Unknown"),
        "on_farm": animal.get("on_farm", "Unknown"),
        "availability": animal.get("availability", "Unknown"),
        "pen": animal.get("pen", "Unknown"),
        "current_mating_id": (chronology.get("mating") or {}).get("mating_id", "Unknown"),
    }


def _unchanged(effects):
    changed = {row["area"] for row in effects if row["supported"]}
    areas = [
        "lifecycle", "medication", "withdrawal", "feeding", "movement_pen",
        "availability", "reservation", "sales", "mating", "litter",
        "medical_observation", "downstream_work",
    ]
    return [area for area in areas if area not in changed]


def _operation_identity(report, animal, parsed, chronology, effects, canonical,
                        confirmations, missing, before):
    identity = {
        "contract": CONTRACT_VERSION,
        "provider_message_id": _clean(report.get("provider_message_id"), 200),
        "authenticated_principal_id": _clean(report.get("authenticated_principal_id"), 200),
        "provider_timestamp": _clean(report.get("provider_timestamp"), 120),
        "provider_timezone": _clean(report.get("provider_timezone"), 80),
        "owner_report_sha256": hashlib.sha256(
            _clean(report.get("text"), 4000).encode("utf-8")
        ).hexdigest(),
        "pig_id": animal.get("pig_id"), "event_date": parsed["event_date"],
        "family": parsed["family"], "observed": parsed["observed"],
        "suspected": parsed["suspected"], "veterinary": parsed["veterinary"],
        "mating_id": (chronology.get("mating") or {}).get("mating_id"),
        "canonical_evidence_generation": _clean(canonical.get("evidence_generation"), 120),
        "canonical_packet_sha256": _digest(canonical),
        "before": before, "effects": effects, "missing": missing,
        "required_confirmations": confirmations,
    }
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)
    return "HERD-HEALTH-LOSS-" + hashlib.sha256(raw.encode()).hexdigest()[:32].upper()


def _result(*, status, identity, family, question, provider_time, observed=None,
            suspected=None, veterinary=None, inference=None, conflicts=None):
    return {
        "success": False, "status": status, "contract_version": CONTRACT_VERSION,
        "provider_report_time": provider_time.isoformat(), "identity": identity,
        "event_family": family, "observed_facts": observed or [],
        "owner_suspected_cause": suspected or [], "veterinary_evidence": veterinary or [],
        "agent_inference": inference or [], "chronology_conflicts": conflicts or [],
        "smallest_missing_follow_up_question": question, "canonical_effects": [],
        "preview": {}, "required_confirmations": [], "operation_id": "",
        "transaction_policy": TRANSACTION_POLICY, **AUTHORITY,
    }


def _animal_identity(animal):
    return {
        "pig_id": _clean(animal.get("pig_id"), 80),
        "tag_number": _clean(animal.get("tag_number"), 120),
        "name": _clean(animal.get("name") or animal.get("tag_number"), 120),
    }


def _display(animal):
    ident = _animal_identity(animal)
    return f"{ident['name'] or ident['tag_number']} ({ident['pig_id']})"


def _clean(value, limit):
    return str(value or "").strip()[:limit]


def _after(before, effects):
    return {
        row["area"]: {
            "proposed_action": row["action"],
            "proposed_facts": row["facts"],
            "state": "proposed" if row["supported"] else "Unknown/unchanged",
        }
        for row in effects
    } | {"prior_state": before}


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _strict_datetime(value, label):
    raw = _clean(value, 120)
    if not raw:
        raise IntakeEvidenceError(f"{label}_required")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntakeEvidenceError(f"{label}_invalid") from exc
    if parsed.tzinfo is None:
        raise IntakeEvidenceError(f"{label}_timezone_required")
    return parsed
