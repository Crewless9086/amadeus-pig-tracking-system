const litterMessage = document.getElementById("litter_message");
const litterPigletsList = document.getElementById("litter_piglets_list");
const attentionPanel = document.getElementById("litter_attention_panel");
const attentionTitle = document.getElementById("litter_attention_title");
const attentionText = document.getElementById("litter_attention_text");
const markWeanedForm = document.getElementById("mark_weaned_form");
const markWeanedDate = document.getElementById("mark_weaned_date");
const markWeanedButton = document.getElementById("mark_weaned_button");
const newbornHealthForm = document.getElementById("newborn_health_form");
const newbornHealthDate = document.getElementById("newborn_health_date");
const newbornHealthEarmarked = document.getElementById("newborn_health_earmarked");
const newbornHealthAntiparasitic = document.getElementById("newborn_health_antiparasitic");
const newbornHealthDeworming = document.getElementById("newborn_health_deworming");
const newbornHealthVaccination = document.getElementById("newborn_health_vaccination");
const newbornHealthGivenBy = document.getElementById("newborn_health_given_by");
const newbornHealthNotes = document.getElementById("newborn_health_notes");
const newbornHealthPreview = document.getElementById("newborn_health_preview");
const newbornHealthPreviewButton = document.getElementById("newborn_health_preview_button");
const newbornHealthApplyButton = document.getElementById("newborn_health_apply_button");
let latestNewbornHealthPreview = null;
let productsLoaded = false;

function getLitterIdFromUrl() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 1] || "");
}

function todayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

function showLitterMessage(message, type = "error") {
  litterMessage.classList.remove("hidden", "message-success", "message-error");
  litterMessage.classList.add(type === "success" ? "message-success" : "message-error");
  litterMessage.textContent = message;
}

function clearLitterMessage() {
  litterMessage.classList.add("hidden");
  litterMessage.textContent = "";
}

function setText(id, value, suffix = "") {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent = value !== null && value !== undefined && value !== ""
    ? `${value}${suffix}`
    : "-";
}

function setLinkedValue(id, label, href) {
  const element = document.getElementById(id);
  if (!element) return;

  if (label && href) {
    element.innerHTML = `<a href="${href}" class="detail-link">${label}</a>`;
  } else {
    element.textContent = "-";
  }
}

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(decimals);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function productLabel(product) {
  const dose = product.default_dose !== null && product.default_dose !== undefined && product.default_dose !== ""
    ? ` / ${product.default_dose}${product.dose_unit ? ` ${product.dose_unit}` : ""}`
    : "";
  return `${product.product_name || product.product_id}${dose}`;
}

function productMatches(product, patterns) {
  const text = `${product.product_name || ""} ${product.product_category || ""}`.toLowerCase();
  return patterns.some((pattern) => text.includes(pattern));
}

function setSelectOptions(select, products, patterns, preferredName = "") {
  if (!select) return;
  select.innerHTML = '<option value="">None</option>';
  const matches = products.filter((product) => productMatches(product, patterns));
  matches.forEach((product) => {
    const option = document.createElement("option");
    option.value = product.product_id;
    option.textContent = productLabel(product);
    select.appendChild(option);
  });

  const preferred = matches.find((product) => (product.product_name || "").toLowerCase().includes(preferredName));
  if (preferred) {
    select.value = preferred.product_id;
  }
}

async function loadProductsForNewbornHealth() {
  if (productsLoaded) return;
  const response = await fetch("/api/pig-weights/products");
  const data = await response.json();
  if (!response.ok) {
    throw new Error("Could not load products.");
  }
  const products = data.products || [];
  setSelectOptions(newbornHealthAntiparasitic, products, ["antiparasitic", "parasite", "ecomectin"], "ecomectin");
  setSelectOptions(newbornHealthDeworming, products, ["deworm", "panacur"], "panacur");
  setSelectOptions(newbornHealthVaccination, products, ["vacc"], "");
  productsLoaded = true;
}

