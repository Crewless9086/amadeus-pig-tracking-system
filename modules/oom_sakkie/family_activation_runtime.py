"""One-shot deployed activation for owner-approved family bindings.

The application process, not a development terminal, records and presents the
configured bindings. Existing durable lifecycles make concurrent worker and
restart replay silent.
"""

from __future__ import annotations

import json
import hashlib
import os
import threading
from typing import Any, Mapping

from modules.oom_sakkie.family_access import (
    FAMILY_BINDINGS_ENV, FamilyRole, family_access_policy, resolve_family_principal,
)


ENABLED_ENV = "OOM_SAKKIE_FAMILY_ACCESS_ACTIVATION_ENABLED"
_START_LOCK = threading.Lock()
_STARTED = False
_OWNER_SHA256 = "3487c91435ddf2d1ed0f129facb4092a86605c0e249d0c63b1eb10aeec7ec59e"
_EXPECTED = {
    "dad": {"identity_sha256": "a377a1f82445f41eafec22156439fd80ab5a374cfc70a62664566ed44115b4e5",
        "role": "farm_manager", "authorization_id": "OOM-FAMILY-AUTH-ANTON-20260815",
        "permissions": frozenset({"farm_observation", "active_follow_up", "explicit_summary",
            "welfare_hold", "welfare_escalation", "found_dead_observation",
            "herdmaster_management_input", "herdmaster_reassessment",
            "irrigation_start", "irrigation_continue"}),
        "summary_domains": frozenset({"herd", "welfare", "breeding", "farrowing",
            "irrigation", "water", "weather", "power"})},
    "mum": {"identity_sha256": "a16f35b4f76a6b97e0c7a2469db09c9488d68a9feb1597b65e6cb96bdef9be52",
        "role": "read_only_family_member",
        "authorization_id": "OOM-FAMILY-AUTH-ANTOINETTE-20260815",
        "permissions": frozenset({"explicit_summary"}),
        "summary_domains": frozenset({"herd", "welfare", "breeding", "farrowing",
            "irrigation", "water", "weather", "power"})},
}


def start_family_access_activation(*, environ=None, runner=None) -> bool:
    """Start the bounded activation once per process when explicitly enabled."""
    global _STARTED
    source = environ if environ is not None else os.environ
    if not _truthy(source.get(ENABLED_ENV)):
        return False
    with _START_LOCK:
        if _STARTED:
            return False
        _STARTED = True
        threading.Thread(target=runner or activate_family_access,
            kwargs={"environ": source}, name="oom-family-access-activation",
            daemon=True).start()
        return True


