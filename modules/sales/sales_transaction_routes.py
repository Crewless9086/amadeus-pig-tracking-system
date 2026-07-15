import ipaddress
import os

from flask import Blueprint, jsonify, request
from modules.auth.owner_access import (
    owner_session_is_valid,
    require_owner_admin_access,
    require_owner_read_access,
)
from modules.beacon.campaign_calendar import (
    approve_rule_version,
    prepare_calendar_entry,
    propose_rule_version,
    revoke_rule_version,
)

from modules.oom_sakkie.sales_campaign_store import (
    create_draft_order_from_sales_lead,
    get_sales_lead_pricing_estimate,
    get_sales_lead_customer_followup_draft,
    get_sales_lead_preorder_contract,
    list_meat_price_book_entries,
    list_sales_leads,
    record_sales_lead_event,
    record_meat_price_book_entry,
    record_customer_booking_confirmation,
    record_customer_followup_send_approval,
    record_owner_money_path_approval,
    send_customer_followup_to_chatwoot,
)
from modules.sales.sales_transaction_cancel import cancel_sales_transaction
from modules.sales.sales_transaction_create import create_sales_transaction
from modules.sales.sales_transaction_dry_run import dry_run_sales_transaction
from modules.sales.sales_transaction_lifecycle import (
    confirm_slaughter_pig_exits,
    reconcile_closed_slaughter_pig_exits,
)
from modules.sales.sales_transaction_read import get_sales_transaction, list_sales_transactions
from modules.sales.sales_transaction_update import update_slaughter_sale_payment
from modules.sales.meat_match_engine import get_sales_lead_meat_match
from modules.sales.butcher_truth_board import get_butcher_truth_board
from modules.sales.meat_fulfillment import (
    approve_meat_journey_notification,
    build_dad_booking_packet,
    build_meat_journey_notification_draft,
    get_meat_fulfillment_timeline,
    list_meat_driver_route,
    record_meat_driver_delivery_event,
    record_meat_fulfillment_event,
    send_meat_journey_notification,
)
from modules.sales.meat_ops import (
    approve_meat_instruction_draft,
    build_meat_instruction_drafts,
    create_carcass_reservation_from_lead,
    get_meat_payment_gate,
    get_meat_ops_status,
    record_carcass_reservation_event,
    record_meat_deposit_event,
    record_meat_instruction_exception,
    send_approved_meat_instruction,
)
from modules.sales.meat_reconciliation import (
    get_meat_reconciliation_status,
    record_meat_reconciliation_event,
)
from modules.sales.meat_documents import (
    authorize_meat_document_delivery_webhook,
    build_meat_estimated_quote_packet,
    generate_meat_deposit_pro_forma_pdf,
    generate_meat_estimated_quote_pdf,
    generate_meat_final_invoice_pdf,
    handle_meat_document_delivery_status_webhook,
    meat_document_delivery_webhook_policy,
    meat_document_policy,
    send_meat_estimated_quote_to_chatwoot,
)
from modules.sales.meat_pilot_readiness import get_meat_pilot_readiness
from modules.sales.meat_production import (
    create_meat_processing_batch,
    get_meat_processing_batch,
    list_meat_processing_batches,
    record_meat_processing_cost,
    record_meat_processing_event,
    record_meat_processing_output,
)
from modules.sales.meat_template_pack import meat_whatsapp_template_pack
from modules.sales.sam_meat_runtime import (
    authorize_sam_meat_webhook,
    handle_sam_meat_chatwoot_inbound,
    sam_meat_webhook_policy,
)
from modules.sales.sam_live_stock_runtime import (
    authorize_sam_live_stock_webhook,
    build_sam_live_stock_resolved_cleanup_packet,
    handle_sam_live_stock_chatwoot_inbound,
    parse_chatwoot_inbound as parse_sam_live_stock_chatwoot_inbound,
    review_sam_live_stock_conversation,
    sam_live_stock_webhook_policy,
    send_owner_approved_live_stock_reply,
)
from modules.sales.sam_live_stock_launch_control import (
    _telegram_send_message,
    apply_sam_live_stock_chatwoot_takeover,
    build_live_stock_reservation_plan,
    build_sam_live_stock_launch_readiness,
    build_sam_live_stock_review_event,
    delete_sam_live_stock_telegram_escalation,
    execute_live_stock_order_reservation,
    get_latest_sam_live_stock_review_event_for_conversation,
    list_sam_live_stock_open_intakes,
    process_sam_live_stock_owner_callback,
    record_sam_live_stock_review_event,
    sam_live_stock_launch_control_policy,
    send_sam_live_stock_new_lead_telegram,
    send_sam_live_stock_owner_review_telegram,
    send_sam_live_stock_telegram_escalation,
)
from modules.sales.sam_live_stock_graduation import notify_new_graduation_candidates
from modules.sales.sam_command_state import get_sam_command_state
from modules.sales.sam_farm_knowledge import load_sam_farm_knowledge
from modules.sales.sam_pricing import (
    list_live_stock_price_entries,
    record_live_stock_price_entry,
)
from modules.sales.conversation_learning import (
    build_live_stock_owner_reply_learning_event,
    build_owner_review_learning_event,
    list_sales_conversation_learning_events,
    record_sales_conversation_learning_event,
    live_stock_learning_scorecard,
)
from modules.sales.beacon_campaign import (
    build_beacon_campaign_publish_packet,
    build_beacon_campaign_selection,
    build_beacon_facebook_image_launch_packet,
    build_beacon_weekly_command_brief,
    execute_beacon_facebook_page_post,
    facebook_posting_policy,
    list_beacon_campaign_performance_events,
    list_beacon_facebook_post_execution_events,
    list_beacon_manual_post_evidence,
    prepare_beacon_owner_decision,
    record_beacon_campaign_performance_event,
    record_beacon_manual_post_evidence,
)
from modules.sales.beacon_facebook_history import import_beacon_facebook_history
from modules.beacon.post_composer import build_beacon_caption_suggestions
from modules.beacon.media_library import (
    beacon_media_storage_policy,
    list_beacon_media_assets,
    record_beacon_media_asset_event,
    register_beacon_media_asset,
    upload_beacon_media_asset,
)
from modules.beacon.marketing_operating_contract import build_beacon_marketing_operating_contract
from modules.beacon.opportunity_scanner import build_beacon_opportunity_cards
from modules.beacon.creative_providers import ALLOWED_CREATIVE_PROVIDERS, DISABLED_PROVIDER_FLAGS
from modules.beacon.creative_studio import create_mock_creative_job, record_creative_review


sales_bp = Blueprint("sales", __name__)


