import hmac
import os
import time
from datetime import datetime, timezone

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.service import TELEGRAM_OWNER_AUTHORITY, handle_message
from modules.oom_sakkie.owner_task_lifecycle import handle_owner_task_input
from modules.oom_sakkie.herdmaster_health_loss_runtime import handle_authenticated_health_loss_message
from modules.oom_sakkie.operational_specialist_intake import (
    handle_operational_specialist_message, recover_contextual_specialist_replay)
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
from modules.oom_sakkie.farm_manager_runtime import handle_farm_manager_round
from modules.oom_sakkie.owner_conversation_front_door import build_owner_clarification
from modules.oom_sakkie.owner_operational_continuation import handle_owner_operational_continuation
from modules.oom_sakkie.grouped_weight_runtime import handle_grouped_weight_message
from modules.oom_sakkie.herdmaster_breeding_exposure_runtime import handle_grouped_breeding_message
from modules.oom_sakkie.semantic_front_door import interpret_owner_message, semantic_front_door_policy
from modules.oom_sakkie.rootline_reassessment_lifecycle import reassess_rootline, record_reassessment_delivery
from modules.oom_sakkie.family_access import FamilyRole, family_access_policy, resolve_family_principal
from modules.oom_sakkie.herdmaster_auction_runtime import handle_auction_confirmation
from modules.oom_sakkie.protected_action_runtime import handle_protected_action_input
from modules.oom_sakkie.herdmaster_request_runtime import (
    delivery_retry_authority_for, handle_herdmaster_request)
from modules.oom_sakkie.beacon_request_runtime import handle_beacon_request
from modules.oom_sakkie.manager_question_runtime import (
    handle_manager_question_reply, load_active_manager_question,
    semantic_context_with_manager_question)


TRUTHY = {"1", "true", "yes", "on"}


def _bind_protected_preview_card(result, delivery):
    token=str(result.get("callback_token") or "")
    message_id=str(delivery.get("telegram_message_id") or "")
    if not token or not delivery.get("success"):
        return delivery
    if not message_id:
        return {**delivery,"success":False,"status":"protected_preview_card_identity_missing"}
    try:
        from modules.oom_sakkie.protected_action_claims import bind_claim_card
        bound=bind_claim_card(token,message_id)
    except Exception:
        bound=False
    if not bound:
        return {**delivery,"success":False,"status":"protected_preview_card_binding_unavailable",
          "do_not_retry_provider_effect":True}
    return {**delivery,"protected_preview_card_bound":True}
ENABLED_ENV = "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED"
TOKEN_ENV = "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN"
ALLOWED_USER_IDS_ENV = "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS"
TLS_CONFIRMED_ENV = "OOM_SAKKIE_TELEGRAM_TLS_CONFIRMED"
RATE_LIMIT_MODEL_ACCEPTED_ENV = "OOM_SAKKIE_TELEGRAM_RATE_LIMIT_MODEL_ACCEPTED"
MAX_TELEGRAM_TEXT_CHARS = 2000
MIN_TOKEN_CHARS = 32
AUTH_FAILURE_LIMIT = 8
AUTH_FAILURE_WINDOW_SECONDS = 60
AUTH_LOCKOUT_SECONDS = 300
_AUTH_FAILURE_TIMES = []
_AUTH_LOCKED_UNTIL = 0.0


def telegram_gateway_policy(environ=None):
    source = environ if environ is not None else os.environ
    semantic_policy = semantic_front_door_policy(source)
    explicitly_enabled = _env_truthy(source.get(ENABLED_ENV))
    token = str(source.get(TOKEN_ENV, "") or "").strip()
    token_configured = bool(token)
    token_meets_minimum = len(token) >= MIN_TOKEN_CHARS
    allowed_ids = _allowed_user_ids(source)
    auth_locked = _auth_locked()
    owner_task_bot_configured = bool(_owner_task_bot_token(source))
    return {
        "enabled": explicitly_enabled and token_configured and token_meets_minimum and bool(allowed_ids) and not auth_locked,
        "explicitly_enabled": explicitly_enabled,
        "configured": token_configured,
        "token_meets_minimum_entropy": token_meets_minimum,
        "minimum_token_chars": MIN_TOKEN_CHARS,
        "mode": "read_only_owner_gateway",
        "route": "POST /api/oom-sakkie/channels/telegram/message",
        "auth": "bearer_or_x_oom_sakkie_telegram_token",
        "allowed_user_ids_required": True,
        "allowed_user_ids_configured": bool(allowed_ids),
        "allowed_user_ids_count": len(allowed_ids),
        "auth_rate_limit": {
            "enabled": True,
            "failure_limit": AUTH_FAILURE_LIMIT,
            "window_seconds": AUTH_FAILURE_WINDOW_SECONDS,
            "lockout_seconds": AUTH_LOCKOUT_SECONDS,
            "locked": auth_locked,
        },
        "sends_telegram": False,
        "reply_transport": "caller_or_provider_bound_family_lifecycle",
        "owner_task_lifecycle": {
            "enabled": owner_task_bot_configured,
            "canonical_bot": "existing_sam_oom_owner_bot",
            "sends_telegram": owner_task_bot_configured,
            "reply_transport": "backend_handles_owner_task_delivery",
            "scope": "authenticated_active_owner_request_acknowledgement_result_or_systemic_exception_only",
            "requires_provider_message_identity": True,
            "ambiguous_delivery_retries": False,
        },
        "provider_bound_family_delivery": {
            "enabled": bool(str(source.get("DATABASE_URL") or "").strip()),
            "requires_authenticated_private_owner": True,
            "requires_provider_message_identity": True,
            "deduplicated": True,
            "scope": "visible_acknowledgement_or_consolidated_read_only_result",
        },
        "deterministic_only": not (semantic_policy["enabled"] and semantic_policy["configured"]),
        "semantic_front_door": semantic_policy,
        "family_access": {
            "contract_version": "oom_sakkie_family_access_v1",
            "configured": family_access_policy(source)["configuration_valid"],
            "protected_actions_owner_only": True,
        },
        "can_trigger_outbound_llm": semantic_policy["enabled"] and semantic_policy["configured"],
        "minimum_token_entropy": "Requires a long random token of at least 32 characters before the gateway can enable.",
        "direct_bot_cutover_enabled": False,
        "writes": False,
        "records_audit_trace": None,
        "audit_trace_mode": "tool_dependent",
        "writes_note": (
            "writes=false means no farm/control/public-output write. Ordinary "
            "tools append their normal audit trace; ROOTLINE intentionally "
            "returns not_stored_rootline_zero_write."
        ),
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    }


