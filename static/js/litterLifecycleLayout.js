function lifecycleStage(number, title, subtitle, id) {
  const section = document.createElement("section");
  section.className = "lifecycle-stage";
  section.id = id;
  section.innerHTML = `
    <header class="lifecycle-stage-header">
      <span class="lifecycle-stage-number">${number}</span>
      <div><h2>${title}</h2><p>${subtitle}</p></div>
      <span class="lifecycle-stage-status" data-stage-status="${id}">Nog nie begin nie</span>
    </header>
    <div class="lifecycle-stage-body"></div>`;
  return section;
}

function prepareLitterLifecycleLayout() {
  const workspace = document.querySelector(".litter-workspace");
  const originalMain = document.querySelector(".litter-main-column");
  const originalSide = document.querySelector(".litter-side-column");
  if (!workspace || !originalMain || !originalSide) return;

  const stages = document.createElement("div");
  stages.className = "lifecycle-stages";
  const identity = lifecycleStage("1", "Paring en identiteit", "Die bekende sog, beer en belangrike datums.", "lifecycle_identity");
  const birth = lifecycleStage("2", "Geboorte", "Geboortetellings en die huidige werpselbalans.", "lifecycle_birth");
  const firstCare = lifecycleStage("3", "Eerste behandeling", "4–7 dae, indien dit gedoen word.", "lifecycle_first_care");
  const weaning = lifecycleStage("4", "Speen en tweede behandeling", "Tags, geslag, speengewig, kamp en behandeling op een plek.", "lifecycle_weaning");
  const notes = lifecycleStage("5", "Vrektes en notas", "Teken ’n vrekte of belangrike werpselnota aan.", "lifecycle_notes");

  const summary = document.getElementById("litter_summary_panel");
  const piglets = document.querySelector(".litter-piglet-section");
  const newbornForm = document.getElementById("newborn_health_form");
  const weaningPanel = document.getElementById("weaning_day_panel");
  const deathPanel = document.getElementById("litter_piglet_death_panel");
  if (summary) identity.querySelector(".lifecycle-stage-body").appendChild(summary);

  const birthSnapshot = document.createElement("div");
  birthSnapshot.className = "lifecycle-birth-snapshot";
  birthSnapshot.innerHTML = `
    <div><span>Totaal gekoppel</span><strong id="lifecycle_birth_total">-</strong></div>
    <div><span>Beertjies (telling)</span><strong id="lifecycle_birth_male">-</strong></div>
    <div><span>Sogvarkies (telling)</span><strong id="lifecycle_birth_female">-</strong></div>
    <div><span>Lewend / aktief</span><strong id="lifecycle_birth_active">-</strong></div>
    <div><span>Doodgebore</span><strong id="lifecycle_birth_stillborn">-</strong></div>
    <div><span>Vrektes ná geboorte</span><strong id="lifecycle_birth_deaths">-</strong></div>`;
  birth.querySelector(".lifecycle-stage-body").appendChild(birthSnapshot);

  if (newbornForm) {
    newbornForm.classList.add("lifecycle-primary-form");
    firstCare.querySelector(".lifecycle-stage-body").appendChild(newbornForm);
  }
  const firstCareSummary = document.createElement("div");
  firstCareSummary.id = "lifecycle_first_care_summary";
  firstCareSummary.className = "lifecycle-stage-closure hidden";
  firstCare.querySelector(".lifecycle-stage-body").prepend(firstCareSummary);
  if (piglets) weaning.querySelector(".lifecycle-stage-body").appendChild(piglets);
  if (weaningPanel) weaning.querySelector(".lifecycle-stage-body").appendChild(weaningPanel);
  if (deathPanel) notes.querySelector(".lifecycle-stage-body").appendChild(deathPanel);

  const corrections = document.createElement("details");
  corrections.className = "lifecycle-corrections";
  corrections.innerHTML = `<summary>Regstellings en geskiedenis <span>Maak slegs oop wanneer iets nie klop nie</span></summary><div class="lifecycle-corrections-body"></div>`;
  const correctionsBody = corrections.querySelector(".lifecycle-corrections-body");
  [
    "litter_outcome_active",
    "litter_attention_panel",
    "litter_reconcile_panel",
    "litter_stillborn_panel",
    "litter_manual_actions_panel",
    "litter_sex_count_panel",
  ].forEach((id) => {
    const node = id === "litter_outcome_active" ? document.getElementById(id)?.closest("section") : document.getElementById(id);
    if (node && !correctionsBody.contains(node)) correctionsBody.appendChild(node);
  });

  stages.append(identity, birth, firstCare, weaning, notes, corrections);
  workspace.replaceChildren(stages);
}

prepareLitterLifecycleLayout();

