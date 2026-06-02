from flask import Blueprint, jsonify, request

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
