const messageBox = document.getElementById("pig_detail_message");

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

async function loadPigDetail() {
  const pigId = getPigIdFromUrl();

  if (!pigId) {
    showMessage("No pig ID found in URL.", "error");
    return;
  }

  try {
    const response = await fetch(`/api/pig-weights/${encodeURIComponent(pigId)}/detail`);
    const data = await response.json();

    if (!response.ok || !data.success) {
      showMessage(data.error || "Could not load pig detail.", "error");
      return;
    }

    const pig = data.pig;

    document.getElementById("pig_detail_title").textContent = pig.tag_number || pig.pig_id;
    document.getElementById("pig_detail_subtitle").textContent = `Pig Profile • ${pig.pig_id}`;
    document.getElementById("record_weight_button").href = `/pig-weights?pig_id=${encodeURIComponent(pig.pig_id)}`;
    document.getElementById("view_weight_history_button").href = `/pig/${encodeURIComponent(pig.pig_id)}/weights`;
    document.getElementById("record_treatment_button").href = `/pig/${encodeURIComponent(pig.pig_id)}/treatment`;
    document.getElementById("view_treatment_history_button").href = `/pig/${encodeURIComponent(pig.pig_id)}/treatments`;
    document.getElementById("record_movement_button").href = `/pig/${encodeURIComponent(pig.pig_id)}/movement`;
    document.getElementById("view_movement_history_button").href = `/pig/${encodeURIComponent(pig.pig_id)}/movements`;

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
  } catch (error) {
    showMessage("Something went wrong while loading pig detail.", "error");
  }
}

loadPigDetail();