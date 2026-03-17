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


@app.route("/pig/<pig_id>")
def pig_detail_page(pig_id):
    return render_template("pig-detail.html")


@app.route("/pig-weights")
def pig_weights_page():
    return render_template("pig-weights.html")


@app.route("/health")
def health():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    app.run(debug=True)