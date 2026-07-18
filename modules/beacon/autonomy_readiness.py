"""Fail-closed, read-only BEACON autonomy-readiness evaluation.

The local SQLite registry is deliberately separate from campaign calendar
authority.  It stores policy lifecycle evidence and an idempotent local
threshold-notification claim; it never calls providers or changes operations.
"""

from copy import deepcopy
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3


GATE_NAMES = (
    "campaign_evidence", "unedited_approval_rate", "attribution_completeness",
    "recommendation_accuracy", "safety_incidents", "trust_history", "budget_compliance",
)
READ_ONLY_AUTHORITY = {
    "read_only": True, "posts_publicly": False, "sends_customer_message": False,
    "spends_money": False, "calls_meta": False, "calls_chatwoot": False,
    "calls_n8n": False, "creates_order": False, "creates_reservation": False,
    "changes_stock": False, "writes_farm_data": False, "approves_policy": False,
}


class AutonomyPolicyRegistry:
    """Append-only local policy authority and idempotency-claim store."""

    def __init__(self, database_path=None):
        configured = database_path or os.getenv("BEACON_AUTONOMY_POLICY_DB_PATH")
        self.database_path = str(Path(configured or "instance/beacon_autonomy_policy.sqlite3"))
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute("""create table if not exists beacon_autonomy_policy_events (
                sequence integer primary key autoincrement, event_type text not null,
                policy_id text not null, policy_version integer not null, policy_json text not null)""")
            connection.execute("""create table if not exists beacon_autonomy_notification_claims (
                claim_key text primary key, policy_sha256 text not null,
                evidence_sha256 text not null, created_at text not null)""")
            connection.commit()

    def _connect(self):
        return sqlite3.connect(self.database_path, timeout=10)

    def record(self, event_type, policy):
        snapshot = deepcopy(policy)
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "insert into beacon_autonomy_policy_events (event_type, policy_id, policy_version, policy_json) values (?, ?, ?, ?)",
                (event_type, snapshot["policy_id"], snapshot["policy_version"], json.dumps(snapshot, sort_keys=True)),
            )
            connection.commit()
        return {"sequence": cursor.lastrowid, "event_type": event_type, "policy": snapshot}

    def latest_policy(self, policy_id):
        with closing(self._connect()) as connection:
            row = connection.execute("select policy_json from beacon_autonomy_policy_events where policy_id = ? order by policy_version desc, sequence desc limit 1", (policy_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    def approved_policy(self, policy_id, version):
        with closing(self._connect()) as connection:
            row = connection.execute("select policy_json from beacon_autonomy_policy_events where policy_id = ? and policy_version = ? and event_type = 'owner_approved' order by sequence desc limit 1", (policy_id, version)).fetchone()
        return json.loads(row[0]) if row else {}

    def claim_notification(self, policy_sha256, evidence_sha256, now):
        key = _digest({"policy_sha256": policy_sha256, "evidence_sha256": evidence_sha256})
        with closing(self._connect()) as connection:
            cursor = connection.execute("insert or ignore into beacon_autonomy_notification_claims (claim_key, policy_sha256, evidence_sha256, created_at) values (?, ?, ?, ?)", (key, policy_sha256, evidence_sha256, now.isoformat()))
            connection.commit()
        return bool(cursor.rowcount), key

    def clear(self):
        with closing(self._connect()) as connection:
            connection.execute("delete from beacon_autonomy_policy_events")
            connection.execute("delete from beacon_autonomy_notification_claims")
            connection.commit()


AUTONOMY_POLICY_REGISTRY = AutonomyPolicyRegistry()


def propose_threshold_policy(payload, now=None, registry=None):
    """Append a proposed immutable policy version; no approval occurs here."""
    payload, registry, now = payload if isinstance(payload, dict) else {}, registry or AUTONOMY_POLICY_REGISTRY, _utc(now)
    prior = registry.latest_policy(_text(payload.get("policy_id")))
    policy = {
        "policy_id": _text(payload.get("policy_id")), "policy_version": int(prior.get("policy_version") or 0) + 1,
        "authority_state": "proposed", "effective_at": _text(payload.get("effective_at")),
        "expires_at": _text(payload.get("expires_at")), "evidence_schema_version": _text(payload.get("evidence_schema_version")),
        "max_evidence_age_seconds": payload.get("max_evidence_age_seconds"),
        "thresholds": deepcopy(payload.get("thresholds") if isinstance(payload.get("thresholds"), dict) else {}),
        "supersedes_version": prior.get("policy_version"), "created_at": now.isoformat(),
    }
    policy["policy_sha256"] = _digest(_policy_content(policy))
    errors = _policy_definition_errors(policy)
    if not errors:
        registry.record("proposed", policy)
    return _packet(not errors, "policy_version_proposed" if not errors else "policy_version_invalid", errors, policy=policy)


def approve_threshold_policy(policy, owner_id, approved_at=None, registry=None):
    """Record exact owner approval for the latest proposed policy only."""
    registry, policy = registry or AUTONOMY_POLICY_REGISTRY, deepcopy(policy) if isinstance(policy, dict) else {}
    authoritative = registry.latest_policy(policy.get("policy_id"))
    errors = _policy_definition_errors(policy)
    if not authoritative or authoritative.get("policy_version") != policy.get("policy_version") or authoritative.get("policy_sha256") != policy.get("policy_sha256"):
        errors.append("policy_proposal_not_authoritative")
    if policy.get("authority_state") != "proposed": errors.append("policy_state_must_be_proposed")
    if not _text(owner_id): errors.append("owner_identity_required")
    if policy.get("policy_sha256") != _digest(_policy_content(policy)): errors.append("policy_content_hash_mismatch")
    approved_at = _utc(approved_at)
    approved = deepcopy(policy)
    approved.update({"authority_state": "owner_approved", "approved_by": _text(owner_id), "approved_at": approved_at.isoformat(), "approval_id": "BEACON-AUTONOMY-APPROVAL-" + _digest({"policy": policy.get("policy_sha256"), "owner": owner_id, "at": approved_at.isoformat()})[:20].upper()})
    if not errors: registry.record("owner_approved", approved)
    return _packet(not errors, "policy_version_owner_approved" if not errors else "policy_approval_rejected", errors, policy=approved if not errors else policy)


def evaluate_autonomy_readiness(policy_id, evidence, now=None, registry=None, supplied_policy_sha256=None):
    """Resolve server policy, validate seven gates, and optionally claim one notification."""
    registry, now = registry or AUTONOMY_POLICY_REGISTRY, _utc(now)
    policy, evidence = registry.latest_policy(_text(policy_id)), evidence if isinstance(evidence, dict) else {}
    evidence_sha256 = _digest(evidence)
    policy_errors = _policy_eligibility_errors(policy, now, supplied_policy_sha256)
    gates = {name: {"passed": False, "blockers": ["policy_not_eligible"]} for name in GATE_NAMES}
    if not policy_errors:
        gates = {name: _evaluate_gate(name, evidence.get(name), policy, now) for name in GATE_NAMES}
    all_gates_passed = not policy_errors and all(result["passed"] for result in gates.values())
    created, claim_key = (False, "")
    if all_gates_passed:
        created, claim_key = registry.claim_notification(policy["policy_sha256"], evidence_sha256, now)
    return _packet(all_gates_passed, "autonomy_ready" if all_gates_passed else "autonomy_not_ready", policy_errors,
                   policy={key: policy.get(key) for key in ("policy_id", "policy_version", "policy_sha256", "authority_state", "approval_id", "approved_by", "approved_at")},
                   gates=gates, all_gates_passed=all_gates_passed, can_promote=all_gates_passed,
                   evidence_sha256=evidence_sha256, notification_created=created,
                   notification_already_claimed=all_gates_passed and not created, notification_claim_key=claim_key)


def _evaluate_gate(name, item, policy, now):
    item = item if isinstance(item, dict) else {}
    blockers = _evidence_errors(item, policy, now)
    threshold = policy["thresholds"].get(name, {})
    value = item.get("value")
    if name == "campaign_evidence": blockers.extend(_minimum(value, threshold.get("minimum_count"), "campaign_evidence_below_minimum"))
    elif name in {"unedited_approval_rate", "attribution_completeness", "recommendation_accuracy"}:
        blockers.extend(_rate(value, threshold.get("minimum_rate"), name + "_below_minimum"))
    elif name == "safety_incidents":
        if _number(value) is None or _number(value) < 0:
            blockers.append("safety_incidents_invalid")
        else:
            blockers.extend(_maximum(value, threshold.get("maximum_open_incidents"), "safety_incidents_above_maximum"))
    elif name == "trust_history":
        blockers.extend(_minimum(value, threshold.get("minimum_score"), "trust_history_below_minimum"))
        blockers.extend(_minimum(item.get("completed_evaluations"), threshold.get("minimum_completed_evaluations"), "trust_history_insufficient_evaluations"))
    else:
        if _text(item.get("currency")) != _text(threshold.get("currency")): blockers.append("budget_currency_mismatch")
        actual_spend, approved_cap = _number(item.get("actual_spend")), _number(item.get("approved_cap"))
        if actual_spend is None or actual_spend < 0: blockers.append("budget_actual_spend_invalid")
        if approved_cap is None or approved_cap < 0: blockers.append("budget_approved_cap_invalid")
        if actual_spend is not None and approved_cap is not None and actual_spend >= 0 and approved_cap >= 0:
            blockers.extend(_maximum(actual_spend, approved_cap, "budget_cap_exceeded"))
    return {"passed": not blockers, "blockers": sorted(set(blockers))}


def _evidence_errors(item, policy, now):
    errors = []
    if _text(item.get("schema_version")) != policy["evidence_schema_version"]: errors.append("evidence_schema_incompatible")
    if not _text(item.get("evidence_id")) or not _text(item.get("source")): errors.append("evidence_provenance_required")
    recorded = _parse_datetime(item.get("recorded_at")); max_age = _number(policy.get("max_evidence_age_seconds"))
    if not recorded or max_age is None or max_age < 0 or recorded > now or (now - recorded).total_seconds() > max_age: errors.append("evidence_stale_or_invalid")
    if item.get("superseded") is True or item.get("malformed") is True or item.get("conflicting") is True: errors.append("evidence_not_current")
    return errors


def _policy_eligibility_errors(policy, now, supplied_hash):
    if not policy: return ["policy_not_found"]
    errors = _policy_definition_errors(policy)
    if policy.get("policy_sha256") != _digest(_policy_content(policy)): errors.append("policy_content_hash_mismatch")
    if policy.get("authority_state") != "owner_approved": errors.append("policy_not_owner_approved")
    if not _text(policy.get("approval_id")) or not _text(policy.get("approved_by")) or not _text(policy.get("approved_at")): errors.append("owner_approval_evidence_required")
    effective, expires = _parse_datetime(policy.get("effective_at")), _parse_datetime(policy.get("expires_at"))
    if not effective or now < effective: errors.append("policy_not_effective")
    if not expires or expires <= now: errors.append("policy_expired")
    if supplied_hash is not None and _text(supplied_hash) != policy.get("policy_sha256"): errors.append("caller_policy_hash_mismatch")
    return sorted(set(errors))


def _policy_definition_errors(policy):
    errors = []
    for key in ("policy_id", "effective_at", "expires_at", "evidence_schema_version"):
        if not _text(policy.get(key)): errors.append(key + "_required")
    if not isinstance(policy.get("policy_version"), int) or policy.get("policy_version", 0) < 1: errors.append("policy_version_invalid")
    if _parse_datetime(policy.get("effective_at")) is None or _parse_datetime(policy.get("expires_at")) is None: errors.append("policy_window_invalid")
    if not isinstance(policy.get("thresholds"), dict) or set(policy.get("thresholds", {})) != set(GATE_NAMES): errors.append("policy_thresholds_invalid")
    if _number(policy.get("max_evidence_age_seconds")) is None: errors.append("max_evidence_age_seconds_invalid")
    budget_threshold = policy.get("thresholds", {}).get("budget_compliance") if isinstance(policy.get("thresholds"), dict) else {}
    if not isinstance(budget_threshold, dict) or not _valid_currency(budget_threshold.get("currency")):
        errors.append("budget_currency_invalid")
    return errors


def _minimum(value, minimum, code):
    return [] if _number(value) is not None and _number(minimum) is not None and _number(value) >= _number(minimum) else [code]
def _maximum(value, maximum, code):
    return [] if _number(value) is not None and _number(maximum) is not None and _number(value) <= _number(maximum) else [code]
def _rate(value, minimum, code):
    return [] if _number(value) is not None and 0 <= _number(value) <= 1 and _number(minimum) is not None and _number(value) >= _number(minimum) else [code]
def _policy_content(policy):
    return {key: policy.get(key) for key in ("policy_id", "policy_version", "effective_at", "expires_at", "evidence_schema_version", "max_evidence_age_seconds", "thresholds", "supersedes_version")}
def _packet(success, status, errors, **extra): return {"success": success, "status": status, "errors": sorted(set(errors)), "authority": deepcopy(READ_ONLY_AUTHORITY), **extra}
def _digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
def _text(value): return str(value or "").strip()
def _valid_currency(value):
    currency = _text(value)
    return len(currency) == 3 and currency.isascii() and currency.isalpha() and currency == currency.upper()
def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError): return None
def _parse_datetime(value):
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00")); return parsed if parsed.tzinfo else None
    except ValueError: return None
def _utc(value):
    if isinstance(value, datetime):
        if value.tzinfo is None: raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)
    return _parse_datetime(value).astimezone(timezone.utc) if _parse_datetime(value) else datetime.now(timezone.utc)