function renderAttention(litter) {
  const attention = litter.attention || {};
  const hasReason = Boolean(attention.reason || attention.recommended_action);
  const canMarkWeaned = attention.action_type === "mark_weaned";
  const attentionTextValue = `${attention.action_type || ""} ${attention.reason || ""} ${attention.recommended_action || ""}`.toLowerCase();
  const canRecordNewbornHealth =
    attention.action_type === "record_litter_newborn_health"
    || attentionTextValue.includes("earmark")
    || attentionTextValue.includes("deworm")
    || attentionTextValue.includes("antiparasitic")
    || attentionTextValue.includes("newborn health");

  attentionPanel.classList.toggle("hidden", !hasReason && !canMarkWeaned && !canRecordNewbornHealth);
  markWeanedForm.classList.toggle("hidden", !canMarkWeaned);
  newbornHealthForm.classList.toggle("hidden", !canRecordNewbornHealth);

  if (!hasReason && !canMarkWeaned && !canRecordNewbornHealth) return;

  attentionTitle.textContent = attention.reason || "Review Litter";
  attentionText.textContent = attention.recommended_action
    || "Confirm the litter status and update the weaning details when ready.";
  markWeanedDate.value = attention.wean_date || todayIsoDate();
  if (newbornHealthDate && !newbornHealthDate.value) {
    newbornHealthDate.value = todayIsoDate();
  }
  if (canRecordNewbornHealth) {
    loadProductsForNewbornHealth().catch(() => {
      showLitterMessage("Could not load products for newborn health.", "error");
    });
  }
}

function renderLifecycleOutcomes(litter) {
  const outcomes = litter.lifecycle_outcomes || {};
  setText("litter_outcome_active", outcomes.active);
  setText("litter_outcome_sold", outcomes.sold);
  setText("litter_outcome_slaughtered", outcomes.slaughtered);
  setText("litter_outcome_dead", outcomes.dead);
  setText("litter_outcome_removed", outcomes.removed);
  setText("litter_outcome_other", outcomes.other);
}

function setMarkWeanedSubmitting(isSubmitting) {
  markWeanedButton.disabled = isSubmitting;
  markWeanedButton.textContent = isSubmitting ? "Saving..." : "Mark as Weaned";
}

function newbornHealthPayload(dryRun) {
  return {
    action_date: newbornHealthDate.value,
    changed_by: newbornHealthGivenBy.value || "web_app",
    earmarked: newbornHealthEarmarked.checked,
    antiparasitic_product_id: newbornHealthAntiparasitic.value,
    deworming_product_id: newbornHealthDeworming.value,
    vaccination_product_id: newbornHealthVaccination.value,
    notes: newbornHealthNotes.value,
    dry_run: dryRun,
  };
}

function renderNewbornHealthPreview(preview) {
  if (!newbornHealthPreview) return;
  newbornHealthPreview.classList.remove("hidden");
  const treatmentCount = preview.treatment_rows_planned || 0;
  const pigletCount = preview.piglet_count || 0;
  newbornHealthPreview.innerHTML = `
    <div class="bulk-review-header">
      <strong>Preview ready</strong>
      <span>${pigletCount} piglet${pigletCount === 1 ? "" : "s"} / ${treatmentCount} treatment row${treatmentCount === 1 ? "" : "s"}</span>
    </div>
    <p class="form-helper">Earmarks and selected treatments will be saved for all active on-farm piglets in this litter.</p>
  `;
}

function resetNewbornHealthPreview() {
  latestNewbornHealthPreview = null;
  if (newbornHealthApplyButton) newbornHealthApplyButton.disabled = true;
  if (newbornHealthPreview) newbornHealthPreview.classList.add("hidden");
}

function setNewbornHealthSubmitting(isSubmitting, mode = "preview") {
  newbornHealthPreviewButton.disabled = isSubmitting;
  newbornHealthApplyButton.disabled = isSubmitting || !latestNewbornHealthPreview;
  newbornHealthPreviewButton.textContent = isSubmitting && mode === "preview" ? "Previewing..." : "Preview";
  newbornHealthApplyButton.textContent = isSubmitting && mode === "apply" ? "Saving..." : "Save Newborn Health";
}

