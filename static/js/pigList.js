const pigListContainer = document.getElementById("pig_list");
const pigSearchInput = document.getElementById("pig_search");
const pigListMessage = document.getElementById("pig_list_message");

let allPigs = [];

function formatTagNumber(value) {
  const raw = String(value || "").trim();
  return /^\d+$/.test(raw) ? raw.padStart(3, "0") : raw;
}

function pigSortKey(pig) {
  const rawTag = String(pig.tag_number || pig.pig_id || "").trim();
  const tagKey = /^\d+$/.test(rawTag) ? rawTag.padStart(8, "0") : rawTag.toLowerCase();
  const penKey = String(pig.current_pen_name || pig.current_pen_id || "").toLowerCase();
  return `${tagKey}|${penKey}|${pig.pig_id || ""}`;
}

function sortPigsForDisplay(pigs) {
  return [...pigs].sort((a, b) => pigSortKey(a).localeCompare(pigSortKey(b)));
}

function showListMessage(message, type = "error") {
  pigListMessage.classList.remove("hidden", "message-success", "message-error");
  pigListMessage.classList.add(type === "success" ? "message-success" : "message-error");
  pigListMessage.textContent = message;
}

function clearListMessage() {
  pigListMessage.classList.add("hidden");
  pigListMessage.textContent = "";
  pigListMessage.classList.remove("message-success", "message-error");
}

function buildPigCard(pig) {
  const card = document.createElement("a");
  card.className = "pig-list-card";
  card.href = `/pig/${encodeURIComponent(pig.pig_id)}`;

  const topRow = document.createElement("div");
  topRow.className = "pig-list-top";

  const tag = document.createElement("div");
  tag.className = "pig-list-tag";
  tag.textContent = formatTagNumber(pig.tag_number || pig.pig_id);

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
    pig.current_weight_kg !== null && pig.current_weight_kg !== ""
      ? `Last Weight: ${pig.current_weight_kg} kg`
      : "No weight recorded yet";

  card.appendChild(topRow);
  card.appendChild(meta);
  card.appendChild(subMeta);

  return card;
}

function renderPigList(pigs) {
  pigListContainer.innerHTML = "";

  if (!pigs.length) {
    pigListContainer.innerHTML = `
      <div class="empty-state">
        <strong>No pigs found.</strong>
        <span>Try a different search.</span>
      </div>
    `;
    return;
  }

  pigs.forEach((pig) => {
    pigListContainer.appendChild(buildPigCard(pig));
  });
}

function filterPigs() {
  const query = pigSearchInput.value.trim().toLowerCase();

  if (!query) {
    renderPigList(allPigs);
    return;
  }

  const filtered = allPigs.filter((pig) => {
    const pigId = String(pig.pig_id || "").toLowerCase();
    const tagNumber = String(pig.tag_number || "").toLowerCase();
    const formattedTagNumber = formatTagNumber(pig.tag_number || "").toLowerCase();
    return pigId.includes(query) || tagNumber.includes(query) || formattedTagNumber.includes(query);
  });

  renderPigList(filtered);
}

async function loadPigList() {
  clearListMessage();

  try {
    const response = await fetch("/api/pig-weights/pigs");
    const data = await response.json();

    allPigs = sortPigsForDisplay(data.pigs || []);
    renderPigList(allPigs);
  } catch (error) {
    showListMessage("Could not load pig list.", "error");
  }
}

pigSearchInput.addEventListener("input", filterPigs);

loadPigList();
