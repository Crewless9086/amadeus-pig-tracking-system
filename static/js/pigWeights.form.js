const pigSelect = document.getElementById("pig_id");
const weightDateInput = document.getElementById("weight_date");
const weightKgInput = document.getElementById("weight_kg");
const conditionNotesInput = document.getElementById("condition_notes");
const previousWeightEl = document.getElementById("previous_weight");
const previousWeightDateEl = document.getElementById("previous_weight_date");
const form = document.getElementById("pig-weight-form");
const submitButton = document.getElementById("submit_button");
const messageBox = document.getElementById("message_box");

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

function resetPreviousWeightDisplay() {
  previousWeightEl.textContent = "—";
  previousWeightDateEl.textContent = "—";
  weightKgInput.value = "";
}

async function loadPigs() {
  try {
    const response = await fetch("/api/pig-weights/pigs");
    const data = await response.json();

    pigSelect.innerHTML = '<option value="">Select a pig</option>';

    data.pigs.forEach((pig) => {
      const option = document.createElement("option");
      option.value = pig.pig_id;
      option.textContent = `${pig.pig_id} - ${pig.tag_number || "No Tag"}`;
      pigSelect.appendChild(option);
    });
  } catch (error) {
    pigSelect.innerHTML = '<option value="">Failed to load pigs</option>';
    showMessage("Could not load pigs.", "error");
  }
}

async function loadLatestWeight(pigId) {
  if (!pigId) {
    resetPreviousWeightDisplay();
    return;
  }

  try {
    const response = await fetch(`/api/pig-weights/${encodeURIComponent(pigId)}/latest`);
    const data = await response.json();

    if (data.previous_weight_kg !== null && data.previous_weight_kg !== "") {
      previousWeightEl.textContent = data.previous_weight_kg;
      weightKgInput.value = data.previous_weight_kg;
    } else {
      previousWeightEl.textContent = "No previous weight";
      weightKgInput.value = "";
    }

    previousWeightDateEl.textContent = data.previous_weight_date || "—";
  } catch (error) {
    resetPreviousWeightDisplay();
    showMessage("Could not load previous weight.", "error");
  }
}

pigSelect.addEventListener("change", async (event) => {
  clearMessage();
  await loadLatestWeight(event.target.value);
});

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