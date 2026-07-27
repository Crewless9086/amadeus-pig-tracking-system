"""Owner-governed ROOTLINE Operating Knowledge policy review.

This module validates immutable policy snapshots and records proposal, review,
and explicit advice-activation events. It has no plan, command, scheduler,
workflow, retry, irrigation transport, IFTTT, n8n, or hardware dependency.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re

from services.database_service import DATABASE_URL_ENV


POLICY_ID = "ROOTLINE-OPERATING-KNOWLEDGE"
UNKNOWN = "Unknown"
ZONES = {"B12345": "lucerne", "C12345": "vegetables"}
LIFECYCLE = ("proposed", "owner_reviewed", "active_for_advice")
AUTHORITY = {
    "writes_farm_data": False,
    "writes_telemetry": False,
    "generates_plan": False,
    "creates_command": False,
    "mutates_schedule": False,
    "activates_workflow": False,
    "calls_ifttt": False,
    "calls_n8n": False,
    "controls_hardware": False,
    "automatic_retry": False,
}

DECISION_GUIDANCE = [
    {
        "key": "seasonal_boundaries",
        "question": "When do summer and winter policy periods begin?",
        "recommendation": "Keep Unknown until Charl approves exact month/day boundaries.",
        "consequence": "Runtime advice remains suppressed while seasonal runtime meaning is unresolved.",
        "applies_to": "both zones",
    },
    {
        "key": "daylight_windows",
        "question": "What exact daylight start and end time is allowed for each zone?",
        "recommendation": "Keep Unknown; daylight-only remains the safety boundary.",
        "consequence": "Eligibility remains Needs Data without an exact allowed window.",
        "applies_to": "per zone",
    },
    {
        "key": "runtime_limits",
        "question": "What are the minimum useful and maximum continuous valve-open minutes?",
        "recommendation": "Keep both Unknown until field evidence supports bounded values.",
        "consequence": "ROOTLINE will not propose runtime while either limit is Unknown.",
        "applies_to": "per zone",
    },
    {
        "key": "forecast_rain",
        "question": "What forecast rain amount, probability and look-ahead horizon should hold advice?",
        "recommendation": "Keep Unknown rather than reusing a legacy workflow default.",
        "consequence": "Forecast-based Irrigate advice remains suppressed.",
        "applies_to": "both zones",
    },
    {
        "key": "live_rain_hold",
        "question": "At what current rain rate must ROOTLINE place advice on Hold?",
        "recommendation": (
            "Use Charl's confirmed greater-than 0.2 mm/hour threshold; keep "
            "the rain-release interval Unknown."
        ),
        "consequence": (
            "Fresh current rain above 0.2 mm/hour produces Hold. Exactly "
            "0.2 mm/hour does not exceed the threshold."
        ),
        "applies_to": "both zones",
    },
    {
        "key": "temperature_limits",
        "question": "What minimum and maximum temperature limits affect advice?",
        "recommendation": "Keep Unknown; temperature remains informational.",
        "consequence": "Temperature cannot independently produce an Irrigate recommendation.",
        "applies_to": "both zones",
    },
    {
        "key": "crop_need_bands",
        "question": "What low, medium and high daily crop-need bands apply?",
        "recommendation": "Keep Unknown until agronomic values are owner-approved.",
        "consequence": "ROOTLINE will not invent crop water need or delivered water.",
        "applies_to": "lucerne and vegetables separately",
    },
    {
        "key": "controller_power_loss",
        "question": "What physical valve state has actually been observed after controller power loss?",
        "recommendation": "Keep Unknown; do not treat the desired fail-closed policy as evidence.",
        "consequence": "Future physical execution remains blocked on unproven power-loss behaviour.",
        "applies_to": "controller evidence",
    },
    {
        "key": "residual_drainage",
        "question": "How long does diminishing residual drip drainage remain after verified closure?",
        "recommendation": "Keep Unknown until a timed observation is recorded.",
        "consequence": "Residual drainage stays separate from OFF failure and measured delivery.",
        "applies_to": "observed line evidence",
    },
]


class PolicyValidationError(ValueError):
    pass


class PolicyConflictError(ValueError):
    pass


class PolicyStoreUnavailable(RuntimeError):
    pass


def policy_review_contract():
    return {
        "success": True,
        "status": "rootline_policy_review_contract",
        "policy_id": POLICY_ID,
        "lifecycle": list(LIFECYCLE),
        "activation_rule": (
            "Only an explicit owner-admin activation bound to the exact reviewed "
            "proposal version, actor, evidence and effective time becomes active for advice."
        ),
        "unknown_is_deliberate": True,
        "decision_guidance": deepcopy(DECISION_GUIDANCE),
        "canary_runtime_is_policy_input": False,
        "measured_water_inferred": False,
        "successful_routine_irrigation_inferred": False,
        "migration_applied": False,
        **AUTHORITY,
    }


def normalize_policy_snapshot(payload):
    source = payload if isinstance(payload, dict) else {}
    allowed = {
        "seasonal_boundaries",
        "zones",
        "forecast_rain",
        "live_rain_hold",
        "temperature_limits",
        "crop_need_bands",
        "controller_power_loss",
        "residual_drainage",
    }
    unexpected = sorted(set(source) - allowed)
    if unexpected:
        raise PolicyValidationError("unexpected_policy_fields")

    zones = source.get("zones")
    if not isinstance(zones, dict) or set(zones) != set(ZONES):
        raise PolicyValidationError("exact_zone_policy_identity_required")

    normalized_zones = {}
    for zone_id, crop in ZONES.items():
        zone = zones.get(zone_id)
        if not isinstance(zone, dict) or set(zone) != {
            "daylight_window",
            "minimum_useful_runtime_minutes",
            "maximum_continuous_runtime_minutes",
        }:
            raise PolicyValidationError("exact_zone_policy_fields_required")
        minimum = _unknown_or_int(
            zone["minimum_useful_runtime_minutes"], 1, 1440, "invalid_minimum_runtime"
        )
        maximum = _unknown_or_int(
            zone["maximum_continuous_runtime_minutes"], 1, 1440, "invalid_maximum_runtime"
        )
        if minimum != UNKNOWN and maximum != UNKNOWN and minimum > maximum:
            raise PolicyConflictError("minimum_runtime_exceeds_maximum")
        normalized_zones[zone_id] = {
            "crop_use": crop,
            "daylight_window": _window(zone["daylight_window"]),
            "minimum_useful_runtime_minutes": minimum,
            "maximum_continuous_runtime_minutes": maximum,
        }

    return {
        "seasonal_boundaries": _season(source.get("seasonal_boundaries")),
        "zones": normalized_zones,
        "forecast_rain": _forecast(source.get("forecast_rain")),
        "live_rain_hold": _live_rain_hold(source.get("live_rain_hold", UNKNOWN)),
        "temperature_limits": _temperature(source.get("temperature_limits")),
        "crop_need_bands": _crop_bands(source.get("crop_need_bands")),
        "controller_power_loss": _power_loss(source.get("controller_power_loss")),
        "residual_drainage": _drainage(source.get("residual_drainage")),
    }


def prepare_policy_proposal(payload, actor, *, now=None):
    actor = str(actor or "").strip()
    if not actor:
        raise PolicyValidationError("owner_admin_identity_required")
    source = payload if isinstance(payload, dict) else {}
    idempotency_key = str(source.get("idempotency_key") or "").strip()
    if not idempotency_key or len(idempotency_key) > 200:
        raise PolicyValidationError("bounded_idempotency_key_required")
    evidence = source.get("evidence")
    if not isinstance(evidence, dict) or not evidence:
        raise PolicyValidationError("proposal_evidence_required")
    snapshot = normalize_policy_snapshot(source.get("policy"))
    proposed_at = _utc(now or datetime.now(timezone.utc)).isoformat()
    canonical = {
        "policy_id": POLICY_ID,
        "policy": snapshot,
        "evidence": evidence,
        "proposed_by": actor,
        "idempotency_key": idempotency_key,
        "canary_runtime_used": False,
        "measured_water_inferred": False,
        "successful_routine_irrigation_inferred": False,
        **AUTHORITY,
    }
    proposal_sha256 = _digest(canonical)
    proposal_id = f"ROOTLINE-POLICY-{proposal_sha256[:24].upper()}"
    return {
        **canonical,
        "proposed_at": proposed_at,
        "proposal_id": proposal_id,
        "proposal_sha256": proposal_sha256,
    }


def preview_policy_effect(proposal_payload, current_advisor):
    try:
        snapshot = normalize_policy_snapshot(proposal_payload)
    except (PolicyValidationError, PolicyConflictError) as exc:
        return _failure(str(exc), 400)
    current = current_advisor if isinstance(current_advisor, dict) else {}
    resolved = []
    still_unknown = []
    _classify_unknown("seasonal_boundaries", snapshot["seasonal_boundaries"], resolved, still_unknown)
    _classify_unknown("forecast_rain", snapshot["forecast_rain"], resolved, still_unknown)
    _classify_unknown("live_rain_hold", snapshot["live_rain_hold"], resolved, still_unknown)
    _classify_unknown("temperature_limits", snapshot["temperature_limits"], resolved, still_unknown)
    _classify_unknown("crop_need_bands", snapshot["crop_need_bands"], resolved, still_unknown)
    _classify_unknown("controller_power_loss", snapshot["controller_power_loss"], resolved, still_unknown)
    _classify_unknown("residual_drainage", snapshot["residual_drainage"], resolved, still_unknown)
    for zone_id, zone in snapshot["zones"].items():
        for key in (
            "daylight_window",
            "minimum_useful_runtime_minutes",
            "maximum_continuous_runtime_minutes",
        ):
            _classify_unknown(f"{zone_id}.{key}", zone[key], resolved, still_unknown)
    return {
        "success": True,
        "status": "advice_preview_only",
        "current_advisor_status": current.get("status", "Unavailable"),
        "resolved_policy_inputs": resolved,
        "remaining_unknown_policy_inputs": still_unknown,
        "eligibility_after_preview": "Needs Data" if still_unknown else "owner_review_required",
        "preview_is_valid": True,
        "proposal_can_be_recorded": True,
        "runtime_after_preview": None,
        "runtime_status": "Unavailable",
        "preview_becomes_active": False,
        "preview_generates_plan": False,
        "preview_creates_command": False,
        "canary_runtime_used": False,
        "measured_water_inferred": False,
        **AUTHORITY,
    }, 200


def list_policy_review(*, store=None):
    try:
        store = store or PostgresPolicyStore()
        result = store.snapshot()
    except PolicyStoreUnavailable as exc:
        return {
            **policy_review_contract(),
            "success": False,
            "status": str(exc),
            "proposals": [],
            "active_policy": None,
        }, 503
    return {**policy_review_contract(), **result, "migration_applied": True}, 200


def propose_policy(payload, actor, *, store=None, now=None):
    try:
        proposal = prepare_policy_proposal(payload, actor, now=now)
        result = (store or PostgresPolicyStore()).append_proposal(proposal)
    except PolicyValidationError as exc:
        return _failure(str(exc), 400)
    except PolicyConflictError as exc:
        return _failure(str(exc), 409)
    except PolicyStoreUnavailable as exc:
        return _failure(str(exc), 503)
    return {
        "success": True,
        "status": "proposal_recorded" if result["created"] else "proposal_replay",
        "proposal": result["proposal"],
        "writes_performed": result["created"],
        **AUTHORITY,
    }, 201 if result["created"] else 200


def review_policy(proposal_id, payload, actor, *, store=None, now=None):
    return _transition(
        "owner_reviewed", proposal_id, payload, actor, store=store, now=now
    )


def activate_policy(proposal_id, payload, actor, *, store=None, now=None):
    effective_at = (payload if isinstance(payload, dict) else {}).get("effective_at")
    if not effective_at:
        return _failure("activation_effective_time_required", 400)
    try:
        effective_at = _timestamp(effective_at).isoformat()
    except PolicyValidationError as exc:
        return _failure(str(exc), 400)
    activation_time = _utc(now or datetime.now(timezone.utc))
    return _transition(
        "active_for_advice",
        proposal_id,
        payload,
        actor,
        store=store,
        now=activation_time,
        effective_at=effective_at,
    )


def _transition(state, proposal_id, payload, actor, *, store, now, effective_at=None):
    actor = str(actor or "").strip()
    source = payload if isinstance(payload, dict) else {}
    if not actor:
        return _failure("owner_admin_identity_required", 403)
    idempotency_key = str(source.get("idempotency_key") or "").strip()
    evidence = source.get("evidence")
    if not idempotency_key or len(idempotency_key) > 200:
        return _failure("bounded_idempotency_key_required", 400)
    if not isinstance(evidence, dict) or not evidence:
        return _failure("owner_transition_evidence_required", 400)
    occurred_at = _utc(now or datetime.now(timezone.utc)).isoformat()
    transition_sha256 = _digest(
        {
            "proposal_id": str(proposal_id or "").strip(),
            "state": state,
            "actor": actor,
            "evidence": evidence,
            "effective_at": effective_at,
        }
    )
    try:
        result = (store or PostgresPolicyStore()).append_transition(
            str(proposal_id or "").strip(),
            state,
            actor,
            evidence,
            idempotency_key,
            occurred_at,
            effective_at,
            transition_sha256,
        )
    except PolicyConflictError as exc:
        return _failure(str(exc), 409)
    except PolicyStoreUnavailable as exc:
        return _failure(str(exc), 503)
    return {
        "success": True,
        "status": state if result["created"] else f"{state}_replay",
        "proposal_id": proposal_id,
        "lifecycle_state": state,
        "effective_at": result.get("effective_at"),
        "writes_performed": result["created"],
        "activation_generates_plan": False,
        "activation_creates_command": False,
        **AUTHORITY,
    }, 201 if result["created"] else 200


class InMemoryPolicyStore:
    def __init__(self):
        self.proposals = []
        self.events = []

    def append_proposal(self, proposal):
        for existing in self.proposals:
            if existing["idempotency_key"] == proposal["idempotency_key"]:
                if existing["proposal_sha256"] != proposal["proposal_sha256"]:
                    raise PolicyConflictError("proposal_idempotency_conflict")
                return {"created": False, "proposal": deepcopy(existing)}
        version = len(self.proposals) + 1
        record = {**deepcopy(proposal), "version": version, "lifecycle_state": "proposed"}
        self.proposals.append(record)
        self.events.append(
            {
                "proposal_id": record["proposal_id"],
                "version": version,
                "state": "proposed",
                "actor": record["proposed_by"],
                "effective_at": None,
            }
        )
        return {"created": True, "proposal": deepcopy(record)}

    def append_transition(
        self, proposal_id, state, actor, evidence, idempotency_key, occurred_at,
        effective_at, transition_sha256
    ):
        proposal = next((item for item in self.proposals if item["proposal_id"] == proposal_id), None)
        if not proposal:
            raise PolicyConflictError("policy_proposal_not_found")
        for event in self.events:
            if event.get("idempotency_key") == idempotency_key:
                if event.get("transition_sha256") != transition_sha256:
                    raise PolicyConflictError("transition_idempotency_conflict")
                return {"created": False, "effective_at": event.get("effective_at")}
        if proposal["version"] != len(self.proposals):
            raise PolicyConflictError("stale_policy_version")
        states = [item["state"] for item in self.events if item["proposal_id"] == proposal_id]
        required = "proposed" if state == "owner_reviewed" else "owner_reviewed"
        if required not in states:
            raise PolicyConflictError(f"{required}_state_required")
        if state in states:
            raise PolicyConflictError("conflicting_transition")
        if (
            state == "active_for_advice"
            and _timestamp(effective_at) < _timestamp(occurred_at)
        ):
            raise PolicyConflictError("effective_time_must_not_precede_activation")
        self.events.append(
            {
                "proposal_id": proposal_id,
                "version": proposal["version"],
                "state": state,
                "actor": actor,
                "evidence": deepcopy(evidence),
                "idempotency_key": idempotency_key,
                "occurred_at": occurred_at,
                "effective_at": effective_at,
                "transition_sha256": transition_sha256,
            }
        )
        proposal["lifecycle_state"] = state
        return {"created": True, "effective_at": effective_at}

    def snapshot(self, *, now=None):
        observed_at = _utc(now or datetime.now(timezone.utc))
        active_events = [
            item for item in self.events
            if item["state"] == "active_for_advice"
            and _timestamp(item["effective_at"]) <= observed_at
        ]
        active = None
        if active_events:
            event = active_events[-1]
            active = deepcopy(
                next(item for item in self.proposals if item["proposal_id"] == event["proposal_id"])
            )
            active["activation"] = deepcopy(event)
        proposals = deepcopy(self.proposals)
        for proposal in proposals:
            proposal["lifecycle_events"] = deepcopy([
                event for event in self.events
                if event["proposal_id"] == proposal["proposal_id"]
            ])
            activation = next(
                (event for event in proposal["lifecycle_events"]
                 if event["state"] == "active_for_advice"),
                None,
            )
            proposal["advice_status"] = (
                "active_for_advice"
                if activation and _timestamp(activation["effective_at"]) <= observed_at
                else "scheduled_for_advice"
                if activation else "inactive"
            )
        return {
            "status": "policy_review_ready",
            "proposals": proposals,
            "active_policy": active,
        }


class PostgresPolicyStore:
    def __init__(self, database_url=None, connect_factory=None):
        self.database_url = str(database_url or os.getenv(DATABASE_URL_ENV, "") or "").strip()
        self.connect_factory = connect_factory
        if not self.database_url:
            raise PolicyStoreUnavailable("rootline_policy_schema_unavailable")

    def _connect(self):
        if self.connect_factory:
            return self.connect_factory(self.database_url)
        try:
            import psycopg
        except ImportError as exc:
            raise PolicyStoreUnavailable("rootline_policy_database_driver_unavailable") from exc
        return psycopg.connect(self.database_url)

    def append_proposal(self, proposal):
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """select version, created, stored_proposed_at
                           from public.rootline_append_operating_policy_proposal(
                           %(policy_id)s,%(proposal_id)s,%(proposal_sha256)s,%(idempotency_key)s,
                           %(policy)s::jsonb,%(evidence)s::jsonb,%(proposed_by)s,%(proposed_at)s)""",
                        {
                            **proposal,
                            "policy": json.dumps(proposal["policy"], sort_keys=True),
                            "evidence": json.dumps(proposal["evidence"], sort_keys=True),
                        },
                    )
                    version, created, stored_proposed_at = cursor.fetchone()
                    return {
                        "created": created,
                        "proposal": {
                            **proposal,
                            "proposed_at": stored_proposed_at.isoformat(),
                            "version": version,
                            "lifecycle_state": "proposed",
                        },
                    }
        except Exception as exc:
            _translate_database_error(exc)

    def append_transition(
        self, proposal_id, state, actor, evidence, idempotency_key, occurred_at,
        effective_at, transition_sha256
    ):
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """select created, stored_effective_at
                           from public.rootline_append_operating_policy_transition(
                           %s,%s,%s,%s::jsonb,%s,%s,%s,%s)""",
                        (
                            proposal_id,
                            state,
                            actor,
                            json.dumps(evidence, sort_keys=True),
                            idempotency_key,
                            occurred_at,
                            effective_at,
                            transition_sha256,
                        ),
                    )
                    created, stored_effective_at = cursor.fetchone()
                    return {
                        "created": created,
                        "effective_at": (
                            stored_effective_at.isoformat()
                            if stored_effective_at is not None else None
                        ),
                    }
        except Exception as exc:
            _translate_database_error(exc)

    def snapshot(self):
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """select proposal_id,version,proposal_sha256,policy_json,evidence_json,
                                  proposed_by,proposed_at,
                                  coalesce((select state from public.rootline_operating_policy_events e
                                    where e.proposal_id=p.proposal_id order by event_sequence desc limit 1),
                                           'proposed')
                           from public.rootline_operating_policy_versions p
                           where policy_id=%s order by version desc""",
                        (POLICY_ID,),
                    )
                    proposals = [
                        {
                            "proposal_id": row[0],
                            "version": row[1],
                            "proposal_sha256": row[2],
                            "policy": row[3],
                            "evidence": row[4],
                            "proposed_by": row[5],
                            "proposed_at": row[6].isoformat(),
                            "lifecycle_state": row[7],
                        }
                        for row in cursor.fetchall()
                    ]
                    cursor.execute(
                        """select proposal_id,state,actor_identity,evidence_json,
                                  occurred_at,effective_at,transition_sha256
                           from public.rootline_operating_policy_events
                           where policy_id=%s order by event_sequence""",
                        (POLICY_ID,),
                    )
                    events_by_proposal = {}
                    for event in cursor.fetchall():
                        events_by_proposal.setdefault(event[0], []).append({
                            "state": event[1],
                            "actor_identity": event[2],
                            "evidence": event[3],
                            "occurred_at": event[4].isoformat(),
                            "effective_at": (
                                event[5].isoformat() if event[5] is not None else None
                            ),
                            "transition_sha256": event[6],
                        })
                    observed_at = datetime.now(timezone.utc)
                    for proposal in proposals:
                        events = events_by_proposal.get(proposal["proposal_id"], [])
                        proposal["lifecycle_events"] = events
                        activation = next(
                            (event for event in events
                             if event["state"] == "active_for_advice"),
                            None,
                        )
                        proposal["advice_status"] = (
                            "active_for_advice"
                            if activation
                            and _timestamp(activation["effective_at"]) <= observed_at
                            else "scheduled_for_advice"
                            if activation else "inactive"
                        )
                    cursor.execute(
                        """select p.proposal_id,p.version,p.proposal_sha256,p.policy_json,
                                  e.actor_identity,e.effective_at
                           from public.rootline_operating_policy_events e
                           join public.rootline_operating_policy_versions p using (proposal_id)
                           where e.policy_id=%s and e.state='active_for_advice'
                                 and e.effective_at <= now()
                           order by e.event_sequence desc limit 1""",
                        (POLICY_ID,),
                    )
                    row = cursor.fetchone()
                    active = None if not row else {
                        "proposal_id": row[0],
                        "version": row[1],
                        "proposal_sha256": row[2],
                        "policy": row[3],
                        "activation": {
                            "actor_identity": row[4],
                            "effective_at": row[5].isoformat(),
                        },
                    }
                    return {
                        "status": "policy_review_ready",
                        "proposals": proposals,
                        "active_policy": active,
                    }
        except Exception as exc:
            _translate_database_error(exc)


def _translate_database_error(exc):
    text = str(exc).lower()
    mappings = {
        "proposal_idempotency_conflict": "proposal_idempotency_conflict",
        "transition_idempotency_conflict": "transition_idempotency_conflict",
        "stale_policy_version": "stale_policy_version",
        "owner_reviewed_state_required": "owner_reviewed_state_required",
        "proposed_state_required": "proposed_state_required",
        "conflicting_transition": "conflicting_transition",
        "policy_proposal_not_found": "policy_proposal_not_found",
        "effective_time_must_not_precede_activation": "effective_time_must_not_precede_activation",
    }
    for marker, status in mappings.items():
        if marker in text:
            raise PolicyConflictError(status) from exc
    if "does not exist" in text or "undefined" in text:
        raise PolicyStoreUnavailable("rootline_policy_schema_unavailable") from exc
    raise PolicyStoreUnavailable("rootline_policy_store_unavailable") from exc


def _failure(status, code):
    return {
        "success": False,
        "status": status,
        "writes_performed": False,
        **AUTHORITY,
    }, code


def _season(value):
    if value == UNKNOWN:
        return UNKNOWN
    if not isinstance(value, dict) or set(value) != {"summer_start", "winter_start"}:
        raise PolicyValidationError("invalid_seasonal_boundaries")
    summer = _month_day(value["summer_start"])
    winter = _month_day(value["winter_start"])
    if summer == winter:
        raise PolicyConflictError("seasonal_boundaries_conflict")
    return {"summer_start": summer, "winter_start": winter}


def _window(value):
    if value == UNKNOWN:
        return UNKNOWN
    if not isinstance(value, dict) or set(value) != {"start", "end"}:
        raise PolicyValidationError("invalid_daylight_window")
    start, end = _clock(value["start"]), _clock(value["end"])
    if start >= end:
        raise PolicyConflictError("daylight_window_must_not_cross_midnight")
    return {"start": start, "end": end, "timezone": "Africa/Johannesburg"}


def _forecast(value):
    if value == UNKNOWN:
        return UNKNOWN
    if not isinstance(value, dict) or set(value) != {
        "amount_mm",
        "probability_pct",
        "horizon_hours",
    }:
        raise PolicyValidationError("invalid_forecast_rain_policy")
    return {
        "amount_mm": _number(value["amount_mm"], 0, 200, "invalid_forecast_amount"),
        "probability_pct": _number(
            value["probability_pct"], 0, 100, "invalid_forecast_probability"
        ),
        "horizon_hours": _integer(value["horizon_hours"], 1, 168, "invalid_forecast_horizon"),
    }


def _live_rain_hold(value):
    if value == UNKNOWN:
        return UNKNOWN
    if not isinstance(value, dict) or set(value) != {
        "evidence_field",
        "threshold_mm_per_hour",
        "comparison",
        "release_policy",
    }:
        raise PolicyValidationError("invalid_live_rain_hold_policy")
    if value["evidence_field"] != "current_rain_rate_mm_per_hour":
        raise PolicyValidationError("invalid_live_rain_evidence_field")
    if value["comparison"] != "greater_than":
        raise PolicyValidationError("invalid_live_rain_comparison")
    if value["release_policy"] != UNKNOWN:
        raise PolicyValidationError("live_rain_release_policy_must_remain_unknown")
    return {
        "evidence_field": "current_rain_rate_mm_per_hour",
        "threshold_mm_per_hour": _confirmed_live_rain_threshold(
            value["threshold_mm_per_hour"]
        ),
        "comparison": "greater_than",
        "release_policy": UNKNOWN,
    }


def _temperature(value):
    if value == UNKNOWN:
        return UNKNOWN
    if not isinstance(value, dict) or set(value) != {"minimum_c", "maximum_c"}:
        raise PolicyValidationError("invalid_temperature_limits")
    low = _number(value["minimum_c"], -20, 50, "invalid_minimum_temperature")
    high = _number(value["maximum_c"], -20, 60, "invalid_maximum_temperature")
    if low >= high:
        raise PolicyConflictError("temperature_limits_conflict")
    return {"minimum_c": low, "maximum_c": high}


def _crop_bands(value):
    if value == UNKNOWN:
        return UNKNOWN
    if not isinstance(value, dict) or set(value) != set(ZONES):
        raise PolicyValidationError("exact_crop_need_identity_required")
    result = {}
    for zone_id, crop in ZONES.items():
        item = value[zone_id]
        if item == UNKNOWN:
            result[zone_id] = UNKNOWN
            continue
        if not isinstance(item, dict) or set(item) != {
            "low_mm_per_day",
            "medium_mm_per_day",
            "high_mm_per_day",
        }:
            raise PolicyValidationError("invalid_crop_need_bands")
        bands = [
            _number(item["low_mm_per_day"], 0, 50, "invalid_crop_need_band"),
            _number(item["medium_mm_per_day"], 0, 50, "invalid_crop_need_band"),
            _number(item["high_mm_per_day"], 0, 50, "invalid_crop_need_band"),
        ]
        if not bands[0] < bands[1] < bands[2]:
            raise PolicyConflictError("crop_need_bands_must_increase")
        result[zone_id] = {
            "crop_use": crop,
            "low_mm_per_day": bands[0],
            "medium_mm_per_day": bands[1],
            "high_mm_per_day": bands[2],
            "measured_delivery_inferred": False,
        }
    return result


def _power_loss(value):
    if value == UNKNOWN:
        return UNKNOWN
    if not isinstance(value, dict) or set(value) != {"observed_state", "evidence_note"}:
        raise PolicyValidationError("invalid_power_loss_evidence")
    state = str(value["observed_state"] or "").strip()
    if state not in {
        "fail_closed_physically_verified",
        "fails_open_physically_verified",
        "other_physically_verified",
    }:
        raise PolicyValidationError("unverified_power_loss_state")
    note = str(value["evidence_note"] or "").strip()
    if not note or len(note) > 500:
        raise PolicyValidationError("bounded_power_loss_evidence_required")
    return {"observed_state": state, "evidence_note": note}


def _drainage(value):
    if value == UNKNOWN:
        return UNKNOWN
    if not isinstance(value, dict) or set(value) != {
        "observation_seconds",
        "classification",
        "evidence_note",
    }:
        raise PolicyValidationError("invalid_residual_drainage")
    classification = str(value["classification"] or "").strip()
    if classification not in {"none", "diminishing", "continued_full_pressure"}:
        raise PolicyValidationError("invalid_residual_drainage_classification")
    note = str(value["evidence_note"] or "").strip()
    if not note or len(note) > 500:
        raise PolicyValidationError("bounded_drainage_evidence_required")
    return {
        "observation_seconds": _integer(
            value["observation_seconds"], 0, 1800, "invalid_drainage_observation"
        ),
        "classification": classification,
        "evidence_note": note,
        "measured_water_inferred": False,
    }


def _unknown_or_int(value, low, high, status):
    return UNKNOWN if value == UNKNOWN else _integer(value, low, high, status)


def _confirmed_live_rain_threshold(value):
    threshold = _number(value, 0, 100, "invalid_live_rain_threshold")
    if threshold != 0.2:
        raise PolicyValidationError("live_rain_threshold_not_owner_confirmed")
    return threshold


def _integer(value, low, high, status):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise PolicyValidationError(status)
    return value


def _number(value, low, high, status):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyValidationError(status)
    number = float(value)
    if not low <= number <= high:
        raise PolicyValidationError(status)
    return number


def _month_day(value):
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{2}-\d{2}", text):
        raise PolicyValidationError("seasonal_boundary_must_be_mm_dd")
    try:
        datetime.strptime(f"2000-{text}", "%Y-%m-%d")
    except ValueError as exc:
        raise PolicyValidationError("invalid_seasonal_boundary_date") from exc
    return text


def _clock(value):
    text = str(value or "").strip()
    try:
        return datetime.strptime(text, "%H:%M").strftime("%H:%M")
    except ValueError as exc:
        raise PolicyValidationError("time_window_must_be_hh_mm") from exc


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise PolicyValidationError("timezone_qualified_effective_time_required") from exc
    if parsed.tzinfo is None:
        raise PolicyValidationError("timezone_qualified_effective_time_required")
    return _utc(parsed)


def _utc(value):
    if value.tzinfo is None:
        raise PolicyValidationError("timezone_qualified_time_required")
    return value.astimezone(timezone.utc)


def _digest(value):
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _classify_unknown(key, value, resolved, unknown):
    target = unknown if value == UNKNOWN or (
        isinstance(value, dict) and any(item == UNKNOWN for item in value.values())
    ) else resolved
    target.append(key)
