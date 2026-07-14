"""Fail-closed owner gate for a one-time Meta paid boost.

This module deliberately has no database or network implementation.  Production
adapters require a separately approved migration, paid policy, credentials, and
live-spend authority.  Tests inject resolvers, an append-only claim recorder,
and a mocked provider.
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import os
import re


META_BOOST_ENABLED_ENV = "BEACON_META_BOOST_ENABLED"
META_BOOST_POLICY_ENV = "BEACON_META_BOOST_OWNER_POLICY_APPROVED"
META_AD_ACCOUNT_ID_ENV = "META_AD_ACCOUNT_ID"
META_ADS_ACCESS_TOKEN_ENV = "META_ADS_ACCESS_TOKEN"
PERFORMANCE_MAX_AGE_SECONDS = 24 * 60 * 60
FULFILMENT_MAX_AGE_SECONDS = 15 * 60
POST_ID_PATTERN = re.compile(r"^[A-Za-z0-9]+_[A-Za-z0-9]+$")


def meta_boost_confirmation_phrase(post_id, total_cap_zar, duration_days):
    amount = Decimal(str(total_cap_zar)).quantize(Decimal("0.01"))
    return f"BOOST {post_id} FOR ZAR {amount:.2f} TOTAL OVER {int(duration_days)} DAYS"


def meta_boost_policy(environ=None):
    env = environ or os.environ
    enabled = _truthy(env.get(META_BOOST_ENABLED_ENV))
    policy_approved = _truthy(env.get(META_BOOST_POLICY_ENV))
    credentials_ready = bool(env.get(META_AD_ACCOUNT_ID_ENV) and env.get(META_ADS_ACCESS_TOKEN_ENV))
    blockers = []
    if not enabled:
        blockers.append("meta_boost_disabled")
    if not policy_approved:
        blockers.append("paid_policy_missing")
    if not credentials_ready:
        blockers.append("meta_ads_credentials_missing")
    return {
        "mode": "beacon_meta_paid_boost_red_zone",
        "status": "ready_for_owner_execution" if not blockers else "hard_stopped",
        "enabled": enabled,
        "paid_policy_approved": policy_approved,
        "credentials_ready": credentials_ready,
        "blockers": blockers,
        "currency": "ZAR",
        "budget_semantics": "fixed_lifetime_total_cap_only",
        "recurring_spend": False,
        "automatic_execution": False,
        "provider_configured": False,
        "writes_customer_order_stock_payment_or_lifecycle": False,
    }


def execute_meta_boost(payload, *, publication_resolver=None, performance_resolver=None,
                       fulfilment_resolver=None, approval_resolver=None, claim_recorder=None,
                       provider=None, result_recorder=None, environ=None, now=None):
    """Validate trusted evidence and invoke an injected provider at most once."""
    policy = meta_boost_policy(environ)
    if policy["blockers"]:
        return _blocked(policy["blockers"][0], policy), 503
    if not all((publication_resolver, performance_resolver, fulfilment_resolver,
                approval_resolver, claim_recorder, provider, result_recorder)):
        return _blocked("paid_boost_adapters_not_configured", policy), 503

    now = now or datetime.now(timezone.utc)
    approval_id = _text(payload.get("approval_id"))
    approval = approval_resolver(approval_id) if approval_id else None
    if not approval or approval.get("status") != "owner_approved":
        return _blocked("owner_approval_missing", policy), 409
    error = _approval_error(approval, now)
    if error:
        return _blocked(error, policy), 409

    publication = publication_resolver(approval.get("publication_evidence_id"))
    post_id = _text((publication or {}).get("canonical_post_id"))
    if (not publication or publication.get("status") != "published" or
            not POST_ID_PATTERN.fullmatch(post_id) or post_id != _text(approval.get("canonical_post_id"))):
        return _blocked("canonical_published_post_mismatch", policy), 409

    performance = performance_resolver(approval.get("performance_event_id"))
    if not performance or _text(performance.get("performance_event_id")) != _text(approval.get("performance_event_id")):
        return _blocked("boost_performance_evidence_missing", policy), 409
    if performance.get("recommended_action") != "light_boost_owner_review":
        return _blocked("latest_performance_does_not_recommend_boost", policy), 409
    if not _fresh(performance.get("created_at"), now, PERFORMANCE_MAX_AGE_SECONDS):
        return _blocked("boost_performance_evidence_stale", policy), 409
    if _text(performance.get("canonical_post_id")) != post_id:
        return _blocked("boost_performance_post_mismatch", policy), 409

    fulfilment = fulfilment_resolver(approval.get("fulfilment_revision"))
    if (not fulfilment or _text(fulfilment.get("revision")) != _text(approval.get("fulfilment_revision")) or
            fulfilment.get("status") != "safe" or int(fulfilment.get("residual_capacity") or 0) <= 0):
        return _blocked("fulfilment_not_safe", policy), 409
    if not _fresh(fulfilment.get("checked_at"), now, FULFILMENT_MAX_AGE_SECONDS):
        return _blocked("fulfilment_evidence_stale", policy), 409

    phrase = meta_boost_confirmation_phrase(post_id, approval["total_cap_zar"], approval["duration_days"])
    if payload.get("final_confirmation") != phrase:
        response = _blocked("exact_final_confirmation_required", policy)
        response["required_confirmation"] = phrase
        return response, 409

    key = _idempotency_key(approval)
    claim = claim_recorder({"event": "claim", "idempotency_key": key, "approval_id": approval_id,
                            "canonical_post_id": post_id})
    if not claim.get("created"):
        return {"success": bool(claim.get("success")), "status": claim.get("status", "already_claimed"),
                "idempotency_key": key, "provider_invoked": False, "policy": policy}, 200

    provider_payload = {"canonical_post_id": post_id, "currency": "ZAR",
                        "lifetime_budget_minor": int(Decimal(str(approval["total_cap_zar"])) * 100),
                        "duration_days": int(approval["duration_days"]), "idempotency_key": key}
    try:
        provider_result = provider.create_fixed_lifetime_boost(provider_payload)
        status = "executed" if provider_result.get("success") else "provider_rejected"
    except TimeoutError:
        provider_result = {"success": False, "provider_reference": "", "uncertain": True}
        status = "provider_acceptance_uncertain"
    evidence = {"event": "result", "idempotency_key": key, "status": status,
                "provider_reference": _text(provider_result.get("provider_reference"))[:160],
                "uncertain": bool(provider_result.get("uncertain"))}
    result_recorder(evidence)
    return {"success": status == "executed", "status": status, "idempotency_key": key,
            "provider_invoked": True, "execution_evidence": evidence, "policy": policy}, (200 if status == "executed" else 502)


def _approval_error(approval, now):
    if approval.get("currency") != "ZAR":
        return "zar_total_cap_required"
    try:
        if Decimal(str(approval.get("total_cap_zar"))) <= 0:
            return "positive_total_cap_required"
        duration = int(approval.get("duration_days"))
    except (InvalidOperation, TypeError, ValueError):
        return "fixed_total_cap_and_duration_required"
    if duration < 1 or duration > 30 or approval.get("budget_type") != "lifetime_total":
        return "fixed_lifetime_total_cap_only"
    if not _future(approval.get("expires_at"), now):
        return "owner_approval_expired"
    for field in ("canonical_post_id", "publication_evidence_id", "performance_event_id", "fulfilment_revision", "owner_id"):
        if not _text(approval.get(field)):
            return "owner_approval_binding_incomplete"
    return ""


def _idempotency_key(approval):
    raw = "|".join(_text(approval.get(k)) for k in
                   ("approval_id", "canonical_post_id", "performance_event_id", "fulfilment_revision",
                    "currency", "total_cap_zar", "duration_days"))
    return "meta-boost-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _blocked(status, policy):
    return {"success": False, "status": status, "provider_invoked": False, "policy": policy}


def _fresh(value, now, max_age):
    stamp = _datetime(value)
    return bool(stamp and 0 <= (now - stamp).total_seconds() <= max_age)


def _future(value, now):
    stamp = _datetime(value)
    return bool(stamp and stamp > now)


def _datetime(value):
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _text(value):
    return str(value or "").strip()


def _truthy(value):
    return _text(value).lower() in {"1", "true", "yes", "on"}