async function previewNewbornHealth() {
  clearLitterMessage();
  latestNewbornHealthPreview = null;
  newbornHealthApplyButton.disabled = true;

  if (!newbornHealthDate.value) {
    showLitterMessage("Choose an action date before previewing.", "error");
    return;
  }

  setNewbornHealthSubmitting(true, "preview");
  try {
    const litterId = getLitterIdFromUrl();
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/newborn-health`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newbornHealthPayload(true)),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.error || "Could not preview newborn health action."]).join(" "));
    }
    latestNewbornHealthPreview = data;
    renderNewbornHealthPreview(data);
  } catch (error) {
    showLitterMessage(error.message || "Could not preview newborn health action.", "error");
  } finally {
    setNewbornHealthSubmitting(false, "preview");
  }
}

async function submitNewbornHealth(event) {
  event.preventDefault();
  clearLitterMessage();

  if (!latestNewbornHealthPreview) {
    showLitterMessage("Preview the newborn health action before saving.", "error");
    return;
  }
  if (!window.confirm("Save newborn health records for all active piglets in this litter?")) {
    return;
  }

  setNewbornHealthSubmitting(true, "apply");
  try {
    const litterId = getLitterIdFromUrl();
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/newborn-health`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newbornHealthPayload(false)),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.error || "Could not save newborn health action."]).join(" "));
    }
    latestNewbornHealthPreview = null;
    newbornHealthPreview.classList.add("hidden");
    showLitterMessage(data.message || "Newborn health action saved.", "success");
    await loadLitterDetail({ keepMessage: true });
  } catch (error) {
    showLitterMessage(error.message || "Could not save newborn health action.", "error");
  } finally {
    setNewbornHealthSubmitting(false, "apply");
  }
}

async function submitMarkWeaned(event) {
  event.preventDefault();
  clearLitterMessage();

  const litterId = getLitterIdFromUrl();
  const weanDate = markWeanedDate.value;

  if (!weanDate) {
    showLitterMessage("Choose a wean date before saving.", "error");
    return;
  }

  setMarkWeanedSubmitting(true);

  try {
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/mark-weaned`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        wean_date: weanDate,
        changed_by: "web_app",
      }),
    });
    const data = await response.json();

    if (!response.ok || !data.success) {
      showLitterMessage((data.errors || [data.error || "Could not mark litter as weaned."]).join(" "), "error");
      return;
    }

    showLitterMessage(data.message || "Litter was marked as weaned.", "success");
    await loadLitterDetail({ keepMessage: true });
  } catch (error) {
    showLitterMessage("Something went wrong while saving the litter action.", "error");
  } finally {
    setMarkWeanedSubmitting(false);
  }
}

function pigletWeightText(piglet) {
  return piglet.current_weight_kg !== null && piglet.current_weight_kg !== ""
    ? `${formatNumber(piglet.current_weight_kg, 2)} kg`
    : "No weight";
}

function buildPigletTable(piglets) {
  const rows = piglets.map((piglet) => {
    const profileHref = `/pig/${encodeURIComponent(piglet.pig_id)}`;
    const tagOrId = piglet.tag_number || piglet.pig_id;
    return `
      <tr class="litter-piglet-row" data-pig-profile="${profileHref}" tabindex="0">
        <td>
          <strong>${escapeHtml(tagOrId || "-")}</strong>
          <span class="table-subtext">${escapeHtml(piglet.pig_id || "-")}</span>
        </td>
        <td>${escapeHtml(piglet.sex || "-")}</td>
        <td>${escapeHtml(piglet.calculated_stage || "-")}</td>
        <td>${escapeHtml(pigletWeightText(piglet))}</td>
        <td>${escapeHtml(piglet.status || "-")}</td>
        <td>${escapeHtml(piglet.on_farm || "-")}</td>
        <td>${escapeHtml(piglet.age_days || "-")}</td>
        <td>${escapeHtml(piglet.current_pen_id || "-")}</td>
        <td><a class="small-action-button table-open-link" href="${profileHref}">Open</a></td>
      </tr>
    `;
  }).join("");

  return `
    <div class="simple-table-wrap litter-piglet-table">
      <table class="simple-table">
        <thead>
          <tr>
            <th>Piglet</th>
            <th>Sex</th>
            <th>Stage</th>
            <th>Weight</th>
            <th>Status</th>
            <th>On Farm</th>
            <th>Age</th>
            <th>Pen</th>
            <th>Profile</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function wirePigletTableRows() {
  document.querySelectorAll("[data-pig-profile]").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.closest("a")) return;
      window.location.href = row.dataset.pigProfile;
    });
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        window.location.href = row.dataset.pigProfile;
      }
    });
  });
}

