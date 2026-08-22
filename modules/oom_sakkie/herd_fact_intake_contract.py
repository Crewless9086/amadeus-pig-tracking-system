"""Pure conversational herd-fact preview and confirmation contract.

The contract parses a bounded set of directly stated facts, resolves exact
canonical animal identity, previews before/after values, and prepares a future
canonical-writer packet only after exact confirmation. It performs no I/O,
writes, routing, dispatch, or recommendation refresh itself.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime


CONTRACT_VERSION = "herdmaster_conversational_fact_intake_v1"
OBSERVATION_MAX_AGE_DAYS = 7
CURRENT_STATE_MAX_AGE_DAYS = 7
WEIGHT_MAX_AGE_DAYS = 365
MATING_MAX_AGE_DAYS = 365
PREGNANCY_MAX_DAYS_SINCE_MATING = 125
PREGNANCY_FARROWING_GRACE_DAYS = 14
PREGNANCY_CHECK_MAX_AGE_DAYS = 60
MAX_OWNER_WORDS_LENGTH = 1000
MAX_ASSESSOR_LENGTH = 120
MAX_CONCERN_DETAIL_LENGTH = 240

SUPPORTED_FACT_CATEGORIES = (
    "weight",
    "physical_condition",
    "movement_observation",
    "visible_concern",
    "heat_observation",
    "pregnancy_check",
    "availability",
    "farm_presence",
    "pen_location",
    "pen_movement",
    "mating",
)

CONDITIONAL_CANONICAL_WORKFLOW_CATEGORIES = ("litter", "lifecycle")

PROTECTED_INFERENCES = (
    "pregnancy",
    "fertility",
    "health_clearance",
    "withdrawal_clearance",
    "breeding_readiness",
    "family_compatibility",
)

_DATE_TOKEN = (
    r"(?:today|this morning|\d{4}-\d{2}-\d{2}|"
    r"\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})"
)


def preview_conversational_herd_fact(
    owner_words,
    *,
    animals,
    canonical_state_by_pig=None,
    recommendation_by_pig=None,
    governed_pregnancy_assessors=None,
    today=None,
):
    """Return one canonical zero-write preview for a bounded owner statement."""
    today = today or date.today()
    parsed = _parse_statement(owner_words, today=today)
    if not parsed["success"]:
        return parsed

    animal_rows = _valid_animals(animals)
    if animal_rows is None:
        return _failure(
            "canonical_herd_identity_unavailable",
            "Canonical herd identity is unavailable. Nothing was recorded.",
        )
    subject = _resolve_exact_identity(parsed["animal"], animal_rows)
    if not subject["success"]:
        return subject

    pig = subject["animal"]
    pig_id = _text(pig.get("pig_id"))
    tag = _text(pig.get("tag_number") or pig.get("name") or pig_id)
    state_by_pig = (
        canonical_state_by_pig
        if isinstance(canonical_state_by_pig, dict) else {}
    )
    canonical_state = state_by_pig.get(pig_id, {})
    if canonical_state is None:
        canonical_state = {}
    if not isinstance(canonical_state, dict):
        return _failure(
            "canonical_herd_state_invalid",
            "Canonical herd state is malformed. Nothing was recorded.",
        )

    facts = [dict(item) for item in parsed["facts"]]
    validation = _validate_facts(
        facts,
        subject=pig,
        animals=animal_rows,
        canonical_state=canonical_state,
        governed_pregnancy_assessors=governed_pregnancy_assessors,
        today=today,
    )
    if not validation["success"]:
        return validation
    facts = validation["facts"]

    before = _canonical_before(facts, canonical_state)
    after = _canonical_after(facts, before)
    recommendation_before = (
        (recommendation_by_pig or {}).get(pig_id)
        if isinstance(recommendation_by_pig, dict) else None
    ) or {
        "status": "Unknown",
        "next_action": "Unknown",
    }
    identity_material = {
        "contract_version": CONTRACT_VERSION,
        "pig_id": pig_id,
        "facts": facts,
    }
    identity_digest = _digest(identity_material)
    idempotency_key = "HERD-FACT-" + identity_digest
    preview_id = "HERD-FACT-PREVIEW-" + idempotency_key[-24:]
    preview_core = {
        "contract_version": CONTRACT_VERSION,
        "preview_id": preview_id,
        "idempotency_key": idempotency_key,
        "subject": {"pig_id": pig_id, "tag_number": tag},
        "facts": facts,
        "canonical_before": before,
    }
    preview_digest = _digest(preview_core)

    return {
        "success": True,
        "status": "herd_fact_preview_ready",
        "contract_version": CONTRACT_VERSION,
        "preview_id": preview_id,
        "preview_digest": preview_digest,
        "idempotency_key": idempotency_key,
        "subject": {
            "pig_id": pig_id,
            "tag_number": tag,
        },
        "fact_categories": [item["category"] for item in facts],
        "facts": facts,
        "canonical_before": before,
        "canonical_after_preview": after,
        "canonical_preview_text": _human_preview(
            {"pig_id": pig_id, "tag_number": tag},
            facts,
            before,
            after,
            preview_id,
        ),
        "recommendation_before": recommendation_before,
        "recommendation_after": {
            "status": "Refresh required after canonical write",
            "next_action": "Refresh required after canonical write",
        },
        "confirmation": {
            "required": True,
            "exact_text": f"CONFIRM {preview_id}",
            "confirmed": False,
        },
        "future_execution": {
            "adapter_keys": sorted({
                _adapter_key(item["category"]) for item in facts
            }),
            "execution_enabled": False,
            "write_authorized": False,
            "requires_persisted_immutable_preview": True,
            "requires_actor_chat_binding": True,
            "requires_canonical_state_revalidation": True,
            "requires_atomic_idempotency_claim": True,
        },
        "protected_inferences": {
            key: "Not inferred" for key in PROTECTED_INFERENCES
        },
        "read_only": True,
        "writes_performed": False,
        "protected_actions_performed": False,
    }


def prepare_confirmed_fact_execution(
    preview,
    confirmation_text,
    *,
    persisted_preview_verified=False,
    actor_chat_binding_verified=False,
    canonical_state_revalidated=False,
    idempotency_claim_status="",
):
    """Prepare, but never execute, a canonical writer packet."""
    if not _valid_preview_envelope(preview):
        return _failure(
            "valid_preview_required",
            "A valid, untampered canonical preview is required before confirmation.",
        )
    expected = f"CONFIRM {preview['preview_id']}"
    if _text(confirmation_text) != expected:
        return _failure(
            "exact_confirmation_required",
            f"Reply exactly `{expected}` to authorize this preview.",
        )
    if not persisted_preview_verified:
        return _failure(
            "persisted_preview_verification_required",
            "Retrieve the immutable server-side preview before confirmation.",
        )
    if not actor_chat_binding_verified:
        return _failure(
            "actor_chat_binding_required",
            "The confirming owner and conversation must match the stored preview.",
        )
    if not canonical_state_revalidated:
        return _failure(
            "canonical_state_revalidation_required",
            "Canonical identity and before-state must be revalidated before any write plan.",
        )

    identity = _text(preview.get("idempotency_key"))
    claim_status = _norm(idempotency_claim_status)
    if claim_status == "completed":
        return {
            "success": True,
            "status": "confirmed_replay_noop",
            "idempotency_key": identity,
            "additional_facts_expected": 0,
            "execution_required": False,
            "writes_performed": False,
            "protected_actions_performed": False,
        }
    if claim_status != "claimed":
        return _failure(
            "atomic_idempotency_claim_required",
            "An authoritative atomic idempotency claim is required before execution planning.",
        )

    protected_categories = {
        item.get("category")
        for item in preview.get("facts", [])
        if item.get("execution_requires_separate_approval")
    }
    if protected_categories:
        return {
            "success": True,
            "status": "protected_action_approval_required",
            "preview_id": preview["preview_id"],
            "idempotency_key": identity,
            "protected_fact_categories": sorted(protected_categories),
            "write_authorized_by_confirmation": False,
            "execution_required": False,
            "execution_performed": False,
            "separate_governed_approval_required": True,
            "writes_performed": False,
            "protected_actions_performed": False,
        }

    return {
        "success": True,
        "status": "confirmed_execution_plan_ready",
        "preview_id": preview["preview_id"],
        "idempotency_key": identity,
        "subject": dict(preview["subject"]),
        "facts": [dict(item) for item in preview["facts"]],
        "adapter_keys": sorted({
            _adapter_key(item["category"]) for item in preview["facts"]
        }),
        "write_authorized_by_confirmation": True,
        "execution_required": True,
        "execution_performed": False,
        "post_write_requirements": {
            "matching_fact_count": len(preview["facts"]),
            "replay_additional_fact_count": 0,
            "refresh_recommendation": True,
            "return_one_next_action": True,
        },
        "writes_performed": False,
        "protected_actions_performed": False,
    }


def verify_recorded_fact_outcome(
    preview,
    *,
    matching_canonical_facts,
    replay_additional_fact_count,
    recommendation_after,
):
    """Verify a future adapter result without performing a write."""
    facts = (
        matching_canonical_facts
        if isinstance(matching_canonical_facts, list) else []
    )
    recommendation = (
        recommendation_after if isinstance(recommendation_after, dict) else {}
    )
    next_action = _text(recommendation.get("next_action"))
    expected = _expected_canonical_facts(preview)
    fact_matches = (
        len(facts) == len(expected)
        and all(
            any(_canonical_fact_matches(actual, item) for actual in facts)
            for item in expected
        )
    )
    if (
        not isinstance(preview, dict)
        or not _valid_preview_envelope(preview)
        or not fact_matches
        or replay_additional_fact_count != 0
        or not next_action
    ):
        return _failure(
            "recorded_outcome_not_proven",
            "The unique canonical fact, zero-additional replay, refreshed recommendation, and next action must all be proven.",
        )
    return {
        "success": True,
        "status": "herd_fact_outcome_verified",
        "preview_id": preview["preview_id"],
        "idempotency_key": preview["idempotency_key"],
        "matching_canonical_fact_count": len(expected),
        "replay_additional_fact_count": 0,
        "recommendation_before": preview.get("recommendation_before"),
        "recommendation_after": recommendation,
        "next_action": next_action,
        "writes_performed_by_verifier": False,
        "protected_actions_performed": False,
    }


def _parse_statement(owner_words, *, today):
    raw_text = _text(owner_words)
    if len(raw_text) > MAX_OWNER_WORDS_LENGTH:
        return _failure(
            "herd_fact_too_long",
            "State one concise herd fact of at most 1000 characters.",
        )
    text = " ".join(raw_text.split()).rstrip(".")
    if not text:
        return _failure(
            "herd_fact_required",
            "State one directly observed herd fact.",
        )
    lower = text.casefold()
    if (
        "heat was observed" in lower
        and "heat was not observed" in lower
    ):
        return _failure(
            "contradictory_heat_observation",
            "The statement says both observed and not observed heat.",
        )
    if re.search(r"\b(died|dead|sold|retired|slaughtered|farrowed|litter)\b", lower):
        category = (
            "litter" if re.search(r"\b(farrowed|litter)\b", lower)
            else "lifecycle"
        )
        return _failure(
            "canonical_workflow_adapter_required",
            f"{category.title()} facts require their existing canonical workflow adapter before conversational preview.",
        )

    weight = re.fullmatch(
        rf"(?P<animal>.+?)\s+weighed\s+"
        rf"(?P<weight>\d+(?:[.,]\d+)?)\s*kg\s+on\s+"
        rf"(?P<when>{_DATE_TOKEN})(?:\s+at\s+(?P<time>\d{{1,2}}:\d{{2}}))?",
        text,
        flags=re.I,
    )
    if weight:
        evidence = _evidence(
            weight.group("when"), weight.group("time"), today=today
        )
        if not evidence["success"]:
            return evidence
        value = float(weight.group("weight").replace(",", "."))
        if value <= 0 or value > 500:
            return _failure(
                "weight_value_invalid",
                "Weight must be greater than zero and no more than 500 kg.",
            )
        return _parsed(weight.group("animal"), [{
            "category": "weight",
            "weight_kg": value,
            **evidence["evidence"],
        }])

    normal_movement = re.fullmatch(
        rf"(?P<animal>.+?)\s+was\s+moving\s+normally"
        rf"(?:\s+(?P<when>{_DATE_TOKEN}))?"
        rf"\s+and\s+no\s+injury\s+was\s+visible",
        text,
        flags=re.I,
    )
    if normal_movement:
        evidence = _evidence(
            normal_movement.group("when") or "today",
            None,
            today=today,
        )
        if not evidence["success"]:
            return evidence
        if (
            normal_movement.group("when")
            and normal_movement.group("when").casefold() == "this morning"
        ):
            evidence["evidence"]["observation_time"] = "Morning"
        return _parsed(normal_movement.group("animal"), [
            {
                "category": "movement_observation",
                "movement": "normal",
                **evidence["evidence"],
            },
            {
                "category": "visible_concern",
                "visible_injury": "none_visible",
                **evidence["evidence"],
            },
        ])

    movement_observation = re.fullmatch(
        rf"(?P<animal>.+?)\s+was\s+"
        rf"(?P<movement>moving\s+normally|moving\s+with\s+difficulty|limping)"
        rf"\s+(?:on\s+)?(?P<when>{_DATE_TOKEN})",
        text,
        flags=re.I,
    )
    if movement_observation:
        evidence = _evidence(
            movement_observation.group("when"), None, today=today
        )
        if not evidence["success"]:
            return evidence
        normalized = _norm(movement_observation.group("movement"))
        return _parsed(movement_observation.group("animal"), [{
            "category": "movement_observation",
            "movement": (
                "normal" if normalized == "moving_normally"
                else "concern"
            ),
            "detail": (
                "None stated" if normalized == "moving_normally"
                else _display_words(movement_observation.group("movement"))
            ),
            **evidence["evidence"],
        }])

    no_injury = re.fullmatch(
        rf"(?P<animal>.+?)\s+had\s+no\s+visible\s+injury"
        rf"\s+(?:on\s+)?(?P<when>{_DATE_TOKEN})",
        text,
        flags=re.I,
    )
    if no_injury:
        evidence = _evidence(no_injury.group("when"), None, today=today)
        if not evidence["success"]:
            return evidence
        return _parsed(no_injury.group("animal"), [{
            "category": "visible_concern",
            "visible_injury": "none_visible",
            **evidence["evidence"],
        }])

    condition = re.fullmatch(
        rf"(?P<animal>.+?)\s+had\s+(?:a\s+)?body\s+condition"
        rf"(?:\s+score)?\s+(?P<score>[1-5](?:\.\d)?)"
        rf"\s+(?:on\s+)?(?P<when>{_DATE_TOKEN})",
        text,
        flags=re.I,
    )
    if condition:
        score = float(condition.group("score"))
        if not 1 <= score <= 5:
            return _failure(
                "body_condition_score_invalid",
                "Body-condition score must be between 1 and 5.",
            )
        evidence = _evidence(condition.group("when"), None, today=today)
        if not evidence["success"]:
            return evidence
        return _parsed(condition.group("animal"), [{
            "category": "physical_condition",
            "body_condition_score": score,
            **evidence["evidence"],
        }])

    injury = re.fullmatch(
        rf"(?P<animal>.+?)\s+had\s+(?:a\s+)?visible\s+"
        rf"(?P<concern>injury|concern)(?:\s*:\s*(?P<detail>.+?))?"
        rf"\s+on\s+(?P<when>{_DATE_TOKEN})",
        text,
        flags=re.I,
    )
    if injury:
        detail = _text(injury.group("detail")) or "Visible concern stated"
        if len(detail) > MAX_CONCERN_DETAIL_LENGTH:
            return _failure(
                "visible_concern_detail_too_long",
                "Visible-concern detail must be at most 240 characters.",
            )
        evidence = _evidence(injury.group("when"), None, today=today)
        if not evidence["success"]:
            return evidence
        return _parsed(injury.group("animal"), [{
            "category": "visible_concern",
            "visible_injury": "visible_concern",
            "detail": detail,
            **evidence["evidence"],
        }])

    heat = re.fullmatch(
        rf"(?P<animal>.+?)\s+(?:heat\s+was|was)\s+"
        rf"(?P<result>observed|not\s+observed|in\s+heat|not\s+in\s+heat)"
        rf"\s+(?:on\s+)?(?P<when>{_DATE_TOKEN})",
        text,
        flags=re.I,
    )
    if heat:
        evidence = _evidence(heat.group("when"), None, today=today)
        if not evidence["success"]:
            return evidence
        result = _norm(heat.group("result"))
        return _parsed(heat.group("animal"), [{
            "category": "heat_observation",
            "heat_observed": result in {"observed", "in_heat"},
            **evidence["evidence"],
        }])

    pregnancy = re.fullmatch(
        rf"(?P<animal>.+?)\s+had\s+(?:an?\s+)?"
        rf"(?P<method>ultrasound|manual\s+palpation|blood\s+test|pregnancy\s+check)"
        rf"\s+by\s+(?P<assessor>.+?)\s+on\s+(?P<when>{_DATE_TOKEN})"
        rf"(?:\s+at\s+(?P<time>\d{{1,2}}:\d{{2}}))?\s*;\s*"
        rf"result\s*:\s*(?P<result>pregnant|not\s+pregnant|inconclusive)",
        text,
        flags=re.I,
    )
    if pregnancy:
        assessor = _text(pregnancy.group("assessor"))
        if len(assessor) > MAX_ASSESSOR_LENGTH:
            return _failure(
                "pregnancy_assessor_too_long",
                "Assessor must be at most 120 characters.",
            )
        evidence = _evidence(
            pregnancy.group("when"), pregnancy.group("time"), today=today
        )
        if not evidence["success"]:
            return evidence
        return _parsed(pregnancy.group("animal"), [{
            "category": "pregnancy_check",
            "method": _display_words(pregnancy.group("method")),
            "assessor": assessor,
            "governance_status": "Pending canonical assessor and method validation",
            "result": _display_words(pregnancy.group("result")),
            **evidence["evidence"],
        }])

    availability = re.fullmatch(
        rf"(?P<animal>.+?)\s+is\s+(?P<not>not\s+)?available"
        rf"(?:\s+for\s+breeding)?\s+as\s+of\s+(?P<when>{_DATE_TOKEN})",
        text,
        flags=re.I,
    )
    if availability:
        evidence = _evidence(availability.group("when"), None, today=today)
        if not evidence["success"]:
            return evidence
        return _parsed(availability.group("animal"), [{
            "category": "availability",
            "available": not bool(availability.group("not")),
            **evidence["evidence"],
        }])

    presence = re.fullmatch(
        rf"(?P<animal>.+?)\s+is\s+(?P<not>not\s+)?on\s+farm"
        rf"\s+as\s+of\s+(?P<when>{_DATE_TOKEN})",
        text,
        flags=re.I,
    )
    if presence:
        evidence = _evidence(presence.group("when"), None, today=today)
        if not evidence["success"]:
            return evidence
        return _parsed(presence.group("animal"), [{
            "category": "farm_presence",
            "on_farm": not bool(presence.group("not")),
            **evidence["evidence"],
        }])

    movement = re.fullmatch(
        rf"(?P<animal>.+?)\s+moved\s+from\s+(?P<from_pen>[A-Za-z0-9_-]+)"
        rf"\s+to\s+(?P<to_pen>[A-Za-z0-9_-]+)\s+on\s+"
        rf"(?P<when>{_DATE_TOKEN})",
        text,
        flags=re.I,
    )
    if movement:
        evidence = _evidence(movement.group("when"), None, today=today)
        if not evidence["success"]:
            return evidence
        if _norm(movement.group("from_pen")) == _norm(movement.group("to_pen")):
            return _failure(
                "pen_movement_contradictory",
                "Source and destination pen must differ.",
            )
        return _parsed(movement.group("animal"), [{
            "category": "pen_movement",
            "from_pen_id": _text(movement.group("from_pen")),
            "to_pen_id": _text(movement.group("to_pen")),
            **evidence["evidence"],
        }])

    location = re.fullmatch(
        rf"(?P<animal>.+?)\s+is\s+in\s+pen\s+"
        rf"(?P<pen>[A-Za-z0-9_-]+)\s+as\s+of\s+(?P<when>{_DATE_TOKEN})",
        text,
        flags=re.I,
    )
    if location:
        evidence = _evidence(location.group("when"), None, today=today)
        if not evidence["success"]:
            return evidence
        return _parsed(location.group("animal"), [{
            "category": "pen_location",
            "pen_id": _text(location.group("pen")),
            **evidence["evidence"],
        }])

    mating = re.fullmatch(
        rf"(?P<female>.+?)\s+was\s+mated\s+with\s+(?P<male>.+?)"
        rf"\s+on\s+(?P<when>{_DATE_TOKEN})",
        text,
        flags=re.I,
    )
    if mating:
        evidence = _evidence(mating.group("when"), None, today=today)
        if not evidence["success"]:
            return evidence
        return _parsed(mating.group("female"), [{
            "category": "mating",
            "male_identity": _text(mating.group("male")),
            **evidence["evidence"],
        }])

    if re.search(
        r"\b(healthy|fertile|withdrawal clear|safe to breed|compatible|pregnant)\b",
        lower,
    ):
        return _failure(
            "unsupported_inference",
            "State the direct observation or governed test result instead of an inferred clearance or breeding conclusion.",
        )
    return _failure(
        "unsupported_or_malformed_herd_fact",
        "That fact is unsupported or missing its fact-specific evidence. Nothing was recorded.",
    )


def _validate_facts(
    facts,
    *,
    subject,
    animals,
    canonical_state,
    governed_pregnancy_assessors,
    today,
):
    pig_id = _text(subject.get("pig_id"))
    for fact in facts:
        category = fact["category"]
        evidence_date = _as_date(fact.get("evidence_date"))
        age = (today - evidence_date).days if evidence_date else None
        max_age = (
            WEIGHT_MAX_AGE_DAYS if category == "weight"
            else MATING_MAX_AGE_DAYS if category == "mating"
            else PREGNANCY_CHECK_MAX_AGE_DAYS
            if category == "pregnancy_check"
            else CURRENT_STATE_MAX_AGE_DAYS
            if category in {
                "availability",
                "farm_presence",
                "pen_location",
                "pen_movement",
            }
            else OBSERVATION_MAX_AGE_DAYS
        )
        if age is None or age < 0:
            return _failure(
                "fact_date_invalid",
                "Evidence date must be a valid date that is not in the future.",
            )
        if age > max_age:
            return _failure(
                "fact_evidence_stale",
                f"{category.replace('_', ' ').title()} evidence is too stale for this intake contract.",
            )

        if category == "pregnancy_check":
            if _norm(subject.get("sex")) != "female":
                return _failure(
                    "pregnancy_subject_must_be_female",
                    "A pregnancy-check result must resolve to the exact canonical female.",
                )
            authorized_assessors = {
                _norm(value)
                for value in (governed_pregnancy_assessors or [])
                if _text(value)
            }
            if _norm(fact.get("assessor")) not in authorized_assessors:
                return _failure(
                    "pregnancy_assessor_not_governed",
                    "The assessor must resolve to an authorized canonical assessor before this result can be previewed.",
                )
            fact["governance_status"] = "Canonical assessor and method validated"
            latest_mating = canonical_state.get("latest_mating") or {}
            mating_date = _as_date(latest_mating.get("mating_date"))
            if (
                _text(latest_mating.get("sow_pig_id")) != pig_id
                or mating_date is None
                or evidence_date < mating_date
            ):
                return _failure(
                    "pregnancy_cycle_not_governed",
                    "The result is not attributable to the current canonical sow mating cycle.",
                )
            existing_result = _norm(
                latest_mating.get("pregnancy_check_result")
            )
            existing_date = _as_date(
                latest_mating.get("pregnancy_check_date")
            )
            new_result = _norm(fact.get("result"))
            governed_results = {
                "pregnant", "not_pregnant", "inconclusive"
            }
            if (
                existing_result in governed_results
                and existing_date == evidence_date
                and new_result != existing_result
            ):
                return _failure(
                    "pregnancy_result_conflict",
                    "The stated result conflicts with the governed result for the same check date. Use the canonical correction workflow.",
                )
            days_since_mating = (today - mating_date).days
            expected_farrowing = _as_date(
                latest_mating.get("expected_farrowing_date")
            )
            resolved = bool(
                latest_mating.get("actual_farrowing_date")
                or latest_mating.get("linked_litter_id")
                or _norm(latest_mating.get("mating_status")) == "farrowed"
            )
            beyond_farrowing = bool(
                expected_farrowing
                and today > expected_farrowing
                and (today - expected_farrowing).days
                > PREGNANCY_FARROWING_GRACE_DAYS
            )
            if (
                resolved
                or days_since_mating > PREGNANCY_MAX_DAYS_SINCE_MATING
                or beyond_farrowing
            ):
                return _failure(
                    "pregnancy_cycle_stale_or_resolved",
                    "The pregnancy-check result is stale or belongs to a resolved cycle.",
                )

        if category == "pen_movement":
            current_pen = _text(canonical_state.get("current_pen_id"))
            if current_pen and _norm(current_pen) != _norm(
                fact.get("from_pen_id")
            ):
                return _failure(
                    "movement_source_pen_conflict",
                    "The stated source pen conflicts with the canonical current pen.",
                )

        if category == "mating":
            if _norm(subject.get("sex")) != "female":
                return _failure(
                    "mating_subject_must_be_female",
                    "The first animal in a mating fact must be the exact canonical female.",
                )
            male = _resolve_exact_identity(fact.pop("male_identity"), animals)
            if not male["success"]:
                return {
                    **male,
                    "status": (
                        "mating_male_identity_ambiguous"
                        if male.get("status") == "animal_identity_ambiguous"
                        else "mating_male_identity_not_found"
                    ),
                }
            male_row = male["animal"]
            if _norm(male_row.get("sex")) != "male":
                return _failure(
                    "mating_male_sex_conflict",
                    "The second animal must be the exact canonical male.",
                )
            if _text(male_row.get("pig_id")) == pig_id:
                return _failure(
                    "mating_identity_conflict",
                    "Female and male must be different canonical animals.",
                )
            fact.update({
                "female_pig_id": pig_id,
                "male_pig_id": _text(male_row.get("pig_id")),
                "male_tag_number": _text(
                    male_row.get("tag_number")
                    or male_row.get("name")
                    or male_row.get("pig_id")
                ),
                "family_compatibility": "Not evaluated",
                "execution_requires_separate_approval": True,
            })
    return {"success": True, "facts": facts}


def _valid_animals(animals):
    if not isinstance(animals, list) or any(
        not isinstance(row, dict) for row in animals
    ):
        return None
    pig_ids = [_text(row.get("pig_id")) for row in animals]
    if any(not value for value in pig_ids) or len(set(pig_ids)) != len(pig_ids):
        return None
    return animals


def _resolve_exact_identity(identity, animals):
    wanted = _text(identity).casefold()
    matches = [
        row for row in animals
        if wanted in {
            _text(row.get(key)).casefold()
            for key in ("pig_id", "tag_number", "name", "pig_name")
            if _text(row.get(key))
        }
    ]
    if len(matches) != 1:
        status = (
            "animal_identity_ambiguous"
            if len(matches) > 1 else "animal_identity_not_found"
        )
        return {
            **_failure(
                status,
                (
                    "More than one canonical animal matches. Use the exact Pig ID."
                    if matches
                    else "No canonical animal matches that exact name, tag, or Pig ID."
                ),
            ),
            "candidate_count": len(matches),
            "safe_disambiguation": "Ask for the exact Pig ID without listing herd records.",
        }
    return {"success": True, "animal": matches[0]}


def _canonical_before(facts, state):
    result = {}
    observations = state.get("latest_observations") or {}
    for fact in facts:
        category = fact["category"]
        if category == "weight":
            result["weight"] = state.get("latest_weight") or {
                "weight_kg": state.get("latest_weight_kg", "Unknown"),
                "evidence_date": state.get("latest_weight_date", "Unknown"),
                "observation_time": "Unknown",
            }
        elif category in {
            "physical_condition",
            "movement_observation",
            "visible_concern",
            "heat_observation",
        }:
            result[category] = observations.get(category, "Unknown")
        elif category == "pregnancy_check":
            mating = state.get("latest_mating") or {}
            result[category] = {
                "result": mating.get("pregnancy_check_result") or "Unknown",
                "evidence_date": mating.get("pregnancy_check_date") or "Unknown",
                "method": mating.get("pregnancy_check_method") or "Unknown",
                "assessor": mating.get("pregnancy_check_assessor") or "Unknown",
                "observation_time": (
                    mating.get("pregnancy_check_time") or "Unknown"
                ),
            }
        elif category == "availability":
            result[category] = state.get("available_for_breeding", "Unknown")
        elif category == "farm_presence":
            result[category] = state.get("on_farm", "Unknown")
        elif category in {"pen_location", "pen_movement"}:
            result["current_pen_id"] = state.get("current_pen_id", "Unknown")
        elif category == "mating":
            result[category] = state.get("latest_mating") or "Unknown"
    return result


def _canonical_after(facts, before):
    result = dict(before)
    for fact in facts:
        category = fact["category"]
        if category == "weight":
            result["weight"] = {
                "weight_kg": fact["weight_kg"],
                "evidence_date": fact["evidence_date"],
                "observation_time": fact["observation_time"],
            }
        elif category in {
            "physical_condition",
            "movement_observation",
            "visible_concern",
            "heat_observation",
            "pregnancy_check",
            "availability",
            "farm_presence",
            "mating",
        }:
            result[category] = dict(fact)
        elif category == "pen_location":
            result["current_pen_id"] = fact["pen_id"]
        elif category == "pen_movement":
            result["current_pen_id"] = fact["to_pen_id"]
    return result


def _human_preview(subject, facts, before, after, preview_id):
    categories = ", ".join(
        item["category"].replace("_", " ") for item in facts
    )
    limits = (
        "This records only the stated availability fact; it is not health, "
        "withdrawal, fertility, or breeding-readiness clearance."
        if any(item["category"] == "availability" for item in facts)
        else "No pregnancy, fertility, health, withdrawal, readiness, or family-compatibility clearance is inferred."
    )
    protected = (
        "Mating remains a protected action requiring separate governed approval."
        if any(item["category"] == "mating" for item in facts)
        else "No write occurs until exact owner confirmation."
    )
    return (
        f"Animal: {subject['tag_number']} ({subject['pig_id']}). "
        f"Fact: {categories}. Before: {json.dumps(before, sort_keys=True)}. "
        f"Proposed after: {json.dumps(after, sort_keys=True)}. "
        f"{limits} {protected} Reply exactly CONFIRM {preview_id}."
    )


def _adapter_key(category):
    return {
        "weight": "canonical_weight_writer",
        "physical_condition": "canonical_observation_writer",
        "movement_observation": "canonical_observation_writer",
        "visible_concern": "canonical_observation_writer",
        "heat_observation": "canonical_observation_writer",
        "pregnancy_check": "canonical_pregnancy_check_writer",
        "availability": "canonical_availability_writer",
        "farm_presence": "canonical_farm_presence_writer",
        "pen_location": "canonical_movement_writer",
        "pen_movement": "canonical_movement_writer",
        "mating": "canonical_mating_preview_writer",
    }[category]


def _evidence(value, observation_time, *, today):
    text = _text(value)
    relative = text.casefold()
    if relative in {"today", "this morning"}:
        parsed = today
    else:
        cleaned = re.sub(
            r"(\d)(st|nd|rd|th)\b", r"\1", text, flags=re.I
        )
        parsed = None
        for pattern in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
            try:
                parsed = datetime.strptime(cleaned, pattern).date()
                break
            except ValueError:
                continue
        if parsed is None:
            return _failure(
                "fact_date_needs_clarification",
                "The evidence date could not be interpreted safely.",
            )
    time_value = _text(observation_time)
    if time_value:
        try:
            time_value = datetime.strptime(time_value, "%H:%M").strftime(
                "%H:%M"
            )
        except ValueError:
            return _failure(
                "observation_time_invalid",
                "Observation time must use HH:MM.",
            )
    elif relative == "this morning":
        time_value = "Morning"
    else:
        time_value = "Unknown"
    return {
        "success": True,
        "evidence": {
            "evidence_date": parsed.isoformat(),
            "observation_time": time_value,
        },
    }


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest().upper()


def _valid_preview_envelope(preview):
    if (
        not isinstance(preview, dict)
        or preview.get("success") is not True
        or preview.get("contract_version") != CONTRACT_VERSION
        or preview.get("read_only") is not True
        or preview.get("writes_performed") is not False
        or not _text(preview.get("preview_id"))
        or not _text(preview.get("idempotency_key"))
        or not isinstance(preview.get("subject"), dict)
        or not _text(preview["subject"].get("pig_id"))
        or not isinstance(preview.get("facts"), list)
        or not preview["facts"]
    ):
        return False
    identity_material = {
        "contract_version": CONTRACT_VERSION,
        "pig_id": _text(preview["subject"].get("pig_id")),
        "facts": preview["facts"],
    }
    expected_identity = "HERD-FACT-" + _digest(identity_material)
    if preview.get("idempotency_key") != expected_identity:
        return False
    expected_preview_id = "HERD-FACT-PREVIEW-" + expected_identity[-24:]
    if preview.get("preview_id") != expected_preview_id:
        return False
    preview_core = {
        "contract_version": CONTRACT_VERSION,
        "preview_id": expected_preview_id,
        "idempotency_key": expected_identity,
        "subject": preview["subject"],
        "facts": preview["facts"],
        "canonical_before": preview.get("canonical_before"),
    }
    return preview.get("preview_digest") == _digest(preview_core)


def _expected_canonical_facts(preview):
    return [
        {
            "pig_id": preview["subject"]["pig_id"],
            "idempotency_key": preview["idempotency_key"],
            **dict(fact),
        }
        for fact in preview["facts"]
    ]


def _canonical_fact_matches(actual, expected):
    if not isinstance(actual, dict):
        return False
    return all(actual.get(key) == value for key, value in expected.items())


def _parsed(animal, facts):
    return {
        "success": True,
        "animal": _text(animal),
        "facts": facts,
    }


def _failure(status, clarification):
    return {
        "success": False,
        "status": status,
        "clarification": clarification,
        "read_only": True,
        "writes_performed": False,
        "protected_actions_performed": False,
    }


def _display_words(value):
    return " ".join(
        part.capitalize() for part in _text(value).split()
    )


def _norm(value):
    return _text(value).casefold().replace(" ", "_").replace("-", "_")


def _text(value):
    return str(value or "").strip()


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_text(value)[:10])
    except ValueError:
        return None
