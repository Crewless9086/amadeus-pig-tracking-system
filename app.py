from flask import Flask, render_template
from modules.pig_weights.pig_weights_routes import pig_weights_bp

app = Flask(__name__)
app.register_blueprint(pig_weights_bp, url_prefix="/api/pig-weights")


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/pigs")
def pigs_page():
    return render_template("pig-list.html")


@app.route("/sales-availability")
def sales_availability_page():
    return render_template("sales-availability.html")


@app.route("/pig/<pig_id>")
def pig_detail_page(pig_id):
    return render_template("pig-detail.html")


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


@app.route("/pig-weights")
def pig_weights_page():
    return render_template("pig-weights.html")


@app.route("/health")
def health():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    app.run(debug=True)