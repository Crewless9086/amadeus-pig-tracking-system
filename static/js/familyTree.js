const familyTreeMessage = document.getElementById("family_tree_message");
const familyTreeMother = document.getElementById("family_tree_mother");
const familyTreeFather = document.getElementById("family_tree_father");
const familyTreeCurrent = document.getElementById("family_tree_current");
const familyTreeSiblings = document.getElementById("family_tree_siblings");
const familyTreeSiblingCount = document.getElementById("family_tree_sibling_count");

function getPigIdFromFamilyTreeUrl() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 2] || "");
}

function showFamilyTreeMessage(message, type = "error") {
  familyTreeMessage.classList.remove("hidden", "message-success", "message-error");
  familyTreeMessage.classList.add(type === "success" ? "message-success" : "message-error");
  familyTreeMessage.textContent = message;
}

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toFixed(decimals);
}

function buildFamilyCard(pig, roleLabel = "") {
  if (!pig) {
    return `
      <div class="family-card family-card-empty">
        <span class="detail-label">${roleLabel || "Unknown"}</span>
        <span class="detail-value">—</span>
      </div>
    `;
  }

  return `
    <a href="/pig/${encodeURIComponent(pig.pig_id)}" class="family-card">
      ${roleLabel ? `<span class="detail-label">${roleLabel}</span>` : ""}
      <span class="detail-value">${pig.tag_number || pig.pig_id}</span>
      <span class="pig-list-meta">Pig ID: ${pig.pig_id}</span>
      <span class="pig-list-submeta">${pig.sex || "—"} • ${pig.calculated_stage || "—"}</span>
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
  action.textContent = "Open Profile →";

  topRow.appendChild(tag);
  topRow.appendChild(action);

  const meta = document.createElement("div");
  meta.className = "pig-list-meta";
  meta.textContent = `Pig ID: ${pig.pig_id}`;

  const subMeta = document.createElement("div");
  subMeta.className = "pig-list-submeta";
  subMeta.textContent =
    `${pig.sex || "—"} • ${pig.calculated_stage || "—"} • ${pig.current_weight_kg !== null && pig.current_weight_kg !== "" ? `${formatNumber(pig.current_weight_kg, 2)} kg` : "No weight"}`;

  const extra = document.createElement("div");
  extra.className = "sales-meta-grid";
  extra.innerHTML = `
    <div><span class="history-label">Status</span><span class="history-value">${pig.status || "—"}</span></div>
    <div><span class="history-label">On Farm</span><span class="history-value">${pig.on_farm || "—"}</span></div>
    <div><span class="history-label">Age (Days)</span><span class="history-value">${pig.age_days || "—"}</span></div>
    <div><span class="history-label">Pen</span><span class="history-value">${pig.current_pen_id || "—"}</span></div>
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

  document.getElementById("family_tree_profile_button").href = `/pig/${encodeURIComponent(pigId)}`;

  try {
    const response = await fetch(`/api/pig-weights/family-tree/${encodeURIComponent(pigId)}`);
    const data = await response.json();

    if (!response.ok || !data.success) {
      showFamilyTreeMessage(data.error || "Could not load family tree.", "error");
      return;
    }

    const tree = data.tree;

    document.getElementById("family_tree_title").textContent = `Family Tree • ${tree.current_pig.tag_number || tree.current_pig.pig_id}`;
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
      return;
    }

    tree.siblings.forEach((pig) => {
      familyTreeSiblings.appendChild(buildSiblingCard(pig));
    });
  } catch (error) {
    showFamilyTreeMessage("Something went wrong while loading family tree.", "error");
  }
}

loadFamilyTree();