def telegram_gateway_exposure_preflight(environ=None):
    source = environ if environ is not None else os.environ
    policy = telegram_gateway_policy(environ=source)
    automated_checks = [
        _check("explicitly_enabled", policy["explicitly_enabled"], "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED is truthy."),
        _check("token_configured", policy["configured"], "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN is configured."),
        _check("token_minimum_length", policy["token_meets_minimum_entropy"], f"Token is at least {MIN_TOKEN_CHARS} characters."),
        _check("allowed_user_ids_configured", policy["allowed_user_ids_configured"], "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS is configured."),
        _check("constant_time_compare", True, "Token comparison uses hmac.compare_digest."),
        _check("auth_lockout_enabled", policy["auth_rate_limit"]["enabled"], "Repeated bad tokens trigger a fail-closed lockout."),
        _check("semantic_llm_has_zero_authority", not policy["semantic_front_door"]["can_execute"],
               "The semantic LLM interprets text only; deterministic specialist boundaries retain authority."),
        _check("ordinary_reply_transport_bounded", not policy["sends_telegram"] and not policy["direct_bot_cutover_enabled"],
               "The gateway itself has no ambient send authority; authenticated provider-bound family lifecycles may deliver through the existing owner bot."),
        _check("owner_task_send_is_scoped", not policy["owner_task_lifecycle"]["enabled"] or (
               policy["owner_task_lifecycle"]["requires_provider_message_identity"]
               and not policy["owner_task_lifecycle"]["ambiguous_delivery_retries"]),
               "When configured, owner-task sends use the existing owner bot, require provider identity, and never retry ambiguity."),
        _check("no_farm_control_write", not policy["writes"] and not policy["dispatch_enabled"], "Gateway does not write farm/control/public output or dispatch."),
        _check(
            "audit_trace_disclosed",
            policy["audit_trace_mode"] == "tool_dependent",
            "Audit storage is reported from the selected tool's trace_store result.",
        ),
    ]
    manual_checks = [
        _check("tls_termination_confirmed", _env_truthy(source.get(TLS_CONFIRMED_ENV)), "Confirm HTTPS/TLS terminates before public traffic reaches the route."),
        _check("rate_limit_model_accepted", _env_truthy(source.get(RATE_LIMIT_MODEL_ACCEPTED_ENV)), "Accept current in-process global lockout, or replace it with shared per-IP throttling before multi-worker production."),
    ]
    automated_ready = all(item["pass"] for item in automated_checks)
    public_ready = automated_ready and all(item["pass"] for item in manual_checks)
    if public_ready:
        status = "public_exposure_ready"
    elif automated_ready:
        status = "private_test_ready_manual_public_checks_pending"
    else:
        status = "blocked"
    return {
        "success": True,
        "status": status,
        "mode": "telegram_gateway_exposure_preflight_only",
        "telegram_gateway": policy,
        "private_test_ready": automated_ready,
        "public_exposure_ready": public_ready,
        "automated_checks": automated_checks,
        "manual_checks": manual_checks,
        "manual_confirm_envs": [TLS_CONFIRMED_ENV, RATE_LIMIT_MODEL_ACCEPTED_ENV],
        "rate_limit_note": "Current auth lockout is in-process and global: acceptable for the local/private trial, but not owner-immune or shared across multiple workers.",
        "sends_telegram": False,
        "direct_bot_cutover_enabled": False,
        "can_trigger_outbound_llm": False,
        "writes": False,
        "records_audit_trace": policy["records_audit_trace"],
        "audit_trace_mode": policy["audit_trace_mode"],
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    }


