const state = { batches: [], selectedId: "", detail: null };

const els = {
  message: document.getElementById("production_message"),
  batchCount: document.getElementById("batch_count"),
  batchList: document.getElementById("batch_list"),
  empty: document.getElementById("batch_empty"),
  detail: document.getElementById("batch_detail"),
};

const stages = [
  ["Planned", "Planned"], ["Selected", "Selected"], ["Sent_To_Abattoir", "Abattoir"],
  ["Carcass_Received", "Carcass"], ["At_Butcher", "Butcher"], ["Cutting", "Cutting"],
  ["Packed", "Packed"],
];

document.addEventListener("DOMContentLoaded", () => {
  bindDialogs();
  bindForms();
  loadBatches();
});

function bindDialogs() {
  document.getElementById("new_batch_button").addEventListener("click", () => openDialog("new_batch_dialog"));
  document.getElementById("add_event_button").addEventListener("click", () => {
    const pig = state.detail?.pigs?.[0];
    const form = document.getElementById("event_form");
    form.elements.event_date.value = today();
    form.elements.pig_id.value = pig?.pig_id || "";
    openDialog("event_dialog");
  });
  document.getElementById("add_cost_button").addEventListener("click", () => {
    document.getElementById("cost_form").elements.cost_date.value = today();
    openDialog("cost_dialog");
  });
  document.getElementById("add_output_button").addEventListener("click", () => openDialog("output_dialog"));
  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => button.closest("dialog").close());
  });
}

function bindForms() {
  document.getElementById("new_batch_form").addEventListener("submit", submitNewBatch);
  document.getElementById("event_form").addEventListener("submit", (event) => submitBatchRecord(event, "events"));
  document.getElementById("cost_form").addEventListener("submit", (event) => submitBatchRecord(event, "costs"));
  document.getElementById("output_form").addEventListener("submit", (event) => submitBatchRecord(event, "outputs"));
}

async function loadBatches(preferredId = "") {
  clearMessage();
  try {
    const payload = await api("/api/sales/meat-production/batches");
    state.batches = payload.batches || [];
    els.batchCount.textContent = `${state.batches.length} ${state.batches.length === 1 ? "batch" : "batches"}`;
    const nextId = preferredId || state.selectedId || state.batches[0]?.batch_id || "";
    state.selectedId = nextId;
    renderBatchList();
    if (nextId) await loadBatch(nextId);
    else renderEmpty();
  } catch (error) {
    showMessage(error.message, "error");
    els.batchList.innerHTML = '<div class="empty-state">Production ledger unavailable.</div>';
  }
}

async function loadBatch(batchId) {
  state.selectedId = batchId;
  renderBatchList();
  try {
    state.detail = await api(`/api/sales/meat-production/batches/${encodeURIComponent(batchId)}`);
    renderDetail();
  } catch (error) {
    showMessage(error.message, "error");
  }
}

function renderBatchList() {
  if (!state.batches.length) {
    els.batchList.innerHTML = '<div class="empty-state">No production batches yet.</div>';
    return;
  }
  els.batchList.innerHTML = state.batches.map((batch) => `
    <button type="button" class="batch-card ${batch.batch_id === state.selectedId ? "active" : ""}" data-batch-id="${escapeHtml(batch.batch_id)}">
      <div class="batch-card-top"><strong>${escapeHtml(batch.batch_code)}</strong><small>${escapeHtml(label(batch.status))}</small></div>
      <small>${escapeHtml(label(batch.batch_kind))} · ${escapeHtml(label(batch.intended_disposition))}</small>
      <div class="batch-card-bottom"><span class="batch-weight">${kg(batch.carcass_weight_kg)} carcass</span><small>${money(batch.total_cost)}</small></div>
    </button>
  `).join("");
  els.batchList.querySelectorAll("[data-batch-id]").forEach((button) => {
    button.addEventListener("click", () => loadBatch(button.dataset.batchId));
  });
}

