from flask import Flask, render_template
from modules.pig_weights.pig_weights_routes import pig_weights_bp

app = Flask(__name__)
app.register_blueprint(pig_weights_bp, url_prefix="/api/pig-weights")


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/health")
def health():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    app.run(debug=True)