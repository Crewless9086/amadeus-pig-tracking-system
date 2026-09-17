"use strict";

const policyState = { packet: null };
const byId = (id) => document.getElementById(id);
const form = byId("policy_form");
const field = (name) => form.elements.namedItem(name);

const errorMessages = {
  minimum_runtime_exceeds_maximum: "Minimum useful runtime must not exceed maximum continuous runtime.",
  daylight_window_must_not_cross_midnight: "The daylight window must start before it ends on the same day.",
  crop_need_bands_must_increase: "Crop-need bands must increase from low to medium to high.",
  invalid_forecast_probability: "Forecast probability must be between 0% and 100%.",
  invalid_forecast_amount: "Forecast rain amount must be between 0 and 200 mm.",
  invalid_live_rain_threshold: "Live-rain threshold must be the confirmed numeric value 0.2 mm/hour.",
  live_rain_threshold_not_owner_confirmed: "The confirmed live-rain threshold is exactly 0.2 mm/hour.",
  invalid_minimum_temperature: "Minimum temperature must be between -20 °C and 50 °C.",
  invalid_maximum_temperature: "Maximum temperature must be between -20 °C and 60 °C.",
  activation_effective_time_required: "Choose an explicit activation effective time.",
  effective_time_must_not_precede_activation: "Activation cannot be backdated.",
  stale_policy_version: "A newer proposal exists; this version is immutable history.",
  transition_idempotency_conflict: "This action identity was already used for different evidence.",
  rootline_policy_schema_unavailable: "The policy schema is not applied; review remains unavailable.",
};

function explain(status) {
  return errorMessages[status] || String(status || "Evidence is Unavailable.").replaceAll("_", " ");
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, { credentials: "same-origin", ...options });
  const data = await response.json().catch(() => ({ status: "invalid_server_response" }));
  if (!response.ok) throw new Error(data.status || `HTTP ${response.status}`);
  return data;
}

function requiredNumber(name, label, integer = false) {
  const raw = String(field(name).value || "").trim();
  if (!raw) throw new Error(`${label} is required when Unknown is cleared.`);
  const value = Number(raw);
  if (!Number.isFinite(value) || (integer && !Number.isInteger(value))) {
    throw new Error(`${label} has an invalid number.`);
  }
  return value;
}

function unknownOr(checkName, builder) {
  return field(checkName).checked ? "Unknown" : builder();
}

function zonePolicy(zone) {
  return {
    daylight_window: unknownOr(`${zone}_window_unknown`, () => {
      const start = String(field(`${zone}_start`).value || "");
      const end = String(field(`${zone}_end`).value || "");
      if (!start || !end) throw new Error(`${zone} needs both daylight times.`);
      return { start, end };
    }),
    minimum_useful_runtime_minutes: unknownOr(`${zone}_min_unknown`, () =>
      requiredNumber(`${zone}_min`, `${zone} minimum runtime`, true)),
    maximum_continuous_runtime_minutes: unknownOr(`${zone}_max_unknown`, () =>
      requiredNumber(`${zone}_max`, `${zone} maximum runtime`, true)),
  };
}

function cropBand(zone) {
  return unknownOr(`${zone}_crop_unknown`, () => ({
    low_mm_per_day: requiredNumber(`${zone}_low`, `${zone} low crop-need band`),
    medium_mm_per_day: requiredNumber(`${zone}_medium`, `${zone} medium crop-need band`),
    high_mm_per_day: requiredNumber(`${zone}_high`, `${zone} high crop-need band`),
  }));
}

function policyPayload() {
  const power = field("power_loss").value;
  const drainage = field("drainage").value;
  const powerNote = String(field("power_note").value || "").trim();
  const drainageNote = String(field("drainage_note").value || "").trim();
  if (power !== "Unknown" && !powerNote) throw new Error("Physical power-loss evidence is required.");
  if (drainage !== "Unknown" && !drainageNote) throw new Error("Residual-drainage evidence is required.");
  return {
    seasonal_boundaries: unknownOr("season_unknown", () => ({
      summer_start: String(field("summer_start").value || "").trim(),
      winter_start: String(field("winter_start").value || "").trim(),
    })),
    zones: { B12345: zonePolicy("B12345"), C12345: zonePolicy("C12345") },
    forecast_rain: unknownOr("forecast_unknown", () => ({
      amount_mm: requiredNumber("forecast_amount", "Forecast amount"),
      probability_pct: requiredNumber("forecast_probability", "Forecast probability"),
      horizon_hours: requiredNumber("forecast_horizon", "Forecast horizon", true),
    })),
    live_rain_hold: unknownOr("live_rain_unknown", () => ({
      evidence_field: "current_rain_rate_mm_per_hour",
      threshold_mm_per_hour: requiredNumber("live_rain_threshold", "Live-rain threshold"),
      comparison: "greater_than",
      release_policy: "Unknown",
    })),
    temperature_limits: unknownOr("temperature_unknown", () => ({
      minimum_c: requiredNumber("temperature_min", "Minimum temperature"),
      maximum_c: requiredNumber("temperature_max", "Maximum temperature"),
    })),
    crop_need_bands: { B12345: cropBand("B12345"), C12345: cropBand("C12345") },
    controller_power_loss: power === "Unknown" ? "Unknown" : { observed_state: power, evidence_note: powerNote },
    residual_drainage: drainage === "Unknown" ? "Unknown" : {
      observation_seconds: requiredNumber("drainage_seconds", "Drainage observation", true),
      classification: drainage,
      evidence_note: drainageNote,
    },
  };
}

