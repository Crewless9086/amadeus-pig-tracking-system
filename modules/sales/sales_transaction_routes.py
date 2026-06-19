import os

from flask import Blueprint, jsonify, request

from modules.oom_sakkie.sales_campaign_store import (
    create_draft_order_from_sales_lead,
    get_sales_lead_pricing_estimate,
    get_sales_lead_customer_followup_draft,
    get_sales_lead_preorder_contract,
    list_meat_price_book_entries,
    list_sales_leads,
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
    build_meat_estimated_quote_packet,
    generate_meat_deposit_pro_forma_pdf,
    generate_meat_estimated_quote_pdf,
    generate_meat_final_invoice_pdf,
    meat_document_policy,
    send_meat_estimated_quote_to_chatwoot,
)
from modules.sales.sam_meat_runtime import (
    authorize_sam_meat_webhook,
    handle_sam_meat_chatwoot_inbound,
    sam_meat_webhook_policy,
)
from modules.sales.conversation_learning import (
    build_owner_review_learning_event,
    list_sales_conversation_learning_events,
    record_sales_conversation_learning_event,
)
from modules.sales.beacon_campaign import (
    build_meat_launch_campaign_publish_packet,
    build_meat_launch_campaign_selection,
    execute_beacon_facebook_page_post,
    facebook_posting_policy,
    list_beacon_campaign_performance_events,
    list_beacon_facebook_post_execution_events,
    list_beacon_manual_post_evidence,
    record_beacon_campaign_performance_event,
    record_beacon_manual_post_evidence,
)
from modules.beacon.media_library import (
    beacon_media_storage_policy,
    list_beacon_media_assets,
    record_beacon_media_asset_event,
    register_beacon_media_asset,
    upload_beacon_media_asset,
)


sales_bp = Blueprint("sales", __name__)


def _env_truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


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


@sales_bp.route("/sales/meat-documents/policy", methods=["GET"])
def meat_documents_policy_route():
    return jsonify(meat_document_policy()), 200


@sales_bp.route("/sales/channels/chatwoot/sam-meat/inbound", methods=["POST"])
def sam_meat_chatwoot_inbound():
    allowed, denied = authorize_sam_meat_webhook(request.headers, request.args)
    if not allowed:
        status_code = 403 if denied.get("status") == "sam_meat_backend_webhook_auth_denied" else 503
        return jsonify(denied), status_code
    payload = request.get_json(silent=True) or {}
    result, status_code = handle_sam_meat_chatwoot_inbound(payload)
    return jsonify(result), status_code


@sales_bp.route("/beacon/media-policy", methods=["GET"])
def beacon_media_policy():
    return jsonify(beacon_media_storage_policy()), 200


@sales_bp.route("/beacon/media-assets", methods=["GET", "POST"])
def beacon_media_assets():
    if request.method == "GET":
        result, status_code = list_beacon_media_assets(
            limit=request.args.get("limit", 50),
            approval_status=request.args.get("approval_status", ""),
            media_type=request.args.get("media_type", ""),
        )
        return jsonify(result), status_code
    payload = request.get_json(silent=True) or {}
    result, status_code = register_beacon_media_asset(payload)
    return jsonify(result), status_code


@sales_bp.route("/beacon/media-assets/upload", methods=["POST"])
def beacon_media_asset_upload():
    upload = request.files.get("file")
    result, status_code = upload_beacon_media_asset(upload, form=request.form.to_dict())
    return jsonify(result), status_code


