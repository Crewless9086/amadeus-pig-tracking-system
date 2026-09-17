const assert = require("assert");
const fs = require("fs");

const source = fs.readFileSync("static/js/litterDetail.js", "utf8");
const routes = fs.readFileSync("modules/pig_weights/pig_weights_routes.py", "utf8");

assert(source.includes("async function readWeaningDayResponse(response)"));
assert(source.includes('includes("application/json")'));
assert(source.includes("Do not press Save again; reload the litter"));
assert(source.includes("await readWeaningDayResponse(response)"));
assert(!source.includes("retryWeaningDay"));
assert(routes.includes('"status": "weaning_day_unexpected_failure"'));
assert(routes.includes('"operation_committed": None'));
assert(routes.includes('"operation_state": "unknown_verify_before_retry"'));
assert(!routes.includes("Weaning day workflow failed: {exc}"));

console.log("litter Weaning Day browser recovery contract passed");
