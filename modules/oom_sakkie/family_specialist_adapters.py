"""Governed Oom Sakkie adapters for delegated family principals."""

from __future__ import annotations

from datetime import datetime
import hashlib
import os
from typing import Any, Mapping
from zoneinfo import ZoneInfo


EVENT_SOURCE = "oom_sakkie_family_runtime"


def family_replay_store(action: str, identity: str, payload: Mapping[str, Any]):
    """Atomically claim one provider/capability identity on the existing spine."""
    return _record_once(identity, "replay_claim", payload)


def load_family_summary(*, principal, domain: str) -> Mapping[str, Any]:
    """Load only the requested authorized canonical domain after authorization."""
    if domain in {"rootline", "irrigation", "water", "weather", "power"}:
        from modules.telemetry.rootline_daily_brief import get_rootline_daily_brief
        packet, status = get_rootline_daily_brief()
        if status != 200 or not isinstance(packet, Mapping): return _unavailable("ROOTLINE-bewyse")
        lines = _rootline_lines(packet, domain)
        freshness = str((packet.get("current_conditions") or {}).get("freshness") or "Unknown")
    elif domain in {"herd", "welfare", "breeding", "farrowing"}:
        from modules.pig_weights.herdmaster_daily_manager_evidence import load_daily_manager_evidence
        packet = load_daily_manager_evidence(
            analysis_date=datetime.now(ZoneInfo("Africa/Johannesburg")).date())
        if not isinstance(packet, Mapping) or packet.get("success") is not True:
            return _unavailable("HERDMASTER-bewyse")
        lines = _herd_lines(packet, domain, manager=principal.role.value == "farm_manager")
        freshness = str(packet.get("evidence_freshness") or packet.get("evidence_date") or "Unknown")
    else:
        return _unavailable("domein")
    return {"available": bool(lines), "summary_lines": lines[:5], "freshness": freshness,
        "recipient_binding": {"telegram_user_id": principal.telegram_user_id,
            "family_key": principal.family_key, "binding_digest": principal.binding_digest,
            "permitted_domain": domain, "language": "af"}}


def herdmaster_family_observation(*, parsed, principal, capability: str, replay_identity: str):
    """Append an attributable HERDMASTER intake; never create a protected preview."""
    text = str(parsed.get("text") or "").strip()
    if (capability not in {"farm_observation", "found_dead_observation", "welfare_hold",
                           "welfare_escalation", "herdmaster_management_input",
                           "herdmaster_reassessment"}
            or text.upper().startswith("CONFIRM ") or parsed.get("callback_confirmation") is True):
        return _hold("herdmaster_family_protected_boundary")
    if capability in {"welfare_hold", "welfare_escalation", "herdmaster_management_input",
                      "herdmaster_reassessment"}:
        stored = _record_once("OOM-FAMILY-HERD-" + replay_identity[:24].upper(),
            "herdmaster_family_input", {"replay_identity": replay_identity,
                "reporter_user_id": principal.telegram_user_id, "family_key": principal.family_key,
                "binding_digest": principal.binding_digest, "capability": capability,
                "provider_message_id": str(parsed.get("provider_message_id") or ""),
                "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
                "evidence_sha256": hashlib.sha256(text.encode()).hexdigest(), "evidence_text": text})
        return ({"success": True, "status": "herdmaster_family_input_retained",
            "answer": "Dankie. HERDMASTER het die toeskryfbare bestuursinset veilig behou vir beoordeling.",
            "writes_farm_data": False, "animal_mutations": 0, "hardware_commands": 0}
            if stored.get("success") else _hold("herdmaster_family_input_unavailable"))
    from modules.oom_sakkie.herdmaster_health_loss_runtime import load_canonical_health_loss_evidence
    from modules.pig_weights.herdmaster_natural_health_loss_intake import evaluate_health_loss_intake
    try:
        evidence = load_canonical_health_loss_evidence()
        evaluated = evaluate_health_loss_intake({"authenticated": True,
            "authenticated_principal_id": principal.telegram_user_id,
            "provider_message_id": str(parsed.get("provider_message_id") or ""),
            "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
            "provider_timezone": "Africa/Johannesburg", "text": text}, evidence)
    except Exception:
        return _hold("herdmaster_family_evidence_unavailable")
    record = {"replay_identity": replay_identity,
        "reporter_user_id": principal.telegram_user_id, "family_key": principal.family_key,
        "binding_digest": principal.binding_digest, "authorization_id": principal.authorization_id,
        "capability": capability, "provider_message_id": str(parsed.get("provider_message_id") or ""),
        "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "evidence_text": text, "evidence_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "animal_identity": dict(evaluated.get("identity") or {}),
        "event_family": str(evaluated.get("event_family") or "unknown"),
        "welfare_priority": dict(evaluated.get("immediate_welfare_priority") or {}),
        "evaluation_status": str(evaluated.get("status") or "")}
    retained = _record_once("OOM-FAMILY-HERD-OBS-" + replay_identity[:24].upper(),
                            "delegated_herdmaster_observation", record)
    if retained.get("success") is not True:
        return _hold("herdmaster_family_observation_unavailable")
    question = str(evaluated.get("smallest_missing_follow_up_question") or "").strip()
    if question:
        answer = "HERDMASTER het die waarneming behou. Een verduideliking is nodig: " + question
    else:
        answer = "HERDMASTER het die toeskryfbare waarneming een keer behou."
    if capability == "found_dead_observation" or evaluated.get("event_family") == "found_dead":
        answer += (" Charl se afsonderlike bevestiging bly nodig voordat enige "
                   "mortaliteit- of lewensiklusrekord verander.")
    return {"success": True, "status": "herdmaster_family_observation_retained",
        "answer": answer, "writes_farm_data": False, "animal_mutations": 0,
        "hardware_commands": 0, "protected_actions_performed": False}


