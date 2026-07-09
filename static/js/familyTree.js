const familyTreeMessage = document.getElementById("family_tree_message");
const familyTreeMother = document.getElementById("family_tree_mother");
const familyTreeFather = document.getElementById("family_tree_father");
const familyTreeCurrent = document.getElementById("family_tree_current");
const familyTreeSiblings = document.getElementById("family_tree_siblings");
const familyTreeSiblingCount = document.getElementById("family_tree_sibling_count");
const familyTreeBreedingPanel = document.getElementById("family_tree_breeding_panel");
const familyTreeBreedingSummary = document.getElementById("family_tree_breeding_summary");
const familyTreeQualityFlags = document.getElementById("family_tree_quality_flags");
const familyTreeMatings = document.getElementById("family_tree_matings");
const familyTreeLitters = document.getElementById("family_tree_litters");

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

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

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(decimals);
}

function formatCount(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "0";
  }
  return String(Number(value));
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(1)}%`;
}

function animalLabel(pigId, tagNumber) {
  const tag = tagNumber || pigId || "-";
  return pigId && tagNumber && pigId !== tagNumber ? `${tagNumber} (${pigId})` : tag;
}

function pairLabel(row) {
  const sow = animalLabel(row.sow_pig_id, row.sow_tag_number);
  const boar = animalLabel(row.boar_pig_id, row.boar_tag_number);
  return `${sow} x ${boar}`;
}

function flagsHtml(flags) {
  if (!flags || !flags.length) {
    return '<span class="quality-flag-muted">No data-quality flags found.</span>';
  }
  return flags.map((flag) => `<span class="quality-flag">${escapeHtml(flag)}</span>`).join("");
}

function renderFamilyMetric(label, value, helper = "") {
  return `
    <div class="family-tree-metric">
      <span class="info-title">${escapeHtml(label)}</span>
      <span class="info-value">${escapeHtml(value)}</span>
      ${helper ? `<span class="pig-list-submeta">${escapeHtml(helper)}</span>` : ""}
    </div>
  `;
}

function renderBreedingContext(context) {
  if (!familyTreeBreedingPanel || !context || !context.is_breeding_animal || !context.animal) {
    if (familyTreeBreedingPanel) familyTreeBreedingPanel.classList.add("hidden");
    return;
  }

  const animal = context.animal;
  const matings = context.matings || [];
  const litters = context.litters || [];
  familyTreeBreedingPanel.classList.remove("hidden");
  familyTreeBreedingSummary.innerHTML = [
    renderFamilyMetric("Role", context.animal_type || "Breeding", animalLabel(animal.pig_id, animal.tag_number)),
    renderFamilyMetric("Matings", formatCount(animal.mating_count), `${formatCount(animal.open_count)} open`),
    renderFamilyMetric("Litters", formatCount(animal.litter_count), `${formatCount(animal.farrowed_count)} farrowed`),
    renderFamilyMetric("Piglets Born Alive", formatCount(animal.born_alive_total), `Avg ${formatNumber(animal.average_born_alive, 1)}`),
    renderFamilyMetric("Piglets Weaned", formatCount(animal.weaned_total), `Avg ${formatNumber(animal.average_weaned, 1)}`),
    renderFamilyMetric("Survival", formatPercent(animal.survival_pct), `${formatCount(context.data_quality?.flag_count)} flags`),
  ].join("");

  familyTreeQualityFlags.innerHTML = flagsHtml(context.data_quality?.flags || []);

  familyTreeMatings.innerHTML = matings.length
    ? matings.slice(0, 5).map((row) => `
        <div class="family-tree-record">
          <div>
            <strong>${escapeHtml(row.mating_id || "Mating")}</strong>
            <span>${escapeHtml(pairLabel(row))}</span>
          </div>
          <div class="family-tree-record-meta">
            <span>${escapeHtml(row.mating_date || "No date")}</span>
            <span>${escapeHtml(row.mating_status || row.pregnancy_check_result || "No status")}</span>
            <span>${row.linked_litter_id ? `Litter ${escapeHtml(row.linked_litter_id)}` : "No linked litter"}</span>
          </div>
          <div class="family-tree-inline-flags">${flagsHtml(row.quality_flags)}</div>
        </div>
      `).join("")
    : '<div class="empty-state compact-empty-state"><strong>No matings found.</strong><span>No service history is linked to this breeding animal yet.</span></div>';

  familyTreeLitters.innerHTML = litters.length
    ? litters.slice(0, 5).map((row) => `
        <a class="family-tree-record" href="/litter/${encodeURIComponent(row.litter_id)}">
          <div>
            <strong>${escapeHtml(row.litter_id || "Litter")}</strong>
            <span>${escapeHtml(pairLabel(row))}</span>
          </div>
          <div class="family-tree-record-meta">
            <span>${escapeHtml(row.farrowing_date || "No date")}</span>
            <span>${escapeHtml(formatCount(row.born_alive))} born alive</span>
            <span>${escapeHtml(formatCount(row.weaned_count))} weaned</span>
            <span>${escapeHtml(formatPercent(row.survival_pct))} survival</span>
          </div>
          <div class="family-tree-inline-flags">${flagsHtml(row.quality_flags)}</div>
        </a>
      `).join("")
    : '<div class="empty-state compact-empty-state"><strong>No litters found.</strong><span>No litter outcomes are linked to this breeding animal yet.</span></div>';
}

function buildFamilyCard(pig, roleLabel = "") {
  if (!pig) {
    return `
      <div class="family-card family-card-empty">
        <span class="detail-label">${escapeHtml(roleLabel || "Unknown")}</span>
        <span class="detail-value">-</span>
      </div>
    `;
  }

  return `
    <a href="/pig/${encodeURIComponent(pig.pig_id)}" class="family-card">
      ${roleLabel ? `<span class="detail-label">${escapeHtml(roleLabel)}</span>` : ""}
      <span class="detail-value">${escapeHtml(pig.tag_number || pig.pig_id)}</span>
      <span class="pig-list-meta">Pig ID: ${escapeHtml(pig.pig_id)}</span>
      <span class="pig-list-submeta">${escapeHtml(pig.sex || "-")} - ${escapeHtml(pig.calculated_stage || "-")}</span>
      <span class="pig-list-submeta">${pig.current_weight_kg !== null && pig.current_weight_kg !== "" ? `${escapeHtml(formatNumber(pig.current_weight_kg, 2))} kg` : "No weight"}</span>
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
  action.textContent = "Open Profile ->";

  topRow.appendChild(tag);
  topRow.appendChild(action);

  const meta = document.createElement("div");
  meta.className = "pig-list-meta";
  meta.textContent = `Pig ID: ${pig.pig_id}`;

  const subMeta = document.createElement("div");
  subMeta.className = "pig-list-submeta";
  subMeta.textContent =
    `${pig.sex || "-"} - ${pig.calculated_stage || "-"} - ${pig.current_weight_kg !== null && pig.current_weight_kg !== "" ? `${formatNumber(pig.current_weight_kg, 2)} kg` : "No weight"}`;

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

async function loadFamilyTree() {
  const pigId = getPigIdFromFamilyTreeUrl();

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
      showFamilyTreeMessage(data.error || "Could not load family tree.", "error");
      return;
    }

    const tree = data.tree;

    document.getElementById("family_tree_title").textContent = `Family Tree - ${tree.current_pig.tag_number || tree.current_pig.pig_id}`;
    document.getElementById("family_tree_subtitle").textContent = `Pig ID: ${tree.current_pig.pig_id}`;
    renderBreedingContext(tree.breeding_context);

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
      return;
    }

    tree.siblings.forEach((pig) => {
      familyTreeSiblings.appendChild(buildSiblingCard(pig));
    });
  } catch (error) {
    console.error("loadFamilyTree error:", error);
    showFamilyTreeMessage("Something went wrong while loading family tree.", "error");
  }
}

loadFamilyTree();