function renderEmpty() {
  els.empty.classList.remove("hidden");
  els.detail.classList.add("hidden");
}

function renderDetail() {
  const data = state.detail;
  const batch = data.batch || {};
  const metrics = data.metrics || {};
  const pig = data.pigs?.[0] || {};
  els.empty.classList.add("hidden");
  els.detail.classList.remove("hidden");

  text("batch_kind", label(batch.batch_kind));
  text("batch_disposition", label(batch.intended_disposition));
  text("batch_code", batch.batch_code || "-");
  text("batch_status", label(batch.status));
  text("batch_context", [batch.abattoir_name, batch.butcher_name].filter(Boolean).join(" → ") || "Provider details pending");
  text("metric_live", kg(metrics.live_weight_kg));
  text("metric_carcass", kg(metrics.carcass_weight_kg));
  text("metric_dressing", pct(metrics.dressing_yield_pct, "dressing yield"));
  text("metric_packed", kg(metrics.packed_weight_kg));
  text("metric_packed_yield", pct(metrics.packed_yield_carcass_pct, "of carcass"));
  text("metric_cost", money(metrics.total_cost));
  text("metric_cost_kg", metrics.cost_per_packed_kg == null ? "Packed cost pending" : `${money(metrics.cost_per_packed_kg)}/kg packed`);
  text("next_action", data.next_capture?.action || "Record the next verified stage.");
  text("timeline_count", `${data.events?.length || 0} events`);
  text("cost_total", money(metrics.total_cost));
  text("output_total", kg(metrics.total_output_weight_kg));

  renderStages(batch.status);
  renderTimeline(data.events || []);
  renderCosts(data.costs || []);
  renderOutputs(data.outputs || []);
  renderFacts(batch, pig, data.next_capture || {});
}

function renderStages(status) {
  const current = status === "Completed" ? stages.length : Math.max(0, stages.findIndex(([value]) => value === status));
  document.getElementById("stage_track").innerHTML = stages.map(([value, stageLabel], index) => {
    const cls = index < current ? "complete" : index === current ? "active" : "";
    return `<div class="stage-step ${cls}">${escapeHtml(stageLabel)}</div>`;
  }).join("");
}

function renderTimeline(events) {
  const list = document.getElementById("timeline_list");
  if (!events.length) {
    list.innerHTML = '<div class="empty-state">No events recorded.</div>';
    return;
  }
  list.innerHTML = [...events].reverse().map((event) => `
    <div class="timeline-entry">
      <time>${escapeHtml(formatDate(event.event_date))}</time>
      <span class="timeline-dot"></span>
      <div class="timeline-content">
        <strong>${escapeHtml(label(event.event_type))}</strong>
        <span>${escapeHtml([event.location_label, event.notes].filter(Boolean).join(" · ") || "Recorded")}</span>
      </div>
    </div>
  `).join("");
}

function renderCosts(costs) {
  const list = document.getElementById("cost_list");
  if (!costs.length) {
    list.innerHTML = '<div class="empty-state">No costs recorded.</div>';
    return;
  }
  list.innerHTML = [...costs].reverse().map((cost) => `
    <div class="compact-row">
      <div><strong>${escapeHtml(label(cost.cost_type))}</strong><small>${escapeHtml(cost.supplier_name || formatDate(cost.cost_date))}</small></div>
      <strong>${money(cost.amount)}</strong>
    </div>
  `).join("");
}

function renderOutputs(outputs) {
  const body = document.getElementById("output_body");
  if (!outputs.length) {
    body.innerHTML = '<tr><td colspan="4" class="empty-state">Waiting for butcher cut weights.</td></tr>';
    return;
  }
  body.innerHTML = outputs.map((output) => `
    <tr>
      <td><strong>${escapeHtml(output.cut_name)}</strong><br><small>${escapeHtml(label(output.output_type))}</small></td>
      <td>${escapeHtml(output.pack_count)}</td>
      <td>${kg(output.weight_kg)}</td>
      <td>${escapeHtml(label(output.disposition))}</td>
    </tr>
  `).join("");
}

