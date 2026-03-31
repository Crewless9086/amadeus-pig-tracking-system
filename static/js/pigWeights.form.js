const penFilterSelect = document.getElementById("pen_filter");
const pigSelect = document.getElementById("pig_id");
const movedToPenSelect = document.getElementById("moved_to_pen_id");

const weightDateInput = document.getElementById("weight_date");
const weightKgInput = document.getElementById("weight_kg");
const conditionNotesInput = document.getElementById("condition_notes");

const previousWeightEl = document.getElementById("previous_weight");
const previousWeightDateEl = document.getElementById("previous_weight_date");
const weightDifferenceEl = document.getElementById("weight_difference");
const growthRateEl = document.getElementById("growth_rate");
const growthStatusEl = document.getElementById("growth_status");

const form = document.getElementById("pig-weight-form");
const submitButton = document.getElementById("submit_button");
const messageBox = document.getElementById("message_box");
const weightsReferenceBody = document.getElementById("weights_reference_body");

let selectedPigLatest = null;
let allPigs = [];
let allPens = [];

function getPreselectedPigId() {
  const params = new URLSearchParams(window.location.search);
  return params.get("pig_id") || "";
}

function setTodayDate() {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  weightDateInput.value = `${yyyy}-${mm}-${dd}`;
}

function showMessage(message, type = "success") {
  messageBox.classList.remove("hidden", "message-success", "message-error");
  messageBox.classList.add(type === "success" ? "message-success" : "message-error");
  messageBox.textContent = message;
}

function clearMessage() {
  messageBox.classList.add("hidden");
  messageBox.textContent = "";
  messageBox.classList.remove("message-success", "message-error");
}

function clearGrowthClasses(element) {
  element.classList.remove("good-text", "bad-text", "neutral-text");
}

function setGrowthStyle(element, styleType) {
  clearGrowthClasses(element);
  if (styleType === "good") element.classList.add("good-text");
  if (styleType === "bad") element.classList.add("bad-text");
  if (styleType === "neutral") element.classList.add("neutral-text");
}

function resetPreview() {
  previousWeightEl.textContent = "—";
  previousWeightDateEl.textContent = "—";
  weightDifferenceEl.textContent = "—";
  growthRateEl.textContent = "—";
  growthStatusEl.textContent = "—";

  clearGrowthClasses(previousWeightEl);
  clearGrowthClasses(previousWeightDateEl);
  clearGrowthClasses(weightDifferenceEl);
  clearGrowthClasses(growthRateEl);
  clearGrowthClasses(growthStatusEl);

  weightKgInput.value = "";
  selectedPigLatest = null;
}

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toFixed(decimals);
}

function getDaysDifference(dateA, dateB) {
  const first = new Date(dateA);
  const second = new Date(dateB);

  if (Number.isNaN(first.getTime()) || Number.isNaN(second.getTime())) {
    return null;
  }

  const msPerDay = 1000 * 60 * 60 * 24;
  return Math.round((first - second) / msPerDay);
}

function updateGrowthPreview() {
  if (!selectedPigLatest || selectedPigLatest.previous_weight_kg === null || selectedPigLatest.previous_weight_kg === "") {
    weightDifferenceEl.textContent = "—";
    growthRateEl.textContent = "—";
    growthStatusEl.textContent = "No previous weight";
    setGrowthStyle(growthStatusEl, "neutral");
    return;
  }

  const newWeight = parseFloat(weightKgInput.value);
  const previousWeight = parseFloat(selectedPigLatest.previous_weight_kg);

  if (Number.isNaN(newWeight)) {
    weightDifferenceEl.textContent = "—";
    growthRateEl.textContent = "—";
    growthStatusEl.textContent = "—";
    clearGrowthClasses(weightDifferenceEl);
    clearGrowthClasses(growthRateEl);
    clearGrowthClasses(growthStatusEl);
    return;
  }

  const difference = newWeight - previousWeight;
  const days = getDaysDifference(weightDateInput.value, selectedPigLatest.previous_weight_date);

  weightDifferenceEl.textContent = `${difference >= 0 ? "+" : ""}${formatNumber(difference, 2)} kg`;

  if (days && days > 0) {
    const growthRate = difference / days;
    growthRateEl.textContent = `${difference >= 0 ? "+" : ""}${formatNumber(growthRate, 3)} kg/day`;
  } else {
    growthRateEl.textContent = "—";
  }

  if (difference > 0) {
    growthStatusEl.textContent = "Good";
    setGrowthStyle(weightDifferenceEl, "good");
    setGrowthStyle(growthRateEl, "good");
    setGrowthStyle(growthStatusEl, "good");
  } else if (difference < 0) {
    growthStatusEl.textContent = "Down";
    setGrowthStyle(weightDifferenceEl, "bad");
    setGrowthStyle(growthRateEl, "bad");
    setGrowthStyle(growthStatusEl, "bad");
  } else {
    growthStatusEl.textContent = "No change";
    setGrowthStyle(weightDifferenceEl, "neutral");
    setGrowthStyle(growthRateEl, "neutral");
    setGrowthStyle(growthStatusEl, "neutral");
  }
}