function syncUnknownControls() {
  form.querySelectorAll("[data-controls]").forEach((control) => {
    const unknown = control.type === "checkbox" ? control.checked : control.value === "Unknown";
    control.dataset.controls.split(",").forEach((name) => {
      const input = field(name);
      input.disabled = unknown;
      input.closest("label")?.classList.toggle("is-muted", unknown);
    });
  });
}

function renderGuidance(items) {
  byId("policy_guidance").innerHTML = (items || []).map((item) =>
    `<div class="ops-list-row"><strong>${item.question}</strong><span>${item.recommendation} ${item.consequence}</span></div>`
  ).join("") || '<div class="ops-empty-inline">Guidance Unavailable.</div>';
}

function renderHistory() {
  const packet = policyState.packet || {};
  const proposals = packet.proposals || [];
  const latest = proposals.reduce((value, item) => Math.max(value, item.version || 0), 0);
  byId("policy_history").innerHTML = proposals.slice().sort((a, b) => b.version - a.version).map((item) => {
    const current = item.version === latest;
    let action = '<span>Immutable history</span>';
    if (current && packet.owner_can_administer && item.lifecycle_state === "proposed") {
      action = `<button data-transition="review" data-proposal="${item.proposal_id}">Record owner review</button>`;
    } else if (current && packet.owner_can_administer && item.lifecycle_state === "owner_reviewed") {
      action = `<button data-transition="activate" data-proposal="${item.proposal_id}">Activate exact version for advice</button>`;
    } else if (current && item.lifecycle_state === "active_for_advice") {
      action = item.advice_status === "scheduled_for_advice"
        ? `<span>Scheduled for advice at ${item.lifecycle_events?.find(event => event.state === "active_for_advice")?.effective_at || "Unavailable"}</span>`
        : "<span>Active for advice</span>";
    }
    return `<div class="ops-list-row"><strong>Version ${item.version} · ${explain(item.lifecycle_state)}</strong><span>${item.proposal_id}</span>${action}</div>`;
  }).join("") || '<div class="ops-empty-inline">No proposal versions recorded.</div>';
}

function showMessage(text, failed = false) {
  byId("policy_message").textContent = text;
  byId("policy_message").className = failed ? "error" : "";
}

async function loadPolicy() {
  const [contract, packet] = await Promise.all([
    requestJson("/api/telemetry/rootline/operating-policy/contract"),
    requestJson("/api/telemetry/rootline/operating-policy"),
  ]);
  policyState.packet = packet;
  renderGuidance(contract.decision_guidance);
  byId("policy_schema_status").textContent = packet.migration_applied
    ? "Immutable policy ledger available."
    : "Policy ledger Unavailable; no policy can become active.";
  renderHistory();
}

async function preview() {
  const result = await requestJson("/api/telemetry/rootline/operating-policy/preview", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy: policyPayload() }),
  });
  byId("policy_preview_result").innerHTML =
    `<div class="ops-list-row"><strong>Valid partial proposal · may be recorded</strong><span>Advice preview: ${explain(result.eligibility_after_preview)}. Runtime ${result.runtime_status}; ${result.remaining_unknown_policy_inputs.length} inputs remain Unknown. Recording this proposal will not change current advice.</span></div>`;
}

async function propose() {
  const note = String(field("proposal_evidence").value || "").trim();
  if (!note) throw new Error("Proposal evidence and owner reasoning are required.");
  await requestJson("/api/telemetry/rootline/operating-policy/proposals", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      idempotency_key: crypto.randomUUID(),
      evidence: { owner_note: note },
      policy: policyPayload(),
    }),
  });
  showMessage("Proposal recorded. It is not reviewed, not active, and current advice is unchanged.");
  await loadPolicy();
}

async function transition(button) {
  const evidence = String(byId("transition_evidence").value || "").trim();
  if (!evidence) throw new Error("Review or activation evidence is required.");
  const kind = button.dataset.transition;
  const body = { idempotency_key: crypto.randomUUID(), evidence: { owner_note: evidence } };
  if (kind === "activate") {
    const raw = byId("activation_effective_at").value;
    if (!raw) throw new Error("Choose an explicit activation effective time.");
    body.effective_at = new Date(raw).toISOString();
  }
  await requestJson(`/api/telemetry/rootline/operating-policy/proposals/${button.dataset.proposal}/${kind}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  showMessage(kind === "review" ? "Owner review recorded; policy is still inactive." : "Exact reviewed version activated for advice only.");
  await loadPolicy();
}

form.querySelectorAll("[data-controls]").forEach((item) => item.addEventListener("change", syncUnknownControls));
byId("policy_preview").addEventListener("click", () => preview().catch((error) => showMessage(explain(error.message), true)));
byId("policy_propose").addEventListener("click", () => propose().catch((error) => showMessage(explain(error.message), true)));
byId("policy_history").addEventListener("click", (event) => {
  const button = event.target.closest("[data-transition]");
  if (button) transition(button).catch((error) => showMessage(explain(error.message), true));
});
syncUnknownControls();
loadPolicy().catch((error) => {
  byId("policy_schema_status").textContent = explain(error.message);
  renderGuidance([]);
});
