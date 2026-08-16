"""Typed non-owner family runtime for the existing authenticated gateway.

Authority is resolved before any context/evidence loader is callable.  This
module does not mint owner authority and does not contain a business writer.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Mapping

from modules.oom_sakkie.family_access import (
    FamilyPrincipal, FamilyRole, authorize_family_message,
)


ZERO = {"writes_farm_data": False, "hardware_commands": 0,
        "protected_actions_performed": False}
SUMMARY_DOMAINS = frozenset({"herd", "welfare", "breeding", "farrowing",
    "rootline", "irrigation", "water", "weather", "power"})
CHARL_ONLY = re.compile(
    r"\b(?:confirm mortality|approve treatment|medication|mate|mating|commission|"
    r"mother valve|fertili[sz]er|borehole|electrical|payment|customer|publish|"
    r"permission|revoke|autonomy|system|mission|bevestig\s+(?:die\s+)?dood|"
    r"behandel|behandeling|medikasie|doseer|dek|paring|teelbesluit|"
    r"registreer.*(?:dood|verkoop|skuif)|lewensiklus|toestemming|herroep|"
    r"outonomie|publiseer|kliënt|betaling)\b", re.I)
WELFARE_HOLD = re.compile(r"\b(?:welfare hold|hold welfare|welstand.*stop|hou.*welstand)\b", re.I)
WELFARE_ESCALATE = re.compile(r"\b(?:escalate welfare|welfare escalation|eskaleer.*welstand|welstand.*eskaleer)\b", re.I)
FOUND_DEAD = re.compile(r"\b(?:found dead|dood gevind|is dood)\b", re.I)
HEALTH = re.compile(r"\b(?:sick|ill|injur|not eating|limp|bleed|siek|beseer|eet nie|mank|bloei)\b", re.I)
IRRIGATION_ACTION_SHAPED = re.compile(
    r"\b(?:stop|start|pause|reschedule)\s+(?:the\s+)?irrigation\b|"
    r"\b(?:stop|begin|onderbreek|herskeduleer|skuif)\s+(?:die\s+)?besproeiing\b", re.I)


def handle_family_runtime_message(parsed: Mapping[str, Any], principal: FamilyPrincipal, *,
        summary_loader: Callable[..., Mapping[str, Any]] | None = None,
        observation_adapter: Callable[..., Mapping[str, Any]] | None = None,
        contextual_loader: Callable[..., Mapping[str, Any] | None] | None = None,
        contextual_adapter: Callable[..., Mapping[str, Any]] | None = None,
        rootline_adapter: Callable[..., Mapping[str, Any]] | None = None,
        replay_store: Callable[..., Mapping[str, Any]] | None = None) -> tuple[dict[str, Any], int]:
    """Authorize one family capability before invoking its sole typed adapter."""
    if principal.role in {FamilyRole.OWNER, FamilyRole.UNKNOWN_SENDER}:
        return _contained("family_runtime_principal_not_delegated", success=False), 403
    capability, domain = resolve_family_capability(parsed, principal)
    decision = authorize_family_message(principal, parsed, capability=capability,
        summary_domain=domain)
    base = {"handled": True, "family_role": principal.role.value,
        "family_key": principal.family_key, "language": principal.language,
        "capability": capability, "summary_domain": domain,
        "authorization_id": principal.authorization_id,
        "binding_digest": principal.binding_digest,
        "replay_identity": decision.replay_identity,
        "audit_trace_recorded": False, **ZERO}
    if (capability == "unsupported_family_capability"
            and principal.role is FamilyRole.FARM_MANAGER
            and not IRRIGATION_ACTION_SHAPED.search(str(parsed.get("text") or ""))):
        return {**base, **_contained("family_clarification_required"),
            "answer": ("Wil jy plaas-, kudde-, welstand-, teel-, water-, weer- of "
                       "kragbewyse sien, of wil jy 'n plaaswaarneming rapporteer?")}, 200
    if not decision.allowed:
        return {**base, **_contained("family_capability_denied", success=False),
            "answer": "Ek kan nie dié versoek met hierdie familieprofiel uitvoer nie."}, 403
    if capability == "explicit_summary":
        if summary_loader is None:
            return {**base, **_unavailable()}, 503
        packet = summary_loader(principal=principal, domain=domain)
        return {**base, **compose_family_summary(principal, domain, packet)}, 200
    if capability == "active_follow_up":
        if contextual_loader is None or contextual_adapter is None:
            return {**base, **_unavailable()}, 503
        # The loader becomes reachable only after the capability decision above.
        claim = _claim_replay(replay_store, decision, principal, parsed, capability)
        if claim.get("allowed") is not True:
            return {**base, **claim["result"]}, claim["status"]
        base["audit_trace_recorded"] = True
        context = contextual_loader(principal=principal, family_key=principal.family_key,
            binding_digest=principal.binding_digest, capability=capability,
            provider_message_id=str(parsed.get("provider_message_id") or ""),
            provider_timestamp=str(parsed.get("provider_timestamp") or ""),
            replay_identity=decision.replay_identity)
        if (not isinstance(context, Mapping)
                or str(context.get("owner_user_id") or "") != principal.telegram_user_id
                or str(context.get("family_key") or "") != principal.family_key
                or str(context.get("binding_digest") or "") != principal.binding_digest):
            return {**base, **_contained("family_context_not_owned", success=False)}, 403
        result = contextual_adapter(parsed=parsed, principal=principal, context=context,
                                    replay_identity=decision.replay_identity)
        bounded, code = _bounded_result(result, capability=capability)
        return {**base, **bounded}, code
    adapter = rootline_adapter if capability.startswith("irrigation_") else observation_adapter
    if adapter is None:
        return {**base, **_unavailable()}, 503
    claim = _claim_replay(replay_store, decision, principal, parsed, capability)
    if claim.get("allowed") is not True:
        return {**base, **claim["result"]}, claim["status"]
    base["audit_trace_recorded"] = True
    result = adapter(parsed=parsed, principal=principal, capability=capability,
                     replay_identity=decision.replay_identity)
    bounded, code = _bounded_result(result, capability=capability)
    return {**base, **bounded}, code


def resolve_family_capability(parsed: Mapping[str, Any], principal: FamilyPrincipal) -> tuple[str, str]:
    text = str(parsed.get("text") or "").strip()
    if CHARL_ONLY.search(text): return "owner_protected_request", ""
    if str(parsed.get("reply_to_message_id") or "").strip(): return "active_follow_up", ""
    action = parsed.get("family_action") if isinstance(parsed.get("family_action"), Mapping) else {}
    action_capability = str(action.get("capability") or "")
    if (action_capability in {"irrigation_start", "irrigation_continue"}
            and all(str(action.get(key) or "").strip() for key in
                    ("decision_id", "commissioned_path_id", "evidence_generation"))):
        return action_capability, ""
    if (action_capability in {"herdmaster_management_input", "herdmaster_reassessment"}
            and all(str(action.get(key) or "").strip() for key in
                    ("decision_id", "evidence_generation"))):
        return action_capability, ""
    if IRRIGATION_ACTION_SHAPED.search(text): return "unsupported_family_capability", ""
    if WELFARE_ESCALATE.search(text): return "welfare_escalation", ""
    if WELFARE_HOLD.search(text): return "welfare_hold", ""
    if FOUND_DEAD.search(text): return "found_dead_observation", ""
    if HEALTH.search(text): return "farm_observation", ""
    domain = _summary_domain(text)
    if domain: return "explicit_summary", domain
    return "unsupported_family_capability", ""


def compose_family_summary(principal: FamilyPrincipal, domain: str,
                           packet: Mapping[str, Any]) -> dict[str, Any]:
    """Render only an already-filtered evidence packet; never copy an owner brief."""
    if domain not in SUMMARY_DOMAINS or domain not in principal.summary_domains:
        return {**_contained("family_summary_scope_denied", success=False), "answer": ""}
    if not isinstance(packet, Mapping) or packet.get("available") is not True:
        return _unavailable()
    lines = [str(value).strip() for value in packet.get("summary_lines", ())
             if str(value).strip()][:5]
    question = str(packet.get("question") or "").strip()
    if not lines:
        return _unavailable()
    heading = "Plaasbestuurder-opdatering" if principal.role is FamilyRole.FARM_MANAGER else "Familie-opdatering"
    answer = f"<b>{heading}</b>\n\n" + "\n".join(f"• {line}" for line in lines)
    if question: answer += "\n\n" + question
    return {**_contained("family_summary_ready"), "answer": answer,
        "reply_markup": None}


def _summary_domain(text: str) -> str:
    folded = text.casefold()
    terms = (("welfare", ("welfare", "welstand")), ("breeding", ("breeding", "teel")),
        ("farrowing", ("farrowing", "kraam")), ("water", ("water", "reservoir", "storage", "opgaardam")),
        ("weather", ("weather", "weer", "rain", "reën")), ("power", ("power", "krag", "solar")),
        ("irrigation", ("irrigation", "besproeiing")), ("herd", ("herd", "pigs", "varke", "diere")))
    return next((domain for domain, words in terms if any(word in folded for word in words)), "")


def _bounded_result(result: Mapping[str, Any], *, capability="") -> tuple[dict[str, Any], int]:
    if not isinstance(result, Mapping): return _unavailable(), 503
    verified_rootline = (_verified_rootline_outcome(result.get("rootline_outcome"))
        if capability in {"irrigation_start", "irrigation_continue"} else None)
    hardware_commands = int(result.get("hardware_commands") or 0)
    if (result.get("writes_farm_data") is True
            or (hardware_commands and (not verified_rootline
                or hardware_commands != int(verified_rootline.get("hardware_commands") or 0)))
            or result.get("protected_actions_performed") is True
            or int(result.get("animal_mutations") or 0)
            or result.get("writes_customer_data") is True
            or result.get("writes_payment_data") is True
            or int(result.get("marketing_effects") or 0)
            or result.get("configuration_changed") is True
            or result.get("authority_changed") is True):
        return ({**_contained("family_adapter_authority_violation", success=False),
            "answer": "Die versoek is veilig gestop. Geen plaas- of toerustingverandering is toegelaat nie."}, 503)
    safe = {"success": result.get("success") is True,
        "status": str(result.get("status") or "family_adapter_contained")[:100],
        "answer": str(result.get("answer") or "")[:2000], **ZERO}
    if verified_rootline:
        safe.update({"hardware_commands": hardware_commands,
            "rootline_outcome_sha256": verified_rootline["outcome_sha256"]})
    return safe, 200 if safe["success"] else 503


def _verified_rootline_outcome(value):
    if not isinstance(value, Mapping) or value.get("contract_version") != "rootline_delegated_outcome.v1":
        return None
    import json
    material = {key: item for key, item in value.items() if key not in {"success", "outcome_sha256"}}
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":"),
        default=str).encode()).hexdigest()
    if (value.get("outcome_sha256") != digest or value.get("owner_authority") is not False
            or value.get("n8n_authority") is not False or value.get("google_sheets_authority") is not False
            or int(value.get("hardware_commands") or 0) < 0
            or int(value.get("provider_control_calls") or 0) < 0):
        return None
    return value


def _claim_replay(store, decision, principal, parsed, capability):
    if store is None:
        return {"allowed": False, "status": 503, "result": _unavailable()}
    payload = {"replay_identity": decision.replay_identity, "binding_digest": principal.binding_digest,
        "family_key": principal.family_key, "capability": capability,
        "provider_message_id": str(parsed.get("provider_message_id") or ""),
        "provider_timestamp": str(parsed.get("provider_timestamp") or "")}
    try: claimed = store("claim", decision.replay_identity, payload)
    except Exception: claimed = None
    if not isinstance(claimed, Mapping) or claimed.get("success") is not True:
        return {"allowed": False, "status": 503, "result": _unavailable()}
    if claimed.get("created") is not True:
        return {"allowed": False, "status": 200,
            "result": {**_contained("family_replay_suppressed"),
                "audit_trace_recorded": True, "suppress_family_delivery": True}}
    return {"allowed": True}


def _unavailable() -> dict[str, Any]:
    return {**_contained("family_capability_temporarily_unavailable", success=False),
        "answer": "Oom Sakkie kan nie nou die veilige plaasbewyse laai nie. Niks is verander of uitgevoer nie."}


def _contained(status: str, *, success=True) -> dict[str, Any]:
    return {"success": success, "status": status, "telegram_sends": 0, "telegram_edits": 0, **ZERO}
