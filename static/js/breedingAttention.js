const body = document.getElementById("attention_body");
const filter = document.getElementById("attention_filter");
const counts = document.getElementById("attention_counts");
const freshness = document.getElementById("attention_freshness");
const message = document.getElementById("attention_message");
const worklistStatus = document.getElementById("breeding_worklist_status");
const worklistTasks = document.getElementById("breeding_worklist_tasks");
let rows = [];
let activeRow = null;
let acceptedPreviewPayload = null;

function escapeHtml(value) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
function render() {
  const selected = filter.value;
  const visible = selected ? rows.filter(row => row.filter_state === selected) : rows;
  body.innerHTML = visible.length ? visible.map(row => {
    const dates = row.evidence_dates || {};
    const facts = [...(row.missing_facts || []), ...(row.conflicting_facts || [])];
    return `<tr><td data-label="Dier"><a class="detail-link" href="${escapeHtml(row.animal_href)}">${escapeHtml(row.tag_number || row.pig_id)}</a></td>
      <td data-label="Huidige toestand">${escapeHtml(row.current_state)}</td><td data-label="Bewysdatums">Paring: ${escapeHtml(dates.latest_mating || "Onbekend")}<br>Werpsel: ${escapeHtml(dates.latest_litter || "Onbekend")}</td>
      <td data-label="Varsheid">${escapeHtml(row.freshness || "Onbekend")}</td><td data-label="Sekerheid">${escapeHtml(row.confidence || "Onbekend")}</td>
      <td data-label="Ontbrekend / teenstrydig">${escapeHtml(facts.join("; ") || "Geen bewysde gaping")}</td><td data-label="Volgende stap">${escapeHtml(row.recommended_human_action)}</td>
      <td class="breeding-row-action"><button type="button" class="secondary-button observation-review" data-pig-id="${escapeHtml(row.pig_id)}">Besonderhede / Neem waar</button></td></tr>`;
  }).join("") : `<tr><td colspan="8" class="table-empty">Geen diere in hierdie aandagstatus nie.</td></tr>`;
}
function renderWorklist(loop) {
  if (!loop || loop.success !== true) {
    worklistStatus.textContent = "Werklys is nie beskikbaar nie — dit beteken nie nul nie.";
    worklistTasks.innerHTML = "";
    return;
  }
  worklistStatus.textContent = `${loop.task_count} huidige taak/take; week van ${loop.week_start}. Waarneming, paring en herinnering-uitvoering is afgeskakel.`;
  worklistTasks.innerHTML = (loop.tasks || []).length
    ? loop.tasks.map(task => {
        const pairing = task.male_recommendation || {};
        const primary = pairing.recommended?.tag_number || "Nog geen veilige keuse";
        const reserve = pairing.reserve?.tag_number || pairing.alternatives?.[0]?.tag_number || "Geen";
        const schedule = task.exposure_start_date && task.exposure_end_date
          ? `Plaas: ${escapeHtml(task.exposure_start_date)} tot ${escapeHtml(task.exposure_end_date)} (${escapeHtml(task.exposure_days)} dae). Geen presiese diensdatum word afgelei nie.`
          : "Geen blootstellingsvenster totdat die huidige lewensiklus dit ondersteun nie.";
        return `<article class="breeding-task" data-task-id="${escapeHtml(task.task_id)}">
        <div><strong><a class="detail-link" href="${escapeHtml(task.animal_href)}">${escapeHtml(task.tag_number)}</a></strong><span class="task-state">${escapeHtml(task.task_group)}</span></div>
        <div><span>${escapeHtml(task.why)}</span><span class="task-checks">Speen: ${escapeHtml(task.weaning_date || "Onbekend")} (${escapeHtml(task.days_since_weaning ?? "Onbekend")} dae). Primêr: ${escapeHtml(primary)}; reserwe: ${escapeHtml(reserve)}. ${schedule} Opsionele ontbrekende waarnemings blokkeer nie plasing nie.</span></div>
        <button type="button" class="secondary-button worklist-observe" data-pig-id="${escapeHtml(task.pig_id)}">Hersien bewyse</button>
      </article>`; }).join("")
    : `<p class="table-empty">Geen dier verg aandag volgens die huidige bewyse nie.</p>`;
}
async function load() {
  try {
    const response = await fetch("/api/pig-weights/breeding-attention");
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.limitations?.[0] || "Teelbewyse is nie beskikbaar nie.");
    rows = data.animals || [];
    filter.innerHTML = `<option value="">Alle huidige sôe en jong sôe</option>` +
      (data.filters || []).map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
    counts.innerHTML = (data.filters || []).map(name => `<div><span class="info-title">${escapeHtml(name)}: </span><span class="info-value">${escapeHtml(data.counts?.[name] ?? "Unknown")}</span></div>`).join("");
    freshness.textContent = `Bewyse: ${data.source_status}; waargeneem ${data.observation_timestamp || "Onbekend"}.`;
    renderWorklist(data.operating_loop);
    render();
  } catch (error) {
    rows = []; counts.innerHTML = ""; renderWorklist(null);
    freshness.textContent = "Bewyse is nie beskikbaar nie — tellings is nie noodwendig nul nie.";
    message.classList.remove("hidden"); message.textContent = error.message;
    body.innerHTML = `<tr><td colspan="8" class="table-empty">Benodig data — kanonieke bewyse is nie beskikbaar nie.</td></tr>`;
  }
}
filter.addEventListener("change", render);
document.addEventListener("DOMContentLoaded", load);