def load_family_question(*, principal, family_key, binding_digest, capability,
                         provider_message_id, provider_timestamp, replay_identity):
    rows = _load("QUESTION-" + principal.telegram_user_id)
    active = [row for row in rows if row.get("state") == "active"]
    if len(active) != 1: return None
    row = active[0]
    if (row.get("family_key") != family_key or row.get("binding_digest") != binding_digest
            or row.get("owner_user_id") != principal.telegram_user_id): return None
    return row


def retain_family_question_reply(*, parsed, principal, context, replay_identity):
    payload = {"state": "answered", "question_id": context.get("question_id"),
        "owner_user_id": principal.telegram_user_id, "family_key": principal.family_key,
        "binding_digest": principal.binding_digest, "replay_identity": replay_identity,
        "provider_message_id": str(parsed.get("provider_message_id") or ""),
        "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "answer_sha256": hashlib.sha256(str(parsed.get("text") or "").encode()).hexdigest(),
        "answer_text": str(parsed.get("text") or "")}
    result = _record_once("OOM-FAMILY-QUESTION-" + replay_identity[:24].upper(),
                          "question_reply", payload)
    return ({"success": True, "status": "family_question_reply_retained",
        "answer": "Dankie. Jou antwoord is een keer by jou eie aktiewe vraag behou."}
        if result.get("success") else _hold("family_question_reply_unavailable"))


def rootline_family_handoff(*, parsed, principal, capability, replay_identity,
        authorization_loader=None, eligibility_loader=None, executor=None, environ=None):
    """Call the sealed ROOTLINE boundary without minting owner authority."""
    from modules.telemetry.rootline_delegated_principal import (
        CAPABILITY, CONTRACT_VERSION, EXCLUDED, delegated_replay_identity,
        handle_delegated_rootline_request, load_delegated_authorization)
    action = parsed.get("family_action") if isinstance(parsed.get("family_action"), Mapping) else {}
    if capability not in {"irrigation_start", "irrigation_continue"}:
        return _hold("rootline_delegated_action_not_reviewed")
    required=("authorization_digest","commissioned_path_id","zone_id","bounded_duration_seconds",
        "evidence_generation","job_id","job_sha256","segment_identity","current_segment",
        "execution_id","eligibility_sha256","consumption_key")
    if any(action.get(key) in (None, "") for key in required):
        return _hold("rootline_delegated_request_incomplete")
    request={"contract_version":CONTRACT_VERSION,"principal_id":principal.telegram_user_id,
        "private_chat_id":principal.private_chat_id,"family_identity":"anton",
        "role":"farm_manager","authorization_id":principal.authorization_id,
        "authorization_digest":str(action["authorization_digest"]),"capability":CAPABILITY,
        "provider_message_id":str(parsed.get("provider_message_id") or ""),
        "provider_timestamp":str(parsed.get("provider_timestamp") or ""),
        "evidence_generation":str(action["evidence_generation"]),
        "commissioned_path_id":str(action["commissioned_path_id"]),"zone_id":str(action["zone_id"]),
        "action":capability,"bounded_duration_seconds":action["bounded_duration_seconds"],
        "job_id":str(action["job_id"]),"job_sha256":str(action["job_sha256"]),
        "segment_identity":str(action["segment_identity"]),"current_segment":action["current_segment"],
        "execution_id":str(action["execution_id"]),"eligibility_sha256":str(action["eligibility_sha256"]),
        "consumption_key":str(action["consumption_key"]),"owner_authority":False,
        "excluded_authority":sorted(EXCLUDED)}
    request["replay_identity"]=delegated_replay_identity(request)
    source=environ if environ is not None else os.environ
    authorization_loader = authorization_loader or (
        lambda identity: load_delegated_authorization(identity,environ=source))
    eligibility_loader = eligibility_loader or (lambda:_load_rootline_eligibility(source))
    executor = executor or (lambda **kwargs:_execute_rootline_delegation(
        principal=principal,source=source,**kwargs))
    outcome=handle_delegated_rootline_request(request,authorization_loader=authorization_loader,
        eligibility_loader=eligibility_loader,executor=executor)
    status=str(outcome.get("status") or "rootline_delegated_contained")
    success=outcome.get("success") is True
    answer=("ROOTLINE het die begrensde, gekommissioneerde besproeiingsbesluit veilig uitgevoer."
        if success else "ROOTLINE hou die besluit veilig terug. Geen nuwe opdrag is uit hierdie versoek bewys nie.")
    return {"success":success,"status":status,"answer":answer,"writes_farm_data":False,
        "hardware_commands":int(outcome.get("hardware_commands") or 0),
        "provider_control_calls":int(outcome.get("provider_control_calls") or 0),
        "protected_actions_performed":False,"rootline_outcome":dict(outcome)}


