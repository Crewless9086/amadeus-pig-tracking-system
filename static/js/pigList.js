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
const pigActiveView = document.getElementById("pig_active_view");
const pigArchiveView = document.getElementById("pig_archive_view");
const pigListDescription = document.getElementById("pig_list_description");
const pigListScopeNotice = document.getElementById("pig_list_scope_notice");
const pigTotalLabel = document.getElementById("pig_total_label");

let allPigs = [];
const pigListView = new URLSearchParams(window.location.search).get("view") === "archive" ? "archive" : "active";

function isArchiveView() {
  return pigListView === "archive";
}

function configureListView() {
  const archive = isArchiveView();
  document.title = archive ? "Amadeus Pig Retained History" : "Amadeus Pig List";
  pigActiveView.classList.toggle("pig-list-view-tab-active", !archive);
  pigArchiveView.classList.toggle("pig-list-view-tab-active", archive);
  pigActiveView.setAttribute("aria-current", archive ? "false" : "page");
  pigArchiveView.setAttribute("aria-current", archive ? "page" : "false");
  pigListDescription.textContent = archive
    ? "Find exited animal records without mixing them into the on-farm herd."
    : "Scan the active on-farm herd by pen, weight status, and profile detail.";
  pigListScopeNotice.textContent = archive
    ? "Retained history shows exited pigs only. Empty exit dates or reasons are left as unknown for owner-reviewed reconciliation; this page does not change farm records."
    : "On-farm herd is the default operational view. Retained history is kept separately so exited animals remain discoverable without appearing in the working herd list.";
  pigTotalLabel.textContent = archive ? "Total Exited" : "Total Active";
}

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
  card.className = "pig-list-card";
  const returnTo = `/pigs${isArchiveView() ? "?view=archive" : ""}`;
  card.href = `/pig/${encodeURIComponent(pig.pig_id)}`;
  card.href += `?${new URLSearchParams({
    return_to: returnTo,
    return_label: isArchiveView() ? "Back to Retained History" : "Back to On-farm Herd",
  }).toString()}`;

  const topRow = document.createElement("div");
  topRow.className = "pig-list-top";

  const heading = document.createElement("div");
  heading.className = "pig-list-heading";

  const tag = document.createElement("div");
  tag.className = "pig-list-tag";
  tag.textContent = formatTagNumber(pig.tag_number || pig.pig_id);

  const meta = document.createElement("div");
  meta.className = "pig-list-meta";
  meta.textContent = `Pig ID: ${pig.pig_id}`;

  heading.appendChild(tag);
  heading.appendChild(meta);

  const action = document.createElement("div");
  action.className = "pig-list-action";
  action.textContent = "Open Profile ->";

  topRow.appendChild(heading);
  topRow.appendChild(action);

  const statusRow = document.createElement("div");
  statusRow.className = "pig-list-status-row";

  const penBadge = document.createElement("span");
  penBadge.className = "pig-list-badge";
  penBadge.textContent = penLabel(pig);

  const weightBadge = document.createElement("span");
  weightBadge.className = hasWeight(pig) ? "pig-list-badge pig-list-badge-good" : "pig-list-badge pig-list-badge-muted";
  weightBadge.textContent = hasWeight(pig) ? "Weighed" : "No weight";

  statusRow.appendChild(penBadge);
  statusRow.appendChild(weightBadge);

  if (isArchiveView()) {
    const exitBadge = document.createElement("span");
    exitBadge.className = "pig-list-badge pig-list-badge-archive";
    exitBadge.textContent = displayValue(pig.status, "Exited");
    statusRow.appendChild(exitBadge);
  }

  const detailGrid = document.createElement("div");
  detailGrid.className = "pig-list-detail-grid";
  appendDetail(detailGrid, "Latest Weight", formatWeight(pig));
  appendDetail(detailGrid, "Weight Date", formatWeightDate(pig));
  appendDetail(detailGrid, "Stage", stageLabel(pig));
  appendDetail(detailGrid, "Purpose", displayValue(pig.purpose, "Not set"));
  if (isArchiveView()) {
    appendDetail(detailGrid, "Exit Date", displayValue(pig.exit_date, "Unknown"));
    appendDetail(detailGrid, "Exit Reason", displayValue(pig.exit_reason, "Unknown"));
  }

  const hoverDetail = document.createElement("div");
  hoverDetail.className = "pig-list-hover-detail";
  hoverDetail.textContent = [
    displayValue(pig.sex, "Sex unknown"),
    `Pen: ${penLabel(pig)}`,
    `Litter: ${displayValue(pig.litter_id, "None")}`,
  ].join(" | ");

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
        <span>${isArchiveView() ? "No exited pigs are available in retained history." : "Try another search, pen, stage, or weight filter."}</span>
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

    return matchesSearch && matchesPen && matchesStage && matchesWeight;
  });

  renderPigList(filtered);
}

async function loadPigList() {
  clearListMessage();
  renderTotals([]);
  configureListView();

  try {
    const scope = isArchiveView() ? "archived" : "active";
    const response = await fetch(`/api/pig-weights/pigs?scope=${encodeURIComponent(scope)}`);
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Could not load pig list.");
    }
    const confirmedScope = data.scope || (scope === "active" ? "active" : "");
    if (confirmedScope !== scope) {
      throw new Error("The server did not confirm the requested herd view.");
    }

    allPigs = sortPigsForDisplay(data.pigs || []);
    populateFilters(allPigs);
    renderPigList(allPigs);
  } catch (error) {
    const message = isArchiveView()
      ? "Retained history is not available until the canonical archive reader is ready. The on-farm herd remains unchanged."
      : "Could not load the on-farm herd.";
    showListMessage(message, "error");
  }
}

pigSearchInput.addEventListener("input", filterPigs);
pigPenFilter.addEventListener("change", filterPigs);
pigWeightFilter.addEventListener("change", filterPigs);
pigStageFilter.addEventListener("change", filterPigs);

loadPigList();