@sales_bp.route("/sales/meat-production/batches", methods=["GET", "POST"])
def meat_processing_batches():
    if request.method == "GET":
        denied = require_owner_read_access()
        if denied:
            return denied
        result, status_code = list_meat_processing_batches()
    else:
        denied = require_owner_admin_access()
        if denied:
            return denied
        result, status_code = create_meat_processing_batch(request.get_json(silent=True) or {})
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-production/batches/<batch_id>", methods=["GET"])
def meat_processing_batch_detail(batch_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = get_meat_processing_batch(batch_id)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-production/batches/<batch_id>/events", methods=["POST"])
def meat_processing_batch_event(batch_id):
    denied = require_owner_admin_access()
    if denied:
        return denied
    result, status_code = record_meat_processing_event(batch_id, request.get_json(silent=True) or {})
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-production/batches/<batch_id>/costs", methods=["POST"])
def meat_processing_batch_cost(batch_id):
    denied = require_owner_admin_access()
    if denied:
        return denied
    result, status_code = record_meat_processing_cost(batch_id, request.get_json(silent=True) or {})
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-production/batches/<batch_id>/outputs", methods=["POST"])
def meat_processing_batch_output(batch_id):
    denied = require_owner_admin_access()
    if denied:
        return denied
    result, status_code = record_meat_processing_output(batch_id, request.get_json(silent=True) or {})
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-production/butcher-board/<lead_id>", methods=["GET"])
def butcher_truth_board(lead_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = get_butcher_truth_board(lead_id)
    return jsonify(result), status_code


@sales_bp.route('/sales/beacon/opportunities', methods=['GET'])
def beacon_opportunity_cards():
    denied = require_owner_read_access()
    if denied:
        return denied
    return jsonify(build_beacon_opportunity_cards()), 200


def _env_truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _require_owner_meat_money_path_access():
    return require_owner_read_access()


def _sam_command_state_access_allowed(remote_addr, headers):
    try:
        address = ipaddress.ip_address(str(remote_addr or "").strip())
    except ValueError:
        return False
    if address.is_loopback:
        return True
    if owner_session_is_valid("read"):
        return True
    expected = str(os.getenv("SAM_COMMAND_STATE_OWNER_TOKEN", "") or "").strip()
    if len(expected) < 32:
        return False
    provided = str((headers or {}).get("X-Sam-Command-State-Token") or "").strip()
    auth = str((headers or {}).get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        provided = auth[7:].strip()
    return provided == expected


def _sam_command_state_access_denied(remote_addr):
    return {
        "ok": False,
        "success": False,
        "status": "sam_command_state_access_denied",
        "message": "SAM command-state is owner/local read-only.",
        "remote_addr": str(remote_addr or ""),
    }, 403


def _text_contains_test_marker(*values):
    joined = " ".join(str(value or "") for value in values).lower()
    return "test flow" in joined or "delete after test" in joined or "codex-smoke" in joined


def _lead_is_test_flow(lead):
    lead = lead if isinstance(lead, dict) else {}
    interest = lead.get("interest") if isinstance(lead.get("interest"), dict) else {}
    events = lead.get("events") if isinstance(lead.get("events"), list) else []
    event_text = " ".join(
        f"{event.get('event_type', '')} {event.get('notes', '')}"
        for event in events
        if isinstance(event, dict)
    )
    return _text_contains_test_marker(
        lead.get("lead_label"),
        lead.get("contact_label"),
        lead.get("chatwoot_conversation_id"),
        interest.get("notes"),
        interest.get("message"),
        event_text,
    )


@sales_bp.route("/sales-transactions", methods=["GET"])
def sales_transaction_list():
    try:
        result, status_code = list_sales_transactions(
            sale_stream=request.args.get("sale_stream", ""),
            limit=request.args.get("limit", 50),
        )
        return jsonify(result), status_code
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)],
            "source": {
                "source": "supabase",
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }), 400


@sales_bp.route("/sales-transactions", methods=["POST"])
def sales_transaction_create():
    payload = request.get_json(silent=True) or {}
    result, status_code = create_sales_transaction(payload)
    return jsonify(result), status_code


@sales_bp.route("/sales-transactions/<sale_id>", methods=["GET"])
def sales_transaction_detail(sale_id):
    try:
        result, status_code = get_sales_transaction(sale_id)
        return jsonify(result), status_code
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)],
            "source": {
                "source": "supabase",
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }), 400


