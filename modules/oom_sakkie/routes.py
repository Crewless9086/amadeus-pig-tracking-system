import hmac
import os

from flask import Blueprint, Response, jsonify, request

from modules.auth.owner_access import (
    owner_admin_principal,
    owner_session_is_valid,
    require_owner_admin_access,
    require_owner_read_access,
    require_strict_owner_admin_access,
)
from modules.oom_sakkie.sam_payment_owner_runtime import present_sale_payment_preview
from modules.beacon.media_intake import (
    canonical_media_group_owner_binding,
    list_media_intakes,
    private_album_review,
    read_private_thumbnail,
    record_media_group_review,
    record_media_review,
)
from modules.beacon.protected_publication_worker import run_protected_publication_cycle

from modules.oom_sakkie.access import (
    is_message_request_allowed,
    is_review_request_allowed,
    message_access_denied_response,
    review_access_denied_response,
)
from modules.oom_sakkie.agent_runtime import (
    get_agent_activation_plan,
    get_agent_activation_preflight,
    get_agent_authority_matrix,
    get_agent_authority_unlock_readiness,
    get_agent_dispatch_decision_rail_blueprint,
    get_agent_operating_contracts,
    get_agent_runtime_review_packet,
    get_agent_runtime_status,
    get_learning_influence_consumption_audit_rail_blueprint,
    get_learning_influence_consumer_design_packet,
    recommend_agent_for_text,
    get_learning_influence_consumption_readiness,
)
from modules.oom_sakkie.agent_dry_run_handoff import build_agent_dry_run_handoff
from modules.oom_sakkie.agent_dry_run_store import (
    get_agent_dry_run_request,
    list_agent_dry_run_requests,
    record_agent_dry_run_event,
    record_agent_dry_run_request,
)
from modules.oom_sakkie.agent_dry_run_result_store import (
    get_agent_dry_run_result,
    list_agent_dry_run_results,
    record_agent_dry_run_result,
    record_agent_dry_run_result_event,
)
from modules.oom_sakkie.agent_dry_run_result_review import build_agent_dry_run_result_review_packet
from modules.oom_sakkie.build_request_store import (
    get_build_request,
    list_build_requests,
    record_build_request,
    record_build_request_event,
)
from modules.oom_sakkie.deploy_decision_store import (
    list_deploy_decisions,
    record_deploy_decision,
)
from modules.oom_sakkie.dispatch_decision_store import (
    list_dispatch_requests,
    record_dispatch_decision,
    record_dispatch_request,
)
from modules.oom_sakkie.dispatch_execution_approval_store import (
    list_dispatch_execution_approvals,
    record_dispatch_execution_approval,
    record_dispatch_execution_approval_event,
)
from modules.oom_sakkie.forge_handoff import build_forge_handoff
from modules.oom_sakkie.learning_advisor import get_learning_advisor, run_learning_analysis
from modules.oom_sakkie.learning_packet import (
    approve_build_request,
    build_learning_packet,
    get_implementation_queue,
)
from modules.oom_sakkie.learning_influence_store import (
    list_learning_influence_proposals,
    record_learning_influence_proposal_event,
    record_learning_influence_proposal_from_result,
    record_learning_influence_proposals_from_accepted,
)
from modules.oom_sakkie.learning_influence_consumption_store import (
    list_learning_influence_consumption_requests,
    record_learning_influence_consumption_event,
    record_learning_influence_consumption_request,
)
from modules.oom_sakkie.learning_influence_consumer import produce_learning_influence_review_note_artifact
from modules.oom_sakkie.patch_proposal_store import (
    list_patch_proposals,
    record_patch_proposal,
    record_patch_proposal_event,
)
from modules.oom_sakkie.policy import get_runtime_policy
from modules.oom_sakkie.review_advisor import get_review_advisor
from modules.oom_sakkie.sales_campaign_store import (
    get_sales_lead_preorder_contract,
    get_sales_lead_customer_followup_draft,
    get_sales_lead_customer_followup_send_design,
    list_sales_campaigns,
    list_sales_leads,
    list_sales_outreach_drafts,
    list_sales_send_design_requests,
    record_sales_campaign,
    record_sales_campaign_event,
    record_sales_lead,
    record_sales_lead_event,
    record_owner_money_path_approval,
    record_customer_followup_send_approval,
    record_sam_meat_intake_lead,
    record_sales_outreach_draft_from_campaign,
    record_sales_send_design_request_from_draft,
    send_customer_followup_to_chatwoot,
)
from modules.oom_sakkie.service import handle_message
from modules.oom_sakkie.morning_scheduler import (
    TOKEN_ENV as MORNING_SCHEDULER_TOKEN_ENV,
    run_provider_schedule,
    run_synthetic_acceptance,
)
from modules.oom_sakkie.protected_payment_recovery import run_payment_recovery_cycle
from modules.oom_sakkie.general_manager_worker import (
    deliver_farm_manager_case, run_general_manager_cycle,
)
from modules.oom_sakkie.rootline_physical_acceptance import attach_physical_acceptance
from modules.oom_sakkie.sentinel_single_shot_runner import run_sentinel_single_shot_dry_run
from modules.oom_sakkie.specialists import list_specialist_manifests
from modules.oom_sakkie.telegram_gateway import (
    handle_rootline_reassessment_trigger,
    handle_telegram_gateway_message,
    telegram_gateway_exposure_preflight,
)
from modules.oom_sakkie.telegram_direct import (
    handle_telegram_direct_webhook,
    telegram_direct_parity_report,
)
from modules.oom_sakkie.tools import accepted_agent_learning_snapshot, list_tool_catalog
from modules.oom_sakkie.trace_store import (
    get_trace_review_summary,
    list_recent_traces,
    record_trace_feedback,
)
from modules.oom_sakkie.voice_stt import transcribe_oom_sakkie_voice_audio