async function loadLitterDetail(options = {}) {
  const litterId = getLitterIdFromUrl();

  if (!litterId) {
    showLitterMessage("No litter ID found in URL.", "error");
    return;
  }

  if (!options.keepMessage) {
    clearLitterMessage();
  }

  try {
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}`);
    const data = await response.json();

    if (!response.ok || !data.success) {
      showLitterMessage(data.error || "Could not load litter detail.", "error");
      return;
    }

    const litter = data.litter;

    document.getElementById("litter_title").textContent = `Litter - ${litter.litter_id}`;
    document.getElementById("litter_subtitle").textContent = `${litter.count} piglet(s) linked to this litter`;

    setText("litter_id_value", litter.litter_id);
    setText("litter_count_value", litter.count);
    setText("litter_male_count_value", litter.male_count);
    setText("litter_female_count_value", litter.female_count);
    setText("litter_active_count_value", litter.active_count);
    setText("litter_average_weight_value", litter.average_weight_kg, litter.average_weight_kg !== null ? " kg" : "");
    setText("litter_birth_date_value", litter.birth_date);
    setText("litter_estimated_wean_date_value", litter.estimated_wean_date);
    setText("litter_wean_attention_start_value", litter.wean_tag_attention_start_date);
    setText(
      "litter_days_until_wean_value",
      litter.days_until_estimated_wean,
      litter.days_until_estimated_wean !== null && litter.days_until_estimated_wean !== undefined ? " days" : ""
    );

    setLinkedValue(
      "litter_mother_value",
      litter.mother_tag_number || litter.mother_pig_id,
      litter.mother_pig_id ? `/pig/${encodeURIComponent(litter.mother_pig_id)}` : ""
    );

    setLinkedValue(
      "litter_father_value",
      litter.father_tag_number || litter.father_pig_id,
      litter.father_pig_id ? `/pig/${encodeURIComponent(litter.father_pig_id)}` : ""
    );

    renderAttention(litter);
    renderLifecycleOutcomes(litter);
    litterPigletsList.innerHTML = "";

    if (!litter.piglets.length) {
      litterPigletsList.innerHTML = `
        <div class="empty-state">
          <strong>No piglets found in this litter.</strong>
          <span>Check the litter links in PIG_OVERVIEW.</span>
        </div>
      `;
      return;
    }

    litterPigletsList.innerHTML = buildPigletTable(litter.piglets);
    wirePigletTableRows();
  } catch (error) {
    showLitterMessage("Something went wrong while loading litter detail.", "error");
  }
}

markWeanedForm.addEventListener("submit", submitMarkWeaned);
newbornHealthPreviewButton.addEventListener("click", previewNewbornHealth);
newbornHealthForm.addEventListener("submit", submitNewbornHealth);
[
  newbornHealthDate,
  newbornHealthEarmarked,
  newbornHealthAntiparasitic,
  newbornHealthDeworming,
  newbornHealthVaccination,
  newbornHealthNotes,
].forEach((element) => {
  if (element) element.addEventListener("change", resetNewbornHealthPreview);
});
loadLitterDetail();