const panel = document.getElementById("observation_panel");
const history = document.getElementById("observation_history");
const previewBox = document.getElementById("observation_preview");
const recordButton = document.getElementById("obs_record");
function localNow() {
  const value = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  return value.toISOString().slice(0, 16);
}
function observationPayload(idempotencyKey) {
  return {
    observed_at: new Date(document.getElementById("obs_time").value).toISOString(),
    body_condition_score: document.getElementById("obs_bcs").value || null,
    visible_build: document.getElementById("obs_build").value,
    feet_legs_movement: document.getElementById("obs_legs").value,
    visible_injury: document.getElementById("obs_injury").value,
    standing_heat: document.getElementById("obs_heat").value,
    temperament: document.getElementById("obs_temperament").value,
    suitability_concern: document.getElementById("obs_suitability").value,
    factual_note: document.getElementById("obs_note").value,
    follow_up: document.getElementById("obs_follow_up").value,
    idempotency_key: idempotencyKey,
  };
}
async function openObservation(pigId) {
  activeRow = rows.find(row => row.pig_id === pigId);
  if (!activeRow) return;
  acceptedPreviewPayload = null; recordButton.disabled = true;
  panel.classList.remove("hidden");
  document.getElementById("observation_heading").textContent = `Feitelike waarneming — ${activeRow.tag_number || activeRow.pig_id}`;
  document.getElementById("observation_context").textContent = `${activeRow.current_state}; ontbreek: ${(activeRow.missing_facts || []).join(", ") || "niks"}.`;
  document.getElementById("obs_time").value = localNow();
  previewBox.classList.add("hidden");
  await refreshObservationHistory(pigId);
  panel.scrollIntoView({behavior:"smooth", block:"start"});
}

function observationFactSummary(item) {
  const values = item.measurements || {};
  const facts = [];
  if (values.body_condition_score != null) facts.push(`Liggaamskondisie ${values.body_condition_score}`);
  if (values.standing_heat === "observed") facts.push("Staande hitte waargeneem");
  if (values.standing_heat === "not_observed") facts.push("Geen staande hitte waargeneem nie");
  if (values.feet_legs_movement === "no_visible_concern") facts.push("Bene, pote en beweging sonder sigbare kommer");
  if (values.feet_legs_movement === "concern") facts.push("Kommer oor bene, pote of beweging");
  if (values.visible_injury === "none_observed") facts.push("Geen sigbare besering");
  if (values.visible_injury === "concern") facts.push("Sigbare beseringskommer");
  if (values.temperament === "calm") facts.push("Kalm temperament");
  if (values.temperament === "watchful") facts.push("Waaksame temperament");
  if (values.temperament === "difficult") facts.push("Moeilik om te hanteer");
  if (values.suitability_concern === "none_observed") facts.push("Geen teelgeskiktheidskommer waargeneem nie");
  if (values.suitability_concern === "concern") facts.push("Teelgeskiktheidskommer waargeneem");
  return facts;
}

