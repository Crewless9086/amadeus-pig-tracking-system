const familyTreeMessage = document.getElementById("family_tree_message");
const familyTreeMother = document.getElementById("family_tree_mother");
const familyTreeFather = document.getElementById("family_tree_father");
const familyTreeCurrent = document.getElementById("family_tree_current");
const familyTreeSiblings = document.getElementById("family_tree_siblings");
const familyTreeSiblingCount = document.getElementById("family_tree_sibling_count");
const familyTreeDecisionPanel = document.getElementById("family_tree_decision_panel");
const familyTreeBreedingDetailLink = document.getElementById("family_tree_breeding_detail_link");
const familyTreeLitterRows = document.getElementById("family_tree_litter_rows");
const familyTreeQualityFlags = document.getElementById("family_tree_quality_flags");

function getPigIdFromFamilyTreeUrl() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 2] || "");
}

function pigProfileHref(pigId) {
  return `/pig/${encodeURIComponent(pigId)}`;
}

function updatePigProfileBackLink(elementId, pigId) {
  const link = document.getElementById(elementId);
  if (!link) return;
  link.href = pigProfileHref(pigId);
  link.textContent = "<- Back to Pig Profile";
}

function showFamilyTreeMessage(message, type = "error") {
  familyTreeMessage.classList.remove("hidden", "message-success", "message-error");
  familyTreeMessage.classList.add(type === "success" ? "message-success" : "message-error");
  familyTreeMessage.textContent = message;
}

function hideFamilyTreeMessage() {
  familyTreeMessage.classList.add("hidden");
  familyTreeMessage.textContent = "";
}

function resetFamilyTreeUi() {
  hideFamilyTreeMessage();
  familyTreeMother.innerHTML = "";
  familyTreeFather.innerHTML = "";
  familyTreeCurrent.innerHTML = "";
  familyTreeSiblings.innerHTML = "";
  familyTreeSiblingCount.textContent = "";
  familyTreeDecisionPanel?.classList.add("hidden");
  if (familyTreeLitterRows) familyTreeLitterRows.innerHTML = "";
  if (familyTreeQualityFlags) familyTreeQualityFlags.innerHTML = "";
}

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(decimals);
}

