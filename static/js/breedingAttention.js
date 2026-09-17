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
const observationCache = new Map();
const placementByPig = new Map();
const heldByPig = new Map();
const localPreview = new URLSearchParams(window.location.search).get("preview") === "animal-evidence-v2";
function apiUrl(path) { return localPreview ? `/preview/api${path}` : `/api/pig-weights${path}`; }

function escapeHtml(value) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
function afEvidenceClass(value) {
  return ({
    "Proven repeat": "Bewese herhaling",
    "Supported cross": "Ondersteunde kruising",
    "Corrective cross": "Korrigerende kruising",
    "Controlled trial": "Beheerde proef",
    "Limited evidence": "Beperkte bewyse",
  })[value] || "Beperkte bewyse";
}
function afState(value) {
  return ({
    "Post-litter recovery": "Herstel ná werpsel",
    "Pregnancy evidence": "Dragtigheidsbewys",
    "Needs Data": "Benodig duidelikheid",
    "Expected to farrow — overdue evidence review": "Verwagte jong-uitkoms nog nie afgesluit nie",
    "Historical pregnancy result; current status Unknown": "Vorige dragtigheidsuitslag; huidige toestand onbekend",
    "Assumed Pregnant": "Waarskynlik dragtig",
    "Inconclusive": "Onbeslis",
    "Ready for review": "Gereed vir hersiening",
  })[value] || value || "Onbekend";
}
function afHoldReason(value) {
  const text = String(value || "");
  if (text.includes("canonical mating was") && text.includes("days ago")) {
    const days = text.match(/was (\d+) days ago/)?.[1];
    return `Die huidige paring is ${days || "verskeie"} dae gelede; die siklusuitkoms moet eers afgesluit word.`;
  }
  if (text.includes("pregnancy result does not establish current pregnancy status")) return "Die vorige dragtigheidsuitslag bewys nie die huidige toestand nie.";
  if (text.includes("current litter closes the prior mating cycle") || text.includes("remains unweaned")) return "’n Huidige werpsel is nog aktief of ongespeen.";
  if (text.includes("Assumed Pregnant")) return "Waarskynlik dragtig volgens huidige waarneming; nie klinies bevestig nie.";
  if (text.includes("Inconclusive")) return "Die huidige voortplantingsiklus bly onbeslis.";
  return text || "Huidige lewensiklus blokkeer plasing.";
}
function practicalAttention(row) {
  const held = heldByPig.get(row.pig_id);
  if (held) return afHoldReason(held.reason || held.state);
  const assignment = placementByPig.get(row.pig_id);
  if (assignment) return "Geen huidige blokker; kontroleer die gekose beer voor plasing.";
  const conflicts = row.conflicting_facts || [];
  if (conflicts.length) return `Teenstrydig: ${conflicts.join("; ")}`;
  if ((row.current_state || "").includes("overdue")) return "Die verwagte jong-/dragtigheidsiklus moet eers afgesluit word.";
  if (row.current_state === "Post-litter recovery") return "Bevestig die werklike speenuitkoms en hersteltoestand.";
  return "Geen dringende menslike aksie uit die huidige plan nie.";
}
function heldEvidenceText(held) {
  const score = held.body_condition_score;
  const observed = held.body_condition_observed_at
    ? new Date(held.body_condition_observed_at).toLocaleDateString("af-ZA")
    : "Onbekend";
  if (score != null) {
    return `Liggaamskondisie ${score}; waargeneem ${observed}. ${afHoldReason(held.reason || held.state)}`;
  }
  return afHoldReason(held.reason || held.state);
}
function planCell(row) {
  const assignment = placementByPig.get(row.pig_id);
  if (assignment) return `<div class="breeding-plan-cell"><span class="breeding-plan-badge ${assignment.kind === "immediate" ? "is-now" : "is-next"}">${assignment.kind === "immediate" ? "Voorgestelde plasing" : "Volgende voorgestelde groep"}</span><strong>${escapeHtml(assignment.boar_name)}</strong><small>Planvenster: ${escapeHtml(assignment.start_date)} tot ${escapeHtml(assignment.end_date)}</small><small>Nie bewys van werklike plasing of diens nie.</small><small>${escapeHtml(afEvidenceClass(assignment.evidence_class))}</small></div>`;
  const held = heldByPig.get(row.pig_id);
  if (held) return `<div class="breeding-plan-cell"><span class="breeding-plan-badge is-held">${held.state === "Boar exposure active" ? "Tans by beer" : "Herstelhouvas"}</span><small>${escapeHtml(heldEvidenceText(held))}</small></div>`;
  return `<span class="breeding-plan-none">Nog nie in die huidige plasingsplan nie.</span>`;
}
function render() {
  const selected = filter.value;
  const visible = selected ? rows.filter(row => row.filter_state === selected) : rows;
  body.innerHTML = visible.length ? visible.map(row => {
    return `<tr><td data-label="Dier"><a class="detail-link" href="${escapeHtml(row.animal_href)}">${escapeHtml(row.tag_number || row.pig_id)}</a><span class="breeding-animal-id">${escapeHtml(row.pig_id)}</span></td>
      <td data-label="Jongste waarneming">${observationSummaryCell(row)}</td>
      <td data-label="Teelplan">${planCell(row)}</td>
      <td data-label="Huidige toestand"><strong>${escapeHtml(afState(row.current_state))}</strong><span class="breeding-confidence">Bewyssekerheid: ${escapeHtml(row.confidence || "Onbekend")}</span></td>
      <td data-label="Werklike aandag">${escapeHtml(practicalAttention(row))}</td><td data-label="Volgende stap">${escapeHtml(placementByPig.has(row.pig_id) ? "Volg die plasingsplan en teken die werklike diens later aan." : heldByPig.has(row.pig_id) ? "Sluit die genoemde lewensiklus of houvas met werklike bewyse af." : "Hersien net wanneer nuwe feite beskikbaar is.")}</td>
      <td class="breeding-row-action"><button type="button" class="secondary-button observation-review" data-pig-id="${escapeHtml(row.pig_id)}">Besonderhede / Neem waar</button></td></tr>`;
  }).join("") : `<tr><td colspan="7" class="table-empty">Geen diere in hierdie aandagstatus nie.</td></tr>`;
  hydrateVisibleObservations(visible);
}

