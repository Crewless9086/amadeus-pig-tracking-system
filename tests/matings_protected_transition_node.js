const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    id, innerHTML: "", textContent: "", dataset: {},
    classList: { values: new Set(["hidden"]), add(value) { this.values.add(value); }, remove(value) { this.values.delete(value); }, contains(value) { return this.values.has(value); } },
    addEventListener() {}, setAttribute() {}, querySelectorAll() { return []; }
  });
  return elements.get(id);
}
const workspace = element("active_exposure_workspace");
const board = element("exposure_removal_board");
element("exposure_removal_preview");
element("matings_board");
element("mating_summary");
element("mating_controls");
element("mating_record_count");

let response = { ok: true, json: async () => ({ success: true, records: [] }) };
const sandbox = {
  console, Promise, Map, Set, Date, String, Boolean, Array, Object,
  URLSearchParams, setTimeout, clearTimeout,
  window: { location: { search: "" }, print() {} },
  document: { addEventListener() {}, getElementById: element, querySelectorAll() { return []; } },
  fetch: async () => response
};
vm.runInNewContext(fs.readFileSync("static/js/matings.js", "utf8"), sandbox);

const complete = { exposure_group_identity: "G1", exposure_identity: "E1", event_kind: "started", sow_pig_id: "S1", boar_pig_id: "B1", occurred_on: "2026-08-12", planned_removal_on: "2026-08-28", sow_label: "Sophie", boar_label: "Bola", current_pen_name: "Kraam Saal 03" };

(async () => {
  workspace.dataset.ownerRole = "admin";
  response = { ok: true, json: async () => ({ success: true, records: [complete] }) };
  await sandbox.loadExposureRemovals();
  assert(!workspace.classList.contains("hidden"));
  assert(board.innerHTML.includes("Sophie") && board.innerHTML.includes("Teken werklike UIT aan"));
  assert(!board.innerHTML.includes("data-confirm-removal"));

  workspace.dataset.ownerRole = "read";
  await sandbox.loadExposureRemovals();
  assert(board.innerHTML.includes("Sophie"));
  assert(!board.innerHTML.includes("data-open-removal"));

  workspace.dataset.ownerRole = "admin";
  response = { ok: true, json: async () => ({ success: true, records: [{ ...complete, exposure_identity: "" }] }) };
  await sandbox.loadExposureRemovals();
  assert(board.innerHTML.includes("Sophie"));
  assert(!board.innerHTML.includes("data-open-removal"));

  response = { ok: true, json: async () => ({ success: true, records: [] }) };
  await sandbox.loadExposureRemovals();
  assert(workspace.classList.contains("hidden"));

  response = { ok: false, json: async () => ({ success: false }) };
  await sandbox.loadExposureRemovals();
  assert(!workspace.classList.contains("hidden"));
  assert(board.innerHTML.includes("Aktiewe blootstellings is tans nie beskikbaar nie."));
  assert(!board.innerHTML.includes("data-open-removal"));
  console.log("matings_protected_transition_node: PASS");
})().catch(error => { console.error(error); process.exit(1); });
