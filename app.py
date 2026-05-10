from flask import Flask, render_template
from modules.pig_weights.pig_weights_routes import pig_weights_bp
from modules.pig_weights.mating_routes import mating_bp
from modules.orders.order_routes import orders_bp
from modules.reports.report_routes import reports_bp

app = Flask(__name__)
app.register_blueprint(pig_weights_bp, url_prefix="/api/pig-weights")
app.register_blueprint(mating_bp, url_prefix="/api/pig-weights")
app.register_blueprint(orders_bp, url_prefix="/api")
app.register_blueprint(reports_bp, url_prefix="/api")


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


@app.route("/health")
def health():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    app.run(debug=True)
