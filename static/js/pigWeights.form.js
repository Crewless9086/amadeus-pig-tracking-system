const pigSelect = document.getElementById("pig_id");
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

let selectedPigLatest = null;

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

async function loadPigs() {
  try {
    const response = await fetch("/api/pig-weights/pigs");
    const data = await response.json();

    pigSelect.innerHTML = '<option value="">Select a pig</option>';

    data.pigs.forEach((pig) => {
      const option = document.createElement("option");
      option.value = pig.pig_id;
      option.textContent = pig.tag_number
        ? `${pig.tag_number}`
        : `${pig.pig_id}`;
      pigSelect.appendChild(option);
    });
  } catch (error) {
    pigSelect.innerHTML = '<option value="">Failed to load pigs</option>';
    showMessage("Could not load pigs.", "error");
  }
}

async function loadLatestWeight(pigId) {
  if (!pigId) {
    resetPreview();
    return;
  }

  try {
    const response = await fetch(`/api/pig-weights/${encodeURIComponent(pigId)}/latest`);
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

pigSelect.addEventListener("change", async (event) => {
  clearMessage();
  await loadLatestWeight(event.target.value);
});

weightKgInput.addEventListener("input", updateGrowthPreview);
weightDateInput.addEventListener("change", updateGrowthPreview);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();

  const payload = {
    pig_id: pigSelect.value,
    weight_date: weightDateInput.value,
    weight_kg: parseFloat(weightKgInput.value),
    condition_notes: conditionNotesInput.value.trim(),
    weighed_by: "WebApp"
  };

  submitButton.disabled = true;
  submitButton.textContent = "Saving...";

  try {
    const response = await fetch("/api/pig-weights", {
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

    showMessage("Weight saved successfully.", "success");
    conditionNotesInput.value = "";
    await loadLatestWeight(pigSelect.value);
  } catch (error) {
    showMessage("Something went wrong while saving.", "error");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Save Weight";
  }
});

setTodayDate();
loadPigs();