function renderEmptyTable(message) {
  weightsReferenceBody.innerHTML = `
    <tr>
      <td colspan="6" class="table-empty">${message}</td>
    </tr>
  `;
}

function renderTableRows(rows) {
  if (!rows || !rows.length) {
    renderEmptyTable("No weight records found.");
    return;
  }

  weightsReferenceBody.innerHTML = rows.map((item) => `
    <tr>
      <td>${item.weight_date_display || "—"}</td>
      <td>${item.tag_number || item.pig_id || "—"}</td>
      <td>${item.current_pen_id || "—"}</td>
      <td>${item.weight_kg !== null && item.weight_kg !== "" ? formatNumber(item.weight_kg, 2) : "—"}</td>
      <td>${item.weighed_by || "—"}</td>
      <td>${item.condition_notes || "—"}</td>
    </tr>
  `).join("");
}

async function loadLatestWeight(pigId) {
  if (!pigId) {
    resetPreview();
    return;
  }

  try {
    const response = await fetch(`/api/pig-weights/pig/${encodeURIComponent(pigId)}/latest-weight`);
    const data = await response.json();

    selectedPigLatest = data;

    if (data.previous_weight_kg !== null && data.previous_weight_kg !== "") {
      previousWeightEl.textContent = `${formatNumber(data.previous_weight_kg, 2)} kg`;
      weightKgInput.value = data.previous_weight_kg;
    } else {
      previousWeightEl.textContent = "No previous weight";
      weightKgInput.value = "";
    }

    previousWeightDateEl.textContent = data.previous_weight_date || "—";
    updateGrowthPreview();
  } catch (error) {
    resetPreview();
    showMessage("Could not load previous weight.", "error");
  }
}

async function loadPens() {
  try {
    const response = await fetch("/api/pig-weights/pens");
    const data = await response.json();

    allPens = data.pens || [];

    movedToPenSelect.innerHTML = `<option value="">No pen change</option>`;

    allPens.forEach((pen) => {
      const label = pen.pen_name ? `${pen.pen_name} (${pen.pen_id})` : (pen.pen_id || "");

      const moveOption = document.createElement("option");
      moveOption.value = pen.pen_id;
      moveOption.textContent = label;
      movedToPenSelect.appendChild(moveOption);
    });

    penFilterSelect.innerHTML = `<option value="">All active pigs</option>`;
  } catch (error) {
    console.error("Could not load pens.", error);
  }
}

function buildPigLabel(pig) {
  const tag = pig.tag_number || pig.pig_id;
  const pen = pig.current_pen_id ? ` • ${pig.current_pen_id}` : "";
  return `${tag}${pen}`;
}

function populatePenFilterFromActivePigs() {
  penFilterSelect.innerHTML = `<option value="">All active pigs</option>`;

  const activePenIds = [...new Set(
    allPigs
      .map((pig) => pig.current_pen_id || "")
      .filter((penId) => penId !== "")
  )].sort();

  activePenIds.forEach((penId) => {
    const matchingPen = allPens.find((pen) => pen.pen_id === penId);
    const label = matchingPen && matchingPen.pen_name
      ? `${matchingPen.pen_name} (${penId})`
      : penId;

    const option = document.createElement("option");
    option.value = penId;
    option.textContent = label;
    penFilterSelect.appendChild(option);
  });
}

