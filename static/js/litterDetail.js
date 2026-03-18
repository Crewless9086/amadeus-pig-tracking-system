const litterMessage = document.getElementById("litter_message");
const litterPigletsList = document.getElementById("litter_piglets_list");

function getLitterIdFromUrl() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 1] || "");
}

function showLitterMessage(message, type = "error") {
  litterMessage.classList.remove("hidden", "message-success", "message-error");
  litterMessage.classList.add(type === "success" ? "message-success" : "message-error");
  litterMessage.textContent = message;
}

function setText(id, value, suffix = "") {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent = value !== null && value !== undefined && value !== ""
    ? `${value}${suffix}`
    : "—";
}

function setLinkedValue(id, label, href) {
  const element = document.getElementById(id);
  if (!element) return;

  if (label && href) {
    element.innerHTML = `<a href="${href}" class="detail-link">${label}</a>`;
  } else {
    element.textContent = "—";
  }
}

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toFixed(decimals);
}

function buildPigletCard(piglet) {
  const card = document.createElement("a");
  card.className = "pig-list-card";
  card.href = `/pig/${encodeURIComponent(piglet.pig_id)}`;

  const topRow = document.createElement("div");
  topRow.className = "pig-list-top";

  const tag = document.createElement("div");
  tag.className = "pig-list-tag";
  tag.textContent = piglet.tag_number || piglet.pig_id;

  const action = document.createElement("div");
  action.className = "pig-list-action";
  action.textContent = "Open Profile →";

  topRow.appendChild(tag);
  topRow.appendChild(action);

  const meta = document.createElement("div");
  meta.className = "pig-list-meta";
  meta.textContent = `Pig ID: ${piglet.pig_id}`;

  const subMeta = document.createElement("div");
  subMeta.className = "pig-list-submeta";
  subMeta.textContent =
    `${piglet.sex || "—"} • ${piglet.calculated_stage || "—"} • ${piglet.current_weight_kg !== null && piglet.current_weight_kg !== "" ? `${formatNumber(piglet.current_weight_kg, 2)} kg` : "No weight"}`;

  const extra = document.createElement("div");
  extra.className = "sales-meta-grid";
  extra.innerHTML = `
    <div><span class="history-label">Status</span><span class="history-value">${piglet.status || "—"}</span></div>
    <div><span class="history-label">On Farm</span><span class="history-value">${piglet.on_farm || "—"}</span></div>
    <div><span class="history-label">Age (Days)</span><span class="history-value">${piglet.age_days || "—"}</span></div>
    <div><span class="history-label">Pen</span><span class="history-value">${piglet.current_pen_id || "—"}</span></div>
  `;

  card.appendChild(topRow);
  card.appendChild(meta);
  card.appendChild(subMeta);
  card.appendChild(extra);

  return card;
}

async function loadLitterDetail() {
  const litterId = getLitterIdFromUrl();

  if (!litterId) {
    showLitterMessage("No litter ID found in URL.", "error");
    return;
  }

  try {
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/detail`);
    const data = await response.json();

    if (!response.ok || !data.success) {
      showLitterMessage(data.error || "Could not load litter detail.", "error");
      return;
    }

    const litter = data.litter;

    document.getElementById("litter_title").textContent = `Litter • ${litter.litter_id}`;
    document.getElementById("litter_subtitle").textContent = `${litter.count} piglet(s) linked to this litter`;

    setText("litter_id_value", litter.litter_id);
    setText("litter_count_value", litter.count);
    setText("litter_male_count_value", litter.male_count);
    setText("litter_female_count_value", litter.female_count);
    setText("litter_active_count_value", litter.active_count);
    setText("litter_average_weight_value", litter.average_weight_kg, litter.average_weight_kg !== null ? " kg" : "");

    setLinkedValue(
      "litter_mother_value",
      litter.mother_tag_number || litter.mother_pig_id,
      litter.mother_pig_id ? `/pig/${encodeURIComponent(litter.mother_pig_id)}` : ""
    );

    setLinkedValue(
      "litter_father_value",
      litter.father_tag_number || litter.father_pig_id,
      litter.father_pig_id ? `/pig/${encodeURIComponent(litter.father_pig_id)}` : ""
    );

    litterPigletsList.innerHTML = "";

    if (!litter.piglets.length) {
      litterPigletsList.innerHTML = `
        <div class="empty-state">
          <strong>No piglets found in this litter.</strong>
          <span>Check the litter links in PIG_OVERVIEW.</span>
        </div>
      `;
      return;
    }

    litter.piglets.forEach((piglet) => {
      litterPigletsList.appendChild(buildPigletCard(piglet));
    });
  } catch (error) {
    showLitterMessage("Something went wrong while loading litter detail.", "error");
  }
}

loadLitterDetail();