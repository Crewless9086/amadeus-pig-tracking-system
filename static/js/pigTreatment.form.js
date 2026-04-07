const treatmentForm = document.getElementById("pig-treatment-form");
const treatmentMessageBox = document.getElementById("treatment_message_box");
const treatmentSubmitButton = document.getElementById("treatment_submit_button");

const pigDisplayInput = document.getElementById("pig_display");
const treatmentDateInput = document.getElementById("treatment_date");
const treatmentTypeInput = document.getElementById("treatment_type");
const productIdInput = document.getElementById("product_id");
const doseInput = document.getElementById("dose");
const doseUnitInput = document.getElementById("dose_unit");
const routeInput = document.getElementById("route");
const reasonInput = document.getElementById("reason_for_treatment");
const batchInput = document.getElementById("batch_lot_number");
const givenByInput = document.getElementById("given_by");
const followUpRequiredInput = document.getElementById("follow_up_required");
const followUpDateInput = document.getElementById("follow_up_date");
const medicalNotesInput = document.getElementById("medical_notes");

const productDefaultDoseEl = document.getElementById("product_default_dose");
const productDoseUnitEl = document.getElementById("product_dose_unit");
const productWithdrawalDaysEl = document.getElementById("product_withdrawal_days");
const productSupplierEl = document.getElementById("product_supplier");

let currentPigId = "";
let currentPigTag = "";
let allProducts = [];

function getPigIdFromUrl() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 2] || "");
}

function setTodayDate() {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  treatmentDateInput.value = `${yyyy}-${mm}-${dd}`;
}

function showMessage(message, type = "success") {
  treatmentMessageBox.classList.remove("hidden", "message-success", "message-error");
  treatmentMessageBox.classList.add(type === "success" ? "message-success" : "message-error");
  treatmentMessageBox.textContent = message;
}

function clearMessage() {
  treatmentMessageBox.classList.add("hidden");
  treatmentMessageBox.textContent = "";
  treatmentMessageBox.classList.remove("message-success", "message-error");
}

function setProductPreview(product) {
  if (!product) {
    productDefaultDoseEl.textContent = "—";
    productDoseUnitEl.textContent = "—";
    productWithdrawalDaysEl.textContent = "—";
    productSupplierEl.textContent = "—";
    return;
  }

  productDefaultDoseEl.textContent = product.default_dose ?? "—";
  productDoseUnitEl.textContent = product.dose_unit || "—";
  productWithdrawalDaysEl.textContent = product.default_withdrawal_days ?? "—";
  productSupplierEl.textContent = product.supplier || "—";

  if ((doseInput.value === "" || doseInput.value === null) && product.default_dose !== null && product.default_dose !== undefined) {
    doseInput.value = product.default_dose;
  }

  if (!doseUnitInput.value && product.dose_unit) {
    doseUnitInput.value = product.dose_unit;
  }
}

async function loadPig() {
  currentPigId = getPigIdFromUrl();

  if (!currentPigId) {
    showMessage("No pig ID found in URL.", "error");
    return;
  }

  try {
    const response = await fetch(`/api/pig-weights/pig/${encodeURIComponent(currentPigId)}`);
    const data = await response.json();

    if (!response.ok || !data.success) {
      showMessage("Could not load pig detail.", "error");
      return;
    }

    const pig = data.pig;
    currentPigTag = pig.tag_number || pig.pig_id;

    document.getElementById("treatment_title").textContent = `Record Treatment • ${currentPigTag}`;
    document.getElementById("treatment_subtitle").textContent = `Pig ID: ${pig.pig_id}`;
    pigDisplayInput.value = `${currentPigTag} (${pig.pig_id})`;

    document.getElementById("treatment_profile_button").href = `/pig/${encodeURIComponent(pig.pig_id)}`;
    document.getElementById("treatment_history_button").href = `/pig/${encodeURIComponent(pig.pig_id)}/treatments`;
  } catch (error) {
    showMessage("Something went wrong while loading pig detail.", "error");
  }
}

async function loadProducts() {
  try {
    const response = await fetch("/api/pig-weights/products");
    const data = await response.json();

    allProducts = data.products || [];
    productIdInput.innerHTML = '<option value="">Select product</option>';

    allProducts.forEach((product) => {
      const option = document.createElement("option");
      option.value = product.product_id;
      option.textContent = product.product_name;
      productIdInput.appendChild(option);
    });
  } catch (error) {
    productIdInput.innerHTML = '<option value="">Failed to load products</option>';
    showMessage("Could not load products.", "error");
  }
}

productIdInput.addEventListener("change", () => {
  const selected = allProducts.find((p) => p.product_id === productIdInput.value);
  setProductPreview(selected);
});

treatmentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();

  const payload = {
    pig_id: currentPigId,
    treatment_date: treatmentDateInput.value,
    treatment_type: treatmentTypeInput.value,
    product_id: productIdInput.value,
    dose: doseInput.value ? parseFloat(doseInput.value) : "",
    dose_unit: doseUnitInput.value.trim(),
    route: routeInput.value,
    reason_for_treatment: reasonInput.value.trim(),
    batch_lot_number: batchInput.value.trim(),
    given_by: givenByInput.value.trim(),
    follow_up_required: followUpRequiredInput.value,
    follow_up_date: followUpDateInput.value,
    medical_notes: medicalNotesInput.value.trim()
  };

  treatmentSubmitButton.disabled = true;
  treatmentSubmitButton.textContent = "Saving...";

  try {
    const response = await fetch("/api/pig-weights/treatments", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      const errorMessage = data.errors ? data.errors.join(" ") : "Failed to save treatment.";
      showMessage(errorMessage, "error");
      return;
    }

    showMessage("Treatment saved successfully.", "success");

    medicalNotesInput.value = "";
    batchInput.value = "";
    reasonInput.value = "";
    followUpRequiredInput.value = "";
    followUpDateInput.value = "";
  } catch (error) {
    showMessage("Something went wrong while saving treatment.", "error");
  } finally {
    treatmentSubmitButton.disabled = false;
    treatmentSubmitButton.textContent = "Save Treatment";
  }
});

setTodayDate();
loadPig();
loadProducts();