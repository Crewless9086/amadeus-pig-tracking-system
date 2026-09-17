from flask import jsonify, render_template

from app import app
from modules.pig_weights.herdmaster_breeding_observation_service import list_observations
from modules.pig_weights.mating_routes import _build_breeding_attention_packets


@app.get("/preview/breeding-attention")
def local_breeding_attention_preview():
    return render_template("breeding-attention.html")


@app.get("/preview/api/breeding-attention")
def local_breeding_attention_packet():
    packet, _hypothetical, _started = _build_breeding_attention_packets()
    return jsonify(packet)


@app.get("/preview/api/breeding-attention/<pig_id>/observations")
def local_breeding_observation_history(pig_id):
    result, status = list_observations(pig_id)
    return jsonify(result), status


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5208, debug=False)
