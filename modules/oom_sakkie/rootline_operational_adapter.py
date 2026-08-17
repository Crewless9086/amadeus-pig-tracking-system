"""Typed read-only handoff from authenticated Oom Sakkie intake to ROOTLINE.

This adapter deliberately owns no Telegram or device transport.  It binds fresh
owner observations to ROOTLINE's canonical read model so a separately governed
execution consumer can decide whether a commissioned segment is eligible.
"""

from __future__ import annotations

from typing import Any, Mapping
from datetime import datetime
import re

from modules.telemetry.rootline_specialist_result import build_current_rootline_specialist_result
from modules.telemetry.rootline_water_energy_plan import record_tank_observations_transactional
from modules.oom_sakkie.gateway_authority import (
    issue_gateway_owner_authority, issue_rootline_observation_write_authority,
    validates_rootline_observation_write_authority,
)

CONTRACT_VERSION = "rootline_operational_dispatch_result_v1"


def recover_pending_manager_rootline_observation(*, database_url=None,
        owner_user_id="", chat_id="", provider_message_id=""):
    """Bind an already-authenticated manager reply that predates the bridge fix.

    The original Telegram identity, timestamp, content digest and typed fact are
    loaded from canonical Oom Sakkie intake.  No text is reinterpreted and the
    tank writer's provider-bound idempotency remains authoritative.
    """
    database_url = str(database_url or __import__("os").environ.get("DATABASE_URL") or "").strip()
    if not database_url:
        return {"success": False, "status": "database_not_configured", "canonical_writes": 0}
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10,
                options="-c default_transaction_read_only=on") as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'manager_question_reply'
                    from public.sam_live_stock_conversation_review_events e
                    where e.event_source='oom_sakkie_manager_question_reply'
                      and e.review_json->'manager_question_reply'->>'status'='recorded'
                      and e.review_json->'manager_question_reply'->>'domain' in ('rootline','water_energy')
                      and e.review_json->'manager_question_reply'->>'owner_user_id'=%s
                      and e.review_json->'manager_question_reply'->>'chat_id'=%s
                      and (%s='' or e.review_json->'manager_question_reply'->>'provider_message_id'=%s)
                      and not exists(select 1 from public.rootline_tank_observations t
                        where t.provider_message_id=e.review_json->'manager_question_reply'->>'provider_message_id')
                    order by e.created_at limit 1""", (str(owner_user_id), str(chat_id),
                        str(provider_message_id), str(provider_message_id)))
                row = cursor.fetchone()
    except Exception:
        return {"success": False, "status": "manager_observation_recovery_read_failed",
                "canonical_writes": 0}
    if not row or not isinstance(row[0], Mapping):
        return {"success": True, "status": "manager_observation_recovery_noop",
                "canonical_writes": 0}
    event = dict(row[0]); facts = (event.get("semantic_facts") or {}).get("observation_facts") or []
    owner = str(event.get("owner_user_id") or ""); chat = str(event.get("chat_id") or "")
    provider = str(event.get("provider_message_id") or "")
    provider_at = str(event.get("provider_timestamp") or "")
    digest = str(event.get("content_sha256") or "")
    mission = "OOM-ROOTLINE-RECOVERY-" + provider
    observations = _recovery_observations(facts, provider, provider_at)
    if not observations or owner != chat or not all((owner, provider, provider_at, digest)):
        return {"success": False, "status": "manager_observation_recovery_binding_invalid",
                "canonical_writes": 0}
    base = issue_gateway_owner_authority(owner, chat)
    authority = issue_rootline_observation_write_authority(base, mission_id=mission,
        provider_message_id=provider, provider_timestamp=provider_at, content_sha256=digest)
    context = {"mission_id": mission, "owner_user_id": owner, "chat_id": chat,
        "provider_message_id": provider, "provider_timestamp": provider_at,
        "content_sha256": digest, "observations": observations}
    return persist_rootline_observations(context, authority, database_url=database_url)


def _recovery_observations(facts, provider, observed_at):
    rows = []
    for fact in facts if isinstance(facts, list) else []:
        if not isinstance(fact, Mapping) or fact.get("subject") not in {"reservoir", "storage_tanks"}:
            return []
        state = str(fact.get("state") or "").upper()
        if state not in {"LOW", "OK", "FULL"}:
            return []
        numerator, denominator = {"LOW": (0, 1), "OK": (1, 2), "FULL": (1, 1)}[state]
        rows.append({"kind": "reservoir_level" if fact["subject"] == "reservoir" else "storage_level",
            "value": f"{numerator}/{denominator}", "numerator": numerator,
            "denominator": denominator, "semantic_state": state,
            "provider_message_id": provider, "observed_at": observed_at})
    return rows


def persist_rootline_observations(context: Mapping[str, Any], authority, *, database_url=None) -> dict[str, Any]:
    if (not validates_rootline_observation_write_authority(authority)
            or authority.owner_user_id != str(context.get("owner_user_id") or "")
            or authority.private_chat_id != str(context.get("chat_id") or "")
            or authority.mission_id != str(context.get("mission_id") or "")
            or authority.provider_message_id != str(context.get("provider_message_id") or "")
            or authority.provider_timestamp != str(context.get("provider_timestamp") or "")
            or authority.content_sha256 != str(context.get("content_sha256") or "")):
        return {"success": False, "contract_version": "rootline_owner_observation_bridge_v1",
                "status": "observation_write_authority_denied", "canonical_writes": 0}
    observations = context.get("observations") if isinstance(context.get("observations"), list) else []
    if not observations or not all(_valid_observation(item,context) for item in observations):
        return {"success":False,"contract_version":"rootline_owner_observation_bridge_v1",
                "status":"owner_observation_binding_invalid","canonical_writes":0}
    kinds=[item.get("kind") for item in observations if isinstance(item,Mapping)]
    if len(kinds) != len(set(kinds)):
        return {"success":False,"contract_version":"rootline_owner_observation_bridge_v1",
                "status":"duplicate_water_observation_ambiguous","canonical_writes":0}
    by_kind = {item.get("kind"): item for item in observations if isinstance(item, Mapping)}
    storage = by_kind.get("storage_level")
    reservoir = by_kind.get("reservoir_level")
    if not storage and not reservoir:
        return {"success": True, "contract_version": "rootline_owner_observation_bridge_v1",
                "created": False, "status": "no_water_observation", "canonical_writes": 0}
    provider_id = str(context.get("provider_message_id") or "")
    provider_at = str(context.get("provider_timestamp") or "")
    owner = str(context.get("owner_user_id") or "")
    payloads = []
    for kind, item in (("storage", storage), ("reservoir", reservoir)):
        if not item:
            continue
        payloads.append({f"{kind}_fraction": [item["numerator"], item["denominator"]],
            f"{kind}_state": _fraction_state(item), "provider_message_id": provider_id,
            "observed_at": provider_at, "source": "oom_sakkie_owner",
            "idempotency_key": (f"telegram:{context.get('mission_id')}:{provider_id}:"
                                f"rootline-water:{kind}:{context.get('content_sha256')}")})
    actor = "telegram-owner:" + __import__("hashlib").sha256(owner.encode()).hexdigest()[:16]
    result, status = record_tank_observations_transactional(payloads, actor, database_url)
    if status >= 400 or result.get("success") is not True:
        return {"success": False, "contract_version": "rootline_owner_observation_bridge_v1",
                "status": str(result.get("status") or "canonical_observation_write_failed"),
                "canonical_writes": None if result.get("write_outcome")=="indeterminate" else 0,
                "write_outcome": result.get("write_outcome") or "not_written"}
    readback = result.get("readback") if isinstance(result.get("readback"), list) else []
    expected = [{"kind": kind, "fraction": [item["numerator"], item["denominator"]],
                 "state": _fraction_state(item), "provider_message_id": provider_id,
                 "observed_at": provider_at}
                for kind, item in (("storage", storage), ("reservoir", reservoir)) if item]
    actual = [{key: row.get(key) for key in ("kind", "fraction", "state", "provider_message_id", "observed_at")}
              for row in readback]
    if actual != expected:
        return {"success": False, "contract_version": "rootline_owner_observation_bridge_v1",
                "status": "canonical_observation_readback_mismatch", "canonical_writes": result.get("created_count"),
                "observation_ids": result.get("observation_ids")}
    return {"success": True, "contract_version": "rootline_owner_observation_bridge_v1",
        "status": str(result.get("status")), "created": result.get("created_count", 0) > 0,
        "canonical_writes": result.get("created_count"), "observation_ids": result.get("observation_ids"),
        "observation_generation": result.get("observation_generation"), "readback": expected}


def _fraction_state(item):
    if not item: return "Unknown"
    if item["numerator"] == 0: return "LOW"
    if item["numerator"] == item["denominator"]: return "FULL"
    return "OK"


def dispatch_rootline_operation(context: Mapping[str, Any]) -> dict[str, Any]:
    expected_authority = {"farm_observation_write": False, "hardware_control": False,
                          "telegram_send": False, "automatic_on_retry": False}
    if not (context.get("contract_version") == "oom_rootline_operational_dispatch_v1"
            and all(str(context.get(key) or "").strip() for key in
                    ("mission_id", "owner_user_id", "chat_id", "provider_message_id",
                     "provider_timestamp", "content_sha256"))
            and str(context.get("owner_user_id")) == str(context.get("chat_id"))
            and _timestamp(context.get("provider_timestamp")) is not None
            and re.fullmatch(r"[0-9a-f]{64}", str(context.get("content_sha256") or ""))
            and context.get("visible_irrigation_need_zone") in (None, "", "C12345")
            and context.get("authority") == expected_authority):
        return _contained("authenticated_operational_binding_invalid")
    observations = context.get("observations") if isinstance(context.get("observations"), list) else []
    if not all(_valid_observation(item, context) for item in observations):
        return _contained("owner_observation_binding_invalid")
    if not observations and not context.get("visible_irrigation_need_zone"):
        return _contained("owner_operational_evidence_required")
    try:
        current = build_current_rootline_specialist_result()
    except Exception:
        return _contained("canonical_rootline_evidence_unavailable")
    if current.get("success") is not True or current.get("contract_version") != "rootline_specialist_result_v1":
        return _contained("canonical_rootline_result_invalid")
    zone = str(context.get("visible_irrigation_need_zone") or "")
    recommendation = next((item for item in current.get("recommendations") or []
                           if str(item.get("subject") or item.get("task_id") or item.get("zone_id") or "") in {zone, f"irrigation_{zone}"}), None)
    canonical_status = str((recommendation or {}).get("recommendation") or (recommendation or {}).get("status") or "Needs Data")
    # Provider-timestamped owner evidence may be recovered later and is not
    # assumed fresh. It triggers, but never substitutes for, a fresh governed
    # eligibility build.
    status = "Reassess" if observations else canonical_status
    labels = {"reservoir_level": "reservoir", "storage_level": "storage tanks"}
    level_text = ", ".join(f"{labels[item['kind']]}: {item['numerator']}/{item['denominator']}" for item in observations)
    return {
        "success": True, "contract_version": CONTRACT_VERSION,
        "specialist_acceptance": True, "recommendation": status,
        "canonical_recommendation_before_observation": canonical_status,
        "rootline_result_id": str(current.get("result_id") or ""),
        "evidence_generation": str(current.get("generation") or current.get("evidence_cutoff") or ""),
        "owner_observations": observations, "visible_irrigation_need_zone": zone or None,
        "observation_binding": "provider_timestamped_owner_evidence_requires_governed_reassessment",
        "owner_answer": (f"<b>ROOTLINE WATER OBSERVATION RECEIVED</b>\n\n"
                         f"Owner observation at {context['provider_timestamp']}: {level_text}. "
                         f"Visible irrigation need: {'C Camp' if zone == 'C12345' else 'not supplied'}. "
                         "ROOTLINE must now revalidate current power, weather, commissioning and channel state. "
                         "No irrigation command was sent by this intake step."),
        "reassessment": current.get("next_reassessment"),
        "unavailable": tuple((current.get("evidence") or {}).get("gaps") or ()),
        "hardware_commands": 0,
        "authority": {"telegram_send": False, "hardware_control": False,
                      "farm_observation_write": False, "automatic_on_retry": False},
    }


def _contained(reason: str) -> dict[str, Any]:
    return {"success": False, "contract_version": CONTRACT_VERSION,
            "specialist_acceptance": False, "reason": reason, "hardware_commands": 0,
            "authority": {"telegram_send": False, "hardware_control": False,
                          "farm_observation_write": False, "automatic_on_retry": False}}


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else None


def _valid_observation(item, context):
    if not isinstance(item, Mapping) or item.get("kind") not in {"reservoir_level", "storage_level"}:
        return False
    if (str(item.get("provider_message_id") or "") != str(context.get("provider_message_id") or "")
            or str(item.get("observed_at") or "") != str(context.get("provider_timestamp") or "")):
        return False
    numerator, denominator = item.get("numerator"), item.get("denominator")
    return (type(numerator) is int and type(denominator) is int and denominator > 0
            and 0 <= numerator <= denominator and item.get("value") == f"{numerator}/{denominator}")
