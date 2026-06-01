const messageBox = document.getElementById("pig_detail_message");
const lifecyclePanel = document.getElementById("lifecycle_action_panel");
const lifecycleForm = document.getElementById("lifecycle_death_form");
const lifecycleEventDate = document.getElementById("lifecycle_event_date");
const lifecycleReason = document.getElementById("lifecycle_reason");
const lifecycleChangedBy = document.getElementById("lifecycle_changed_by");
const lifecycleNotes = document.getElementById("lifecycle_notes");
const lifecycleSubmitButton = document.getElementById("lifecycle_submit_button");
let currentPigId = "";

function getPigIdFromUrl() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 1] || "");
}

function showMessage(message, type = "error") {
  messageBox.classList.remove("hidden", "message-success", "message-error");
  messageBox.classList.add(type === "success" ? "message-success" : "message-error");
  messageBox.textContent = message;
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

function todayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

function setLifecycleSubmitting(isSubmitting) {
  if (!lifecycleSubmitButton) return;
  lifecycleSubmitButton.disabled = isSubmitting;
  lifecycleSubmitButton.textContent = isSubmitting ? "Saving..." : "Record Death / Removal";
}

function updateLifecyclePanel(pig) {
  if (!lifecyclePanel) return;
  const canRecordOutcome = pig.status === "Active" && pig.on_farm === "Yes";
  lifecyclePanel.classList.toggle("hidden", !canRecordOutcome);
  if (canRecordOutcome && lifecycleEventDate && !lifecycleEventDate.value) {
    lifecycleEventDate.value = todayIsoDate();
  }
}

async function loadPigDetail() {
  const pigId = getPigIdFromUrl();

  if (!pigId) {
    showMessage("No pig ID found in URL.", "error");
    return;
  }

  try {
    const response = await fetch(`/api/pig-weights/pig/${encodeURIComponent(pigId)}`);
    const data = await response.json();

    if (!response.ok || !data.success) {
      showMessage(data.error || "Could not load pig detail.", "error");
      return;
    }

    const pig = data.pig;
    currentPigId = pig.pig_id;

    document.getElementById("pig_detail_title").textContent = pig.tag_number || pig.pig_id;
    document.getElementById("pig_detail_subtitle").textContent = `Pig Profile • ${pig.pig_id}`;
    document.getElementById("record_weight_button").href = `/pig-weights?pig_id=${encodeURIComponent(pig.pig_id)}`;
    document.getElementById("view_weight_history_button").href = `/pig/${encodeURIComponent(pig.pig_id)}/weights`;
    document.getElementById("record_treatment_button").href = `/pig/${encodeURIComponent(pig.pig_id)}/treatment`;
    document.getElementById("view_treatment_history_button").href = `/pig/${encodeURIComponent(pig.pig_id)}/treatments`;
    document.getElementById("record_movement_button").href = `/pig/${encodeURIComponent(pig.pig_id)}/movement`;
    document.getElementById("view_movement_history_button").href = `/pig/${encodeURIComponent(pig.pig_id)}/movements`;
    document.getElementById("view_family_tree_button").href = `/pig/${encodeURIComponent(pig.pig_id)}/family-tree`;

    setText("detail_tag_number", pig.tag_number);
    setText("detail_pig_id", pig.pig_id);
    setText("detail_status", pig.status);
    setText("detail_on_farm", pig.on_farm);
    setText("detail_animal_type", pig.animal_type);
    setText("detail_sex", pig.sex);
    setText("detail_purpose", pig.purpose);
    setText("detail_dob", pig.date_of_birth);
    setText("detail_age_days", pig.age_days);
    setText("detail_pen", pig.current_pen_id);
    setText("detail_weight", pig.current_weight_kg, pig.current_weight_kg !== "" ? " kg" : "");
    setText("detail_last_weight_date", pig.last_weight_date);
    setText("detail_stage", pig.calculated_stage);
    setText("detail_weight_band", pig.weight_band);
    setText("detail_sale_ready", pig.is_sale_ready);
    setText("detail_reserved_status", pig.reserved_status);
    setText("detail_last_treatment_date", pig.last_treatment_date);
    setText("detail_last_product_name", pig.last_product_name);
    setText("detail_withdrawal_end_date", pig.current_withdrawal_end_date);
    setText("detail_withdrawal_clear", pig.withdrawal_clear);

    setLinkedValue(
      "detail_mother",
      pig.mother_tag_number || pig.mother_pig_id,
      pig.mother_pig_id ? `/pig/${encodeURIComponent(pig.mother_pig_id)}` : ""
    );

    setLinkedValue(
      "detail_father",
      pig.father_tag_number || pig.father_pig_id,
      pig.father_pig_id ? `/pig/${encodeURIComponent(pig.father_pig_id)}` : ""
    );

    setLinkedValue(
      "detail_litter",
      pig.litter_id,
      pig.litter_id ? `/litter/${encodeURIComponent(pig.litter_id)}` : ""
    );

    setText("detail_notes", pig.general_notes);
    updateLifecyclePanel(pig);
  } catch (error) {
    showMessage("Something went wrong while loading pig detail.", "error");
  }
}

async function submitLifecycleDeath(event) {
  event.preventDefault();
  if (!currentPigId) {
    showMessage("Pig details have not loaded yet.", "error");
    return;
  }

  if (!window.confirm("Record this lifecycle outcome? The pig row will be kept for history and reporting.")) {
    return;
  }

  setLifecycleSubmitting(true);
  try {
    const response = await fetch(`/api/pig-weights/pig/${encodeURIComponent(currentPigId)}/lifecycle/death`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_date: lifecycleEventDate.value,
        reason: lifecycleReason.value,
        changed_by: lifecycleChangedBy.value,
        notes: lifecycleNotes.value,
      }),
    });
    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error((data.errors || []).join(" ") || "Could not record lifecycle outcome.");
    }

    showMessage(data.message || "Lifecycle outcome recorded.", "success");
    lifecycleForm.reset();
    lifecycleEventDate.value = todayIsoDate();
    lifecycleChangedBy.value = "web_app";
    await loadPigDetail();
  } catch (error) {
    showMessage(error.message || "Something went wrong while recording lifecycle outcome.", "error");
  } finally {
    setLifecycleSubmitting(false);
  }
}

if (lifecycleForm) {
  lifecycleForm.addEventListener("submit", submitLifecycleDeath);
}

loadPigDetail();