oom_sakkie_bp = Blueprint("oom_sakkie", __name__)
SAM_MEAT_INTAKE_REMOTE_ENABLED_ENV = "OOM_SAKKIE_SAM_MEAT_INTAKE_REMOTE_ENABLED"
SAM_MEAT_INTAKE_REMOTE_TOKEN_ENV = "OOM_SAKKIE_SAM_MEAT_INTAKE_REMOTE_TOKEN"
SAM_MEAT_INTAKE_REMOTE_MIN_TOKEN_CHARS = 32
MEAT_FOLLOWUP_SEND_ENABLED_ENV = "OOM_SAKKIE_MEAT_FOLLOWUP_SEND_ENABLED"
MEAT_FOLLOWUP_SEND_TOKEN_ENV = "OOM_SAKKIE_MEAT_FOLLOWUP_SEND_TOKEN"
MEAT_FOLLOWUP_SEND_MIN_TOKEN_CHARS = 32


def _require_review_access():
    if is_review_request_allowed(request.remote_addr):
        return None
    body, status_code = review_access_denied_response(request.remote_addr)
    return jsonify(body), status_code


def _require_runtime_review_packet_access():
    """Allow the existing local reviewer or an authenticated owner-read session."""
    if is_review_request_allowed(request.remote_addr) or owner_session_is_valid("read"):
        return None
    body, status_code = review_access_denied_response(request.remote_addr)
    return jsonify(body), status_code


def _require_sam_meat_intake_remote_access():
    if not _env_truthy(os.environ.get(SAM_MEAT_INTAKE_REMOTE_ENABLED_ENV)):
        return jsonify(_sam_meat_intake_remote_denied("sam_meat_intake_remote_disabled")), 503

    expected = str(os.environ.get(SAM_MEAT_INTAKE_REMOTE_TOKEN_ENV, "") or "").strip()
    if not expected:
        return jsonify(_sam_meat_intake_remote_denied("sam_meat_intake_remote_token_not_configured")), 503
    if len(expected) < SAM_MEAT_INTAKE_REMOTE_MIN_TOKEN_CHARS:
        return jsonify(_sam_meat_intake_remote_denied("sam_meat_intake_remote_token_too_short")), 503
    if not _sam_meat_intake_remote_token_matches(expected):
        return jsonify(_sam_meat_intake_remote_denied("sam_meat_intake_remote_auth_denied")), 403
    return None


def _require_meat_followup_send_access():
    if not _env_truthy(os.environ.get(MEAT_FOLLOWUP_SEND_ENABLED_ENV)):
        return jsonify(_meat_followup_send_denied("meat_followup_send_disabled")), 503

    expected = str(os.environ.get(MEAT_FOLLOWUP_SEND_TOKEN_ENV, "") or "").strip()
    if not expected:
        return jsonify(_meat_followup_send_denied("meat_followup_send_token_not_configured")), 503
    if len(expected) < MEAT_FOLLOWUP_SEND_MIN_TOKEN_CHARS:
        return jsonify(_meat_followup_send_denied("meat_followup_send_token_too_short")), 503
    if not _remote_token_matches(expected, "X-Amadeus-Meat-Followup-Send-Key"):
        return jsonify(_meat_followup_send_denied("meat_followup_send_auth_denied")), 403
    return None


def _sam_meat_intake_remote_token_matches(expected):
    return _remote_token_matches(expected, "X-Amadeus-Sam-Intake-Key")


