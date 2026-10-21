const pigListContainer = document.getElementById("pig_list");
const pigSearchInput = document.getElementById("pig_search");
const pigPenFilter = document.getElementById("pig_pen_filter");
const pigWeightFilter = document.getElementById("pig_weight_filter");
const pigStageFilter = document.getElementById("pig_stage_filter");
const pigListMessage = document.getElementById("pig_list_message");
const pigTotalCount = document.getElementById("pig_total_count");
const pigWeighedCount = document.getElementById("pig_weighed_count");
const pigNoWeightCount = document.getElementById("pig_no_weight_count");
const pigPenCount = document.getElementById("pig_pen_count");
const pigVisibleCount = document.getElementById("pig_visible_count");
const pigClearFilters = document.getElementById("pig_clear_filters");
const pigQuickViews = [...document.querySelectorAll("[data-herd-view]")];

let allPigs = [];
let activeQuickView = "all";

function formatTagNumber(value) {
  const raw = String(value || "").trim();
  return /^\d+$/.test(raw) ? raw.padStart(3, "0") : raw;
}

function pigSortKey(pig) {
  const rawTag = String(pig.tag_number || pig.pig_id || "").trim();
  const tagKey = /^\d+$/.test(rawTag) ? rawTag.padStart(8, "0") : rawTag.toLowerCase();
  const penKey = String(pig.current_pen_name || pig.current_pen_id || "").toLowerCase();
  return `${penKey}|${tagKey}|${pig.pig_id || ""}`;
}

function sortPigsForDisplay(pigs) {
  return [...pigs].sort((a, b) => pigSortKey(a).localeCompare(pigSortKey(b)));
}

function hasWeight(pig) {
  return pig.current_weight_kg !== null && pig.current_weight_kg !== "" && pig.current_weight_kg !== undefined;
}

function displayValue(value, fallback = "Unknown") {
  const text = String(value || "").trim();
  return text || fallback;
}

function penLabel(pig) {
  return displayValue(pig.current_pen_name || pig.current_pen_id);
}

function stageLabel(pig) {
  return displayValue(pig.calculated_stage || pig.animal_type, "Unclassified");
}

function formatWeight(pig) {
  return hasWeight(pig) ? `${pig.current_weight_kg} kg` : "No weight";
}

function formatWeightDate(pig) {
  return displayValue(pig.last_weight_date, "No date");
}

function animalName(pig) {
  return displayValue(pig.name || pig.pig_name || pig.animal_name, formatTagNumber(pig.tag_number || pig.pig_id));
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

function optionKey(value) {
  return String(value || "").trim().toLowerCase();
}

function setSelectOptions(selectElement, values, defaultLabel) {
  const currentValue = selectElement.value;
  selectElement.innerHTML = "";

  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = defaultLabel;
  selectElement.appendChild(defaultOption);

  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    selectElement.appendChild(option);
  });

  selectElement.value = values.includes(currentValue) ? currentValue : "";
}

function populateFilters(pigs) {
  const pens = [...new Set(pigs.map((pig) => penLabel(pig)).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true })
  );
  const stages = [...new Set(pigs.map((pig) => stageLabel(pig)).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true })
  );

  setSelectOptions(pigPenFilter, pens, "All pens");
  setSelectOptions(pigStageFilter, stages, "All stages");
}

function renderTotals(visiblePigs = allPigs) {
  const weighed = allPigs.filter(hasWeight).length;
  const pens = new Set(allPigs.map((pig) => penLabel(pig)).filter((pen) => pen !== "Unknown"));

  pigTotalCount.textContent = allPigs.length;
  pigWeighedCount.textContent = weighed;
  pigNoWeightCount.textContent = allPigs.length - weighed;
  pigPenCount.textContent = pens.size;
  pigVisibleCount.textContent = visiblePigs.length;
}

function appendDetail(parent, label, value) {
  const item = document.createElement("div");
  item.className = "pig-list-detail-item";

  const labelElement = document.createElement("span");
  labelElement.textContent = label;

  const valueElement = document.createElement("strong");
  valueElement.textContent = value;

  item.appendChild(labelElement);
  item.appendChild(valueElement);
  parent.appendChild(item);
}

