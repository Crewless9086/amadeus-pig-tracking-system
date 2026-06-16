import os

from flask import Blueprint, jsonify, request

from modules.oom_sakkie.sales_campaign_store import (
    create_draft_order_from_sales_lead,
    get_sales_lead_customer_followup_draft,
    get_sales_lead_preorder_contract,
    list_sales_leads,
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


@sales_bp.route("/sales/meat-leads", methods=["GET"])
def meat_sales_leads_list():
    result, status_code = list_sales_leads(
        limit=request.args.get("limit", 50),
        status_filter=request.args.get("status", "launch_test"),
    )
    return jsonify(result), status_code


@sales_bp.route("/sales/meat-leads/<lead_id>/contract", methods=["GET"])
def meat_sales_lead_contract(lead_id):
    result, status_code = get_sales_lead_preorder_contract(lead_id)
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
