from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, render_template
from modules.pig_weights.pig_weights_routes import pig_weights_bp
from modules.pig_weights.mating_routes import mating_bp
from modules.orders.order_routes import orders_bp
from modules.reports.report_routes import reports_bp
from modules.sales.sales_transaction_routes import sales_bp
from modules.telemetry.telemetry_routes import telemetry_bp
from modules.oom_sakkie.routes import oom_sakkie_bp
from services.database_service import (
    check_irrigation_schema,
    check_database_foundation,
    check_database_health,
    check_order_schema,
    check_sales_transaction_payment_date_schema,
    check_sales_transaction_schema,
    check_telemetry_power_schema,
    check_telemetry_rollup_schema,
    check_telemetry_weather_schema,
)

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

app = Flask(__name__)
app.register_blueprint(pig_weights_bp, url_prefix="/api/pig-weights")
app.register_blueprint(mating_bp, url_prefix="/api/pig-weights")
app.register_blueprint(orders_bp, url_prefix="/api")
app.register_blueprint(reports_bp, url_prefix="/api")
app.register_blueprint(sales_bp, url_prefix="/api")
app.register_blueprint(telemetry_bp, url_prefix="/api")
app.register_blueprint(oom_sakkie_bp, url_prefix="/api")


@app.route("/")
def home():
    return render_template("dashboard.html")


@app.route("/pigs")
def pigs_page():
    return render_template("pig-list.html")


@app.route("/sales-availability")
def sales_availability_page():
    return render_template("sales-availability.html")


@app.route("/sales-dashboard")
def sales_dashboard_page():
    return render_template("sales-dashboard.html")


@app.route("/pig-allocation")
def pig_allocation_page():
    return render_template("pig-allocation.html")


@app.route("/purpose-review")
def purpose_review_page():
    return render_template("purpose-review.html")


@app.route("/meat-planning")
def meat_planning_page():
    return render_template("meat-planning.html")


@app.route("/oom-sakkie")
def oom_sakkie_page():
    return render_template("oom-sakkie.html")


@app.route("/sales/slaughter")
def slaughter_sale_page():
    return render_template("slaughter-sale.html")


@app.route("/sales/slaughter/<sale_id>")
def slaughter_sale_detail_page(sale_id):
    return render_template("slaughter-sale-detail.html", sale_id=sale_id)


@app.route("/sales/transactions/<sale_id>")
def sales_transaction_detail_page(sale_id):
    return render_template("slaughter-sale-detail.html", sale_id=sale_id)


@app.route("/orders")
def orders_page():
    return render_template("orders.html")


@app.route("/matings")
def matings_page():
    return render_template("matings.html")


@app.route("/orders/new")
def add_order_page():
    return render_template("add-order.html")


@app.route("/orders/<order_id>")
def order_detail_page(order_id):
    return render_template("order-detail.html")


@app.route("/master/add-pig")
def add_pig_page():
    return render_template("add-pig.html")


@app.route("/master/add-product")
def add_product_page():
    return render_template("add-product.html")


@app.route("/master/add-pen")
def add_pen_page():
    return render_template("add-pen.html")


@app.route("/master/add-litter")
def add_litter_page():
    return render_template("add-litter.html")


@app.route("/master/add-mating")
def add_mating_page():
    return render_template("add-mating.html")


@app.route("/breeding-analytics")
def breeding_analytics_page():
    return render_template("breeding-analytics.html")


@app.route("/breeding-analytics/<pig_id>")
def breeding_analytics_detail_page(pig_id):
    return render_template("breeding-analytics-detail.html")


@app.route("/pig/<pig_id>")
def pig_detail_page(pig_id):
    return render_template("pig-detail.html")


@app.route("/pig/<pig_id>/family-tree")
def family_tree_page(pig_id):
    return render_template("family-tree.html")


@app.route("/pig/<pig_id>/weights")
def pig_weight_history_page(pig_id):
    return render_template("pig-weight-history.html")


@app.route("/pig/<pig_id>/treatment")
def pig_treatment_page(pig_id):
    return render_template("pig-treatment.html")


@app.route("/pig/<pig_id>/treatments")
def pig_treatment_history_page(pig_id):
    return render_template("pig-treatment-history.html")


@app.route("/pig/<pig_id>/movement")
def pig_movement_page(pig_id):
    return render_template("pig-movement.html")


@app.route("/pig/<pig_id>/movements")
def pig_movement_history_page(pig_id):
    return render_template("pig-movement-history.html")


@app.route("/litter/<litter_id>")
def litter_detail_page(litter_id):
    return render_template("litter-detail.html")


@app.route("/pig-weights")
def pig_weights_page():
    return render_template("pig-weights.html")


@app.route("/bulk-weights")
def bulk_weights_page():
    return render_template("bulk-weights.html")


@app.route("/weight-report")
def weight_report_page():
    return render_template("weight-report.html")


@app.route("/print-sheets")
def print_sheets_page():
    return render_template("print-sheets.html")


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/health/database")
def database_health():
    body, status_code = check_database_health()
    return body, status_code


@app.route("/health/database/foundation")
def database_foundation_health():
    body, status_code = check_database_foundation()
    return body, status_code


@app.route("/health/database/order-schema")
def database_order_schema_health():
    body, status_code = check_order_schema()
    return body, status_code


@app.route("/health/database/sales-transaction-schema")
def database_sales_transaction_schema_health():
    body, status_code = check_sales_transaction_schema()
    return body, status_code


@app.route("/health/database/sales-payment-date-schema")
def database_sales_payment_date_schema_health():
    body, status_code = check_sales_transaction_payment_date_schema()
    return body, status_code


@app.route("/health/database/telemetry-power-schema")
def database_telemetry_power_schema_health():
    body, status_code = check_telemetry_power_schema()
    return body, status_code


@app.route("/health/database/telemetry-weather-schema")
def database_telemetry_weather_schema_health():
    body, status_code = check_telemetry_weather_schema()
    return body, status_code


@app.route("/health/database/irrigation-schema")
def database_irrigation_schema_health():
    body, status_code = check_irrigation_schema()
    return body, status_code


@app.route("/health/database/telemetry-rollup-schema")
def database_telemetry_rollup_schema_health():
    body, status_code = check_telemetry_rollup_schema()
    return body, status_code


if __name__ == "__main__":
    app.run(debug=True)