function buildPigCard(pig) {
  const card = document.createElement("a");
  card.className = "herd-animal-card";
  card.href = `/pig/${encodeURIComponent(pig.pig_id)}`;

  const topRow = document.createElement("div");
  topRow.className = "herd-animal-top";

  const heading = document.createElement("div");
  heading.className = "herd-animal-identity";

  const name = document.createElement("div");
  name.className = "herd-animal-name";
  name.textContent = animalName(pig);

  const meta = document.createElement("div");
  meta.className = "herd-animal-tag";
  meta.textContent = pig.pig_id;

  heading.appendChild(name);
  heading.appendChild(meta);

  const action = document.createElement("div");
  action.className = "herd-animal-open";
  action.textContent = "Open →";

  topRow.appendChild(heading);
  topRow.appendChild(action);

  const statusRow = document.createElement("div");
  statusRow.className = "herd-animal-badges";

  const penBadge = document.createElement("span");
  penBadge.className = "herd-animal-badge";
  penBadge.textContent = penLabel(pig);

  const weightBadge = document.createElement("span");
  weightBadge.className = hasWeight(pig) ? "herd-animal-badge is-muted" : "herd-animal-badge is-alert";
  weightBadge.textContent = hasWeight(pig) ? "Weight recorded" : "Needs weight";

  statusRow.appendChild(penBadge);
  statusRow.appendChild(weightBadge);

  const detailGrid = document.createElement("div");
  detailGrid.className = "herd-animal-facts";
  appendDetail(detailGrid, "Latest weight", formatWeight(pig));
  appendDetail(detailGrid, "Recorded", formatWeightDate(pig));
  appendDetail(detailGrid, "Stage", stageLabel(pig));
  appendDetail(detailGrid, "Purpose", displayValue(pig.purpose, "Not set"));

  [...detailGrid.children].forEach((item) => { item.className = "herd-animal-fact"; });

  const hoverDetail = document.createElement("div");
  hoverDetail.className = "herd-animal-footer";
  hoverDetail.textContent = [
    displayValue(pig.sex, "Sex unknown"),
    `Litter: ${displayValue(pig.litter_id, "None")}`,
  ].join(" · ");

  card.appendChild(topRow);
  card.appendChild(statusRow);
  card.appendChild(detailGrid);
  card.appendChild(hoverDetail);

  return card;
}

function renderPigList(pigs) {
  pigListContainer.innerHTML = "";
  renderTotals(pigs);

  if (!pigs.length) {
    pigListContainer.innerHTML = `
      <div class="empty-state pig-list-empty">
        <strong>No pigs found.</strong>
        <span>Try another search, pen, stage, or weight filter.</span>
      </div>
    `;
    return;
  }

  pigs.forEach((pig) => {
    pigListContainer.appendChild(buildPigCard(pig));
  });
}

function searchableText(pig) {
  const formattedTagNumber = formatTagNumber(pig.tag_number || "");
  return [
    pig.pig_id,
    pig.tag_number,
    formattedTagNumber,
    penLabel(pig),
    pig.current_pen_id,
    stageLabel(pig),
    pig.purpose,
    pig.sex,
    pig.litter_id,
    animalName(pig),
  ]
    .map((value) => String(value || "").toLowerCase())
    .join(" ");
}

function filterPigs() {
  const query = pigSearchInput.value.trim().toLowerCase();
  const selectedPen = optionKey(pigPenFilter.value);
  const selectedWeight = pigWeightFilter.value;
  const selectedStage = optionKey(pigStageFilter.value);

  const filtered = allPigs.filter((pig) => {
    const matchesSearch = !query || searchableText(pig).includes(query);
    const matchesPen = !selectedPen || optionKey(penLabel(pig)) === selectedPen;
    const matchesStage = !selectedStage || optionKey(stageLabel(pig)) === selectedStage;
    const matchesWeight =
      !selectedWeight ||
      (selectedWeight === "weighed" && hasWeight(pig)) ||
      (selectedWeight === "missing" && !hasWeight(pig));
    const stage = optionKey(stageLabel(pig));
    const purpose = optionKey(pig.purpose);
    const matchesQuickView =
      activeQuickView === "all" ||
      (activeQuickView === "missing" && !hasWeight(pig)) ||
      (activeQuickView === "breeding" && (purpose.includes("breed") || stage.includes("sow") || stage.includes("boar"))) ||
      (activeQuickView === "sale" && purpose.includes("sale"));

    return matchesSearch && matchesPen && matchesStage && matchesWeight && matchesQuickView;
  });

  renderPigList(filtered);
}

async function loadPigList() {
  clearListMessage();
  renderTotals([]);

  try {
    const response = await fetch("/api/pig-weights/pigs");
    const data = await response.json();

    allPigs = sortPigsForDisplay(data.pigs || []);
    populateFilters(allPigs);
    renderPigList(allPigs);
  } catch (error) {
    showListMessage("Could not load pig list.", "error");
  }
}

pigSearchInput.addEventListener("input", filterPigs);
pigPenFilter.addEventListener("change", filterPigs);
pigWeightFilter.addEventListener("change", filterPigs);
pigStageFilter.addEventListener("change", filterPigs);
pigClearFilters.addEventListener("click", () => {
  pigSearchInput.value = "";
  pigPenFilter.value = "";
  pigWeightFilter.value = "";
  pigStageFilter.value = "";
  activeQuickView = "all";
  pigQuickViews.forEach((button) => button.classList.toggle("is-active", button.dataset.herdView === "all"));
  filterPigs();
  pigSearchInput.focus();
});
pigQuickViews.forEach((button) => {
  button.addEventListener("click", () => {
    activeQuickView = button.dataset.herdView;
    pigQuickViews.forEach((item) => item.classList.toggle("is-active", item === button));
    filterPigs();
  });
});

loadPigList();