@sales_bp.route("/beacon/media-assets/<asset_id>/events", methods=["POST"])
def beacon_media_asset_event(asset_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = record_beacon_media_asset_event(asset_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/beacon/campaign-draft-selection", methods=["GET"])
def beacon_campaign_draft_selection():
    assets_result, assets_status = list_beacon_media_assets(
        limit=request.args.get("limit", 25),
        approval_status="approved",
        media_type=request.args.get("media_type", ""),
    )
    if assets_status >= 400:
        return jsonify(assets_result), assets_status
    result = build_meat_launch_campaign_selection({
        "pilot_name": request.args.get("pilot_name", ""),
        "area": request.args.get("area", ""),
        "product_focus": request.args.get("product_focus", ""),
    }, approved_assets=assets_result.get("assets", []))
    return jsonify(result), 200


@sales_bp.route("/beacon/campaign-publish-packet", methods=["POST"])
def beacon_campaign_publish_packet():
    payload = request.get_json(silent=True) or {}
    assets_result, assets_status = list_beacon_media_assets(
        limit=25,
        approval_status="approved",
        media_type=payload.get("media_type", ""),
    )
    if assets_status >= 400:
        return jsonify(assets_result), assets_status
    result = build_meat_launch_campaign_publish_packet(payload, approved_assets=assets_result.get("assets", []))
    return jsonify(result), 200 if result.get("success") else 400


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


@sales_bp.route("/beacon/facebook-posting-policy", methods=["GET"])
def beacon_facebook_posting_policy():
    return jsonify(facebook_posting_policy()), 200


@sales_bp.route("/beacon/facebook-post-executions", methods=["GET", "POST"])
def beacon_facebook_post_executions():
    if request.method == "GET":
        result, status_code = list_beacon_facebook_post_execution_events(
            limit=request.args.get("limit", 25),
            publish_packet_id=request.args.get("publish_packet_id", ""),
        )
        return jsonify(result), status_code
    payload = request.get_json(silent=True) or {}
    asset_id = str(payload.get("asset_id") or "").strip()
    if asset_id:
        assets_result, assets_status = list_beacon_media_assets(
            limit=100,
            approval_status="approved",
            media_type="image",
        )
        if assets_status >= 400:
            return jsonify(assets_result), assets_status
        approved_asset = next(
            (asset for asset in assets_result.get("assets", []) if asset.get("asset_id") == asset_id),
            None,
        )
        if not approved_asset:
            return jsonify({
                "success": False,
                "status": "selected_image_asset_not_approved_or_not_found",
                "asset_id": asset_id,
                "posts_publicly": False,
                "calls_meta": False,
                "spends_money": False,
            }), 400
        payload = {**payload, "selected_asset": approved_asset}
    result, status_code = execute_beacon_facebook_page_post(payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads", methods=["GET"])
def meat_sales_leads_list():
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


@sales_bp.route("/sales/meat-pricing", methods=["GET"])
def meat_price_book_list():
    result, status_code = list_meat_price_book_entries(limit=request.args.get("limit", 50))
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-pricing", methods=["POST"])
def meat_price_book_create():
    payload = request.get_json(silent=True) or {}
    result, status_code = record_meat_price_book_entry(payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/contract", methods=["GET"])
def meat_sales_lead_contract(lead_id):
    result, status_code = get_sales_lead_preorder_contract(lead_id)
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
    payload = request.get_json(silent=True) or {}
    if request.method == "GET":
        payload = {
            "selected_pig_live_weight_kg": request.args.get("selected_pig_live_weight_kg", ""),
        }
    result, status_code = get_sales_lead_pricing_estimate(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/estimated-quote", methods=["GET", "POST"])
def meat_sales_lead_estimated_quote(lead_id):
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
    payload = request.get_json(silent=True) or {}
    result, status_code = generate_meat_estimated_quote_pdf(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/estimated-quote/send", methods=["POST"])
def meat_sales_lead_estimated_quote_send(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = send_meat_estimated_quote_to_chatwoot(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/deposit-pro-forma/pdf", methods=["POST"])
def meat_sales_lead_deposit_pro_forma_pdf(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = generate_meat_deposit_pro_forma_pdf(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/final-invoice/pdf", methods=["POST"])
def meat_sales_lead_final_invoice_pdf(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = generate_meat_final_invoice_pdf(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/meat-match", methods=["GET", "POST"])
def meat_sales_lead_meat_match(lead_id):
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
    result, status_code = get_meat_ops_status(lead_id)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/carcass-reservations", methods=["POST"])
def meat_sales_lead_carcass_reservation(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = create_carcass_reservation_from_lead(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/reservation-events", methods=["POST"])
def meat_sales_lead_reservation_event(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = record_carcass_reservation_event(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/deposit-events", methods=["POST"])
def meat_sales_lead_deposit_event(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = record_meat_deposit_event(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/instruction-drafts", methods=["POST"])
def meat_sales_lead_instruction_drafts(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = build_meat_instruction_drafts(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/fulfillment", methods=["GET"])
def meat_sales_lead_fulfillment_timeline(lead_id):
    result, status_code = get_meat_fulfillment_timeline(lead_id)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/reconciliation", methods=["GET"])
def meat_sales_lead_reconciliation_status(lead_id):
    result, status_code = get_meat_reconciliation_status(lead_id)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/reconciliation-events", methods=["POST"])
def meat_sales_lead_reconciliation_event(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = record_meat_reconciliation_event(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/dad-booking-packet", methods=["GET", "POST"])
def meat_sales_lead_dad_booking_packet(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = build_dad_booking_packet(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/fulfillment-events", methods=["POST"])
def meat_sales_lead_fulfillment_event(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = record_meat_fulfillment_event(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-deliveries/driver-route", methods=["GET"])
def meat_sales_driver_route():
    result, status_code = list_meat_driver_route(
        driver_label=request.args.get("driver", ""),
        scheduled_date=request.args.get("date", ""),
    )
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/driver-events", methods=["POST"])
def meat_sales_lead_driver_event(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = record_meat_driver_delivery_event(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/journey-notification-draft", methods=["POST"])
def meat_sales_lead_journey_notification_draft(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = build_meat_journey_notification_draft(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/journey-notification-approval", methods=["POST"])
def meat_sales_lead_journey_notification_approval(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = approve_meat_journey_notification(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/journey-notification-send", methods=["POST"])
def meat_sales_lead_journey_notification_send(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = send_meat_journey_notification(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/instruction-drafts/<instruction_draft_id>/approval", methods=["POST"])
def meat_sales_lead_instruction_draft_approval(lead_id, instruction_draft_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = approve_meat_instruction_draft(lead_id, instruction_draft_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/instruction-drafts/<instruction_draft_id>/send", methods=["POST"])
def meat_sales_lead_instruction_draft_send(lead_id, instruction_draft_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = send_approved_meat_instruction(lead_id, instruction_draft_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/instruction-drafts/<instruction_draft_id>/exception", methods=["POST"])
def meat_sales_lead_instruction_draft_exception(lead_id, instruction_draft_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = record_meat_instruction_exception(lead_id, instruction_draft_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/owner-money-path-approval", methods=["POST"])
def meat_sales_lead_owner_money_path_approval(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = record_owner_money_path_approval(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/customer-followup-draft", methods=["GET"])
def meat_sales_lead_customer_followup_draft(lead_id):
    result, status_code = get_sales_lead_customer_followup_draft(lead_id)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/customer-followup-send-approval", methods=["POST"])
def meat_sales_lead_customer_followup_send_approval(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = record_customer_followup_send_approval(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/customer-followup-send", methods=["POST"])
def meat_sales_lead_customer_followup_send(lead_id):
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
    payload = request.get_json(silent=True) or {}
    result, status_code = record_customer_booking_confirmation(lead_id, payload)
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/draft-order", methods=["POST"])
def meat_sales_lead_draft_order(lead_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = create_draft_order_from_sales_lead(lead_id, payload)
    return jsonify(result), status_code
