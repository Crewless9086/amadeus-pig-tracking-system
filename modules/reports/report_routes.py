from flask import Blueprint, jsonify, request

from modules.reports.report_service import get_daily_order_summary


reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/reports/daily-summary", methods=["GET"])
def daily_summary():
    report_date = request.args.get("date", "").strip()

    try:
        result = get_daily_order_summary(report_date=report_date)
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)],
        }), 400