def activate_family_access(*, environ=None, binding_recorder=None, deliver=None):
    """Persist and present every exact valid configured non-owner binding."""
    source = environ if environ is not None else os.environ
    policy = family_access_policy(source)
    if not _truthy(source.get(ENABLED_ENV)) or policy.get("configuration_valid") is not True:
        return _result("family_activation_not_authorized", success=False)
    try:
        bindings = json.loads(str(source.get(FAMILY_BINDINGS_ENV) or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return _result("family_activation_configuration_invalid", success=False)
    if (not isinstance(bindings, list) or len(bindings) != 2
            or not _approved_manifest_matches(bindings)):
        return _result("family_activation_exact_binding_set_required", success=False)

    if binding_recorder is None:
        from modules.oom_sakkie.family_authorization_lifecycle import record_binding_decision
        binding_recorder = record_binding_decision
    if deliver is None:
        from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
        deliver = deliver_family_result

    outcomes = []
    for binding in sorted(bindings, key=lambda row: str(row.get("family_key") or "")):
        user_id = str(binding.get("telegram_user_id") or "").strip()
        parsed = {"telegram_user_id": user_id, "telegram_chat_id": user_id,
            "telegram_chat_type": "private",
            "provider_message_id": "family-activation:" + str(binding.get("authorization_id") or ""),
            "provider_timestamp": str(binding.get("authorized_at") or ""),
            "text": "Oom Sakkie family access activation"}
        principal = resolve_family_principal(parsed, source)
        expected = (FamilyRole.FARM_MANAGER if binding.get("family_key") == "dad"
                    else FamilyRole.READ_ONLY_FAMILY_MEMBER)
        if principal.role is not expected:
            return _result("family_activation_principal_mismatch", success=False,
                           outcomes=outcomes)
        recorded = binding_recorder(binding, environ=source)
        if not isinstance(recorded, Mapping) or recorded.get("success") is not True:
            return _result("family_activation_binding_unproven", success=False,
                           outcomes=outcomes)
        mission_id = "OOM-FAMILY-ONBOARDING-" + principal.binding_digest[:24].upper()
        message = _onboarding_message(principal)
        delivery = deliver(parsed, {"success": True, "status": "family_onboarding_ready",
            "answer": message, "writes_farm_data": False, "hardware_commands": 0,
            "protected_actions_performed": False}, specialist="OOM_SAKKIE_FAMILY",
            mission_id=mission_id, card_mission_id=mission_id)
        confirmed = bool(isinstance(delivery, Mapping) and delivery.get("success") is True
                         and (delivery.get("provider_delivery_confirmed") is True
                              or str(delivery.get("telegram_message_id") or "")))
        if not confirmed:
            return _result("family_activation_delivery_unconfirmed", success=False,
                           outcomes=outcomes)
        outcomes.append({"family_key": principal.family_key, "role": principal.role.value,
            "binding_digest": principal.binding_digest,
            "binding_created": recorded.get("created") is True,
            "telegram_message_id": str(delivery.get("telegram_message_id") or ""),
            "telegram_sends": int(delivery.get("telegram_sends") or 0),
            "telegram_edits": int(delivery.get("telegram_edits") or 0)})
    return _result("family_activation_complete", outcomes=outcomes)


def _onboarding_message(principal) -> str:
    if principal.role is FamilyRole.FARM_MANAGER:
        return ("<b>Welkom by Oom Sakkie</b>\n\n"
            "Anton, jou plaasbestuurdertoegang is nou aktief. Jy kan beperkte "
            "Afrikaanse kudde-, welstand-, teel-, water-, weer- en kragopsommings "
            "sien en toeskryfbare plaaswaarnemings deel. ROOTLINE kan slegs 'n "
            "vars, gekommissioneerde besproeiing begin of voortgaan binne bestaande "
            "staande gesag en veiligheidsgrense. Geen STOP/OFF, kommissie, outonomie, "
            "boorgat, bemesting, elektriese of eienaarsgesag is toegestaan nie.")
    return ("<b>Welkom by Oom Sakkie</b>\n\n"
        "Antoinette, jou Afrikaanse familie-toegang is leesalleen. Jy kan beperkte "
        "kudde-, teel/kraam-, water-, weer-, krag- en welstandopsommings sien en "
        "veilige leesalleen-vrae vra. Jy kan nie waarnemings, goedkeurings, plaas- "
        "of diereveranderings, besproeiing of enige toerustingaksie uitvoer nie.")


def _result(status, *, success=True, outcomes=None):
    values = list(outcomes or [])
    return {"success": success, "status": status, "outcomes": values,
        "telegram_sends": sum(int(row.get("telegram_sends") or 0) for row in values),
        "telegram_edits": sum(int(row.get("telegram_edits") or 0) for row in values),
        "farm_writes": 0, "hardware_commands": 0,
        "protected_actions_performed": False}


def _approved_manifest_matches(bindings) -> bool:
    rows = {str(row.get("family_key") or "").strip(): row
            for row in bindings if isinstance(row, Mapping)}
    if set(rows) != set(_EXPECTED):
        return False
    for family_key, expected in _EXPECTED.items():
        row = rows[family_key]
        identity = str(row.get("telegram_user_id") or "").strip()
        authorizer = str(row.get("authorized_by_user_id") or "").strip()
        if (hashlib.sha256(identity.encode()).hexdigest() != expected["identity_sha256"]
                or hashlib.sha256(authorizer.encode()).hexdigest() != _OWNER_SHA256
                or str(row.get("role") or "").strip() != expected["role"]
                or str(row.get("authorization_id") or "").strip() != expected["authorization_id"]
                or str(row.get("language") or "").strip() != "af"
                or frozenset(str(value).strip() for value in row.get("permissions", ()))
                    != expected["permissions"]
                or frozenset(str(value).strip() for value in row.get("summary_domains", ()))
                    != expected["summary_domains"]):
            return False
    return True


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