@sales_bp.route("/sales-transactions/<sale_id>/cancel", methods=["POST"])
def sales_transaction_cancel(sale_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = cancel_sales_transaction(sale_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales-transactions/<sale_id>/payment", methods=["PATCH"])
def sales_transaction_payment_update(sale_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = update_slaughter_sale_payment(sale_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales-transactions/<sale_id>/confirm-pig-exits", methods=["POST"])
def sales_transaction_confirm_pig_exits(sale_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = confirm_slaughter_pig_exits(sale_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales-transactions/<sale_id>/reconcile-pig-exits", methods=["POST"])
def sales_transaction_reconcile_pig_exits(sale_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = reconcile_closed_slaughter_pig_exits(sale_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales-transactions/dry-run", methods=["POST"])
def sales_transaction_dry_run():
    payload = request.get_json(silent=True) or {}
    result, status_code = dry_run_sales_transaction(payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/channels/chatwoot/sam-meat/policy", methods=["GET"])
def sam_meat_chatwoot_policy():
    return jsonify({
        "success": True,
        "policy": sam_meat_webhook_policy(),
    }), 200


@sales_bp.route("/sales/sam-farm-knowledge", methods=["GET"])
def sam_farm_knowledge_route():
    return jsonify(load_sam_farm_knowledge()), 200


@sales_bp.route("/sales/meat-documents/policy", methods=["GET"])
def meat_documents_policy_route():
    return jsonify(meat_document_policy()), 200


@sales_bp.route("/sales/meat-whatsapp-templates", methods=["GET"])
def meat_whatsapp_templates_route():
    return jsonify(meat_whatsapp_template_pack()), 200


@sales_bp.route("/sales/meat-pilot-readiness", methods=["GET"])
def meat_pilot_readiness_route():
    result, status_code = get_meat_pilot_readiness(
        limit=request.args.get("limit", 12),
        status_filter=request.args.get("status", "launch_test"),
    )
    return jsonify(result), status_code


@sales_bp.route("/sales/channels/chatwoot/meat-documents/delivery-status/policy", methods=["GET"])
def meat_document_delivery_status_policy_route():
    return jsonify(meat_document_delivery_webhook_policy()), 200


@sales_bp.route("/sales/channels/chatwoot/sam-meat/inbound", methods=["POST"])
def sam_meat_chatwoot_inbound():
    allowed, denied = authorize_sam_meat_webhook(request.headers, request.args)
    if not allowed:
        status_code = 403 if denied.get("status") == "sam_meat_backend_webhook_auth_denied" else 503
        return jsonify(denied), status_code
    payload = request.get_json(silent=True) or {}
    try:
        result, status_code = handle_sam_meat_chatwoot_inbound(payload)
        if result.get("status") == "sam_meat_live_stock_handoff":
            live_result, live_status_code = handle_sam_live_stock_chatwoot_inbound(payload)
            _attach_sam_live_stock_review_event(live_result, payload)
            result["sam_live_stock_handoff"] = {
                "status_code": live_status_code,
                "status": live_result.get("status"),
                "processed": live_result.get("processed") is True,
                "sent": live_result.get("sent") is True,
                "sam_decision": live_result.get("sam_decision") if isinstance(live_result.get("sam_decision"), dict) else {},
                "conversation_review_event": live_result.get("conversation_review_event") if isinstance(live_result.get("conversation_review_event"), dict) else {},
                "policy": live_result.get("policy") if isinstance(live_result.get("policy"), dict) else {},
            }
    except Exception as exc:
        result, status_code = {
            "success": False,
            "status": "sam_meat_inbound_unhandled_exception",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "processed": False,
            "sent": False,
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "creates_quote": False,
            "creates_order": False,
            "changes_stock": False,
        }, 500
    return jsonify(result), status_code


def _attach_sam_live_stock_review_event(result, raw_payload):
    if not result.get("processed") or not isinstance(result.get("sam_decision"), dict):
        return
    decision = result["sam_decision"]
    review = decision.get("conversation_review") if isinstance(decision.get("conversation_review"), dict) else {}
    event = build_sam_live_stock_review_event(
        decision.get("inbound") if isinstance(decision.get("inbound"), dict) else raw_payload,
        decision.get("facts") if isinstance(decision.get("facts"), dict) else {},
        decision,
        review,
        event_source="sam_meat_internal_live_stock_handoff",
    )
    learning_result, learning_status = record_sam_live_stock_review_event(event)
    notification_result = _send_sam_live_stock_owner_notification_if_needed(event, learning_result)
    result["conversation_review_event"] = {
        "status": learning_result.get("status"),
        "status_code": learning_status,
        "review_event_id": learning_result.get("review_event_id") or event.get("review_event_id"),
        "recorded": learning_result.get("success") is True,
        "conversation_event_count": learning_result.get("conversation_event_count"),
        "owner_notification": notification_result,
    }


def _send_sam_live_stock_owner_notification_if_needed(event, learning_result):
    if not learning_result.get("success"):
        return {"attempted": False, "status": "review_event_not_recorded"}
    if learning_result.get("created") is False:
        return {
            "attempted": False,
            "status": "review_event_already_recorded_no_duplicate_telegram",
            "review_event_id": learning_result.get("review_event_id"),
        }
    decision = event.get("decision_json") if isinstance(event.get("decision_json"), dict) else {}
    review = event.get("review_json") if isinstance(event.get("review_json"), dict) else {}
    packet = decision.get("escalation_packet") if isinstance(decision.get("escalation_packet"), dict) else {}
    if packet and review.get("escalation_required"):
        sent, status_code = send_sam_live_stock_telegram_escalation(packet)
        return {"attempted": True, "type": "escalation", "status_code": status_code, "status": sent.get("status"), "sent": sent.get("success") is True}
    if _sam_live_stock_owner_review_notification_needed(event):
        sent, status_code = send_sam_live_stock_owner_review_telegram(event)
        return {"attempted": True, "type": "owner_review", "status_code": status_code, "status": sent.get("status"), "sent": sent.get("success") is True}
    if int(learning_result.get("conversation_event_count") or 0) == 1:
        sent, status_code = send_sam_live_stock_new_lead_telegram(event)
        return {"attempted": True, "type": "new_lead", "status_code": status_code, "status": sent.get("status"), "sent": sent.get("success") is True}
    return {"attempted": False, "status": "not_new_or_escalation"}


def _sam_live_stock_owner_review_notification_needed(event):
    if not isinstance(event, dict):
        return False
    if event.get("no_reply_recommended") or event.get("escalation_required"):
        return False
    reply = str(event.get("sam_reply_excerpt") or "").strip()
    action = str(event.get("recommended_action") or "").strip()
    return bool(reply and action == "owner_review_send_candidate")


@sales_bp.route("/sales/channels/chatwoot/sam-live-stock/policy", methods=["GET"])
def sam_live_stock_chatwoot_policy():
    return jsonify({
        "success": True,
        "policy": sam_live_stock_webhook_policy(),
        "launch_control": sam_live_stock_launch_control_policy(),
    }), 200


@sales_bp.route("/sales/channels/chatwoot/sam-live-stock/inbound", methods=["POST"])
def sam_live_stock_chatwoot_inbound():
    allowed, denied = authorize_sam_live_stock_webhook(request.headers, request.args)
    if not allowed:
        status_code = 403 if denied.get("status") == "sam_live_stock_backend_webhook_auth_denied" else 503
        return jsonify(denied), status_code
    payload = request.get_json(silent=True) or {}
    owner_reply_capture = _capture_sam_live_stock_owner_reply_if_needed(payload)
    if owner_reply_capture.get("attempted"):
        return jsonify(owner_reply_capture), owner_reply_capture.get("status_code", 200)
    try:
        result, status_code = handle_sam_live_stock_chatwoot_inbound(payload)
    except Exception as exc:
        result, status_code = {
            "success": False,
            "status": "sam_live_stock_inbound_unhandled_exception",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "processed": False,
            "sent": False,
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "creates_order": False,
            "changes_stock": False,
            "reserves_stock": False,
        }, 500
    if result.get("processed") and isinstance(result.get("sam_decision"), dict):
        _attach_sam_live_stock_review_event(result, payload)
    return jsonify(result), status_code


def _capture_sam_live_stock_owner_reply_if_needed(payload):
    inbound = parse_sam_live_stock_chatwoot_inbound(payload)
    if inbound.get("message_type") != "outgoing" or not inbound.get("content") or not inbound.get("conversation_id"):
        return {"attempted": False, "captured": False, "status": "not_outgoing_owner_reply"}
    if _truthy_payload_value((payload or {}).get("private")):
        return _owner_reply_capture_skipped("private_note_skipped", inbound)
    if _is_sam_live_stock_send_echo(payload):
        return _owner_reply_capture_skipped("sam_live_stock_send_echo_skipped", inbound)
    latest, latest_status = get_latest_sam_live_stock_review_event_for_conversation(inbound.get("conversation_id"))
    latest_event = latest.get("event") if latest.get("success") and isinstance(latest.get("event"), dict) else {}
    event = build_live_stock_owner_reply_learning_event({
        **inbound,
        "message_id": str((payload or {}).get("id") or (payload or {}).get("message_id") or ""),
        "created_at": str((payload or {}).get("created_at") or (payload or {}).get("timestamp") or ""),
    }, latest_event)
    learning, learning_status = record_sales_conversation_learning_event(event)
    graduation_notification = {"attempted": False, "status": "learning_event_not_created"}
    if learning.get("success") and int(learning.get("created_count") or 0):
        try:
            graduation_notification = notify_new_graduation_candidates(
                scorecard_loader=lambda: live_stock_learning_scorecard(limit=500),
                event_recorder=record_sales_conversation_learning_event,
                telegram_sender=_telegram_send_message,
            )
        except Exception as exc:
            graduation_notification = {
                "success": False,
                "attempted": True,
                "status": "graduation_notification_failed_safely",
                "error_type": exc.__class__.__name__,
                "auto_send_enabled": False,
                "sends_customer_message": False,
            }
    return {
        "success": learning.get("success") is True,
        "attempted": True,
        "captured": learning.get("success") is True,
        "status": learning.get("status"),
        "status_code": 200,
        "learning_status_code": learning_status,
        "latest_review_status": latest.get("status"),
        "latest_review_status_code": latest_status,
        "learning_event_id": learning.get("learning_event_id", ""),
        "graduation_notification": graduation_notification,
        "chatwoot_conversation_id": inbound.get("conversation_id"),
        "source": "sam_live_stock_owner_reply_capture",
        "processed": False,
        "sent": False,
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "creates_order": False,
        "changes_stock": False,
        "reserves_stock": False,
    }


def _owner_reply_capture_skipped(status, inbound):
    return {
        "success": True,
        "attempted": True,
        "captured": False,
        "status": status,
        "status_code": 200,
        "chatwoot_conversation_id": inbound.get("conversation_id"),
        "source": "sam_live_stock_owner_reply_capture",
        "processed": False,
        "sent": False,
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "creates_order": False,
        "changes_stock": False,
        "reserves_stock": False,
    }


def _is_sam_live_stock_send_echo(payload):
    payload = payload if isinstance(payload, dict) else {}
    source_id = str(payload.get("source_id") or "").strip().lower()
    if source_id.startswith("sam_live_stock:") or source_id.startswith("order_document:"):
        return True
    attrs = payload.get("content_attributes") if isinstance(payload.get("content_attributes"), dict) else {}
    return attrs.get("amadeus_source") in {
        "sam_live_stock_owner_approved_send",
        "order_document_delivery",
    } or attrs.get("sam_live_stock_generated") is True


def _truthy_payload_value(value):
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


@sales_bp.route("/sales/channels/chatwoot/sam-live-stock/review", methods=["POST"])
def sam_live_stock_conversation_review():
    payload = request.get_json(silent=True) or {}
    result = review_sam_live_stock_conversation(
        payload.get("inbound") if isinstance(payload.get("inbound"), dict) else payload,
        payload.get("facts") if isinstance(payload.get("facts"), dict) else {},
        payload.get("decision") if isinstance(payload.get("decision"), dict) else {},
        payload.get("context_packet") if isinstance(payload.get("context_packet"), dict) else {},
    )
    event = build_sam_live_stock_review_event(
        payload.get("inbound") if isinstance(payload.get("inbound"), dict) else payload,
        payload.get("facts") if isinstance(payload.get("facts"), dict) else {},
        payload.get("decision") if isinstance(payload.get("decision"), dict) else {},
        result,
        event_source="manual_review_route",
    )
    learning_result, learning_status = record_sam_live_stock_review_event(event)
    return jsonify({
        "success": True,
        "review": result,
        "conversation_review_event": {
            "status": learning_result.get("status"),
            "status_code": learning_status,
            "review_event_id": learning_result.get("review_event_id") or event.get("review_event_id"),
            "recorded": learning_result.get("success") is True,
        },
    }), 200


@sales_bp.route("/sales/channels/chatwoot/sam-live-stock/open-intakes", methods=["GET"])
def sam_live_stock_open_intakes():
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    result, status_code = list_sam_live_stock_open_intakes(limit=request.args.get("limit", 25))
    return jsonify(result), status_code


@sales_bp.route("/sales/channels/chatwoot/sam-live-stock/launch-readiness", methods=["GET"])
def sam_live_stock_launch_readiness():
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    result, status_code = build_sam_live_stock_launch_readiness()
    return jsonify(result), status_code


@sales_bp.route("/sales/channels/chatwoot/sam-live-stock/owner-send", methods=["POST"])
def sam_live_stock_owner_send():
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = send_owner_approved_live_stock_reply(
        payload.get("conversation_id"),
        payload.get("message"),
        owner=payload.get("owner") or "owner",
        escalation_id=payload.get("escalation_id") or "",
    )
    return jsonify(result), status_code


@sales_bp.route("/sales/channels/chatwoot/sam-live-stock/escalations/send-telegram", methods=["POST"])
def sam_live_stock_send_escalation_telegram():
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = send_sam_live_stock_telegram_escalation(payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/channels/chatwoot/sam-live-stock/escalations/callback", methods=["POST"])
def sam_live_stock_escalation_callback():
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = process_sam_live_stock_owner_callback(payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/channels/chatwoot/sam-live-stock/escalations/<escalation_id>/cleanup-packet", methods=["POST"])
def sam_live_stock_escalation_cleanup_packet(escalation_id):
    payload = request.get_json(silent=True) or {}
    return jsonify({
        "success": True,
        "cleanup_packet": build_sam_live_stock_resolved_cleanup_packet(
            escalation_id,
            telegram_chat_id=payload.get("telegram_chat_id") or "",
            telegram_message_id=payload.get("telegram_message_id") or "",
            conversation_id=payload.get("conversation_id") or "",
        ),
    }), 200


@sales_bp.route("/sales/channels/chatwoot/sam-live-stock/escalations/<escalation_id>/delete-telegram", methods=["POST"])
def sam_live_stock_escalation_delete_telegram(escalation_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = delete_sam_live_stock_telegram_escalation(
        escalation_id,
        payload.get("telegram_chat_id") or "",
        payload.get("telegram_message_id") or "",
    )
    return jsonify(result), status_code


@sales_bp.route("/sales/channels/chatwoot/sam-live-stock/takeover", methods=["POST"])
def sam_live_stock_chatwoot_takeover():
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = apply_sam_live_stock_chatwoot_takeover(
        payload.get("conversation_id"),
        mode=payload.get("mode") or "HUMAN",
        reason=payload.get("reason") or "owner_takeover",
    )
    return jsonify(result), status_code


@sales_bp.route("/sales/channels/chatwoot/sam-live-stock/reservation-plan", methods=["POST"])
def sam_live_stock_reservation_plan():
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    return jsonify({
        "success": True,
        "reservation_plan": build_live_stock_reservation_plan(
            order_id=payload.get("order_id") or "",
            match_packet=payload.get("match_packet") if isinstance(payload.get("match_packet"), dict) else {},
        ),
    }), 200


@sales_bp.route("/sales/channels/chatwoot/sam-live-stock/order-reservation", methods=["POST"])
def sam_live_stock_order_reservation():
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = execute_live_stock_order_reservation(
        payload.get("order_id"),
        action=payload.get("action") or "reserve",
    )
    return jsonify(result), status_code


@sales_bp.route("/sales/channels/chatwoot/meat-documents/delivery-status", methods=["POST"])
def meat_document_delivery_status_webhook():
    allowed, denied = authorize_meat_document_delivery_webhook(request.headers, request.args)
    if not allowed:
        status_code = 403 if denied.get("status") == "meat_sales_delivery_webhook_auth_denied" else 503
        return jsonify(denied), status_code
    payload = request.get_json(silent=True) or {}
    result, status_code = handle_meat_document_delivery_status_webhook(payload)
    return jsonify(result), status_code


@sales_bp.route("/beacon/campaign-calendar/rules/propose", methods=["POST"])
def beacon_campaign_calendar_rule_propose():
    denied = require_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result = propose_rule_version(payload.get("rule") or payload, previous_version=payload.get("previous_version"))
    return jsonify(result), 200 if result["success"] else 400


@sales_bp.route("/beacon/campaign-calendar/rules/approve", methods=["POST"])
def beacon_campaign_calendar_rule_approve():
    denied = require_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result = approve_rule_version(payload.get("rule"), "authenticated_owner_admin", approved_at=payload.get("approved_at"))
    return jsonify(result), 200 if result["success"] else 400


@sales_bp.route("/beacon/campaign-calendar/rules/revoke", methods=["POST"])
def beacon_campaign_calendar_rule_revoke():
    denied = require_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result = revoke_rule_version(payload.get("rule_id"), payload.get("version"),
                                 "authenticated_owner_admin", revoked_at=payload.get("revoked_at"),
                                 reason_code=payload.get("reason_code"))
    return jsonify(result), 200 if result["success"] else 400


@sales_bp.route("/beacon/campaign-calendar/prepare", methods=["POST"])
def beacon_campaign_calendar_prepare():
    denied = require_owner_admin_access()
    if denied:
        return denied
    result = prepare_calendar_entry(request.get_json(silent=True) or {})
    return jsonify(result), 200 if result["success"] else 400


@sales_bp.route("/beacon/media-policy", methods=["GET"])
def beacon_media_policy():
    denied = require_owner_read_access()
    if denied:
        return denied
    return jsonify(beacon_media_storage_policy()), 200


@sales_bp.route("/beacon/marketing-operating-contract", methods=["GET"])
def beacon_marketing_operating_contract():
    denied = require_owner_read_access()
    if denied:
        return denied
    try:
        result = build_beacon_marketing_operating_contract(
            sale_stream=request.args.get("sale_stream", "meat"),
        )
    except ValueError as exc:
        return jsonify({"success": False, "status": str(exc), "authority": {"posts_publicly": False, "spends_money": False, "sends_customer_messages": False}}), 400
    return jsonify(result), 200


@sales_bp.route("/beacon/media-assets", methods=["GET", "POST"])
def beacon_media_assets():
    if request.method == "GET":
        denied = require_owner_read_access()
        if denied:
            return denied
        result, status_code = list_beacon_media_assets(
            limit=request.args.get("limit", 50),
            approval_status=request.args.get("approval_status", ""),
            media_type=request.args.get("media_type", ""),
        )
        return jsonify(result), status_code
    denied = require_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    payload["created_by"] = "authenticated_owner_admin"
    result, status_code = register_beacon_media_asset(payload)
    return jsonify(result), status_code


@sales_bp.route("/beacon/media-assets/upload", methods=["POST"])
def beacon_media_asset_upload():
    denied = require_owner_admin_access()
    if denied:
        return denied
    upload = request.files.get("file")
    result, status_code = upload_beacon_media_asset(upload, form=request.form.to_dict())
    return jsonify(result), status_code


@sales_bp.route("/beacon/media-assets/<asset_id>/events", methods=["POST"])
def beacon_media_asset_event(asset_id):
    denied = require_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    payload["recorded_by"] = "authenticated_owner_admin"
    result, status_code = record_beacon_media_asset_event(asset_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/beacon/creative-studio/providers", methods=["GET"])
def beacon_creative_studio_providers():
    denied = require_owner_read_access()
    if denied:
        return denied
    return jsonify({
        "success": True,
        "mode": "beacon_creative_provider_evaluation_disabled",
        "providers": sorted(ALLOWED_CREATIVE_PROVIDERS),
        **DISABLED_PROVIDER_FLAGS,
    }), 200


@sales_bp.route("/beacon/creative-studio/jobs", methods=["POST"])
def beacon_creative_studio_jobs():
    denied = require_owner_admin_access()
    if denied:
        return denied
    result, status_code = create_mock_creative_job(
        request.get_json(silent=True) or {}, recorded_by="authenticated_owner_admin"
    )
    return jsonify(result), status_code


@sales_bp.route("/beacon/creative-studio/jobs/<job_id>/reviews", methods=["POST"])
def beacon_creative_studio_reviews(job_id):
    denied = require_owner_admin_access()
    if denied:
        return denied
    result, status_code = record_creative_review(
        job_id, request.get_json(silent=True) or {}, recorded_by="authenticated_owner_admin"
    )
    return jsonify(result), status_code


@sales_bp.route("/beacon/campaign-draft-selection", methods=["GET"])
def beacon_campaign_draft_selection():
    denied = require_owner_read_access()
    if denied:
        return denied
    assets_result, assets_status = list_beacon_media_assets(
        limit=request.args.get("limit", 25),
        approval_status="approved",
        media_type=request.args.get("media_type", ""),
    )
    if assets_status >= 400:
        return jsonify(assets_result), assets_status
    campaign_payload = {
        "campaign_lane": request.args.get("campaign_lane", ""),
        "pilot_name": request.args.get("pilot_name", ""),
        "area": request.args.get("area", ""),
        "product_focus": request.args.get("product_focus", ""),
    }
    if campaign_payload["campaign_lane"] == "live_stock_sales":
        source_payload, source_error, source_status = _beacon_live_stock_sales_sources(campaign_payload)
        if source_error:
            return jsonify(source_error), source_status
        campaign_payload.update(source_payload)
    result = build_beacon_campaign_selection(campaign_payload, approved_assets=assets_result.get("assets", []))
    return jsonify(result), 200 if result.get("success") else 400


@sales_bp.route("/beacon/campaign-publish-packet", methods=["POST"])
def beacon_campaign_publish_packet():
    denied = require_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    assets_result, assets_status = list_beacon_media_assets(
        limit=25,
        approval_status="approved",
        media_type=payload.get("media_type", ""),
    )
    if assets_status >= 400:
        return jsonify(assets_result), assets_status
    if payload.get("campaign_lane") == "live_stock_sales":
        source_payload, source_error, source_status = _beacon_live_stock_sales_sources(payload)
        if source_error:
            return jsonify(source_error), source_status
        payload = {**payload, **source_payload}
    result = build_beacon_campaign_publish_packet(payload, approved_assets=assets_result.get("assets", []))
    return jsonify(result), 200 if result.get("success") else 400


@sales_bp.route("/beacon/post-composer/suggestions", methods=["POST"])
def beacon_post_composer_suggestions():
    denied = require_owner_admin_access()
    if denied:
        return denied
    history, history_status = list_beacon_manual_post_evidence(limit=30)
    if history_status >= 400:
        return jsonify(history), history_status
    result, status_code = build_beacon_caption_suggestions(
        request.get_json(silent=True) or {},
        historical_events=history.get("manual_post_events", []),
    )
    return jsonify(result), status_code


def _beacon_live_stock_sales_sources(payload):
    opportunities = build_beacon_opportunity_cards()
    card = next((item for item in opportunities.get("cards", []) if item.get("lane") == "live_stock"), {})
    prices, price_status = list_live_stock_price_entries(limit=500)
    if price_status >= 400:
        return {}, prices, price_status
    price_entries = prices.get("price_entries", []) if prices.get("source") == "supabase" else []
    requested = str(payload.get("product_focus") or "").strip().lower()
    candidates = [entry for entry in price_entries if entry.get("active") is not False]
    if requested:
        matching = [entry for entry in candidates if requested in str(entry.get("sale_category") or "").lower() or requested in str(entry.get("weight_band") or "").lower()]
        candidates = matching or candidates
    candidates.sort(key=lambda entry: (str(entry.get("effective_from") or ""), str(entry.get("created_at") or "")), reverse=True)
    pricing = candidates[0] if candidates else {"source": prices.get("source", "")}
    return {"opportunity_card": card, "pricing": pricing}, None, 200


@sales_bp.route("/beacon/facebook-image-launch-packet", methods=["GET", "POST"])
def beacon_facebook_image_launch_packet():
    payload = request.get_json(silent=True) or {}
    if request.method == "GET":
        payload = {
            "pilot_name": request.args.get("pilot_name", ""),
            "area": request.args.get("area", ""),
            "product_focus": request.args.get("product_focus", ""),
            "asset_id": request.args.get("asset_id", ""),
            "pilot_cap": request.args.get("pilot_cap", ""),
        }
    assets_result, assets_status = list_beacon_media_assets(
        limit=25,
        approval_status="approved",
        media_type="image",
    )
    if assets_status >= 400:
        return jsonify(assets_result), assets_status
    result = build_beacon_facebook_image_launch_packet(payload, approved_assets=assets_result.get("assets", []))
    return jsonify(result), 200 if result.get("success") else 409


@sales_bp.route("/beacon/manual-post-evidence", methods=["GET", "POST"])
def beacon_manual_post_evidence():
    if request.method == "GET":
        result, status_code = list_beacon_manual_post_evidence(
            limit=request.args.get("limit", 25),
            publish_packet_id=request.args.get("publish_packet_id", ""),
        )
        return jsonify(result), status_code
    payload = request.get_json(silent=True) or {}
    result, status_code = record_beacon_manual_post_evidence(payload)
    return jsonify(result), status_code


@sales_bp.route("/beacon/campaign-performance", methods=["GET", "POST"])
def beacon_campaign_performance():
    if request.method == "GET":
        result, status_code = list_beacon_campaign_performance_events(
            limit=request.args.get("limit", 25),
            publish_packet_id=request.args.get("publish_packet_id", ""),
            manual_post_event_id=request.args.get("manual_post_event_id", ""),
        )
        return jsonify(result), status_code
    payload = request.get_json(silent=True) or {}
    result, status_code = record_beacon_campaign_performance_event(payload)
    return jsonify(result), status_code


@sales_bp.route("/beacon/weekly-command-brief", methods=["GET"])
def beacon_weekly_command_brief():
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = list_beacon_campaign_performance_events(limit=request.args.get("limit", 100))
    if status_code >= 400:
        return jsonify(result), status_code
    brief = build_beacon_weekly_command_brief(result.get("performance_events", []))
    return jsonify({"success": True, "weekly_command_brief": brief}), 200


@sales_bp.route("/beacon/facebook-history-import", methods=["POST"])
def beacon_facebook_history_import():
    denied = require_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = import_beacon_facebook_history(max_posts=payload.get("max_posts", 5000))
    return jsonify(result), status_code


@sales_bp.route("/beacon/weekly-command-brief/prepare-decision", methods=["POST"])
def beacon_weekly_command_prepare_decision():
    denied = require_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    performance_event_id = str(payload.get("performance_event_id") or "").strip()
    if not performance_event_id:
        return jsonify({"success": False, "status": "recommendation_source_required"}), 400
    source, source_status = list_beacon_campaign_performance_events(limit=100)
    if source_status >= 400:
        return jsonify(source), source_status
    performance_event = next(
        (event for event in source.get("performance_events", []) if event.get("performance_event_id") == performance_event_id),
        None,
    )
    if performance_event is None:
        return jsonify({"success": False, "status": "recommendation_source_not_found"}), 404
    result, status_code = prepare_beacon_owner_decision(performance_event, payload.get("destination"))
    return jsonify(result), status_code


@sales_bp.route("/beacon/facebook-posting-policy", methods=["GET"])
def beacon_facebook_posting_policy():
    return jsonify(facebook_posting_policy()), 200


@sales_bp.route("/beacon/facebook-post-executions", methods=["GET", "POST"])
def beacon_facebook_post_executions():
    denied = require_owner_admin_access()
    if denied:
        return denied
    if request.method == "GET":
        result, status_code = list_beacon_facebook_post_execution_events(
            limit=request.args.get("limit", 25),
            publish_packet_id=request.args.get("publish_packet_id", ""),
        )
        return jsonify(result), status_code
    payload = request.get_json(silent=True) or {}
    asset_ids = payload.get("asset_ids") if isinstance(payload.get("asset_ids"), list) else []
    if not asset_ids and payload.get("asset_id"):
        asset_ids = [payload.get("asset_id")]
    asset_ids = list(dict.fromkeys(str(value or "").strip() for value in asset_ids if str(value or "").strip()))[:10]
    asset_id = asset_ids[0] if asset_ids else ""
    approved_assets = []
    if asset_ids:
        assets_result, assets_status = list_beacon_media_assets(
            limit=100,
            approval_status="approved",
        )
        if assets_status >= 400:
            return jsonify(assets_result), assets_status
        by_id = {asset.get("asset_id"): asset for asset in assets_result.get("assets", [])}
        selected_assets = [by_id.get(selected_id) for selected_id in asset_ids]
        missing_asset_ids = [selected_id for selected_id, asset in zip(asset_ids, selected_assets) if not asset]
        if missing_asset_ids:
            return jsonify({
                "success": False,
                "status": "selected_media_asset_not_approved_or_not_found",
                "asset_ids": missing_asset_ids,
                "posts_publicly": False,
                "calls_meta": False,
                "spends_money": False,
            }), 400
        approved_assets = assets_result.get("assets", [])
        payload = {
            **payload,
            "asset_id": asset_id,
            "asset_ids": asset_ids,
            "selected_asset": selected_assets[0],
            "selected_assets": selected_assets,
        }
    if payload.get("campaign_lane") == "live_stock_sales":
        return jsonify({
            "success": False,
            "status": "live_stock_sales_meta_posting_prohibited",
            "reason": "Livestock Meta publishing is awareness-only. Sales, price, stock, availability, and reservation language are prohibited.",
            "posts_publicly": False,
            "calls_meta": False,
            "spends_money": False,
        }), 409
    if payload.get("campaign_lane") == "live_stock_awareness":
        authoritative = build_beacon_campaign_publish_packet({
            "campaign_lane": "live_stock_awareness",
            "draft_id": "facebook_awareness_post",
            "asset_id": asset_id,
            "asset_ids": asset_ids,
            "channel": "Facebook",
            "owner_exact_text": payload.get("exact_text"),
        }, approved_assets=approved_assets)
        if (not authoritative.get("success") or
                authoritative.get("publish_packet_id") != payload.get("publish_packet_id") or
                (authoritative.get("selected_draft") or {}).get("exact_text") != payload.get("exact_text")):
            return jsonify({
                "success": False,
                "status": "live_stock_awareness_packet_stale_or_altered",
                "posts_publicly": False,
                "calls_meta": False,
                "spends_money": False,
                "authoritative_packet_id": authoritative.get("publish_packet_id", ""),
                "errors": authoritative.get("errors", []),
            }), 409
    meat_launch_authorized = False
    if payload.get("campaign_lane") == "meat_launch":
        authoritative = build_beacon_campaign_publish_packet({
            "campaign_lane": "meat_launch",
            "draft_id": "facebook_post",
            "asset_id": asset_id,
            "channel": "Facebook",
            "pilot_cap": payload.get("pilot_cap"),
        }, approved_assets=approved_assets)
        canonical_text = (authoritative.get("selected_draft") or {}).get("exact_text", "")
        canonical_asset_id = (authoritative.get("selected_asset") or {}).get("asset_id", "")
        packet_matches = (
            authoritative.get("success")
            and authoritative.get("publish_packet_id") == payload.get("publish_packet_id")
            and canonical_text == payload.get("exact_text")
            and canonical_asset_id == asset_id
            and str(payload.get("channel") or "").strip() == "Facebook"
            and str(authoritative.get("pilot_cap") or "") == str(payload.get("pilot_cap") or "").strip()
        )
        if not packet_matches:
            return jsonify({
                "success": False,
                "status": "meat_launch_packet_not_ready_or_stale",
                "posts_publicly": False,
                "calls_meta": False,
                "spends_money": False,
                "authoritative_packet_id": authoritative.get("publish_packet_id", ""),
                "errors": authoritative.get("errors", []),
            }), 409
        payload = {
            **payload,
            "publish_packet_id": authoritative["publish_packet_id"],
            "channel": "Facebook",
            "exact_text": canonical_text,
            "asset_id": canonical_asset_id,
            "selected_asset": authoritative["selected_asset"],
        }
        meat_launch_authorized = True
    result, status_code = execute_beacon_facebook_page_post(
        payload, meat_launch_authorized=meat_launch_authorized
    ) if meat_launch_authorized else execute_beacon_facebook_page_post(payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads", methods=["GET"])
def meat_sales_leads_list():
    guard = require_owner_read_access()
    if guard:
        return guard
    result, status_code = list_sales_leads(
        limit=request.args.get("limit", 50),
        status_filter=request.args.get("status", "launch_test"),
    )
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-learning", methods=["GET"])
def meat_sales_conversation_learning_list():
    result, status_code = list_sales_conversation_learning_events(
        limit=request.args.get("limit", 50),
        lead_id=request.args.get("lead_id", ""),
    )
    return jsonify(result), status_code


@sales_bp.route("/sales/live-stock-learning/scorecard", methods=["GET"])
def live_stock_conversation_learning_scorecard():
    guard = require_owner_read_access()
    if guard:
        return guard
    result, status_code = live_stock_learning_scorecard(limit=request.args.get("limit", 500))
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-pricing", methods=["GET"])
def meat_price_book_list():
    result, status_code = list_meat_price_book_entries(limit=request.args.get("limit", 50))
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-pricing", methods=["POST"])
def meat_price_book_create():
    payload = request.get_json(silent=True) or {}
    result, status_code = record_meat_price_book_entry(payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/live-stock-pricing", methods=["GET"])
def live_stock_price_book_list():
    guard = require_owner_read_access()
    if guard:
        return guard
    result, status_code = list_live_stock_price_entries(limit=request.args.get("limit", 100))
    return jsonify(result), status_code


@sales_bp.route("/sales/live-stock-pricing", methods=["POST"])
def live_stock_price_book_create():
    guard = require_owner_read_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = record_live_stock_price_entry(payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/contract", methods=["GET"])
def meat_sales_lead_contract(lead_id):
    guard = require_owner_read_access()
    if guard:
        return guard
    result, status_code = get_sales_lead_preorder_contract(lead_id)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/command-state", methods=["GET"])
def meat_sales_lead_command_state(lead_id):
    if not _sam_command_state_access_allowed(request.remote_addr, request.headers):
        result, status_code = _sam_command_state_access_denied(request.remote_addr)
        return jsonify(result), status_code
    result, status_code = get_sam_command_state(lead_id)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/test-cleanup", methods=["POST"])
def meat_sales_lead_test_cleanup(lead_id):
    payload = request.get_json(silent=True) or {}
    contract_result, contract_status = get_sales_lead_preorder_contract(lead_id)
    if contract_status >= 400:
        return jsonify(contract_result), contract_status
    lead = contract_result.get("lead") if isinstance(contract_result.get("lead"), dict) else {}
    if not _lead_is_test_flow(lead):
        return jsonify({
            "success": False,
            "status": "test_cleanup_denied_not_marked_test_flow",
            "lead_id": lead_id,
            "requires_marker": "TEST FLOW or delete after test",
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "creates_quote": False,
            "creates_order": False,
            "changes_stock": False,
        }), 409
    latest_event = lead.get("latest_event") if isinstance(lead.get("latest_event"), dict) else {}
    if latest_event.get("event_type") == "closed":
        return jsonify({
            "success": True,
            "status": "already_closed",
            "lead_id": lead_id,
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "creates_quote": False,
            "creates_order": False,
            "changes_stock": False,
        }), 200
    result, status_code = record_sales_lead_event(lead_id, {
        "event_type": "closed",
        "recorded_by": str(payload.get("closed_by") or "Farm App").strip()[:80],
        "status_observed": "closed",
        "notes": "Test flow cleanup: soft-closed after owner WhatsApp pilot test.",
    })
    if status_code < 400:
        result = {
            **result,
            "status": "test_flow_soft_closed",
            "removes_from_launch_test_queue": True,
            "deletes_physical_records": False,
        }
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/learning-events", methods=["GET", "POST"])
def meat_sales_lead_learning_events(lead_id):
    if request.method == "GET":
        result, status_code = list_sales_conversation_learning_events(
            limit=request.args.get("limit", 50),
            lead_id=lead_id,
        )
        return jsonify(result), status_code
    payload = request.get_json(silent=True) or {}
    event = build_owner_review_learning_event(lead_id, payload)
    result, status_code = record_sales_conversation_learning_event(event)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/pricing-estimate", methods=["GET", "POST"])
def meat_sales_lead_pricing_estimate(lead_id):
    if request.method == "GET":
        guard = require_owner_read_access()
        if guard:
            return guard
    payload = request.get_json(silent=True) or {}
    if request.method == "GET":
        payload = {
            "selected_pig_live_weight_kg": request.args.get("selected_pig_live_weight_kg", ""),
        }
    result, status_code = get_sales_lead_pricing_estimate(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/estimated-quote", methods=["GET", "POST"])
def meat_sales_lead_estimated_quote(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    if request.method == "GET":
        payload = {
            "selected_pig_live_weight_kg": request.args.get("selected_pig_live_weight_kg", ""),
            "estimated_weight_kg": request.args.get("estimated_weight_kg", ""),
        }
    result, status_code = build_meat_estimated_quote_packet(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/estimated-quote/pdf", methods=["POST"])
def meat_sales_lead_estimated_quote_pdf(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = generate_meat_estimated_quote_pdf(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/estimated-quote/send", methods=["POST"])
def meat_sales_lead_estimated_quote_send(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = send_meat_estimated_quote_to_chatwoot(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/deposit-pro-forma/pdf", methods=["POST"])
def meat_sales_lead_deposit_pro_forma_pdf(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = generate_meat_deposit_pro_forma_pdf(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/final-invoice/pdf", methods=["POST"])
def meat_sales_lead_final_invoice_pdf(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = generate_meat_final_invoice_pdf(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/meat-match", methods=["GET", "POST"])
def meat_sales_lead_meat_match(lead_id):
    if request.method == "GET":
        guard = require_owner_read_access()
        if guard:
            return guard
    payload = request.get_json(silent=True) or {}
    if request.method == "GET":
        payload = {
            "preference": request.args.get("preference", ""),
            "target_packed_kg": request.args.get("target_packed_kg", ""),
            "budget_amount": request.args.get("budget_amount", ""),
        }
    result, status_code = get_sales_lead_meat_match(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/meat-ops", methods=["GET"])
def meat_sales_lead_ops_status(lead_id):
    guard = require_owner_read_access()
    if guard:
        return guard
    result, status_code = get_meat_ops_status(lead_id)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/payment-gate", methods=["GET"])
def meat_sales_lead_payment_gate(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    result, status_code = get_meat_payment_gate(lead_id)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/carcass-reservations", methods=["POST"])
def meat_sales_lead_carcass_reservation(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = create_carcass_reservation_from_lead(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/reservation-events", methods=["POST"])
def meat_sales_lead_reservation_event(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = record_carcass_reservation_event(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/deposit-events", methods=["POST"])
def meat_sales_lead_deposit_event(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = record_meat_deposit_event(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/instruction-drafts", methods=["POST"])
def meat_sales_lead_instruction_drafts(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = build_meat_instruction_drafts(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/fulfillment", methods=["GET"])
def meat_sales_lead_fulfillment_timeline(lead_id):
    guard = require_owner_read_access()
    if guard:
        return guard
    result, status_code = get_meat_fulfillment_timeline(lead_id)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/reconciliation", methods=["GET"])
def meat_sales_lead_reconciliation_status(lead_id):
    guard = require_owner_read_access()
    if guard:
        return guard
    result, status_code = get_meat_reconciliation_status(lead_id)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/reconciliation-events", methods=["POST"])
def meat_sales_lead_reconciliation_event(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = record_meat_reconciliation_event(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/dad-booking-packet", methods=["GET", "POST"])
def meat_sales_lead_dad_booking_packet(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = build_dad_booking_packet(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/fulfillment-events", methods=["POST"])
def meat_sales_lead_fulfillment_event(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = record_meat_fulfillment_event(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-deliveries/driver-route", methods=["GET"])
def meat_sales_driver_route():
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    result, status_code = list_meat_driver_route(
        driver_label=request.args.get("driver", ""),
        scheduled_date=request.args.get("date", ""),
    )
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/driver-events", methods=["POST"])
def meat_sales_lead_driver_event(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = record_meat_driver_delivery_event(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/journey-notification-draft", methods=["POST"])
def meat_sales_lead_journey_notification_draft(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = build_meat_journey_notification_draft(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/journey-notification-approval", methods=["POST"])
def meat_sales_lead_journey_notification_approval(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = approve_meat_journey_notification(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/journey-notification-send", methods=["POST"])
def meat_sales_lead_journey_notification_send(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = send_meat_journey_notification(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/instruction-drafts/<instruction_draft_id>/approval", methods=["POST"])
def meat_sales_lead_instruction_draft_approval(lead_id, instruction_draft_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = approve_meat_instruction_draft(lead_id, instruction_draft_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/instruction-drafts/<instruction_draft_id>/send", methods=["POST"])
def meat_sales_lead_instruction_draft_send(lead_id, instruction_draft_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = send_approved_meat_instruction(lead_id, instruction_draft_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/instruction-drafts/<instruction_draft_id>/exception", methods=["POST"])
def meat_sales_lead_instruction_draft_exception(lead_id, instruction_draft_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = record_meat_instruction_exception(lead_id, instruction_draft_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/owner-money-path-approval", methods=["POST"])
def meat_sales_lead_owner_money_path_approval(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = record_owner_money_path_approval(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/customer-followup-draft", methods=["GET"])
def meat_sales_lead_customer_followup_draft(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    result, status_code = get_sales_lead_customer_followup_draft(lead_id)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/customer-followup-send-approval", methods=["POST"])
def meat_sales_lead_customer_followup_send_approval(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = record_customer_followup_send_approval(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/customer-followup-send", methods=["POST"])
def meat_sales_lead_customer_followup_send(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    if not _env_truthy(os.getenv("OOM_SAKKIE_MEAT_FOLLOWUP_SEND_ENABLED")):
        return jsonify({
            "success": False,
            "status": "meat_followup_send_disabled",
            "sent": False,
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "creates_quote": False,
            "creates_order": False,
            "changes_stock": False,
        }), 503
    payload = request.get_json(silent=True) or {}
    result, status_code = send_customer_followup_to_chatwoot(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/customer-booking-confirmation", methods=["POST"])
def meat_sales_lead_customer_booking_confirmation(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = record_customer_booking_confirmation(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/draft-order", methods=["POST"])
def meat_sales_lead_draft_order(lead_id):
    guard = _require_owner_meat_money_path_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    result, status_code = create_draft_order_from_sales_lead(lead_id, payload)
    return jsonify(result), status_code
