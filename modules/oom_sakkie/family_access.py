"""Identity-bound family access policy for the existing Oom Sakkie gateway.

This module grants no send, write, dispatch, or protected-action authority.  It
turns authenticated Telegram identity plus an owner-approved configuration
record into a closed, typed principal that existing lifecycle adapters may
consume.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping


FAMILY_BINDINGS_ENV = "OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON"
OWNER_USER_ID_ENV = "OOM_SAKKIE_TELEGRAM_OWNER_USER_ID"
PROTECTED_CAPABILITIES = frozenset({
    "mortality_confirmation", "sales_decision", "reservation", "payment",
    "mating_execution", "treatment", "hardware_exception",
    "permission_change", "publication", "customer_send",
})
REPORTER_CAPABILITIES = frozenset({"farm_observation", "active_follow_up"})
READ_ONLY_CAPABILITY = "explicit_summary"


class FamilyRole(str, Enum):
    OWNER = "owner"
    TRUSTED_FAMILY_REPORTER = "trusted_family_reporter"
    READ_ONLY_FAMILY_MEMBER = "read_only_family_member"
    UNKNOWN_SENDER = "unknown_sender"


@dataclass(frozen=True)
class FamilyPrincipal:
    telegram_user_id: str
    private_chat_id: str
    role: FamilyRole
    family_key: str
    permissions: frozenset[str]
    summary_domains: frozenset[str]
    authorization_id: str
    authorized_by_user_id: str
    authorized_at: str
    binding_digest: str

    @property
    def authenticated(self) -> bool:
        return self.role is not FamilyRole.UNKNOWN_SENDER

    @property
    def is_owner(self) -> bool:
        return self.role is FamilyRole.OWNER


@dataclass(frozen=True)
class FamilyAccessDecision:
    allowed: bool
    status: str
    principal: FamilyPrincipal
    reporter_attribution: Mapping[str, str]
    may_read_private_context: bool = False
    may_write_farm_data: bool = False
    may_confirm_protected_action: bool = False


def bound_family_manager_result(actions: list[Mapping[str, Any]], questions: list[str]) -> dict[str, Any]:
    """Apply the family-facing cardinality contract without changing facts."""
    ranked = sorted((dict(item) for item in actions if isinstance(item, Mapping)),
                    key=lambda item: (-int(item.get("priority") or 0), _clean(item.get("identity"))))
    unique, seen = [], set()
    for item in ranked:
        identity = _clean(item.get("identity"))
        if not identity or identity in seen or item.get("completed") is True or item.get("stale") is True:
            continue
        seen.add(identity); unique.append(item)
        if len(unique) == 3:
            break
    question = next((_clean(value) for value in questions if _clean(value)), "")
    return {"actions": unique, "question": question, "question_count": int(bool(question)),
            "protected_actions_executed": False, "farm_writes": 0, "telegram_sends": 0}


def resolve_family_principal(parsed: Mapping[str, Any], environ: Mapping[str, str]) -> FamilyPrincipal:
    user_id = _clean(parsed.get("telegram_user_id"))
    chat_id = _clean(parsed.get("telegram_chat_id"))
    chat_type = _clean(parsed.get("telegram_chat_type")).lower()
    owner_id = _owner_id(environ)
    if not user_id or user_id != chat_id or chat_type != "private":
        return _unknown(user_id, chat_id)
    if owner_id and user_id == owner_id:
        return FamilyPrincipal(user_id, chat_id, FamilyRole.OWNER, "charl",
            frozenset({"*"}), frozenset({"*"}), "configured-owner",
            owner_id, "configured", _digest({"owner_user_id": owner_id}))
    for record in _bindings(environ):
        if _clean(record.get("telegram_user_id")) != user_id:
            continue
        principal = _principal_from_record(record, owner_id, chat_id)
        return principal if principal is not None else _unknown(user_id, chat_id)
    return _unknown(user_id, chat_id)


def authorize_family_message(principal: FamilyPrincipal, parsed: Mapping[str, Any], *,
                             capability: str, context_owner_user_id: str = "",
                             summary_domain: str = "") -> FamilyAccessDecision:
    attribution = {
        "reporter_user_id": principal.telegram_user_id,
        "provider_message_id": _clean(parsed.get("provider_message_id")),
        "provider_timestamp": _clean(parsed.get("provider_timestamp")),
        "family_key": principal.family_key,
        "authorization_id": principal.authorization_id,
        "binding_digest": principal.binding_digest,
    }
    if not principal.authenticated:
        return FamilyAccessDecision(False, "unknown_sender_denied", principal, attribution)
    if not attribution["provider_message_id"] or not attribution["provider_timestamp"]:
        return FamilyAccessDecision(False, "provider_provenance_required", principal, attribution)
    capability = _clean(capability)
    if capability in PROTECTED_CAPABILITIES:
        allowed = principal.is_owner
        return FamilyAccessDecision(allowed,
            "owner_protected_authority" if allowed else "owner_authority_required",
            principal, attribution, may_read_private_context=allowed,
            may_confirm_protected_action=allowed)
    if capability in REPORTER_CAPABILITIES:
        allowed = principal.is_owner or capability in principal.permissions
        if capability == "active_follow_up" and context_owner_user_id:
            allowed = allowed and principal.telegram_user_id == _clean(context_owner_user_id)
        return FamilyAccessDecision(allowed,
            "attributable_family_observation" if allowed else "family_reporting_not_permitted",
            principal, attribution, may_read_private_context=allowed)
    if capability == READ_ONLY_CAPABILITY:
        domain = _clean(summary_domain).lower()
        allowed = principal.is_owner or (capability in principal.permissions and
            (domain in principal.summary_domains or "*" in principal.summary_domains))
        return FamilyAccessDecision(allowed,
            "family_summary_permitted" if allowed else "family_summary_not_permitted",
            principal, attribution, may_read_private_context=allowed)
    return FamilyAccessDecision(False, "unsupported_family_capability", principal, attribution)


def family_access_policy(environ: Mapping[str, str]) -> dict[str, Any]:
    owner_id = _owner_id(environ)
    principals = [_principal_from_record(row, owner_id, _clean(row.get("telegram_user_id")))
                  for row in _bindings(environ)]
    principals = [item for item in principals if item is not None]
    return {
        "contract_version": "oom_sakkie_family_access_v1",
        "owner_configured": bool(owner_id),
        "authorized_identity_count": (1 if owner_id else 0) + len(principals),
        "family_bindings_count": len(principals),
        "family_keys": sorted(item.family_key for item in principals),
        "roles": [role.value for role in FamilyRole],
        "protected_actions_owner_only": True,
        "display_names_are_authority": False,
        "language_is_authority": False,
    }


def _principal_from_record(record: Mapping[str, Any], owner_id: str, chat_id: str) -> FamilyPrincipal | None:
    try:
        role = FamilyRole(_clean(record.get("role")).lower())
    except ValueError:
        return None
    user_id = _clean(record.get("telegram_user_id"))
    authorized_by = _clean(record.get("authorized_by_user_id"))
    authorization_id = _clean(record.get("authorization_id"))
    authorized_at = _clean(record.get("authorized_at"))
    family_key = _clean(record.get("family_key")).lower()
    if (role not in {FamilyRole.TRUSTED_FAMILY_REPORTER, FamilyRole.READ_ONLY_FAMILY_MEMBER}
            or not owner_id or authorized_by != owner_id or not user_id
            or user_id == owner_id or user_id != chat_id or family_key not in {"mum", "dad"}
            or not authorization_id or not authorized_at):
        return None
    permissions = frozenset(_clean(item) for item in record.get("permissions", []) if _clean(item))
    summaries = frozenset(_clean(item).lower() for item in record.get("summary_domains", []) if _clean(item))
    allowed_permissions = REPORTER_CAPABILITIES | {READ_ONLY_CAPABILITY}
    if not permissions <= allowed_permissions:
        return None
    if role is FamilyRole.READ_ONLY_FAMILY_MEMBER and permissions - {READ_ONLY_CAPABILITY}:
        return None
    canonical = {"telegram_user_id": user_id, "role": role.value, "family_key": family_key,
        "permissions": sorted(permissions), "summary_domains": sorted(summaries),
        "authorization_id": authorization_id, "authorized_by_user_id": authorized_by,
        "authorized_at": authorized_at}
    return FamilyPrincipal(user_id, chat_id, role, family_key, permissions, summaries,
        authorization_id, authorized_by, authorized_at, _digest(canonical))


def _owner_id(environ: Mapping[str, str]) -> str:
    explicit = _clean(environ.get(OWNER_USER_ID_ENV))
    if explicit:
        return explicit
    allowed = [_clean(item) for item in _clean(environ.get("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS")).split(",") if _clean(item)]
    return allowed[0] if len(allowed) == 1 else ""


def _bindings(environ: Mapping[str, str]) -> list[Mapping[str, Any]]:
    try:
        value = json.loads(str(environ.get(FAMILY_BINDINGS_ENV) or "").strip() or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _unknown(user_id: str, chat_id: str) -> FamilyPrincipal:
    return FamilyPrincipal(user_id, chat_id, FamilyRole.UNKNOWN_SENDER, "", frozenset(),
        frozenset(), "", "", "", "")


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _clean(value: Any) -> str:
    return str(value or "").strip()[:200]