def _remote_token_matches(expected, header_name):
    authorization = str(request.headers.get("Authorization", "") or "").strip()
    bearer_prefix = "Bearer "
    if authorization.startswith(bearer_prefix):
        return hmac.compare_digest(authorization[len(bearer_prefix):].strip(), expected)
    provided = str(request.headers.get(header_name, "") or "").strip()
    return hmac.compare_digest(provided, expected)


def _sam_meat_intake_remote_denied(status):
    return {
        "success": False,
        "status": status,
        "mode": "sam_meat_intake_remote_ingest",
        "route": "POST /api/oom-sakkie/channels/chatwoot/sam-meat-intake",
        "enabled_env": SAM_MEAT_INTAKE_REMOTE_ENABLED_ENV,
        "token_env": SAM_MEAT_INTAKE_REMOTE_TOKEN_ENV,
        "minimum_token_chars": SAM_MEAT_INTAKE_REMOTE_MIN_TOKEN_CHARS,
        "auth": "bearer_or_x_amadeus_sam_intake_key",
        "records_tracking_lead": False,
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_n8n": False,
        "creates_quote": False,
        "creates_order": False,
        "changes_stock": False,
        "financial_action": False,
    }


def _meat_followup_send_denied(status):
    return {
        "success": False,
        "status": status,
        "mode": "meat_followup_send_remote_consumer",
        "route": "POST /api/oom-sakkie/channels/chatwoot/sales-leads/<lead_id>/customer-followup-send",
        "enabled_env": MEAT_FOLLOWUP_SEND_ENABLED_ENV,
        "token_env": MEAT_FOLLOWUP_SEND_TOKEN_ENV,
        "minimum_token_chars": MEAT_FOLLOWUP_SEND_MIN_TOKEN_CHARS,
        "auth": "bearer_or_x_amadeus_meat_followup_send_key",
        "sent": False,
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_n8n": False,
        "creates_quote": False,
        "creates_order": False,
        "changes_stock": False,
        "financial_action": False,
    }


def _env_truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@oom_sakkie_bp.route("/oom-sakkie/management/morning-schedule", methods=["POST"])
def oom_sakkie_morning_schedule():
    expected = str(os.environ.get(MORNING_SCHEDULER_TOKEN_ENV) or "").strip()
    if len(expected) < 32 or not _remote_token_matches(
            expected, "X-Amadeus-Morning-Scheduler-Key"):
        return jsonify({"success": False, "status": "morning_scheduler_auth_denied",
                        "telegram_sends": 0, "telegram_edits": 0,
                        "hardware_commands": 0, "writes_farm_data": False}), 403
    payload = request.get_json(silent=True) or {}
    synthetic = str(payload.get("synthetic_acceptance_identity") or "").strip()
    result = (run_synthetic_acceptance(synthetic) if synthetic
              else run_provider_schedule())
    return jsonify(result), 200 if result.get("success") else 503


@oom_sakkie_bp.route("/oom-sakkie/management/protected-payment-recovery", methods=["POST"])
def oom_sakkie_protected_payment_recovery():
    expected = str(os.environ.get(MORNING_SCHEDULER_TOKEN_ENV) or "").strip()
    if len(expected) < 32 or not _remote_token_matches(
            expected, "X-Amadeus-Morning-Scheduler-Key"):
        return jsonify({"success": False, "status": "payment_recovery_auth_denied",
                        "telegram_sends": 0, "telegram_edits": 0,
                        "writes_to_supabase": False}), 403
    result = run_payment_recovery_cycle()
    status = 200 if result.get("success") else 503
    return jsonify(result), status


@oom_sakkie_bp.route("/oom-sakkie/management/general-manager-cycle", methods=["POST"])
def oom_sakkie_general_manager_cycle():
    expected = str(os.environ.get(MORNING_SCHEDULER_TOKEN_ENV) or "").strip()
    if len(expected) < 32 or not _remote_token_matches(
            expected, "X-Amadeus-Morning-Scheduler-Key"):
        return jsonify({"success": False, "status": "general_manager_auth_denied",
                        "telegram_sends": 0, "telegram_edits": 0,
                        "customer_sends": 0, "provider_actions": 0,
                        "hardware_commands": 0, "writes_farm_data": False}), 403
    result = run_general_manager_cycle(deliver=deliver_farm_manager_case)
    return jsonify(result), 200 if result.get("success") else 503


@oom_sakkie_bp.route("/oom-sakkie/management/beacon-publication-cycle", methods=["POST"])
def oom_sakkie_beacon_publication_cycle():
    expected = str(os.environ.get(MORNING_SCHEDULER_TOKEN_ENV) or "").strip()
    if len(expected) < 32 or not _remote_token_matches(
            expected, "X-Amadeus-Morning-Scheduler-Key"):
        return jsonify({"success": False, "status": "beacon_publication_worker_auth_denied",
                        "publishes": False, "meta_call": False}), 403
    result = run_protected_publication_cycle()
    return jsonify(result), 200 if result.get("success") else 503