def _load_rootline_eligibility(source):
    from datetime import datetime, timezone
    from modules.telemetry.rootline_execution_runtime import _current
    from modules.telemetry.rootline_ewelink_oauth_store import PostgresOAuthTokenStore
    from modules.telemetry.rootline_ewelink_readback import read_current_device
    from modules.telemetry.rootline_irrigation_execution_store import rootline_irrigation_execution_store
    from modules.telemetry.rootline_water_energy_plan import read_current_water_energy_evidence
    database_url=source.get("DATABASE_URL"); now=datetime.now(timezone.utc)
    token_store=PostgresOAuthTokenStore(database_url)
    return _current(read_current_water_energy_evidence,read_current_device,token_store,source,
        database_url,now,rootline_irrigation_execution_store)["artifact"]


def _execute_rootline_delegation(*, principal, source, expected_artifact, delegated_authority):
    if (delegated_authority.get("owner_authority") is not False
            or delegated_authority.get("principal_id")!=principal.telegram_user_id
            or delegated_authority.get("private_chat_id")!=principal.private_chat_id
            or delegated_authority.get("role")!="farm_manager"):
        return _hold("rootline_delegated_authority_invalid")
    from modules.telemetry.rootline_execution_runtime import run_rootline_execution_cycle
    return run_rootline_execution_cycle(notify=lambda *_:{"provider_delivery_confirmed":False,
        "provider_delivery_ambiguous":False},environ=source,database_url=source.get("DATABASE_URL"),
        owner_user_id=principal.telegram_user_id,chat_id=principal.private_chat_id,
        expected_artifact=expected_artifact)


def _record_once(identity, kind, payload):
    from modules.sales.sam_live_stock_launch_control import (
        build_sam_live_stock_review_event, record_sam_live_stock_review_event)
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    event = build_sam_live_stock_review_event({"conversation_id": identity}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": kind}, event_source=EVENT_SOURCE)
    event.update({"review_event_id": identity, "chatwoot_conversation_id": identity,
        "review_json": {"family_runtime": {"kind": kind, **dict(payload)}},
        "decision_json": {}, "facts_json": {}, "customer_message_excerpt": "",
        "sam_reply_excerpt": ""})
    result, status = record_sam_live_stock_review_event(event,
        connect_factory=lambda: connect_bounded_rootline_postgres(
            database_url=os.environ.get("DATABASE_URL"), read_only=False))
    return {**result, "success": status < 400 and result.get("success") is True,
            "created": result.get("created", status < 300)}


def _load(identity):
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL")) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'family_runtime' from public.sam_live_stock_conversation_review_events
                where event_source=%s and chatwoot_conversation_id=%s order by created_at desc""",
                (EVENT_SOURCE, identity))
            return [dict(row[0]) for row in cursor.fetchall() if isinstance(row[0], Mapping)]


def _rootline_lines(packet, domain):
    values=[]
    if domain in {"rootline","irrigation","water"}: values.append(str(packet.get("executive_summary") or ""))
    if domain in {"rootline","weather"}: values.append("Weerbewyse: "+str((packet.get("current_conditions") or {}).get("freshness") or "Unknown"))
    if domain in {"rootline","power"}: values.append("Krag: "+str((packet.get("power") or {}).get("interpretation") or "Unknown"))
    return [value for value in values if value and not value.endswith(": Unknown")]


def _herd_lines(packet, domain, *, manager):
    weight=packet.get("weight") if isinstance(packet.get("weight"),Mapping) else {}
    current=weight.get("current_snapshot") if isinstance(weight.get("current_snapshot"),Mapping) else {}
    lines=[]
    if domain in {"herd","welfare"} and current:
        lines.append(f"Gemerkte jong/groeiende varke geweeg: {current.get('covered','Unknown')}/{current.get('eligible_tagged','Unknown')}.")
    mortality=packet.get("mortality") if isinstance(packet.get("mortality"),Mapping) else {}
    if domain in {"herd","welfare"} and mortality.get("digest_changed") is True:
        lines.append("HERDMASTER het 'n veranderde mortaliteitssein vir Charl se bevestiging gemerk.")
    if domain in {"breeding","farrowing"}: lines.append("Teel- en kraambewyse is beskikbaar." if packet.get("success") else "Teel- en kraambewyse: Unknown.")
    return lines


def _unavailable(label): return {"available": False, "summary_lines": [f"{label}: Unknown of tans nie beskikbaar nie."]}
def _hold(status): return {"success": False, "status": status,
    "answer": "Die versoek is veilig op Hou. Niks is verander of uitgevoer nie.",
    "writes_farm_data": False, "animal_mutations": 0, "hardware_commands": 0,
    "protected_actions_performed": False}