def handle_telegram_gateway_message(payload, headers=None, environ=None):
    policy = telegram_gateway_policy(environ=environ)
    if not policy["explicitly_enabled"]:
        return _gateway_result(False, "telegram_gateway_disabled", policy, 503)
    if not policy["configured"]:
        return _gateway_result(False, "telegram_gateway_token_not_configured", policy, 503)
    if not policy["token_meets_minimum_entropy"]:
        return _gateway_result(False, "telegram_gateway_token_too_short", policy, 503)
    if not policy["allowed_user_ids_configured"]:
        return _gateway_result(False, "telegram_gateway_allowed_user_ids_required", policy, 503)
    if policy["auth_rate_limit"]["locked"]:
        return _gateway_result(False, "telegram_gateway_auth_rate_limited", policy, 429)
    if not _token_matches(headers or {}, environ=environ):
        _record_auth_failure()
        return _gateway_result(False, "telegram_gateway_auth_denied", policy, 403)

    source = environ if environ is not None else os.environ
    parsed = parse_telegram_gateway_payload(payload)
    allowed_ids = _allowed_user_ids(source)
    if allowed_ids and parsed["telegram_user_id"] not in allowed_ids:
        return _gateway_result(False, "telegram_user_not_allowed", policy, 403)
    family_principal = resolve_family_principal(parsed, source)
    if family_principal.role is FamilyRole.UNKNOWN_SENDER:
        return _gateway_result(False, "telegram_family_identity_not_authorized", policy, 403)
    if family_principal.role is not FamilyRole.OWNER:
        return _gateway_result(False, "telegram_family_lifecycle_not_enabled", policy, 503)

    owner_task, owner_task_status = handle_owner_task_input(
        payload,
        environ=source,
        telegram_sender=lambda chat_id, text, purpose: _send_owner_task_telegram(
            chat_id, text, source),
    )
    if owner_task.get("handled"):
        owner_task.update({
            "mode": "authenticated_gateway_owner_task",
            "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": any(int(owner_task.get(key) or 0) > 0 for key in
                                  ("acknowledgements", "results", "systemic_exceptions")),
            "direct_bot_cutover_enabled": False,
            "can_trigger_outbound_llm": False,
            "writes": False,
            "records_audit_trace": True,
            "dispatch_enabled": False,
            "changes_runtime_now": False,
            "changes_prompt_now": False,
            "physical_controls_enabled": False,
            "customer_public_output_enabled": False,
        })
        return owner_task, owner_task_status

    if not parsed["text"]:
        return _gateway_result(False, "telegram_text_required", policy, 400)
    gateway_authority = issue_gateway_owner_authority(
        parsed["telegram_user_id"],
        parsed["telegram_chat_id"],
    )
    if parsed["telegram_chat_type"] != "private":
        gateway_authority = None

    if gateway_authority is not None:
        replay_result = recover_contextual_specialist_replay(parsed)
        if replay_result and replay_result.get("handled"):
            if replay_result.get("delivery_recovery_required") is True:
                delivery = deliver_family_result(parsed, replay_result,
                    specialist=str(replay_result.get("specialist_identity") or "OOM_SAKKIE"),
                    mission_id=str(replay_result.get("mission_id") or ""),
                    card_mission_id=str(replay_result.get("card_mission_id") or ""))
                body, _ = _gateway_result(delivery.get("success") is True,
                    str(replay_result.get("status") or "contained"), policy, 200)
                body.update({"telegram_user_id": parsed["telegram_user_id"],
                    "telegram_chat_id": parsed["telegram_chat_id"], "text": parsed["text"],
                    "answer": replay_result.get("answer", ""), "message": replay_result,
                    "delivery": delivery, "records_audit_trace": True,
                    "reply_transport": "backend_handles_owner_task_delivery",
                    "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0})
                return body, 200 if delivery.get("success") else 202
            body, _ = _gateway_result(True, str(replay_result.get("status") or "replay_suppressed"),
                                      policy, 200)
            body.update({"telegram_user_id": parsed["telegram_user_id"],
                "telegram_chat_id": parsed["telegram_chat_id"], "text": parsed["text"],
                "answer": replay_result.get("answer", ""), "message": replay_result,
                "delivery": {"success": True, "status": "owner_delivery_suppressed_replay_or_metadata",
                             "telegram_sends": 0, "telegram_edits": 0},
                "records_audit_trace": True,
                "reply_transport": "backend_handles_owner_task_delivery", "sends_telegram": False})
            return body, 200

    auction_result, auction_status = handle_auction_confirmation(parsed, gateway_authority)
    if auction_result.get("handled"):
        delivery = ({"success": True, "telegram_sends": 0, "telegram_edits": 0,
                     "status": "owner_delivery_suppressed_replay"}
                    if auction_result.get("suppress_owner_delivery") else
                    deliver_family_result(parsed, auction_result, specialist="HERDMASTER",
                        mission_id=str(auction_result.get("mission_id") or ""),
                        card_mission_id=str(auction_result.get("card_mission_id") or "")))
        body, _ = _gateway_result(auction_result.get("success") is True,
            str(auction_result.get("status") or "auction_confirmation_contained"),
            policy, auction_status)
        body.update({"telegram_user_id": parsed["telegram_user_id"],
            "telegram_chat_id": parsed["telegram_chat_id"], "text": parsed["text"],
            "answer": auction_result.get("answer", ""), "message": auction_result,
            "delivery": delivery, "records_audit_trace": True,
            "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0,
            "writes": auction_result.get("writes_farm_data") is True})
        return body, auction_status if delivery.get("success") else 202

    protected_result, protected_status = handle_protected_action_input(parsed,gateway_authority)
    if protected_result.get("handled"):
        delivery=({"success":True,"telegram_sends":0,"telegram_edits":0,"status":"protected_replay_noop"}
          if protected_result.get("suppress_owner_delivery") else deliver_family_result(
            parsed,protected_result,specialist=str(protected_result.get("specialist") or "HERDMASTER"),
            mission_id=str(protected_result.get("mission_id") or ""),
            card_mission_id=str(protected_result.get("card_mission_id") or protected_result.get("mission_id") or "")))
        body,_=_gateway_result(protected_result.get("success") is True,
          str(protected_result.get("status") or "protected_action_contained"),policy,protected_status)
        body.update({"telegram_user_id":parsed["telegram_user_id"],"telegram_chat_id":parsed["telegram_chat_id"],
          "text":parsed["text"],"answer":protected_result.get("answer","") ,"message":protected_result,
          "delivery":delivery,"records_audit_trace":True,"reply_transport":"backend_handles_owner_task_delivery",
          "sends_telegram":int(delivery.get("telegram_sends") or 0)>0,"writes":protected_result.get("writes_farm_data") is True})
        return body,(protected_status if delivery.get("success") else
          503 if protected_result.get("success") is True else 202)

    active_manager_question = (load_active_manager_question(parsed)
                               if gateway_authority is not None else None)
    if isinstance(active_manager_question, dict) and active_manager_question.get("load_unavailable"):
        body, _ = _gateway_result(False, "manager_question_context_unavailable", policy, 503)
        body.update({"telegram_user_id": parsed["telegram_user_id"],
            "telegram_chat_id": parsed["telegram_chat_id"], "text": parsed["text"],
            "answer": ("I received the update, but could not safely load the active farm "
                       "question. Nothing was retained or acted on; the same provider receipt "
                       "will remain eligible for exact recovery."),
            "message": {"handled": True, "success": False,
                "status": "manager_question_context_unavailable",
                "writes_farm_data": False, "hardware_commands": 0},
            "delivery": {"success": False, "status": "durable_context_unavailable",
                "telegram_sends": 0, "telegram_edits": 0},
            "records_audit_trace": False,
            "reply_transport": "bounded_authenticated_gateway_response",
            "sends_telegram": False, "writes": False})
        return body, 503
    semantic_policy = semantic_front_door_policy(source)
    semantic_authoritative = bool(gateway_authority is not None and semantic_policy.get("enabled"))
    if gateway_authority is not None and active_manager_question:
        from modules.oom_sakkie.semantic_front_door import load_bounded_owner_context
        semantic = interpret_owner_message(parsed, environ=source,
            context_loader=lambda inbound: semantic_context_with_manager_question(
                inbound, base_context_loader=load_bounded_owner_context,
                question=active_manager_question))
    else:
        semantic = interpret_owner_message(parsed, environ=source) if gateway_authority is not None else None
    if semantic is not None:
        parsed = {**parsed, "semantic": semantic.as_hint()}

    beacon_result, beacon_status = handle_beacon_request(parsed, gateway_authority)
    if beacon_result.get("handled"):
        delivery = ({"success": True, "telegram_sends": 0, "telegram_edits": 0,
                     "status": "owner_delivery_suppressed_replay"}
                    if beacon_result.get("suppress_owner_delivery") else
                    deliver_family_result(parsed, beacon_result, specialist="BEACON",
                        mission_id=str(beacon_result.get("mission_id") or ""),
                        card_mission_id=str(beacon_result.get("card_mission_id") or "")))
        body, _ = _gateway_result(delivery.get("success") is True,
            str(beacon_result.get("status") or "beacon_request_contained"), policy, beacon_status)
        body.update({"telegram_user_id": parsed["telegram_user_id"],
            "telegram_chat_id": parsed["telegram_chat_id"], "text": parsed["text"],
            "answer": beacon_result.get("answer", ""), "message": beacon_result,
            "delivery": delivery, "records_audit_trace": True,
            "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0,
            "writes": False})
        return body, beacon_status if delivery.get("success") else 202

    breeding_result, breeding_status = handle_grouped_breeding_message(parsed, gateway_authority)
    if breeding_result.get("handled"):
        delivery = ({"success": True, "telegram_sends": 0, "telegram_edits": 0,
                     "status": "owner_delivery_suppressed_replay"}
            if breeding_result.get("suppress_owner_delivery") else
            deliver_family_result(parsed, breeding_result, specialist="HERDMASTER",
            mission_id=str(breeding_result.get("mission_id") or ""),
            card_mission_id=str(breeding_result.get("card_mission_id") or ""))
            if breeding_result.get("answer") else {"success": False, "telegram_sends": 0, "telegram_edits": 0})
        if not breeding_result.get("suppress_owner_delivery"):
            delivery = _bind_protected_preview_card(breeding_result, delivery)
        body, _ = _gateway_result(delivery.get("success") is True,
            str(breeding_result.get("status") or "contained"), policy, breeding_status)
        body.update({"telegram_user_id": parsed["telegram_user_id"], "telegram_chat_id": parsed["telegram_chat_id"],
            "text": parsed["text"], "answer": breeding_result.get("answer", ""), "message": breeding_result,
            "delivery": delivery, "records_audit_trace": True,
            "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0})
        return body, breeding_status if delivery.get("success") else 202

    manager_reply, manager_reply_status = handle_manager_question_reply(
        parsed, gateway_authority, semantic, question=active_manager_question)
    if manager_reply.get("handled"):
        delivery = ({"success": True, "telegram_sends": 0, "telegram_edits": 0,
                     "status": "owner_delivery_suppressed_replay"}
                    if manager_reply.get("suppress_owner_delivery") else
                    deliver_family_result(parsed, manager_reply,
                        specialist=str(manager_reply.get("specialist_identity") or "OOM_SAKKIE"),
                        mission_id=str(manager_reply.get("mission_id") or ""),
                        card_mission_id=str(manager_reply.get("card_mission_id") or "")))
        body, _ = _gateway_result(delivery.get("success") is True,
            str(manager_reply.get("status") or "manager_question_contained"),
            policy, manager_reply_status)
        body.update({"telegram_user_id": parsed["telegram_user_id"],
            "telegram_chat_id": parsed["telegram_chat_id"], "text": parsed["text"],
            "answer": manager_reply.get("answer", ""), "message": manager_reply,
            "delivery": delivery, "records_audit_trace": True,
            "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0})
        return body, manager_reply_status if delivery.get("success") else 202

    continuation_result, continuation_status = handle_owner_operational_continuation(
        parsed, gateway_authority,
    )
    if continuation_result.get("handled"):
        delivery = ({"success": True, "telegram_sends": 0, "telegram_edits": 0,
                     "status": "owner_delivery_suppressed_replay_or_metadata"}
                    if continuation_result.get("suppress_owner_delivery") else
                    deliver_family_result(parsed, continuation_result, specialist="ROOTLINE",
                        mission_id=str(continuation_result.get("mission_id") or ""),
                        card_mission_id=str(continuation_result.get("card_mission_id") or "")))
        body, _ = _gateway_result(delivery.get("success") is True,
            str(continuation_result.get("status") or "contained"), policy, continuation_status)
        body.update({"telegram_user_id": parsed["telegram_user_id"],
            "telegram_chat_id": parsed["telegram_chat_id"], "text": parsed["text"],
            "answer": continuation_result.get("answer", ""), "message": continuation_result,
            "delivery": delivery, "records_audit_trace": True,
            "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0})
        return body, 200 if delivery.get("success") else 202

    operational_result, operational_status = handle_operational_specialist_message(
        parsed, gateway_authority,
    )
    if operational_result.get("handled"):
        if (str(operational_result.get("status") or "") == "specialist_accepted"
                and str(operational_result.get("next_specialist_step") or "") ==
                    "supervised_fertilizer_mixer_proof"):
            from modules.oom_sakkie.rootline_fertilizer_commissioning_runtime import (
                continue_fertilizer_commissioning,
            )
            continued = continue_fertilizer_commissioning(
                owner_result=operational_result, parsed=parsed,
                gateway_authority=gateway_authority)
            operational_result = {**operational_result, **continued,
                "mission_id": operational_result.get("mission_id"),
                "card_mission_id": operational_result.get("card_mission_id"),
                "specialist_identity": "ROOTLINE"}
        answer = str(operational_result.get("answer") or "")
        if str(operational_result.get("status") or "") == "waiting_for_input":
            if not answer.strip() or operational_result.get("question_count") != 1:
                operational_result = {**operational_result,
                    "success": False, "status": "operational_waiting_question_invalid",
                    "answer": ("<b>OOM SAKKIE — FOLLOW-UP CONTAINED</b>\n\n"
                               "I retained your reply, but could not prove the one remaining question. "
                               "No farm or hardware action was taken."),
                    "requires_visible_notification": True, "question_count": 0}
            else:
                operational_result = {**operational_result,
                    "requires_visible_notification": True}
            answer = str(operational_result.get("answer") or "")
        delivery = ({"success": True, "telegram_sends": 0, "telegram_edits": 0,
                     "status": "owner_delivery_not_required"}
                    if not answer and not operational_result.get("requires_visible_notification")
                    else deliver_family_result(
                        parsed, operational_result,
                        specialist=str(operational_result.get("specialist_identity") or "OOM_SAKKIE"),
                        mission_id=str(operational_result.get("mission_id") or ""),
                        card_mission_id=str(operational_result.get("card_mission_id") or "")))
        body, _ = _gateway_result(
            delivery.get("success") is True,
            str(operational_result.get("status") or "contained"), policy, operational_status,
        )
        body.update({"telegram_user_id": parsed["telegram_user_id"],
            "telegram_chat_id": parsed["telegram_chat_id"], "text": parsed["text"],
            "answer": answer, "message": operational_result, "delivery": delivery,
            "records_audit_trace": True, "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0})
        body["writes"] = operational_result.get("writes_farm_data")
        body["writes_unknown"] = operational_result.get("writes_farm_data_unknown") is True
        return body, 200 if delivery.get("success") else 202

    weight_result, weight_status = handle_grouped_weight_message(parsed, gateway_authority)
    if weight_result.get("handled"):
        delivery = (deliver_family_result(parsed, weight_result, specialist="HERDMASTER",
            mission_id=str(weight_result.get("mission_id") or ""),
            card_mission_id=str(weight_result.get("card_mission_id") or ""))
            if weight_result.get("answer") else {"success": False, "telegram_sends": 0, "telegram_edits": 0})
        delivery = _bind_protected_preview_card(weight_result, delivery)
        body, _ = _gateway_result(delivery.get("success") is True,
            str(weight_result.get("status") or "contained"), policy, weight_status)
        body.update({"telegram_user_id": parsed["telegram_user_id"], "telegram_chat_id": parsed["telegram_chat_id"],
            "text": parsed["text"], "answer": weight_result.get("answer", ""), "message": weight_result,
            "delivery": delivery, "records_audit_trace": True,
            "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0})
        return body, weight_status if delivery.get("success") else 202

    health_result, health_status = handle_authenticated_health_loss_message(
        parsed,
        gateway_authority,
    )
    if health_result.get("handled"):
        answer = str(health_result.get("answer") or "")
        if not answer and health_result.get("success") is not True:
            answer = ("⚠️ <b>HERDMASTER FOLLOW-UP CONTAINED</b>\n\n"
                      "Your message reached Oom Sakkie, but safe HERDMASTER processing was not proven. "
                      "Nothing was recorded; one technical follow-up is required.")
            health_result = {**health_result, "answer": answer,
                             "status": str(health_result.get("status") or "contained")}
        body, _ = _gateway_result(
            health_result.get("success") is True,
            str(health_result.get("status") or "health_loss_contained"),
            policy,
            health_status,
        )
        delivery = ({"success": True, "telegram_sends": 0, "telegram_edits": 0,
                     "status": "owner_delivery_suppressed_existing_card_unchanged"}
                    if health_result.get("suppress_owner_delivery") is True else
                    deliver_family_result(
                        parsed, health_result, specialist="HERDMASTER",
                        mission_id=str(health_result.get("mission_id") or ""),
                        card_mission_id=str(health_result.get("card_mission_id") or "")))
        delivery = _bind_protected_preview_card(health_result, delivery)
        body.update({
            "telegram_user_id": parsed["telegram_user_id"],
            "telegram_chat_id": parsed["telegram_chat_id"],
            "text": parsed["text"],
            "answer": answer,
            "message": health_result,
            "records_audit_trace": health_result.get("records_audit_trace") is True,
            "audit_trace_status": "stored" if health_result.get("records_audit_trace") is True else "not_written",
            "reply": {
                "chat_id": parsed["telegram_chat_id"],
                "text": answer,
                "parse_mode": "HTML",
                "sends_telegram": False,
            },
            "delivery": delivery,
            "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0,
        })
        return body, health_status if delivery.get("success") else 202

    herd_request, herd_request_status = handle_herdmaster_request(parsed, gateway_authority)
    if herd_request.get("handled"):
        if not str(herd_request.get("answer") or "").strip() and not herd_request.get("suppress_owner_delivery"):
            herd_request = {**herd_request,
                "answer": ("<b>HERDMASTER — BREEDING PLAN WAITING</b>\n\n"
                           "I could not refresh the current canonical breeding evidence. "
                           "No mating or farm record was changed. Oom Sakkie will reassess "
                           "when current herd evidence is available.")}
        delivery = deliver_family_result(parsed, herd_request, specialist="HERDMASTER",
            mission_id=str(herd_request.get("mission_id") or ""),
            card_mission_id=str(herd_request.get("card_mission_id") or ""),
            delivery_retry_authority=delivery_retry_authority_for(herd_request))
        body, _ = _gateway_result(bool(herd_request.get("success")),
            str(herd_request.get("status") or "herdmaster_request_contained"),
            policy, herd_request_status)
        body.update({"telegram_user_id": parsed["telegram_user_id"],
            "telegram_chat_id": parsed["telegram_chat_id"], "text": parsed["text"],
            "answer": herd_request.get("answer", ""), "message": herd_request,
            "delivery": delivery, "records_audit_trace": True,
            "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0})
        return body, herd_request_status if delivery.get("success") else 202

    manager_result, manager_status = handle_farm_manager_round(parsed, gateway_authority)
    if manager_result.get("handled"):
        answer = str(manager_result.get("answer") or "")
        delivery = deliver_family_result(parsed, manager_result, specialist="OOM_SAKKIE",
            mission_id=str(manager_result.get("mission_id") or ""),
            card_mission_id=str(manager_result.get("card_mission_id") or "")) \
            if manager_result.get("success") else {"success": False, "telegram_sends": 0}
        body, _ = _gateway_result(bool(manager_result.get("success")),
            str(manager_result.get("status") or "farm_manager_contained"), policy, manager_status)
        body.update({"telegram_user_id": parsed["telegram_user_id"],
            "telegram_chat_id": parsed["telegram_chat_id"], "text": parsed["text"],
            "answer": answer, "message": manager_result, "delivery": delivery,
            "records_audit_trace": True, "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0})
        return body, manager_status if delivery.get("success") else 202

    service_payload = {
        "text": parsed["text"],
        "channel": "telegram_read_only",
        "session_id": parsed["session_id"],
        "authenticated_owner": TELEGRAM_OWNER_AUTHORITY,
        "gateway_authority": gateway_authority,
    }
    if semantic_authoritative:
        service_payload.update({"semantic": parsed.get("semantic") or {},
                                "semantic_authoritative": True})
    message_result, message_status = handle_message(service_payload)
    if (gateway_authority is not None
            and message_result.get("needs_clarification") is True
            and not str(message_result.get("tool_used") or "").strip()):
        message_result = build_owner_clarification(parsed)
        message_status = 200
    rootline_auth_denied = (
        message_result.get("tool_used") == "rootline_water_energy_plan"
        and message_result.get("success") is not True
    )
    response_status = (
        "protected_reader_authentication_denied"
        if rootline_auth_denied
        else "answered"
    )
    response_code = 403 if rootline_auth_denied else message_status
    trace_store = message_result.get("trace_store") or {}
    body, _ = _gateway_result(
        bool(message_result.get("success")),
        response_status,
        policy,
        response_code,
    )
    body.update({
        "telegram_user_id": parsed["telegram_user_id"],
        "telegram_chat_id": parsed["telegram_chat_id"],
        "text": parsed["text"],
        "answer": message_result.get("answer", ""),
        "message": message_result,
        "records_audit_trace": trace_store.get("stored") is True,
        "audit_trace_status": str(trace_store.get("status") or "not_written"),
        "reply": {
            "chat_id": parsed["telegram_chat_id"],
            "text": message_result.get("answer", ""),
            "parse_mode": None,
            "sends_telegram": False,
        },
    })
    durable_delivery_ready = bool(str(os.environ.get("DATABASE_URL") or "").strip()
                                  and str(parsed.get("provider_message_id") or "").strip()
                                  and str(parsed.get("provider_timestamp") or "").strip())
    if body.get("success") and str(body.get("answer") or "").strip() and durable_delivery_ready:
        specialist = str(message_result.get("tool_used") or "OOM_SAKKIE").upper()
        delivery = deliver_family_result(
            parsed, message_result, specialist=specialist,
            mission_id=str(message_result.get("mission_id") or ""),
            card_mission_id=str(message_result.get("card_mission_id") or ""))
        body.update({"delivery": delivery,
            "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0})
        if not delivery.get("success"):
            return body, 202
    return body, response_code


def handle_rootline_reassessment_trigger(payload, headers=None, environ=None, *, specialist_loader=None,
                                         state_store=None, family_delivery=None, schedule_store=None,
                                         scheduler_now=None, execution_cycle=None):
    """Run one authenticated scheduled/evidence-change reassessment via the existing family rail."""
    source = environ if environ is not None else os.environ
    policy = telegram_gateway_policy(source)
    if not policy["enabled"] or not _token_matches(headers or {}, environ=source):
        return _gateway_result(False, "rootline_reassessment_auth_denied", policy, 403)
    if str((payload or {}).get("scheduler_identity") or "").strip():
        scheduled_owner = str((payload or {}).get("owner_user_id") or "").strip()
        scheduled_chat = str((payload or {}).get("chat_id") or "").strip()
        scheduled_principal = resolve_family_principal({
            "telegram_user_id": scheduled_owner, "telegram_chat_id": scheduled_chat,
            "telegram_chat_type": "private"}, source)
        if (scheduled_owner not in _allowed_user_ids(source)
                or scheduled_principal.role is not FamilyRole.OWNER):
            return _gateway_result(False, "rootline_reassessment_owner_binding_denied", policy, 403)
        from modules.oom_sakkie.automatic_reassessment_scheduler import run_due_reassessment
        from concurrent.futures import ThreadPoolExecutor, wait
        from modules.oom_sakkie.daily_farm_manager import run_daily_farm_manager
        production_persistence = schedule_store is None or state_store is None
        if schedule_store is None:
            from modules.oom_sakkie.automatic_reassessment_store import automatic_reassessment_store
            schedule_store = automatic_reassessment_store
        if state_store is None:
            from modules.oom_sakkie.rootline_reassessment_store import rootline_reassessment_state_store
            state_store = rootline_reassessment_state_store
        manual_payload = {key: value for key, value in (payload or {}).items()
                          if key not in {"scheduler_identity", "specialist", "due_at", "evidence_cutoff"}}
        base_scheduled_loader = specialist_loader
        if base_scheduled_loader is None:
            from modules.telemetry.rootline_specialist_result import build_current_rootline_specialist_result
            base_scheduled_loader = lambda: build_current_rootline_specialist_result(
                now=datetime.fromisoformat(str(payload.get("evidence_cutoff")).replace("Z", "+00:00")))
        def scheduled_loader():
            current = base_scheduled_loader()
            try:
                observed = datetime.fromisoformat(str(current.get("evidence_cutoff") or "").replace("Z", "+00:00"))
                requested = datetime.fromisoformat(str(payload.get("evidence_cutoff")).replace("Z", "+00:00"))
            except (AttributeError, TypeError, ValueError):
                return {"success": False, "status": "scheduled_reassessment_evidence_cutoff_unproven"}
            if observed > requested:
                return {"success": False, "status": "scheduled_reassessment_evidence_after_cutoff"}
            return current
        def invoke():
            deliver = family_delivery or deliver_family_result
            if production_persistence:
                try:
                    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read
                    with connect_bounded_read(database_url=source.get("DATABASE_URL")) as connection:
                        with connection.cursor() as cursor:
                            cursor.execute("select 1")
                            cursor.fetchone()
                except Exception:
                    return {"success": False,
                        "status": "scheduled_reassessment_database_unavailable",
                        "telegram_sends": 0, "telegram_edits": 0, "hardware_commands": 0,
                        "writes_farm_data": False, "automatic_irrigation_authority": False,
                        "answer": ("The scheduled assessment could not load its durable context. "
                                   "No provider or hardware action was attempted.")}
            mixer_recovery = {"status": "fertilizer_recovery_unproven",
                              "hardware_commands": 0, "telegram_sends": 0}
            try:
                from modules.oom_sakkie.farm_manager_runtime import _load_herdmaster, _load_rootline
                from modules.pig_weights.farm_supabase_read_service import get_breeding_attention_source_snapshot
                from modules.sales.sales_transaction_read import list_sales_transactions
                manager_now = scheduler_now or datetime.now(timezone.utc)
                manager_owner = str(manual_payload.get("owner_user_id") or "")
                authority = issue_gateway_owner_authority(manager_owner,
                    str(manual_payload.get("chat_id") or ""))
                executor = ThreadPoolExecutor(max_workers=4,
                    thread_name_prefix="oom-daily-manager")
                try:
                    futures = {
                        "herd": executor.submit(_load_herdmaster, authority,
                            manager_owner, manager_now,
                            str(manual_payload.get("language") or "en")),
                        "rootline": executor.submit(_load_rootline, manager_now),
                        "litters": executor.submit(get_breeding_attention_source_snapshot,
                            deadline_seconds=20),
                        "sales": executor.submit(list_sales_transactions),
                    }
                    from modules.oom_sakkie.bounded_postgres_read import OWNER_REQUEST_DEADLINE_SECONDS
                    done, pending = wait(tuple(futures.values()),
                                         timeout=OWNER_REQUEST_DEADLINE_SECONDS)
                    if futures["herd"] not in done or futures["rootline"] not in done:
                        raise TimeoutError("daily_manager_specialist_deadline")
                    specialists = [futures["herd"].result(), futures["rootline"].result()]
                    litter_rows = []
                    if futures["litters"] in done:
                        snapshot = futures["litters"].result()
                        litter_rows = ((snapshot.get("allocation_inputs") or {})
                            .get("litter_rows") or [])
                    sale_rows = []
                    if futures["sales"] in done:
                        try:
                            sales_payload, sales_status = futures["sales"].result()
                            if sales_status == 200 and sales_payload.get("success") is True:
                                sale_rows = sales_payload.get("sales_transactions") or []
                        except Exception:
                            sale_rows = []
                    for future in pending:
                        future.cancel()
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)
                daily = run_daily_farm_manager(owner_user_id=manager_owner,
                    chat_id=str(manual_payload.get("chat_id") or ""),
                    specialist_results=specialists, litter_rows=litter_rows,
                    sale_rows=sale_rows,
                    deliver=deliver, now=manager_now,
                    language=str(manual_payload.get("language") or "en"))
            except TimeoutError:
                daily = {"success": False, "status": "daily_farm_manager_deadline_exceeded",
                         "telegram_sends": 0, "telegram_edits": 0,
                         "hardware_commands": 0, "writes_farm_data": False}
            except Exception as exc:
                from modules.oom_sakkie.bounded_postgres_read import is_database_unavailable
                daily = {"success": False, "status": (
                    "daily_farm_manager_database_unavailable"
                    if production_persistence and is_database_unavailable(exc)
                    else "daily_farm_manager_unavailable"),
                         "telegram_sends": 0, "telegram_edits": 0,
                         "hardware_commands": 0, "writes_farm_data": False}
            if daily.get("status") in {"daily_farm_manager_deadline_exceeded",
                                      "daily_farm_manager_database_unavailable"}:
                database_unavailable = daily.get("status") == "daily_farm_manager_database_unavailable"
                return {"success": False,
                    "status": ("scheduled_reassessment_database_unavailable" if database_unavailable
                               else "scheduled_reassessment_evidence_deadline_exceeded"),
                    "daily_presentation_status": str(daily.get("status") or "unavailable"),
                    "telegram_sends": int(mixer_recovery.get("telegram_sends") or 0),
                    "telegram_edits": 0,
                    "hardware_commands": int(mixer_recovery.get("hardware_commands") or 0),
                    "writes_farm_data": False, "automatic_irrigation_authority": False,
                    "answer": (("The scheduled assessment lost durable database availability. "
                                "No further ROOTLINE assessment was started; the durable schedule "
                                "remains recoverable.") if database_unavailable else
                               ("The scheduled assessment exceeded its bounded evidence deadline. "
                                "No further ROOTLINE assessment was started; the durable schedule "
                                "remains recoverable."))}
            if not str(source.get("DATABASE_URL") or "").strip():
                mixer_recovery = {"status": "no_active_fertilizer_commissioning",
                    "hardware_commands": 0, "telegram_sends": 0}
            else:
                try:
                    from modules.oom_sakkie.rootline_fertilizer_commissioning_runtime import (
                        MISSION_ID, recover_fertilizer_commissioning,
                    )
                    mixer_recovery = recover_fertilizer_commissioning(
                        now=scheduler_now, environ=source)
                    if mixer_recovery.get("answer"):
                        mixer_parsed = {
                            "telegram_user_id": str(manual_payload.get("owner_user_id") or ""),
                            "telegram_chat_id": str(manual_payload.get("chat_id") or ""),
                            "provider_message_id": "scheduled:fertilizer:" + str(
                                manual_payload.get("trigger_id") or ""),
                            "provider_timestamp": str(manual_payload.get("trigger_timestamp") or "")}
                        mixer_delivery = deliver(mixer_parsed, mixer_recovery,
                            specialist="ROOTLINE", mission_id=MISSION_ID,
                            card_mission_id=MISSION_ID)
                        mixer_recovery = {**mixer_recovery,
                            "telegram_sends": int(mixer_delivery.get("telegram_sends") or 0)}
                except Exception:
                    mixer_recovery = {"status": "fertilizer_recovery_unproven",
                        "hardware_commands": 0, "telegram_sends": 0}
            mixer_status = str(mixer_recovery.get("status") or "")
            mixer_owns_controller = mixer_status not in {
                "no_active_fertilizer_commissioning", "auxiliary_completed"}
            if (str(source.get("ROOTLINE_AUTONOMOUS_BC_ENABLED") or "").lower() == "true"
                    and not mixer_owns_controller):
                cycle = execution_cycle
                if cycle is None:
                    from modules.telemetry.rootline_execution_runtime import run_rootline_execution_cycle
                    cycle = run_rootline_execution_cycle
                parsed = {"telegram_user_id": str(manual_payload.get("owner_user_id") or ""),
                          "telegram_chat_id": str(manual_payload.get("chat_id") or ""),
                          "provider_message_id": f"scheduled:{manual_payload.get('trigger_id')}",
                          "provider_timestamp": str(manual_payload.get("trigger_timestamp") or "")}
                def notify(state, execution):
                    zone = str(execution.get("zone_id") or "irrigation")
                    answer = ({"Started": f"<b>💧 IRRIGATION STARTED</b>\n\n{zone} is running for no more than 59 minutes 59 seconds.",
                               "Completed": f"<b>✅ IRRIGATION COMPLETED</b>\n\n{zone} is stopped and the supported segment is complete.",
                               "Blocked": (f"<b>IRRIGATION WAITING</b>\n\n{zone} is ready for water but cannot start: "
                                           f"{execution.get('blocker')}. No owner action is currently required. "
                                           f"ROOTLINE will reassess at {execution.get('next_reassessment_at') or 'the next automatic check'}."),
                               "Intervention": (f"<b>🚨 IRRIGATION INTERVENTION</b>\n\n{zone} is stopped, but its outcome needs confirmation."
                                                if execution.get("shutdown_verified") is True
                                                else f"<b>🚨 IRRIGATION INTERVENTION</b>\n\n{zone} shutdown is uncertain. Automatic reuse is contained and owner attention is required.")}
                              .get(state, f"{zone} irrigation: {state}."))
                    base_identity = str(execution.get("notification_identity")
                                        or execution.get("execution_id") or "")
                    event_identity = f"{base_identity}:{str(state).upper()}"
                    delivery = deliver(parsed, {"success": True, "status": state.lower(),
                        "answer": answer}, specialist="ROOTLINE",
                        mission_id=event_identity, card_mission_id=event_identity)
                    return {**delivery,
                        "provider_delivery_confirmed": bool(delivery.get("telegram_message_id"))
                            and (delivery.get("success") is True
                                 or delivery.get("provider_delivery_confirmed") is True),
                        "provider_delivery_ambiguous": "ambiguous" in str(delivery.get("status") or ""),
                        "provider_message_id": str(delivery.get("telegram_message_id") or "")}
                cycle_result = dict(cycle(notify=notify, environ=source, now=scheduler_now,
                    owner_user_id=str(manual_payload.get("owner_user_id") or ""),
                    chat_id=str(manual_payload.get("chat_id") or ""),
                    next_reassessment_at=str(manual_payload.get("next_due_at") or
                                             manual_payload.get("due_at") or ""),
                    observation_store=state_store) or {})
                return {**cycle_result,
                    "fertilizer_commissioning_status": str(mixer_recovery.get("status") or ""),
                    "daily_presentation_status": str(daily.get("status") or ""),
                    "daily_presentation_identity": str(daily.get("daily_identity") or ""),
                    "telegram_sends": int(daily.get("telegram_sends") or 0)
                        + int(mixer_recovery.get("telegram_sends") or 0)
                        + int(cycle_result.get("telegram_sends") or cycle_result.get("telegram_messages") or 0),
                    "telegram_edits": int(daily.get("telegram_edits") or 0)
                        + int(cycle_result.get("telegram_edits") or 0)}
            if mixer_owns_controller:
                return {**mixer_recovery,
                    "daily_presentation_status": str(daily.get("status") or ""),
                    "daily_presentation_identity": str(daily.get("daily_identity") or ""),
                    "telegram_sends": int(daily.get("telegram_sends") or 0)
                        + int(mixer_recovery.get("telegram_sends") or 0)}
            result, nested_status = handle_rootline_reassessment_trigger(
                manual_payload, headers=headers, environ=source, specialist_loader=scheduled_loader,
                state_store=state_store, family_delivery=family_delivery)
            if nested_status != 200:
                return {**result, "success": False,
                        "scheduled_underlying_status": str(result.get("status") or ""),
                        "status": "scheduled_reassessment_delivery_contained"}
            return {**result, "daily_presentation_status": str(daily.get("status") or ""),
                    "daily_presentation_identity": str(daily.get("daily_identity") or ""),
                    "telegram_sends": int(daily.get("telegram_sends") or 0)
                        + int(result.get("telegram_sends") or 0)}
        scheduled = run_due_reassessment(payload=payload, invoke=invoke, store=schedule_store,
                                         now=scheduler_now)
        return scheduled, 200 if scheduled.get("success") else 202
    owner = str((payload or {}).get("owner_user_id") or "").strip()
    chat = str((payload or {}).get("chat_id") or "").strip()
    trigger = str((payload or {}).get("trigger") or "").strip()
    trigger_id = str((payload or {}).get("trigger_id") or "").strip()
    trigger_at = str((payload or {}).get("trigger_timestamp") or "").strip()
    if owner != chat or owner not in _allowed_user_ids(source) or not trigger_id or not trigger_at:
        return _gateway_result(False, "rootline_reassessment_binding_invalid", policy, 403)
    if specialist_loader is None:
        from modules.telemetry.rootline_specialist_result import build_current_rootline_specialist_result
        specialist_loader = build_current_rootline_specialist_result
    if state_store is None:
        from modules.oom_sakkie.rootline_reassessment_store import rootline_reassessment_state_store
        state_store = rootline_reassessment_state_store
    result = reassess_rootline(owner_user_id=owner, chat_id=chat, trigger=trigger,
        specialist_loader=specialist_loader, state_store=state_store,
        language="af" if str((payload or {}).get("language") or "").casefold().startswith("af") else "en")
    if not result.get("notify_owner"):
        return result, 200 if result.get("success") else 202
    parsed = {"telegram_user_id": owner, "telegram_chat_id": chat,
        "provider_message_id": f"scheduled:{trigger_id}", "provider_timestamp": trigger_at,
        "semantic": {"domain": "water_energy", "intent": "rootline_reassessment",
                     "language": str((payload or {}).get("language") or "en")}}
    deliver = family_delivery or deliver_family_result
    delivery = deliver(parsed, {**result, "status": result["status"]}, specialist="ROOTLINE",
        mission_id=result["notification_identity"], card_mission_id=result["notification_identity"])
    delivery_proof = {"provider_delivery_confirmed": bool(delivery.get("telegram_message_id"))
        and (delivery.get("success") is True or delivery.get("provider_delivery_confirmed") is True),
        "provider_delivery_ambiguous": "ambiguous" in str(delivery.get("status") or ""),
        "provider_message_id": str(delivery.get("telegram_message_id") or ""),
        "provider_timestamp": str(delivery.get("provider_timestamp") or "")}
    recorded = record_reassessment_delivery(identity=result["notification_identity"], owner_user_id=owner,
        chat_id=chat, material_digest=result["material_digest"], delivery=delivery_proof, state_store=state_store)
    return {**result, "delivery": delivery, "delivery_record": recorded,
            "telegram_sends": int(delivery.get("telegram_sends") or 0)}, 200 if delivery_proof["provider_delivery_confirmed"] else 202


def parse_telegram_gateway_payload(payload):
    payload = payload or {}
    message = payload.get("message") or payload.get("edited_message") or {}
    from_user = message.get("from") or payload.get("from") or {}
    chat = message.get("chat") or payload.get("chat") or {}
    text = payload.get("text") or message.get("text") or message.get("caption") or ""
    telegram_user_id = payload.get("telegram_user_id") or payload.get("from_user_id") or from_user.get("id") or ""
    telegram_chat_id = payload.get("telegram_chat_id") or payload.get("chat_id") or chat.get("id") or ""
    session_id = payload.get("session_id") or telegram_chat_id or telegram_user_id or ""
    telegram_chat_type = payload.get("telegram_chat_type") or chat.get("type") or ""
    if not telegram_chat_type and str(telegram_chat_id) == str(telegram_user_id):
        telegram_chat_type = "private"
    return {
        "text": str(text or "").strip()[:MAX_TELEGRAM_TEXT_CHARS],
        "telegram_user_id": str(telegram_user_id or "").strip()[:80],
        "telegram_chat_id": str(telegram_chat_id or "").strip()[:80],
        "telegram_chat_type": str(telegram_chat_type or "").strip()[:20],
        "session_id": f"telegram-{str(session_id or '').strip()[:100]}",
        "provider_message_id": str(message.get("message_id") or payload.get("message_id") or "").strip()[:120],
        "provider_timestamp": (
            datetime.fromtimestamp(float(message.get("date")), timezone.utc).isoformat()
            if isinstance(message.get("date"), (int, float)) else ""
        ),
        "reply_to_message_id": str(
            (message.get("reply_to_message") or {}).get("message_id") or ""
        ).strip()[:120],
    }


def _send_owner_task_telegram(chat_id, text, source):
    from modules.sales.sam_live_stock_launch_control import _telegram_api
    token = _owner_task_bot_token(source)
    if not token:
        return {"success": False, "status": "owner_task_telegram_token_not_configured",
                "delivery_definitely_not_sent": True}
    try:
        response = _telegram_api(token, "sendMessage", {
            "chat_id": str(chat_id), "text": str(text), "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
    except Exception:
        return {"success": False, "status": "owner_task_telegram_delivery_ambiguous"}
    result = response.get("result") if isinstance(response, dict) else {}
    message_id = str((result or {}).get("message_id") or "")
    provider_date = (result or {}).get("date")
    provider_timestamp = (datetime.fromtimestamp(int(provider_date), tz=timezone.utc).isoformat()
                          if provider_date is not None else "")
    return {"success": response.get("ok") is True and bool(message_id),
            "status": "owner_task_telegram_delivered" if message_id else "owner_task_telegram_delivery_unconfirmed",
            "delivery_definitely_not_sent": response.get("ok") is False and not message_id,
            "telegram_message_id": message_id,
            "provider_timestamp": provider_timestamp}


def _owner_task_bot_token(source):
    return str(source.get("SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN")
               or source.get("OOM_SAKKIE_TELEGRAM_BOT_TOKEN") or "").strip()


def _gateway_result(success, status, policy, status_code):
    return {
        "success": success,
        "status": status,
        "mode": "telegram_read_only_gateway",
        "telegram_gateway": policy,
        "sends_telegram": False,
        "reply_transport": "caller_handles_telegram_send",
        "deterministic_only": policy.get("deterministic_only", True),
        "can_trigger_outbound_llm": policy.get("can_trigger_outbound_llm", False),
        "writes": False,
        "records_audit_trace": False,
        "audit_trace_mode": policy.get("audit_trace_mode", "tool_dependent"),
        "writes_note": policy.get("writes_note", ""),
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    }, status_code


def _token_matches(headers, environ=None):
    source = environ if environ is not None else os.environ
    expected = str(source.get(TOKEN_ENV, "") or "").strip()
    if not expected:
        return False
    authorization = str(_header_value(headers, "Authorization") or "").strip()
    bearer_prefix = "Bearer "
    if authorization.startswith(bearer_prefix) and hmac.compare_digest(authorization[len(bearer_prefix):].strip(), expected):
        return True
    provided = str(_header_value(headers, "X-Oom-Sakkie-Telegram-Token") or "").strip()
    return hmac.compare_digest(provided, expected)


def _header_value(headers, name):
    if hasattr(headers, "get"):
        return headers.get(name) or headers.get(name.lower()) or headers.get(name.upper())
    return ""


def _allowed_user_ids(source):
    raw = str(source.get(ALLOWED_USER_IDS_ENV, "") or "")
    return {
        item.strip()
        for item in raw.split(",")
        if item.strip()
    }


def _env_truthy(value):
    return str(value or "").strip().lower() in TRUTHY


def _check(name, passed, note):
    return {
        "name": name,
        "pass": bool(passed),
        "note": note,
    }


def _auth_locked(now=None):
    now = time.monotonic() if now is None else now
    return now < _AUTH_LOCKED_UNTIL


def _record_auth_failure(now=None):
    global _AUTH_LOCKED_UNTIL
    now = time.monotonic() if now is None else now
    cutoff = now - AUTH_FAILURE_WINDOW_SECONDS
    kept = [stamp for stamp in _AUTH_FAILURE_TIMES if stamp >= cutoff]
    kept.append(now)
    _AUTH_FAILURE_TIMES[:] = kept
    if len(_AUTH_FAILURE_TIMES) >= AUTH_FAILURE_LIMIT:
        _AUTH_LOCKED_UNTIL = now + AUTH_LOCKOUT_SECONDS


def _reset_auth_rate_limit_for_tests():
    global _AUTH_LOCKED_UNTIL
    _AUTH_FAILURE_TIMES.clear()
    _AUTH_LOCKED_UNTIL = 0.0
