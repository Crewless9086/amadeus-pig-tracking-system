const assert = require("assert");
const fs = require("fs");

const html = fs.readFileSync("templates/breeding-attention.html", "utf8");
const js = fs.readFileSync("static/js/breedingAttention.js", "utf8");

assert(html.includes('id="attention_filter"'));
assert(html.includes("Current explained state"));
assert(html.includes("Human action"));
assert(js.includes('fetch("/api/pig-weights/breeding-attention")'));
assert(js.includes("counts are not zero."));
assert(!js.includes("method: \"POST\""));
assert(!html.includes("customer"));
console.log("breeding attention browser contract passed");