window.renderLitterLifecyclePresentation = function renderLitterLifecyclePresentation(litter) {
  const state = String(litter.detail_state || litter.litter_status || "active").toLowerCase();
  const reconciliation = litter.reconciliation || {};
  const outcomes = litter.lifecycle_outcomes || {};
  const attention = litter.attention || {};
  const active = Number(litter.active_count || 0);
  const stillborn = Number(reconciliation.stillborn_count || outcomes.stillborn || 0);
  const deaths = Number(outcomes.dead || 0) - stillborn;
  const set = (id, value) => { const node = document.getElementById(id); if (node) node.textContent = value; };
  set("lifecycle_birth_total", reconciliation.total_born ?? litter.count ?? "-");
  set("lifecycle_birth_male", litter.male_count ?? "-");
  set("lifecycle_birth_female", litter.female_count ?? "-");
  set("lifecycle_birth_active", active);
  set("lifecycle_birth_stillborn", stillborn);
  set("lifecycle_birth_deaths", Math.max(0, deaths));

  const status = (stage, label, kind = "") => {
    const node = document.querySelector(`[data-stage-status="${stage}"]`);
    if (!node) return;
    node.textContent = label;
    node.className = `lifecycle-stage-status ${kind}`.trim();
  };
  status("lifecycle_identity", "Voltooi", "is-complete");
  status("lifecycle_birth", reconciliation.mismatch ? "Aandag nodig" : "Voltooi", reconciliation.mismatch ? "needs-attention" : "is-complete");
  const firstCareComplete = litter.first_treatment_complete === true;
  const firstCarePartial = litter.first_treatment_partial === true;
  const firstCareSkipped = state !== "active" && !firstCareComplete;
  status("lifecycle_first_care",
    firstCareComplete ? "Voltooi" : firstCareSkipped ? "Oorgeslaan · gesluit" : firstCarePartial ? "Kontroleer" : "Opsioneel",
    firstCareComplete || firstCareSkipped ? "is-complete" : firstCarePartial ? "needs-attention" : "is-current"
  );
  const firstCareSummary = document.getElementById("lifecycle_first_care_summary");
  const newbornForm = document.getElementById("newborn_health_form");
  const firstCareClosed = firstCareComplete || firstCareSkipped || firstCarePartial;
  if (newbornForm) newbornForm.classList.toggle("hidden", firstCareClosed);
  if (firstCareSummary) {
    firstCareSummary.classList.toggle("hidden", !firstCareClosed);
    if (firstCareComplete) {
      const recordCount = Number(litter.first_treatment_record_count || 0);
      const treatmentDate = litter.first_treatment_date || "datum nie beskikbaar nie";
      const tallyText = litter.first_treatment_tally_recorded ? " Die werpselgeslagtelling is aangeteken." : "";
      firstCareSummary.innerHTML = `<strong>Eerste behandeling voltooi</strong><span>${recordCount ? `${recordCount} mediese rekord${recordCount === 1 ? "" : "e"} op ${treatmentDate}.` : `Werpseltelling aangeteken.`}${tallyText} Hierdie stap is gesluit om duplisering te voorkom.</span>`;
    } else if (firstCarePartial) {
      firstCareSummary.innerHTML = `<strong>Behandeling moet gekontroleer word</strong><span>Slegs gedeeltelike mediese bewyse is beskikbaar. Die gewone hele-werpselaksie is gesluit om duplisering te voorkom; gebruik die regstellingspad.</span>`;
    } else {
      firstCareSummary.innerHTML = `<strong>Eerste behandeling oorgeslaan</strong><span>Speen is reeds voltooi. Hierdie vroeë behandelingstap is gesluit en kan nie nou per ongeluk herhaal word nie.</span>`;
    }
  }
  status("lifecycle_weaning", state === "active" ? "Besig" : "Voltooi", state === "active" ? "is-current" : "is-complete");
  status("lifecycle_notes", active ? "Beskikbaar" : "Geskiedenis", active ? "is-current" : "is-complete");

  let nextAction = "Geen verdere werpselaksie word nou vereis nie.";
  let nextReason = "Hierdie werpsel is reeds gespeen of voltooi.";
  if (reconciliation.mismatch) {
    nextAction = "Kontroleer die geboortetellings.";
    nextReason = attention.reason || reconciliation.recommended_action || "Die brontelling en gekoppelde varkies stem nie ooreen nie.";
  } else if (state === "active" && attention.action_type === "mark_weaned") {
    nextAction = "Voltooi Speen en tweede behandeling.";
    nextReason = attention.reason || attention.recommended_action || "Die werpsel is gereed vir die speenwerkvloei.";
  } else if (state === "active") {
    nextAction = "Werk die huidige werpselstadium hieronder by.";
    nextReason = attention.reason || "Gebruik Eerste behandeling indien nodig, of berei Speen voor wanneer dit tyd is.";
  }
  set("lifecycle_next_action", nextAction);
  set("lifecycle_next_reason", nextReason);
};