function formatInteger(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return String(Math.round(Number(value)));
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(1)}%`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function animalLabel(pig) {
  if (!pig) return "-";
  return pig.tag_number || pig.pig_id || "-";
}

function breedingDetailHref(pigId) {
  const params = new URLSearchParams({
    return_to: window.location.pathname,
    return_label: "Back to Family Tree",
  });
  return `/breeding-analytics/${encodeURIComponent(pigId)}?${params.toString()}`;
}

function litterHref(litterId) {
  const params = new URLSearchParams({
    return_to: window.location.pathname,
    return_label: "Back to Family Tree",
  });
  return `/litter/${encodeURIComponent(litterId)}?${params.toString()}`;
}

function buildFamilyCard(pig, roleLabel = "") {
  if (!pig) {
    return `
      <div class="family-card family-card-empty">
        <span class="detail-label">${roleLabel || "Unknown"}</span>
        <span class="detail-value">-</span>
      </div>
    `;
  }

  return `
    <a href="/pig/${encodeURIComponent(pig.pig_id)}" class="family-card">
      ${roleLabel ? `<span class="detail-label">${roleLabel}</span>` : ""}
      <span class="detail-value">${escapeHtml(pig.tag_number || pig.pig_id)}</span>
      <span class="pig-list-meta">Pig ID: ${escapeHtml(pig.pig_id)}</span>
      <span class="pig-list-submeta">${escapeHtml(pig.sex || "-")} | ${escapeHtml(pig.calculated_stage || "-")}</span>
      <span class="pig-list-submeta">${pig.current_weight_kg !== null && pig.current_weight_kg !== "" ? `${formatNumber(pig.current_weight_kg, 2)} kg` : "No weight"}</span>
    </a>
  `;
}

function buildSiblingCard(pig) {
  const card = document.createElement("a");
  card.className = "pig-list-card";
  card.href = `/pig/${encodeURIComponent(pig.pig_id)}`;

  const topRow = document.createElement("div");
  topRow.className = "pig-list-top";

  const tag = document.createElement("div");
  tag.className = "pig-list-tag";
  tag.textContent = pig.tag_number || pig.pig_id;

  const action = document.createElement("div");
  action.className = "pig-list-action";
  action.textContent = "Open Profile";

  topRow.appendChild(tag);
  topRow.appendChild(action);

  const meta = document.createElement("div");
  meta.className = "pig-list-meta";
  meta.textContent = `Pig ID: ${pig.pig_id}`;

  const subMeta = document.createElement("div");
  subMeta.className = "pig-list-submeta";
  subMeta.textContent =
    `${pig.sex || "-"} | ${pig.calculated_stage || "-"} | ${pig.current_weight_kg !== null && pig.current_weight_kg !== "" ? `${formatNumber(pig.current_weight_kg, 2)} kg` : "No weight"}`;

  const extra = document.createElement("div");
  extra.className = "sales-meta-grid";
  extra.innerHTML = `
    <div><span class="history-label">Status</span><span class="history-value">${escapeHtml(pig.status || "-")}</span></div>
    <div><span class="history-label">On Farm</span><span class="history-value">${escapeHtml(pig.on_farm || "-")}</span></div>
    <div><span class="history-label">Age (Days)</span><span class="history-value">${escapeHtml(pig.age_days || "-")}</span></div>
    <div><span class="history-label">Pen</span><span class="history-value">${escapeHtml(pig.current_pen_id || "-")}</span></div>
  `;

  card.appendChild(topRow);
  card.appendChild(meta);
  card.appendChild(subMeta);
  card.appendChild(extra);

  return card;
}

function setMetric(elementId, value, formatter = formatInteger) {
  const element = document.getElementById(elementId);
  if (!element) return;
  element.textContent = formatter(value);
}

function pairLabel(row) {
  const sow = row.sow_tag_number || row.sow_pig_id || "-";
  const boar = row.boar_tag_number || row.boar_pig_id || "-";
  return `${sow} x ${boar}`;
}

function renderLitterOutcomes(litters) {
  if (!familyTreeLitterRows) return;
  if (!litters.length) {
    familyTreeLitterRows.innerHTML = `
      <div class="empty-state family-empty-state">
        <strong>No litter outcomes found.</strong>
        <span>This animal has no linked litters in breeding analytics yet.</span>
      </div>
    `;
    return;
  }

  familyTreeLitterRows.innerHTML = litters.slice(0, 6).map((litter) => {
    const litterId = litter.litter_id || "";
    const litterLabel = litterId
      ? `<a class="detail-link family-litter-link" href="${litterHref(litterId)}">${escapeHtml(litterId)}</a>`
      : "-";
    const flags = (litter.quality_flags || []).length
      ? `<span class="status-pill status-pill-warning">${escapeHtml((litter.quality_flags || []).length)} flag(s)</span>`
      : '<span class="status-pill status-pill-muted">Clear</span>';
    return `
      <article class="family-outcome-row">
        <div>
          <span class="history-label">${escapeHtml(litter.farrowing_date || "No date")}</span>
          <strong>${litterLabel}</strong>
          <small>${escapeHtml(pairLabel(litter))}</small>
        </div>
        <dl>
          <div><dt>Born</dt><dd>${escapeHtml(formatInteger(litter.born_alive))}</dd></div>
          <div><dt>Weaned</dt><dd>${escapeHtml(formatInteger(litter.weaned_count))}</dd></div>
          <div><dt>Active / Exited</dt><dd>${escapeHtml(formatInteger(litter.active_pig_count))} / ${escapeHtml(formatInteger(litter.exited_pig_count))}</dd></div>
          <div><dt>Avg Weight</dt><dd>${escapeHtml(formatNumber(litter.average_current_weight_kg, 1))} kg</dd></div>
        </dl>
        ${flags}
      </article>
    `;
  }).join("");
}

function renderQualityFlags(dataQuality) {
  if (!familyTreeQualityFlags) return;
  const flags = dataQuality?.flags || [];
  if (!flags.length) {
    familyTreeQualityFlags.innerHTML = '<span class="quality-flag-muted">No data-quality flags found for this breeding animal.</span>';
    return;
  }
  familyTreeQualityFlags.innerHTML = flags
    .map((flag) => `<span class="quality-flag">${escapeHtml(flag)}</span>`)
    .join("");
}

function renderBreedingDecision(data, pigId) {
  if (!familyTreeDecisionPanel || !data?.success) return;
  const animal = data.animal || {};
  const litters = data.litters || [];

  document.getElementById("family_tree_decision_kicker").textContent = `${data.animal_type || "Breeding animal"} decision view`;
  document.getElementById("family_tree_decision_title").textContent = `Breeding Summary: ${animalLabel(animal)}`;
  document.getElementById("family_tree_decision_subtitle").textContent =
    `${litters.length} litter outcome(s), ${(data.matings || []).length} mating record(s), ${(data.data_quality?.flag_count ?? 0)} data-quality flag(s).`;
  document.getElementById("family_tree_litter_summary").textContent =
    litters.length ? "Latest linked litters and piglet outcomes from breeding analytics." : "No litter outcomes are linked to this animal yet.";

  setMetric("family_tree_mating_count", animal.mating_count);
  setMetric("family_tree_litter_count", animal.litter_count);
  setMetric("family_tree_born_alive_total", animal.born_alive_total);
  setMetric("family_tree_weaned_total", animal.weaned_total);
  setMetric("family_tree_survival_pct", animal.survival_pct, formatPercent);
  setMetric("family_tree_open_count", animal.open_count);
  setMetric("family_tree_repeat_service_count", animal.repeat_service_count);
  setMetric("family_tree_quality_count", data.data_quality?.flag_count);

  if (familyTreeBreedingDetailLink) {
    familyTreeBreedingDetailLink.href = breedingDetailHref(pigId);
  }
  renderLitterOutcomes(litters);
  renderQualityFlags(data.data_quality || {});
  familyTreeDecisionPanel.classList.remove("hidden");
}

async function loadBreedingDecisionContext(pigId) {
  if (!familyTreeDecisionPanel) return;
  try {
    const response = await fetch(`/api/pig-weights/breeding-analytics/${encodeURIComponent(pigId)}`);
    const data = await response.json();
    if (!response.ok || !data.success) {
      familyTreeDecisionPanel.classList.add("hidden");
      return;
    }
    renderBreedingDecision(data, pigId);
  } catch (error) {
    console.error("loadBreedingDecisionContext error:", error);
    familyTreeDecisionPanel.classList.add("hidden");
  }
}

async function loadFamilyTree() {
  const pigId = getPigIdFromFamilyTreeUrl();
  resetFamilyTreeUi();

  if (!pigId) {
    showFamilyTreeMessage("No pig ID found in URL.", "error");
    return;
  }

  updatePigProfileBackLink("family_tree_back_link", pigId);
  document.getElementById("family_tree_profile_button").href = pigProfileHref(pigId);

  try {
    const response = await fetch(`/api/pig-weights/pig/${encodeURIComponent(pigId)}/family-tree`);
    const data = await response.json();

    if (!response.ok || !data.success) {
      resetFamilyTreeUi();
      showFamilyTreeMessage(data.error || "Could not load family tree.", "error");
      return;
    }

    const tree = data.tree;

    document.getElementById("family_tree_title").textContent = `Family Tree: ${tree.current_pig.tag_number || tree.current_pig.pig_id}`;
    document.getElementById("family_tree_subtitle").textContent = `Pig ID: ${tree.current_pig.pig_id}`;

    familyTreeMother.innerHTML = buildFamilyCard(tree.mother, "Mother");
    familyTreeFather.innerHTML = buildFamilyCard(tree.father, "Father");
    familyTreeCurrent.innerHTML = buildFamilyCard(tree.current_pig, "Current Pig");

    familyTreeSiblingCount.textContent = `${tree.sibling_count} sibling(s) found${tree.litter_id ? ` in litter ${tree.litter_id}` : ""}`;

    familyTreeSiblings.innerHTML = "";

    if (!tree.siblings.length) {
      familyTreeSiblings.innerHTML = `
        <div class="empty-state">
          <strong>No siblings found.</strong>
          <span>This pig may not yet be linked to other littermates.</span>
        </div>
      `;
    } else {
      tree.siblings.forEach((pig) => {
        familyTreeSiblings.appendChild(buildSiblingCard(pig));
      });
    }

    await loadBreedingDecisionContext(pigId);
  } catch (error) {
    console.error("loadFamilyTree error:", error);
    resetFamilyTreeUi();
    showFamilyTreeMessage("Something went wrong while loading family tree.", "error");
  }
}

loadFamilyTree();