async function refreshObservationHistory(pigId) {
  const response = await fetch(`/api/pig-weights/breeding-attention/${encodeURIComponent(pigId)}/observations`);
  const data = await response.json();
  if (!response.ok || !data.success) {
    history.className = "breeding-history breeding-history-error";
    history.textContent = "Waarnemingsgeskiedenis is nie beskikbaar nie — dit beteken nie nul nie.";
    return;
  }
  const items = data.history || [];
  history.className = "breeding-history";
  history.innerHTML = items.length
    ? `<div class="breeding-history-title"><strong>${items.length} aangetekende waarneming(s)</strong><span>Nuutste eerste</span></div>` + items.map(item => {
        const facts = observationFactSummary(item);
        const followUp = item.measurements?.follow_up;
        return `<article class="breeding-history-item">
          <div><strong>${escapeHtml(new Date(item.observed_at).toLocaleString("af-ZA"))}</strong><span class="breeding-recorded-badge">Aangeteken</span></div>
          <p>${escapeHtml(item.factual_note)}</p>
          ${facts.length ? `<small>${escapeHtml(facts.join(" · "))}</small>` : ""}
          ${followUp ? `<small><strong>Opvolg:</strong> ${escapeHtml(followUp)}</small>` : ""}
          <code>${escapeHtml(item.observation_event_id)}</code>
        </article>`;
      }).join("")
    : "Geen teelwaarnemings is aangeteken nie.";
}
body.addEventListener("click", event => {
  const button = event.target.closest(".observation-review");
  if (button) openObservation(button.dataset.pigId);
});
worklistTasks.addEventListener("click", event => {
  const button = event.target.closest(".worklist-observe");
  if (button) openObservation(button.dataset.pigId);
});
document.getElementById("observation_close").addEventListener("click", () => panel.classList.add("hidden"));
document.getElementById("obs_preview").addEventListener("click", async () => {
  if (!activeRow) return;
  const payload = observationPayload(crypto.randomUUID());
  const response = await fetch(`/api/pig-weights/breeding-attention/${encodeURIComponent(activeRow.pig_id)}/observations/preview`, {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)
  });
  const data = await response.json();
  acceptedPreviewPayload = response.ok && data.success ? payload : null;
  recordButton.disabled = !acceptedPreviewPayload;
  previewBox.classList.remove("hidden");
  const change = data.system_recommendation?.advisory_change;
  previewBox.textContent = acceptedPreviewPayload
    ? `Waargeneem: slegs feitelike bewyse. Vertolking: ${data.owner_interpretation} Uitwerking: ${data.system_recommendation.effect.join(" ")} Voorheen: ${change.before.state} — ${change.before.recommended_human_action}. Indien aangeteken: ${change.after_if_recorded.state} — ${change.after_if_recorded.recommended_human_action}. Huidige advies bly onveranderd totdat dit aangeteken word.`
    : (data.status || "Voorskou is nie beskikbaar nie.");
});
document.getElementById("observation_form").addEventListener("input", () => {
  acceptedPreviewPayload = null; recordButton.disabled = true;
});
document.getElementById("observation_form").addEventListener("submit", async event => {
  event.preventDefault();
  if (!activeRow || !acceptedPreviewPayload) return;
  const payload = {...acceptedPreviewPayload};
  const response = await fetch(`/api/pig-weights/breeding-attention/${encodeURIComponent(activeRow.pig_id)}/observations`, {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)
  });
  const data = await response.json();
  acceptedPreviewPayload = null; recordButton.disabled = true;
  previewBox.classList.remove("hidden");
  previewBox.classList.toggle("breeding-save-success", response.ok && data.success);
  previewBox.classList.toggle("breeding-save-error", !response.ok || !data.success);
  previewBox.textContent = response.ok && data.success
    ? `AANGETEKEN — hierdie waarneming is veilig gestoor as ${data.observation_event_id}. Moenie dit weer invoer nie.`
    : `NIE AANGETEKEN NIE — ${data.status || "die waarneming kon nie gestoor word nie"}.`;
  if (response.ok && data.success) {
    await load();
    await refreshObservationHistory(activeRow.pig_id);
    previewBox.scrollIntoView({behavior:"smooth", block:"center"});
  }
});
