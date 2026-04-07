const movementForm = document.getElementById("pig-movement-form");
const movementMessageBox = document.getElementById("movement_message_box");
const movementSubmitButton = document.getElementById("movement_submit_button");

const movementPigDisplayInput = document.getElementById("movement_pig_display");
const moveDateInput = document.getElementById("move_date");
const fromPenIdInput = document.getElementById("from_pen_id");
const toPenIdInput = document.getElementById("to_pen_id");
const reasonForMoveInput = document.getElementById("reason_for_move");
const movedByInput = document.getElementById("moved_by");
const moveNotesInput = document.getElementById("move_notes");
const currentPenDisplay = document.getElementById("current_pen_display");

let currentMovementPigId = "";
let currentMovementPigTag = "";
let currentPenIdValue = "";
let allPens = [];

function getPigIdFromMovementUrl() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 2] || "");
}

function setTodayDate() {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  moveDateInput.value = `${yyyy}-${mm}-${dd}`;
}

function showMovementMessage(message, type = "success") {
  movementMessageBox.classList.remove("hidden", "message-success", "message-error");
  movementMessageBox.classList.add(type === "success" ? "message-success" : "message-error");
  movementMessageBox.textContent = message;
}

function clearMovementMessage() {
  movementMessageBox.classList.add("hidden");
  movementMessageBox.textContent = "";
  movementMessageBox.classList.remove("message-success", "message-error");
}

async function loadMovementPig() {
  currentMovementPigId = getPigIdFromMovementUrl();

  if (!currentMovementPigId) {
    showMovementMessage("No pig ID found in URL.", "error");
    return;
  }

  try {
    const response = await fetch(`/api/pig-weights/pig/${encodeURIComponent(currentMovementPigId)}`);
    const data = await response.json();

    if (!response.ok || !data.success) {
      showMovementMessage("Could not load pig detail.", "error");
      return;
    }

    const pig = data.pig;
    currentMovementPigTag = pig.tag_number || pig.pig_id;
    currentPenIdValue = pig.current_pen_id || "";

    document.getElementById("movement_title").textContent = `Record Movement • ${currentMovementPigTag}`;
    document.getElementById("movement_subtitle").textContent = `Pig ID: ${pig.pig_id}`;
    movementPigDisplayInput.value = `${currentMovementPigTag} (${pig.pig_id})`;

    fromPenIdInput.value = currentPenIdValue;
    currentPenDisplay.textContent = currentPenIdValue || "No current pen";

    document.getElementById("movement_profile_button").href = `/pig/${encodeURIComponent(pig.pig_id)}`;
    document.getElementById("movement_history_button").href = `/pig/${encodeURIComponent(pig.pig_id)}/movements`;
  } catch (error) {
    console.error("loadMovementPig error:", error);
    showMovementMessage("Something went wrong while loading pig detail.", "error");
  }
}

async function loadPens() {
  try {
    const response = await fetch("/api/pig-weights/pens");
    const data = await response.json();

    allPens = data.pens || [];
    toPenIdInput.innerHTML = '<option value="">Select destination pen</option>';

    allPens.forEach((pen) => {
      const option = document.createElement("option");
      option.value = pen.pen_id;
      option.textContent = `${pen.pen_name} (${pen.pen_id})`;
      toPenIdInput.appendChild(option);
    });
  } catch (error) {
    console.error("loadPens error:", error);
    toPenIdInput.innerHTML = '<option value="">Failed to load pens</option>';
    showMovementMessage("Could not load pens.", "error");
  }
}

movementForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMovementMessage();

  const payload = {
    pig_id: currentMovementPigId,
    move_date: moveDateInput.value,
    from_pen_id: currentPenIdValue,
    to_pen_id: toPenIdInput.value,
    reason_for_move: reasonForMoveInput.value.trim(),
    moved_by: movedByInput.value.trim(),
    move_notes: moveNotesInput.value.trim()
  };

  movementSubmitButton.disabled = true;
  movementSubmitButton.textContent = "Saving...";

  try {
    const response = await fetch("/api/pig-weights/movements", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      const errorMessage = data.errors ? data.errors.join(" ") : "Failed to save movement.";
      showMovementMessage(errorMessage, "error");
      return;
    }

    showMovementMessage("Movement saved successfully.", "success");
    reasonForMoveInput.value = "";
    moveNotesInput.value = "";
  } catch (error) {
    console.error("save movement error:", error);
    showMovementMessage("Something went wrong while saving movement.", "error");
  } finally {
    movementSubmitButton.disabled = false;
    movementSubmitButton.textContent = "Save Movement";
  }
});

setTodayDate();
loadMovementPig();
loadPens();