function populatePigSelect() {
  const preselectedPigId = getPreselectedPigId();
  const selectedPen = penFilterSelect.value || "";
  const currentPigSelection = pigSelect.value || preselectedPigId || "";

  pigSelect.innerHTML = '<option value="">Select a pig</option>';

  let filteredPigs = [...allPigs];

  if (selectedPen) {
    filteredPigs = filteredPigs.filter((pig) => (pig.current_pen_id || "") === selectedPen);
  }

  filteredPigs.sort((a, b) => {
    const left = (a.tag_number || a.pig_id || "").toLowerCase();
    const right = (b.tag_number || b.pig_id || "").toLowerCase();
    return left.localeCompare(right);
  });

  filteredPigs.forEach((pig) => {
    const option = document.createElement("option");
    option.value = pig.pig_id;
    option.textContent = buildPigLabel(pig);

    if (currentPigSelection && pig.pig_id === currentPigSelection) {
      option.selected = true;
    }

    pigSelect.appendChild(option);
  });

  const selectedStillExists = filteredPigs.some((pig) => pig.pig_id === currentPigSelection);
  if (!selectedStillExists) {
    pigSelect.value = "";
    resetPreview();
  }
}

async function loadPigs() {
  try {
    const response = await fetch("/api/pig-weights/pigs");
    const data = await response.json();

    allPigs = data.pigs || [];

    populatePenFilterFromActivePigs();
    populatePigSelect();

    const preselectedPigId = getPreselectedPigId();
    if (preselectedPigId) {
      await loadLatestWeight(preselectedPigId);
      await refreshReferenceTable();
    } else {
      renderEmptyTable("Select a pig or date to view weight records.");
    }
  } catch (error) {
    console.error("loadPigs error:", error);
    pigSelect.innerHTML = '<option value="">Failed to load pigs</option>';
    showMessage("Could not load pigs.", "error");
  }
}

async function loadPigWeightHistoryForTable(pigId) {
  const response = await fetch(`/api/pig-weights/pig/${encodeURIComponent(pigId)}/weights`);
  const data = await response.json();

  if (!response.ok || !data.success) {
    renderEmptyTable("Could not load pig weight history.");
    return;
  }

  renderTableRows(data.history || []);
}

async function loadWeightsByDateForTable(weightDate) {
  const response = await fetch(`/api/pig-weights/weights-by-date?weight_date=${encodeURIComponent(weightDate)}`);
  const data = await response.json();

  if (!response.ok || !data.success) {
    renderEmptyTable("Could not load daily weights.");
    return;
  }

  renderTableRows(data.history || []);
}

async function refreshReferenceTable() {
  const selectedPigId = pigSelect.value || "";
  const selectedDate = weightDateInput.value || "";

  if (selectedPigId) {
    await loadPigWeightHistoryForTable(selectedPigId);
    return;
  }

  if (selectedDate) {
    await loadWeightsByDateForTable(selectedDate);
    return;
  }

  renderEmptyTable("Select a pig or date to view weight records.");
}

pigSelect.addEventListener("change", async (event) => {
  clearMessage();
  await loadLatestWeight(event.target.value);
  await refreshReferenceTable();
});

penFilterSelect.addEventListener("change", async () => {
  populatePigSelect();
  await refreshReferenceTable();
});

weightKgInput.addEventListener("input", updateGrowthPreview);

weightDateInput.addEventListener("change", async () => {
  updateGrowthPreview();
  await refreshReferenceTable();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();

  const payload = {
    pig_id: pigSelect.value,
    weight_date: weightDateInput.value,
    weight_kg: parseFloat(weightKgInput.value),
    condition_notes: conditionNotesInput.value.trim(),
    weighed_by: "WebApp",
    moved_to_pen_id: movedToPenSelect.value || ""
  };

  submitButton.disabled = true;
  submitButton.textContent = "Saving...";

  try {
    const response = await fetch("/api/pig-weights/weights-with-optional-move", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      const errorMessage = data.errors ? data.errors.join(" ") : "Failed to save weight.";
      showMessage(errorMessage, "error");
      return;
    }

    if (data.movement_logged) {
      showMessage("Weight and pen movement saved successfully.", "success");
    } else {
      showMessage("Weight saved successfully.", "success");
    }

    conditionNotesInput.value = "";
    movedToPenSelect.value = "";
    await loadPigs();
    await loadLatestWeight(pigSelect.value);
    await refreshReferenceTable();
  } catch (error) {
    console.error("save weight error:", error);
    showMessage("Something went wrong while saving.", "error");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Save Weight";
  }
});

setTodayDate();

(async function initPage() {
  await loadPens();
  await loadPigs();
})();