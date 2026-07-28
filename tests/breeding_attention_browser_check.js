const assert = require("assert");
const fs = require("fs");

const html = fs.readFileSync("templates/breeding-attention.html", "utf8");
const js = fs.readFileSync("static/js/breedingAttention.js", "utf8");

assert(html.includes('id="attention_filter"'));
assert(html.includes("Current explained state"));
assert(html.includes("Human action"));
assert(js.includes('fetch("/api/pig-weights/breeding-attention")'));
assert(js.includes("counts are not zero."));
assert(html.includes('id="observation_panel"'));
assert(html.includes("Observed fact, owner interpretation and Herdmaster recommendation remain separate."));
assert(html.includes("Actually observed"));
assert(js.includes("/observations/preview"));
assert(js.includes("/observations`"));
assert(js.includes("acceptedPreviewPayload"));
assert(js.includes("recordButton.disabled = true"));
assert(js.includes("crypto.randomUUID()"));
assert(js.includes("If recorded:"));
assert(!html.includes("customer"));
console.log("breeding attention browser contract passed");