function observationSummaryCell(row) {
  const cached = observationCache.get(row.pig_id);
  if (!cached) return `<span class="breeding-observation-loading">Laai dier se waarneming…</span>`;
  if (cached.status === "error") return `<span class="breeding-observation-unavailable">Waarneming nie beskikbaar nie — dit beteken nie geen rekord nie.</span>`;
  const item = cached.latest;
  if (!item) return `<span class="breeding-observation-empty">Nog geen teelwaarneming aangeteken nie.</span>`;
  const facts = observationFactSummary(item);
  const when = new Date(item.observed_at).toLocaleString("af-ZA", {dateStyle:"medium", timeStyle:"short"});
  return `<div class="breeding-latest-observation">
    <div><span class="breeding-recorded-badge">Aangeteken</span><time>${escapeHtml(when)}</time></div>
    <p>${escapeHtml(item.factual_note || "Feitelike nota nie beskikbaar nie.")}</p>
    ${facts.length ? `<ul>${facts.slice(0, 4).map(fact => `<li>${escapeHtml(fact)}</li>`).join("")}</ul>` : ""}
    ${item.measurements?.follow_up ? `<small><strong>Opvolg:</strong> ${escapeHtml(item.measurements.follow_up)}</small>` : ""}
  </div>`;
}

async function hydrateVisibleObservations(visible) {
  const pending = visible.filter(row => !observationCache.has(row.pig_id));
  if (!pending.length) return;
  pending.forEach(row => observationCache.set(row.pig_id, {status:"loading"}));
  await Promise.all(pending.map(async row => {
    try {
      const response = await fetch(apiUrl(`/breeding-attention/${encodeURIComponent(row.pig_id)}/observations`));
      const data = await response.json();
      observationCache.set(row.pig_id, response.ok && data.success
        ? {status:"ready", latest:(data.history || [])[0] || null}
        : {status:"error"});
    } catch (_) {
      observationCache.set(row.pig_id, {status:"error"});
    }
  }));
  render();
}
function renderWorklist(loop) {
  placementByPig.clear(); heldByPig.clear();
  if (!loop || loop.success !== true) {
    worklistStatus.textContent = "Werklys is nie beskikbaar nie — dit beteken nie nul nie.";
    worklistTasks.innerHTML = "";
    return;
  }
  worklistStatus.textContent = `${loop.task_count} huidige taak/take; week van ${loop.week_start}. Waarneming, paring en herinnering-uitvoering is afgeskakel.`;
  const schedule = loop.placement_cohorts;
  if (schedule && Array.isArray(schedule.cohorts)) {
    schedule.cohorts.forEach(cohort => cohort.females.forEach(row => placementByPig.set(row.pig_id, {...row, kind:cohort.kind, boar_name:cohort.boar_name, start_date:cohort.start_date, end_date:cohort.end_date})));
    (schedule.held || []).forEach(row => heldByPig.set(row.pig_id, row));
    const immediate = schedule.cohorts.filter(row => row.kind === "immediate");
    const next = schedule.cohorts.filter(row => row.kind !== "immediate");
    const cohortSection = (title, items, css) => `<section class="breeding-cohort ${css}"><div class="breeding-cohort-heading"><span>${title}</span><strong>${items.reduce((total, item) => total + item.females.length, 0)} sôe</strong></div>${items.map(cohort => `<article class="breeding-boar-group"><header><strong>${escapeHtml(cohort.boar_name)}</strong><span>${escapeHtml(cohort.start_date)} tot ${escapeHtml(cohort.end_date)}</span></header>${cohort.females.map(row => `<button type="button" class="breeding-female-chip worklist-observe" data-pig-id="${escapeHtml(row.pig_id)}"><strong>${escapeHtml(row.name)}</strong><small>${escapeHtml(afEvidenceClass(row.evidence_class))}</small></button>`).join("")}</article>`).join("") || `<p>Geen groep nie.</p>`}</section>`;
    const active = schedule.current_exposures || [];
    const activeSection = active.length ? `<section class="breeding-cohort held"><div class="breeding-cohort-heading"><span>Tans by beer</span><strong>${active.length} sôe</strong></div>${active.map(row => `<button type="button" class="breeding-held-row worklist-observe" data-pig-id="${escapeHtml(row.pig_id)}"><strong>${escapeHtml(row.name)} — ${escapeHtml(row.boar_name)}</strong><small>IN ${escapeHtml(row.in_date || "Onbekend")}; beplan UIT ${escapeHtml(row.planned_out_date || "Onbekend")}; ${escapeHtml(row.current_pen_name || "Hok onbekend")}</small></button>`).join("")}</section>` : "";
    worklistTasks.innerHTML = activeSection + cohortSection("Voorgestelde plasing", immediate, "is-immediate") + cohortSection("Volgende voorgestelde groep", next, "is-next") + (schedule.held?.length ? `<section class="breeding-cohort held"><div class="breeding-cohort-heading"><span>Herstel / houvas</span><strong>${schedule.held.length} sôe</strong></div>${schedule.held.map(row => `<button type="button" class="breeding-held-row worklist-observe" data-pig-id="${escapeHtml(row.pig_id)}"><strong>${escapeHtml(row.name)}</strong><small>${escapeHtml(heldEvidenceText(row))}</small></button>`).join("")}</section>` : "");
    return;
  }
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
    const response = await fetch(apiUrl("/breeding-attention"));
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.limitations?.[0] || "Teelbewyse is nie beskikbaar nie.");
    const currentCases = new Map((data.operating_loop?.cases || []).map(item => [item.pig_id, item]));
    rows = (data.animals || []).map(row => {
      const current = currentCases.get(row.pig_id)?.classification;
      return current ? {...row, current_state:current.state, current_state_reason:current.reason} : row;
    });
    observationCache.clear();
    filter.innerHTML = `<option value="">Alle huidige sôe en jong sôe</option>` +
      (data.filters || []).map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
    freshness.textContent = `Bewyse: ${data.source_status}; waargeneem ${data.observation_timestamp || "Onbekend"}.`;
    renderWorklist(data.operating_loop);
    const observed = rows.filter(row => (data.operating_loop?.cases || []).find(item => item.pig_id === row.pig_id)?.observation_history?.length).length;
    counts.innerHTML = `<div><span class="info-title">Voorgestelde plasing</span><span class="info-value">${[...placementByPig.values()].filter(row => row.kind === "immediate").length}</span><small>Plan alleen; nie werklike plasing nie</small></div><div><span class="info-title">Volgende voorstel</span><span class="info-value">${[...placementByPig.values()].filter(row => row.kind !== "immediate").length}</span><small>Plan alleen; geen diens afgelei nie</small></div><div><span class="info-title">Herstel / houvas</span><span class="info-value">${heldByPig.size}</span><small>Nie tans geskik vir plasing nie</small></div><div><span class="info-title">Met waarnemings</span><span class="info-value">${observed}</span><small>Feitelike dierbewyse beskikbaar</small></div>`;
    render();
  } catch (error) {
    rows = []; counts.innerHTML = ""; renderWorklist(null);
    freshness.textContent = "Bewyse is nie beskikbaar nie — tellings is nie noodwendig nul nie.";
    message.classList.remove("hidden"); message.textContent = error.message;
    body.innerHTML = `<tr><td colspan="7" class="table-empty">Benodig data — kanonieke bewyse is nie beskikbaar nie.</td></tr>`;
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
  document.getElementById("observation_context").textContent = `${afState(activeRow.current_state)}. ${practicalAttention(activeRow)}`;
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
  const response = await fetch(apiUrl(`/breeding-attention/${encodeURIComponent(pigId)}/observations`));
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
  const response = await fetch(apiUrl(`/breeding-attention/${encodeURIComponent(activeRow.pig_id)}/observations/preview`), {
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
  const response = await fetch(apiUrl(`/breeding-attention/${encodeURIComponent(activeRow.pig_id)}/observations`), {
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