function renderFacts(batch, pig, nextCapture) {
  const facts = [
    ["Pig", `${formatTag(pig.tag_number)} · ${pig.pig_id || "-"}`],
    ["Head included", pig.head_included ? "Yes" : "No"],
    ["Slaughter date", formatDate(batch.slaughter_date)],
    ["Butcher date", formatDate(batch.butcher_date)],
    ["Abattoir", batch.abattoir_name || "-"],
    ["Butcher", batch.butcher_name || "Pending"],
    ["Still needed", (nextCapture.missing || []).map(label).join(", ") || "Nothing"],
    ["Revenue", "R0.00 · internal use"],
  ];
  document.getElementById("batch_facts").innerHTML = facts.map(([name, value]) => `
    <div><dt>${escapeHtml(name)}</dt><dd>${escapeHtml(value)}</dd></div>
  `).join("");
}

async function submitNewBatch(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const values = formValues(form);
  const payload = {
    batch_code: values.batch_code,
    batch_kind: values.batch_kind,
    intended_disposition: values.intended_disposition,
    status: "Planned",
    abattoir_name: values.abattoir_name,
    slaughter_date: values.slaughter_date,
    notes: values.notes,
    created_by: "Charl",
    pigs: [{
      pig_id: values.pig_id,
      tag_number: values.tag_number,
      live_weight_kg: numberOrNull(values.live_weight_kg),
    }],
  };
  await submitForm(form, "/api/sales/meat-production/batches", payload, "Batch created.");
}

async function submitBatchRecord(event, resource) {
  event.preventDefault();
  if (!state.selectedId) return;
  const form = event.currentTarget;
  const values = formValues(form);
  const payload = { ...values, recorded_by: "Charl" };
  ["amount", "live_weight_kg", "carcass_weight_kg", "weight_kg", "pack_count"].forEach((key) => {
    if (key in payload) payload[key] = numberOrNull(payload[key]);
  });
  if (resource === "events") payload.head_included = form.elements.head_included.checked;
  if (resource === "outputs") payload.counts_toward_packed_yield = form.elements.counts_toward_packed_yield.checked;
  await submitForm(form, `/api/sales/meat-production/batches/${encodeURIComponent(state.selectedId)}/${resource}`, payload, "Batch updated.");
}

async function submitForm(form, url, payload, successMessage) {
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    const result = await api(url, { method: "POST", body: JSON.stringify(payload) });
    form.closest("dialog").close();
    form.reset();
    state.detail = result;
    showMessage(successMessage, "success");
    await loadBatches(result.batch?.batch_id || state.selectedId);
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || label(payload.status) || `Request failed (${response.status})`);
  }
  return payload;
}

function formValues(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function openDialog(id) {
  const dialog = document.getElementById(id);
  if (dialog.showModal) dialog.showModal();
}

function showMessage(message, type) {
  els.message.textContent = message;
  els.message.className = `production-message ${type}`;
}

function clearMessage() {
  els.message.textContent = "";
  els.message.className = "production-message hidden";
}

function text(id, value) { document.getElementById(id).textContent = value; }
function label(value) { return String(value || "-").replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase()); }
function kg(value) { return value == null || value === "" ? "-" : `${Number(value).toFixed(1)} kg`; }
function money(value) { return `R${Number(value || 0).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }
function pct(value, suffix) { return value == null ? "Yield pending" : `${Number(value).toFixed(1)}% ${suffix}`; }
function today() { return new Date().toISOString().slice(0, 10); }
function formatDate(value) { return value ? new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString("en-ZA", { day: "2-digit", month: "short", year: "numeric" }) : "-"; }
function formatTag(value) { const raw = String(value || "-"); return /^\d+$/.test(raw) ? raw.padStart(3, "0") : raw; }
function numberOrNull(value) { return value === "" || value == null ? null : Number(value); }
function escapeHtml(value) { return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;"); }