@oom_sakkie_bp.route("/oom-sakkie/message", methods=["POST"])
def oom_sakkie_message():
    if not is_message_request_allowed(request.remote_addr):
        body, status_code = message_access_denied_response(request.remote_addr)
        return jsonify(body), status_code
    payload = request.get_json(silent=True) or {}
    result, status_code = handle_message(payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/channels/telegram/message", methods=["POST"])
def oom_sakkie_telegram_message():
    payload = request.get_json(silent=True) or {}
    result, status_code = handle_telegram_gateway_message(payload, headers=request.headers)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales/payment-preview", methods=["POST"])
def oom_sakkie_sale_payment_preview():
    denied = require_strict_owner_admin_access()
    if denied:
        return denied
    result, status_code = present_sale_payment_preview(request.get_json(silent=True) or {})
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/management/rootline/reassess", methods=["POST"])
def oom_sakkie_rootline_reassess():
    result, status_code = handle_rootline_reassessment_trigger(
        request.get_json(silent=True) or {}, headers=request.headers)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/management/rootline/physical-acceptance", methods=["POST"])
def oom_sakkie_rootline_physical_acceptance():
    denied = require_strict_owner_admin_access()
    if denied:
        return denied
    from modules.auth.owner_access import strict_owner_admin_principal
    result, status_code = attach_physical_acceptance(
        request.get_json(silent=True) or {},
        owner_principal=strict_owner_admin_principal(),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/channels/telegram/direct-webhook", methods=["POST"])
def oom_sakkie_telegram_direct_webhook():
    if not request.is_json:
        return jsonify({
            "success": False,
            "status": "telegram_json_content_type_required",
            "expected_content_type": "application/json",
            "download_attempted": False,
            "persistence_attempted": False,
            "sends_telegram": False,
            "writes": False,
        }), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload:
        return jsonify({
            "success": False,
            "status": "telegram_json_object_required",
            "download_attempted": False,
            "persistence_attempted": False,
            "sends_telegram": False,
            "writes": False,
        }), 400
    result, status_code = handle_telegram_direct_webhook(payload, headers=request.headers)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/channels/telegram/direct-parity", methods=["GET"])
def oom_sakkie_telegram_direct_parity():
    denied = _require_review_access()
    if denied:
        return denied
    return jsonify(telegram_direct_parity_report()), 200


@oom_sakkie_bp.route("/oom-sakkie/beacon/media-intakes", methods=["GET"])
def beacon_media_intakes():
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = list_media_intakes(limit=request.args.get("limit", 50))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/beacon/media-intakes/groups/<intake_group_id>/review", methods=["GET"])
def beacon_media_intake_group_review_packet(intake_group_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = private_album_review(intake_group_id)
    return jsonify(result), status_code


@oom_sakkie_bp.route(
    "/oom-sakkie/beacon/media-intakes/<binary_asset_id>/thumbnail",
    methods=["GET"],
)
def beacon_media_intake_thumbnail(binary_asset_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = read_private_thumbnail(
        binary_asset_id,
        token=request.args.get("token", ""),
        expires=request.args.get("expires", ""),
    )
    if status_code >= 400:
        return jsonify(result), status_code
    return Response(
        result["body"],
        status=200,
        content_type=result["content_type"],
        headers={
            "Cache-Control": result["cache_control"],
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )


@oom_sakkie_bp.route(
    "/oom-sakkie/beacon/media-intakes/<binary_asset_id>/review",
    methods=["POST"],
)
def beacon_media_intake_review(binary_asset_id):
    denied = require_owner_admin_access()
    if denied:
        return denied
    principal = owner_admin_principal()
    if not principal:
        return jsonify({
            "success": False,
            "status": "owner_identity_required",
            "publish": False,
            "public_use_approved": False,
        }), 403
    result, status_code = record_media_review(
        binary_asset_id,
        request.get_json(silent=True) or {},
        principal,
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route(
    "/oom-sakkie/beacon/media-intakes/groups/<intake_group_id>/review",
    methods=["POST"],
)
def beacon_media_intake_group_review(intake_group_id):
    denied = require_owner_admin_access()
    if denied:
        return denied
    principal = owner_admin_principal()
    if not principal:
        return jsonify({
            "success": False,
            "status": "owner_identity_required",
            "publish": False,
            "public_use_approved": False,
        }), 403
    binding,binding_status=canonical_media_group_owner_binding(intake_group_id)
    if binding_status>=400 or binding.get("success") is not True:
        return jsonify(binding),binding_status
    decision=request.get_json(silent=True) or {}
    decision={**decision,"subject_owner_principal":binding["owner_principal"],
        "subject_chat_hmac":binding["chat_hmac"]}
    result, status_code = record_media_group_review(
        intake_group_id, decision, binding["owner_principal"]
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/channels/telegram/exposure-preflight", methods=["GET"])
def oom_sakkie_telegram_exposure_preflight():
    denied = _require_review_access()
    if denied:
        return denied
    return jsonify(telegram_gateway_exposure_preflight()), 200


@oom_sakkie_bp.route("/oom-sakkie/tools", methods=["GET"])
def oom_sakkie_tools():
    denied = _require_review_access()
    if denied:
        return denied
    return jsonify({
        "success": True,
        "tools": list_tool_catalog(),
        "policy": {
            "channel": "kiosk",
            "max_risk_level": 0,
            "write_tools_enabled": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/sales-campaigns", methods=["GET"])
def oom_sakkie_sales_campaigns():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_sales_campaigns(limit=request.args.get("limit", 20))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-campaigns", methods=["POST"])
def oom_sakkie_sales_campaign_create():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_sales_campaign(payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-campaigns/<campaign_id>/events", methods=["POST"])
def oom_sakkie_sales_campaign_events(campaign_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_sales_campaign_event(campaign_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-campaigns/<campaign_id>/outreach-drafts", methods=["POST"])
def oom_sakkie_sales_campaign_outreach_draft_create(campaign_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_sales_outreach_draft_from_campaign(campaign_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-outreach-drafts", methods=["GET"])
def oom_sakkie_sales_outreach_drafts():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_sales_outreach_drafts(limit=request.args.get("limit", 20))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-outreach-drafts/<draft_id>/send-design-requests", methods=["POST"])
def oom_sakkie_sales_send_design_request_create(draft_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_sales_send_design_request_from_draft(draft_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-send-design-requests", methods=["GET"])
def oom_sakkie_sales_send_design_requests():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_sales_send_design_requests(limit=request.args.get("limit", 20))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-leads", methods=["GET"])
def oom_sakkie_sales_leads():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_sales_leads(
        limit=request.args.get("limit", 20),
        status_filter=request.args.get("status", ""),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-leads", methods=["POST"])
def oom_sakkie_sales_lead_create():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_sales_lead(payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-leads/sam-meat-intake", methods=["POST"])
def oom_sakkie_sam_meat_intake_create():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_sam_meat_intake_lead(payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/channels/chatwoot/sam-meat-intake", methods=["POST"])
def oom_sakkie_chatwoot_sam_meat_intake_create():
    denied = _require_sam_meat_intake_remote_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_sam_meat_intake_lead(payload)
    result["remote_ingest"] = {
        "enabled": True,
        "mode": "sam_meat_intake_tracking_only",
        "auth": "bearer_or_x_amadeus_sam_intake_key",
        "records_tracking_lead": True,
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_n8n": False,
        "creates_quote": False,
        "creates_order": False,
        "changes_stock": False,
        "financial_action": False,
    }
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-leads/<lead_id>/events", methods=["POST"])
def oom_sakkie_sales_lead_events(lead_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_sales_lead_event(lead_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-leads/<lead_id>/owner-money-path-approval", methods=["POST"])
def oom_sakkie_sales_lead_owner_money_path_approval(lead_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_owner_money_path_approval(lead_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-leads/<lead_id>/preorder-contract", methods=["GET"])
def oom_sakkie_sales_lead_preorder_contract(lead_id):
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = get_sales_lead_preorder_contract(lead_id)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-leads/<lead_id>/customer-followup-draft", methods=["GET"])
def oom_sakkie_sales_lead_customer_followup_draft(lead_id):
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = get_sales_lead_customer_followup_draft(lead_id)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-leads/<lead_id>/customer-followup-send-design", methods=["GET"])
def oom_sakkie_sales_lead_customer_followup_send_design(lead_id):
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = get_sales_lead_customer_followup_send_design(lead_id)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/sales-leads/<lead_id>/customer-followup-send-approval", methods=["POST"])
def oom_sakkie_sales_lead_customer_followup_send_approval(lead_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_customer_followup_send_approval(lead_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/channels/chatwoot/sales-leads/<lead_id>/customer-followup-send", methods=["POST"])
def oom_sakkie_chatwoot_sales_lead_customer_followup_send(lead_id):
    denied = _require_meat_followup_send_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = send_customer_followup_to_chatwoot(lead_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/policy", methods=["GET"])
def oom_sakkie_policy():
    denied = _require_review_access()
    if denied:
        return denied
    return jsonify(get_runtime_policy()), 200


@oom_sakkie_bp.route("/oom-sakkie/voice/transcribe", methods=["POST"])
def oom_sakkie_voice_transcribe():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = transcribe_oom_sakkie_voice_audio(request.files.get("audio"))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/specialists", methods=["GET"])
def oom_sakkie_specialists():
    denied = _require_review_access()
    if denied:
        return denied
    return jsonify({
        "success": True,
        "status": "planned_only",
        "delegation_enabled": False,
        "autonomous_loops_enabled": False,
        "specialists": list_specialist_manifests(),
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agents", methods=["GET"])
def oom_sakkie_agents():
    denied = _require_review_access()
    if denied:
        return denied
    return jsonify(get_agent_runtime_status()), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/contracts", methods=["GET"])
def oom_sakkie_agent_contracts():
    denied = _require_review_access()
    if denied:
        return denied
    contracts = get_agent_operating_contracts()
    return jsonify({
        **contracts,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/preflight", methods=["GET"])
def oom_sakkie_agent_preflight():
    denied = _require_review_access()
    if denied:
        return denied
    preflight = get_agent_activation_preflight()
    return jsonify({
        **preflight,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/authority-matrix", methods=["GET"])
def oom_sakkie_agent_authority_matrix():
    denied = _require_review_access()
    if denied:
        return denied
    matrix = get_agent_authority_matrix()
    return jsonify({
        **matrix,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/unlock-readiness", methods=["GET"])
def oom_sakkie_agent_unlock_readiness():
    denied = _require_review_access()
    if denied:
        return denied
    readiness = get_agent_authority_unlock_readiness()
    return jsonify({
        **readiness,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/dispatch-rail-blueprint", methods=["GET"])
def oom_sakkie_agent_dispatch_rail_blueprint():
    denied = _require_review_access()
    if denied:
        return denied
    blueprint = get_agent_dispatch_decision_rail_blueprint()
    return jsonify({
        **blueprint,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/runtime-review-packet", methods=["GET"])
def oom_sakkie_agent_runtime_review_packet():
    denied = _require_runtime_review_packet_access()
    if denied:
        return denied
    packet = get_agent_runtime_review_packet()
    return jsonify({
        **packet,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/recommend", methods=["POST"])
def oom_sakkie_agent_recommend():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    return jsonify(recommend_agent_for_text(payload.get("text") or "")), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/activation-plan", methods=["GET"])
def oom_sakkie_agent_activation_plan():
    denied = _require_review_access()
    if denied:
        return denied
    learning = accepted_agent_learning_snapshot(limit=request.args.get("limit", 20))
    return jsonify({
        "success": learning["status_code"] == 200,
        "mode": "agent_activation_plan_panel",
        "activation_plan": get_agent_activation_plan(),
        "accepted_learning": learning["evidence"],
        "accepted_learning_count": learning["accepted_count"],
        "accepted_by_specialist": learning.get("accepted_by_specialist", {}),
        "accepted_learning_status": learning["status"],
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200 if learning["status_code"] == 200 else 503


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-runs", methods=["GET"])
def oom_sakkie_agent_dry_runs():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_agent_dry_run_requests(limit=request.args.get("limit", 20))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-runs", methods=["POST"])
def oom_sakkie_agent_dry_run_create():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_agent_dry_run_request(payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-runs/<dry_run_request_id>/events", methods=["POST"])
def oom_sakkie_agent_dry_run_events(dry_run_request_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_agent_dry_run_event(dry_run_request_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-runs/handoff", methods=["POST"])
def oom_sakkie_agent_dry_run_handoff():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    dry_run_request_id = str(payload.get("dry_run_request_id") or "").strip()
    loaded, load_status = get_agent_dry_run_request(dry_run_request_id)
    if load_status != 200:
        return jsonify(loaded), load_status
    dry_run_request = loaded.get("dry_run_request", {})
    result, status_code = build_agent_dry_run_handoff(dry_run_request)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-runs/<dry_run_request_id>/results", methods=["POST"])
def oom_sakkie_agent_dry_run_result_create(dry_run_request_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_agent_dry_run_result(dry_run_request_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-run-results", methods=["GET"])
def oom_sakkie_agent_dry_run_results():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_agent_dry_run_results(
        dry_run_request_id=request.args.get("dry_run_request_id", "").strip(),
        limit=request.args.get("limit", 20),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-run-results/<dry_run_result_id>/events", methods=["POST"])
def oom_sakkie_agent_dry_run_result_events(dry_run_result_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_agent_dry_run_result_event(dry_run_result_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-run-results/<dry_run_result_id>/review-packet", methods=["GET"])
def oom_sakkie_agent_dry_run_result_review_packet(dry_run_result_id):
    denied = _require_review_access()
    if denied:
        return denied
    loaded, load_status = get_agent_dry_run_result(dry_run_result_id)
    if load_status != 200:
        return jsonify(loaded), load_status
    dry_run_result = loaded.get("dry_run_result", {})
    result, status_code = build_agent_dry_run_result_review_packet(dry_run_result)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/influence-proposals", methods=["GET"])
def oom_sakkie_learning_influence_proposals():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_learning_influence_proposals(limit=request.args.get("limit", 20))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/influence-proposals/from-accepted", methods=["POST"])
def oom_sakkie_learning_influence_proposals_from_accepted():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_learning_influence_proposals_from_accepted(limit=payload.get("limit", 20))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/influence-proposals/from-result", methods=["POST"])
def oom_sakkie_learning_influence_proposal_from_result():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_learning_influence_proposal_from_result(payload.get("source_result_id", ""))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/influence-proposals/<proposal_id>/events", methods=["POST"])
def oom_sakkie_learning_influence_proposal_events(proposal_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_learning_influence_proposal_event(proposal_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/consumption-readiness", methods=["GET"])
def oom_sakkie_learning_influence_consumption_readiness():
    denied = _require_review_access()
    if denied:
        return denied
    readiness = get_learning_influence_consumption_readiness()
    return jsonify({
        **readiness,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/consumption-audit-rail-blueprint", methods=["GET"])
def oom_sakkie_learning_influence_consumption_audit_rail_blueprint():
    denied = _require_review_access()
    if denied:
        return denied
    blueprint = get_learning_influence_consumption_audit_rail_blueprint()
    return jsonify({
        **blueprint,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/consumer-design-packet", methods=["GET"])
def oom_sakkie_learning_influence_consumer_design_packet():
    denied = _require_review_access()
    if denied:
        return denied
    design_packet = get_learning_influence_consumer_design_packet()
    return jsonify({
        **design_packet,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/consumption-requests", methods=["GET"])
def oom_sakkie_learning_influence_consumption_requests():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_learning_influence_consumption_requests(limit=request.args.get("limit", 20))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/consumption-requests", methods=["POST"])
def oom_sakkie_learning_influence_consumption_request_create():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_learning_influence_consumption_request(payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/consumption-requests/<consumption_request_id>/events", methods=["POST"])
def oom_sakkie_learning_influence_consumption_request_events(consumption_request_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_learning_influence_consumption_event(consumption_request_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/consumption-requests/<consumption_request_id>/review-note-artifact", methods=["POST"])
def oom_sakkie_learning_influence_consumption_review_note_artifact(consumption_request_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = produce_learning_influence_review_note_artifact(consumption_request_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/review-packet", methods=["GET"])
def oom_sakkie_review_packet():
    denied = _require_review_access()
    if denied:
        return denied
    review_summary, review_status = get_trace_review_summary(
        channel=request.args.get("channel", "kiosk").strip(),
        days=request.args.get("days", 14),
    )
    recent_traces, traces_status = list_recent_traces(
        limit=request.args.get("limit", 12),
        channel=request.args.get("channel", "kiosk").strip(),
        review=request.args.get("review", "all").strip(),
        search=request.args.get("q", "").strip(),
    )
    return jsonify({
        "success": review_status == 200 and traces_status == 200,
        "policy": get_runtime_policy(),
        "tools": list_tool_catalog(),
        "specialists": list_specialist_manifests(),
        "agent_runtime": get_agent_runtime_status(),
        "review_summary": review_summary,
        "recent_traces": recent_traces,
        "statuses": {
            "review_summary": review_status,
            "recent_traces": traces_status,
        },
    }), max(review_status, traces_status)


@oom_sakkie_bp.route("/oom-sakkie/review-advisor", methods=["GET"])
def oom_sakkie_review_advisor():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = get_review_advisor(
        channel=request.args.get("channel", "kiosk").strip(),
        days=request.args.get("days", 14),
        limit=request.args.get("limit", 12),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/learning-advisor", methods=["GET"])
def oom_sakkie_learning_advisor():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = get_learning_advisor(
        channel=request.args.get("channel", "kiosk").strip(),
        days=request.args.get("days", 14),
        limit=request.args.get("limit", 12),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/learning-advisor/analyze", methods=["POST"])
def oom_sakkie_learning_advisor_analyze():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = run_learning_analysis(
        channel=str(payload.get("channel") or "kiosk").strip(),
        days=payload.get("days", 14),
        limit=payload.get("limit", 12),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/learning-advisor/build-packet", methods=["POST"])
def oom_sakkie_learning_advisor_build_packet():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    proposal = payload.get("proposal") if isinstance(payload, dict) else {}
    result, status_code = build_learning_packet(proposal)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/learning-advisor/implementation-queue", methods=["GET"])
def oom_sakkie_learning_advisor_implementation_queue():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = get_implementation_queue(
        channel=request.args.get("channel", "kiosk").strip(),
        days=request.args.get("days", 14),
        limit=request.args.get("limit", 12),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/learning-advisor/approve-build", methods=["POST"])
def oom_sakkie_learning_advisor_approve_build():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    packet = payload.get("packet") if isinstance(payload, dict) else {}
    result, status_code = approve_build_request(
        packet,
        approved_by=str(payload.get("approved_by") or "owner").strip()[:80],
    )
    if status_code == 200:
        store_result, store_status = record_build_request(result)
        result["build_request_store"] = store_result
        if store_status < 500 and store_result.get("stored"):
            event_result, _event_status = record_build_request_event(
                result.get("build_request_id", ""),
                {
                    "event_type": "approved",
                    "notes": "Approved from Oom Sakkie kiosk.",
                    "recorded_by": result.get("approved_by", "owner"),
                },
            )
            result["build_request_event"] = event_result
        if store_status >= 500:
            status_code = store_status
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/build-requests", methods=["GET"])
def oom_sakkie_build_requests():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_build_requests(limit=request.args.get("limit", 20))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/build-requests/<build_request_id>/events", methods=["POST"])
def oom_sakkie_build_request_events(build_request_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_build_request_event(build_request_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/build-requests/forge-handoff", methods=["POST"])
def oom_sakkie_build_request_forge_handoff():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    build_request_id = str(payload.get("build_request_id") or "").strip()
    loaded, load_status = get_build_request(build_request_id)
    if load_status != 200:
        return jsonify(loaded), load_status
    build_request = loaded.get("build_request", {})
    result, status_code = build_forge_handoff(build_request)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/build-requests/<build_request_id>/patch-proposals", methods=["POST"])
def oom_sakkie_patch_proposal_create(build_request_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_patch_proposal(build_request_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/patch-proposals", methods=["GET"])
def oom_sakkie_patch_proposals():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_patch_proposals(
        build_request_id=request.args.get("build_request_id", "").strip(),
        limit=request.args.get("limit", 20),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/patch-proposals/<patch_proposal_id>/events", methods=["POST"])
def oom_sakkie_patch_proposal_events(patch_proposal_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_patch_proposal_event(patch_proposal_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/patch-proposals/<patch_proposal_id>/deploy-decisions", methods=["POST"])
def oom_sakkie_deploy_decision_create(patch_proposal_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_deploy_decision(patch_proposal_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/deploy-decisions", methods=["GET"])
def oom_sakkie_deploy_decisions():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_deploy_decisions(
        patch_proposal_id=request.args.get("patch_proposal_id", "").strip(),
        limit=request.args.get("limit", 20),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/dispatch-requests", methods=["GET"])
def oom_sakkie_dispatch_requests():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_dispatch_requests(limit=request.args.get("limit", 20))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/dispatch-requests", methods=["POST"])
def oom_sakkie_dispatch_request_create():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_dispatch_request(payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/dispatch-requests/<dispatch_request_id>/decisions", methods=["POST"])
def oom_sakkie_dispatch_decision_create(dispatch_request_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_dispatch_decision(dispatch_request_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/dispatch-requests/<dispatch_request_id>/execution-approvals", methods=["POST"])
def oom_sakkie_dispatch_execution_approval_create(dispatch_request_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_dispatch_execution_approval(dispatch_request_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/dispatch-execution-approvals", methods=["GET"])
def oom_sakkie_dispatch_execution_approvals():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_dispatch_execution_approvals(
        dispatch_request_id=request.args.get("dispatch_request_id", "").strip(),
        limit=request.args.get("limit", 20),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/dispatch-execution-approvals/<approval_id>/events", methods=["POST"])
def oom_sakkie_dispatch_execution_approval_events(approval_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_dispatch_execution_approval_event(approval_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/dispatch-execution-approvals/<approval_id>/run-sentinel-dry-run", methods=["POST"])
def oom_sakkie_sentinel_single_shot_dry_run(approval_id):
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = run_sentinel_single_shot_dry_run(approval_id)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/traces", methods=["GET"])
def oom_sakkie_traces():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_recent_traces(
        limit=request.args.get("limit", 20),
        channel=request.args.get("channel", "").strip(),
        review=request.args.get("review", "all").strip(),
        search=request.args.get("q", "").strip(),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/traces/review-summary", methods=["GET"])
def oom_sakkie_trace_review_summary():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = get_trace_review_summary(
        channel=request.args.get("channel", "").strip(),
        days=request.args.get("days", 14),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/traces/<trace_id>/feedback", methods=["POST"])
def oom_sakkie_trace_feedback(trace_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_trace_feedback(trace_id, payload)
    return jsonify(result), status_code
