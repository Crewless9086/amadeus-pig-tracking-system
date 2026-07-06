const litterMessage = document.getElementById("litter_message");
const litterPigletsList = document.getElementById("litter_piglets_list");
const litterDetailBackLink = document.getElementById("litter_detail_back_link");
const attentionPanel = document.getElementById("litter_attention_panel");
const attentionTitle = document.getElementById("litter_attention_title");
const attentionText = document.getElementById("litter_attention_text");
const attentionLinks = document.getElementById("litter_attention_links");
const markWeanedForm = document.getElementById("mark_weaned_form");
const markWeanedDate = document.getElementById("mark_weaned_date");
const markWeanedUseLatestWeights = document.getElementById("mark_weaned_use_latest_weights");
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
const pigletDeathPanel = document.getElementById("litter_piglet_death_panel");
const pigletDeathForm = document.getElementById("piglet_death_form");
const pigletDeathDate = document.getElementById("piglet_death_date");
const pigletDeathReason = document.getElementById("piglet_death_reason");
const pigletDeathCount = document.getElementById("piglet_death_count");
const pigletDeathMaleCount = document.getElementById("piglet_death_male_count");
const pigletDeathFemaleCount = document.getElementById("piglet_death_female_count");
const pigletDeathRecordedBy = document.getElementById("piglet_death_recorded_by");
const pigletDeathNotes = document.getElementById("piglet_death_notes");
const pigletDeathPreview = document.getElementById("piglet_death_preview");
const pigletDeathPreviewButton = document.getElementById("piglet_death_preview_button");
const pigletDeathApplyButton = document.getElementById("piglet_death_apply_button");
const sexCountPanel = document.getElementById("litter_sex_count_panel");
const sexCountForm = document.getElementById("sex_count_form");
const sexCountDate = document.getElementById("sex_count_date");
const sexCountMale = document.getElementById("sex_count_male");
const sexCountFemale = document.getElementById("sex_count_female");
const sexCountRecordedBy = document.getElementById("sex_count_recorded_by");
const sexCountNotes = document.getElementById("sex_count_notes");
const sexCountPreview = document.getElementById("sex_count_preview");
const sexCountPreviewButton = document.getElementById("sex_count_preview_button");
const sexCountApplyButton = document.getElementById("sex_count_apply_button");
const tagNumbersForm = document.getElementById("tag_numbers_form");
const tagNumbersText = document.getElementById("tag_numbers_text");
const tagNumbersDate = document.getElementById("tag_numbers_date");
const tagNumbersRecordedBy = document.getElementById("tag_numbers_recorded_by");
const tagNumbersNotes = document.getElementById("tag_numbers_notes");
const tagNumbersPreview = document.getElementById("tag_numbers_preview");
const tagNumbersPreviewButton = document.getElementById("tag_numbers_preview_button");
const tagNumbersApplyButton = document.getElementById("tag_numbers_apply_button");
const reconcilePanel = document.getElementById("litter_reconcile_panel");
const reconcileForm = document.getElementById("litter_reconcile_form");
const reconcileText = document.getElementById("litter_reconcile_text");
const reconcileBornAlive = document.getElementById("reconcile_born_alive");
const reconcileLinkedRecords = document.getElementById("reconcile_linked_records");
const reconcileSuggested = document.getElementById("reconcile_suggested");
const reconcileTargetBornAlive = document.getElementById("reconcile_target_born_alive");
const reconcileChangedBy = document.getElementById("reconcile_changed_by");
const reconcileReason = document.getElementById("reconcile_reason");
const reconcilePreview = document.getElementById("litter_reconcile_preview");
const reconcilePreviewButton = document.getElementById("reconcile_preview_button");
const reconcileApplyButton = document.getElementById("reconcile_apply_button");
const stillbornPanel = document.getElementById("litter_stillborn_panel");
const stillbornReclassifyForm = document.getElementById("stillborn_reclassify_form");
const stillbornReclassifyText = document.getElementById("stillborn_reclassify_text");
const stillbornExpected = document.getElementById("stillborn_expected");
const stillbornExisting = document.getElementById("stillborn_existing");
const stillbornShortfall = document.getElementById("stillborn_shortfall");
const stillbornReclassifyChangedBy = document.getElementById("stillborn_reclassify_changed_by");
const stillbornReclassifyReason = document.getElementById("stillborn_reclassify_reason");
const stillbornReclassifyPreview = document.getElementById("stillborn_reclassify_preview");
const stillbornReclassifyPreviewButton = document.getElementById("stillborn_reclassify_preview_button");
const stillbornReclassifyApplyButton = document.getElementById("stillborn_reclassify_apply_button");
const manualActionsPanel = document.getElementById("litter_manual_actions_panel");
const manualActionsText = document.getElementById("litter_manual_actions_text");
const manualActionsToggle = document.getElementById("litter_manual_actions_toggle");
const weaningDayPanel = document.getElementById("weaning_day_panel");
const weaningDayForm = document.getElementById("weaning_day_form");
const weaningDayDate = document.getElementById("weaning_day_date");
const weaningDayTargetPen = document.getElementById("weaning_day_target_pen");
const weaningDayAntiparasitic = document.getElementById("weaning_day_antiparasitic");
const weaningDayDeworming = document.getElementById("weaning_day_deworming");
const weaningDayVaccination = document.getElementById("weaning_day_vaccination");
const weaningDayRecordedBy = document.getElementById("weaning_day_recorded_by");
const weaningDayNotes = document.getElementById("weaning_day_notes");
const weaningDayPreview = document.getElementById("weaning_day_preview");
const weaningDayPreviewButton = document.getElementById("weaning_day_preview_button");
const weaningDayApplyButton = document.getElementById("weaning_day_apply_button");
let latestNewbornHealthPreview = null;
let latestPigletDeathPreview = null;
let latestSexCountPreview = null;
let latestTagNumbersPreview = null;
let latestReconcilePreview = null;
let latestStillbornReclassifyPreview = null;
let latestWeaningDayPreview = null;
let productsLoaded = false;
let weaningProductsLoaded = false;
let pensLoaded = false;
let manualActionsExpanded = false;

function getLitterIdFromUrl() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 1] || "");
}

function todayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

function safeInternalReturnPath(value) {
  const path = String(value || "").trim();
  if (!path.startsWith("/") || path.startsWith("//")) {
    return "";
  }
  return path;
}

function updateBackLinkFromQuery() {
  if (!litterDetailBackLink) return;
  const params = new URLSearchParams(window.location.search);
  const returnTo = safeInternalReturnPath(params.get("return_to"));
  const returnLabel = String(params.get("return_label") || "").trim();
  if (!returnTo) return;
  litterDetailBackLink.href = returnTo;
  litterDetailBackLink.textContent = `← ${returnLabel || "Back"}`;
}

function pigProfileHref(pigId, litterId) {
  const params = new URLSearchParams({
    return_to: `/litter/${litterId}`,
    return_label: "Back to Litter",
  });
  return `/pig/${encodeURIComponent(pigId)}?${params.toString()}`;
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

function setVisible(id, isVisible) {
  const element = document.getElementById(id);
  if (!element) return;
  element.classList.toggle("hidden", !isVisible);
}

function detailState(litter) {
  const state = String(litter.detail_state || "").toLowerCase();
  if (state) return state;
  const status = String(litter.litter_status || "").toLowerCase();
  if (status === "completed") return "completed";
  if (status === "weaned") return "weaned";
  return "active";
}

function renderStateSummary(litter) {
  const state = detailState(litter);
  const summaryPanel = document.getElementById("litter_summary_panel");
  const intro = document.getElementById("litter_summary_intro");
  const averageLabel = document.getElementById("litter_average_weight_label");

  if (summaryPanel) {
    summaryPanel.classList.remove("litter-state-active", "litter-state-weaned", "litter-state-completed");
    summaryPanel.classList.add(`litter-state-${state}`);
  }

  if (intro) {
    if (state === "completed") {
      intro.textContent = "Completed litter outcome summary. Active wean countdowns are closed.";
    } else if (state === "weaned") {
      intro.textContent = "Weaned litter summary. Growth now continues on each individual pig profile.";
    } else {
      intro.textContent = "Active litter records and current linked piglet counts.";
    }
  }

  if (averageLabel) {
    averageLabel.textContent = state === "active" ? "Average Current Weight" : "Average Wean Weight";
  }

  setVisible("litter_estimated_wean_card", state === "active");
  setVisible("litter_wean_attention_card", state === "active");
  setVisible("litter_days_until_wean_card", state === "active");
  setVisible("litter_actual_wean_card", state !== "active");
  setText("litter_actual_wean_date_value", litter.wean_date);
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

async function loadProductsForWeaningDay() {
  if (weaningProductsLoaded) return;
  const response = await fetch("/api/pig-weights/products");
  const data = await response.json();
  if (!response.ok) {
    throw new Error("Could not load products.");
  }
  const products = data.products || [];
  setSelectOptions(weaningDayAntiparasitic, products, ["antiparasitic", "parasite", "ecomectin"], "ecomectin");
  setSelectOptions(weaningDayDeworming, products, ["deworm", "panacur"], "panacur");
  setSelectOptions(weaningDayVaccination, products, ["vacc"], "");
  weaningProductsLoaded = true;
}

async function loadPensForWeaningDay() {
  if (pensLoaded || !weaningDayTargetPen) return;
  const response = await fetch("/api/pig-weights/pens");
  const data = await response.json();
  if (!response.ok) {
    throw new Error("Could not load pens.");
  }
  const currentValue = weaningDayTargetPen.value;
  weaningDayTargetPen.innerHTML = '<option value="">No pen move</option>';
  (data.pens || []).forEach((pen) => {
    const option = document.createElement("option");
    option.value = pen.pen_id || pen.Pen_ID || "";
    option.textContent = `${pen.pen_name || pen.Pen_Name || option.value}${option.value ? ` (${option.value})` : ""}`;
    if (option.value) weaningDayTargetPen.appendChild(option);
  });
  weaningDayTargetPen.value = currentValue;
  pensLoaded = true;
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
  if (attentionLinks) {
    attentionLinks.innerHTML = "";
  }

  if (!hasReason && !canMarkWeaned && !canRecordNewbornHealth) return;

  attentionTitle.textContent = attention.reason || "Review Litter";
  attentionText.textContent = attention.recommended_action
    || "Confirm the litter status and update the weaning details when ready.";
  renderAttentionLinks(litter.litter_id, attention.action_type);
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

function renderAttentionLinks(litterId, actionType) {
  if (!attentionLinks) return;
  const encodedLitterId = encodeURIComponent(litterId || getLitterIdFromUrl());
  const links = [];
  if (actionType === "review_purpose") {
    links.push(`<a class="button-link button-link-secondary" href="/purpose-review?litter_id=${encodedLitterId}">Open Purpose Review</a>`);
  }
  if (actionType === "record_post_wean_weight") {
    links.push(`<a class="button-link button-link-secondary" href="/bulk-weights?return_to=${encodeURIComponent(`/purpose-review?litter_id=${litterId || getLitterIdFromUrl()}`)}&return_label=${encodeURIComponent("Back to Purpose Review")}">Capture Weights</a>`);
  }
  if (actionType && actionType !== "mark_weaned") {
    links.push('<a class="button-link button-link-secondary" href="/">Dashboard</a>');
  }
  attentionLinks.innerHTML = links.join("");
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

function reconcilePayload(dryRun) {
  return {
    target_born_alive: reconcileTargetBornAlive.value,
    changed_by: reconcileChangedBy.value || "web_app",
    reason: reconcileReason.value,
    dry_run: dryRun,
  };
}

function resetReconcilePreview() {
  latestReconcilePreview = null;
  if (reconcileApplyButton) reconcileApplyButton.disabled = true;
  if (reconcilePreview) reconcilePreview.classList.add("hidden");
}

function setReconcileSubmitting(isSubmitting, mode = "preview") {
  reconcilePreviewButton.disabled = isSubmitting;
  reconcileApplyButton.disabled = isSubmitting || !latestReconcilePreview;
  reconcilePreviewButton.textContent = isSubmitting && mode === "preview" ? "Previewing..." : "Preview";
  reconcileApplyButton.textContent = isSubmitting && mode === "apply" ? "Saving..." : "Save Correction";
}

function renderReconcilePreview(preview) {
  if (!reconcilePreview) return;
  reconcilePreview.classList.remove("hidden");
  reconcilePreview.innerHTML = `
    <div class="bulk-review-header">
      <strong>Preview ready</strong>
      <span>Born Alive will become ${escapeHtml(preview.target_born_alive)}</span>
    </div>
    <p class="form-helper">This writes only to LITTERS. LITTER_OVERVIEW will recalculate from the sheet formula.</p>
  `;
}

function renderReconcilePanel(litter) {
  const reconciliation = litter.reconciliation || {};
  const canReconcileBirthCount = Boolean(reconciliation.can_reconcile_birth_count);
  const stillbornFixAvailable = Boolean(reconciliation.can_reclassify_stillborn);
  if (reconcilePanel) {
    reconcilePanel.classList.toggle("hidden", stillbornFixAvailable || !canReconcileBirthCount);
  }
  if (stillbornFixAvailable || !canReconcileBirthCount) {
    resetReconcilePreview();
    return;
  }

  reconcileBornAlive.textContent = reconciliation.born_alive ?? "-";
  reconcileLinkedRecords.textContent = reconciliation.linked_pig_records ?? "-";
  reconcileSuggested.textContent = reconciliation.suggested_born_alive ?? "-";
  reconcileTargetBornAlive.value = reconciliation.suggested_born_alive ?? "";
  reconcileText.textContent = `The source litter says ${reconciliation.born_alive ?? "-"} born alive, but ${reconciliation.linked_pig_records ?? "-"} piglet record(s) are linked.`;
  if (reconcileTargetBornAlive) reconcileTargetBornAlive.disabled = false;
  if (reconcileReason) reconcileReason.disabled = false;
  if (reconcilePreviewButton) reconcilePreviewButton.disabled = false;
  if (reconcileApplyButton) reconcileApplyButton.disabled = true;
}

function stillbornReclassifyPayload(dryRun) {
  const reconciliation = (window.currentLitterDetail || {}).reconciliation || {};
  return {
    count: reconciliation.stillborn_history_shortfall,
    changed_by: stillbornReclassifyChangedBy.value || "web_app",
    reason: stillbornReclassifyReason.value,
    dry_run: dryRun,
  };
}

function resetStillbornReclassifyPreview() {
  latestStillbornReclassifyPreview = null;
  if (stillbornReclassifyApplyButton) stillbornReclassifyApplyButton.disabled = true;
  if (stillbornReclassifyPreview) stillbornReclassifyPreview.classList.add("hidden");
}

function setStillbornReclassifySubmitting(isSubmitting, mode = "preview") {
  stillbornReclassifyPreviewButton.disabled = isSubmitting;
  stillbornReclassifyApplyButton.disabled = isSubmitting || !latestStillbornReclassifyPreview;
  stillbornReclassifyPreviewButton.textContent = isSubmitting && mode === "preview" ? "Previewing..." : "Preview";
  stillbornReclassifyApplyButton.textContent = isSubmitting && mode === "apply" ? "Saving..." : "Save Stillborn Fix";
}

function renderStillbornReclassifyPreview(preview) {
  if (!stillbornReclassifyPreview) return;
  stillbornReclassifyPreview.classList.remove("hidden");
  const selected = preview.selected_piglets || [];
  const rows = selected.map((piglet) => `
    <tr>
      <td>${escapeHtml(piglet.tag_number || piglet.pig_id || "-")}</td>
      <td>${escapeHtml(piglet.pig_id || "-")}</td>
      <td>${escapeHtml(piglet.exit_date || "-")}</td>
      <td>${escapeHtml(piglet.exit_reason || "-")}</td>
    </tr>
  `).join("");
  stillbornReclassifyPreview.innerHTML = `
    <div class="bulk-review-header">
      <strong>Preview ready</strong>
      <span>${preview.correction_count || 0} row${preview.correction_count === 1 ? "" : "s"} will become Stillborn</span>
    </div>
    <div class="simple-table-wrap">
      <table class="simple-table compact-table">
        <thead>
          <tr>
            <th>Piglet</th>
            <th>Pig ID</th>
            <th>Old Exit Date</th>
            <th>Old Reason</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="form-helper">Exit date will be set to the farrowing date and Exit Reason will become Stillborn.</p>
  `;
}

function renderStillbornReclassifyPanel(litter) {
  const reconciliation = litter.reconciliation || {};
  const canFix = Boolean(reconciliation.can_reclassify_stillborn);
  if (stillbornPanel) {
    stillbornPanel.classList.toggle("hidden", !canFix);
  }
  if (!canFix) {
    resetStillbornReclassifyPreview();
    return;
  }

  stillbornExpected.textContent = reconciliation.stillborn_count ?? "-";
  stillbornExisting.textContent = reconciliation.stillborn_history_count ?? "-";
  stillbornShortfall.textContent = reconciliation.stillborn_history_shortfall ?? "-";
  stillbornReclassifyText.textContent = reconciliation.recommended_action
    || "Preview the dead piglet rows that should become Stillborn history rows.";
}

function manualActionAvailability(litter) {
  if (detailState(litter) !== "active") {
    return {
      canRecordPigletDeath: false,
      canRecordSexCounts: false,
      canAssignTagNumbers: false,
      activeUnsexedCount: 0,
      activeUntaggedCount: 0,
    };
  }

  const hasActivePiglets = Number(litter.active_count || 0) > 0;
  const activeUnsexedPiglets = (litter.piglets || []).filter((piglet) => (
    piglet.status === "Active"
    && piglet.on_farm === "Yes"
    && !piglet.sex
  ));
  const activeUntaggedPiglets = (litter.piglets || []).filter((piglet) => (
    piglet.status === "Active"
    && piglet.on_farm === "Yes"
    && !piglet.tag_number
  ));
  return {
    canRecordPigletDeath: hasActivePiglets,
    canRecordSexCounts: activeUnsexedPiglets.length > 0,
    canAssignTagNumbers: activeUntaggedPiglets.length > 0,
    activeUnsexedCount: activeUnsexedPiglets.length,
    activeUntaggedCount: activeUntaggedPiglets.length,
  };
}

function renderManualActionsPanel(litter) {
  const availability = manualActionAvailability(litter);
  const hasManualActions = availability.canRecordPigletDeath || availability.canRecordSexCounts || availability.canAssignTagNumbers;
  if (manualActionsPanel) {
    manualActionsPanel.classList.toggle("hidden", !hasManualActions);
  }
  if (!hasManualActions) return;

  const labels = [];
  if (availability.canRecordPigletDeath) labels.push("piglet death");
  if (availability.canRecordSexCounts) labels.push("sex counts");
  if (availability.canAssignTagNumbers) labels.push("tag numbers");
  manualActionsText.textContent = `Available: ${labels.join(", ")}. Keep hidden unless you need to record one now.`;
  manualActionsToggle.textContent = manualActionsExpanded ? "Hide Manual Actions" : "Show Manual Actions";
}

function renderWeaningDayPanel(litter) {
  const isActive = detailState(litter) === "active";
  if (weaningDayPanel) {
    weaningDayPanel.classList.toggle("hidden", !isActive);
  }
  if (!isActive) {
    resetWeaningDayPreview();
    return;
  }
  if (weaningDayDate && !weaningDayDate.value) {
    weaningDayDate.value = todayIsoDate();
  }
  loadProductsForWeaningDay().catch(() => {
    showLitterMessage("Could not load products for weaning day.", "error");
  });
  loadPensForWeaningDay().catch(() => {
    showLitterMessage("Could not load pens for weaning day.", "error");
  });
}

function weaningDayPayload(dryRun) {
  const assignments = Array.from(document.querySelectorAll(".piglet-tag-input"))
    .map((input) => ({
      pig_id: input.dataset.pigId || "",
      tag_number: input.value.trim(),
    }))
    .filter((assignment) => assignment.pig_id || assignment.tag_number);
  return {
    wean_date: weaningDayDate.value,
    assignments,
    target_pen_id: weaningDayTargetPen.value,
    changed_by: weaningDayRecordedBy.value || "web_app",
    notes: weaningDayNotes.value,
    medicine: {
      antiparasitic_product_id: weaningDayAntiparasitic.value,
      deworming_product_id: weaningDayDeworming.value,
      vaccination_product_id: weaningDayVaccination.value,
      notes: weaningDayNotes.value,
    },
    dry_run: dryRun,
  };
}

function resetWeaningDayPreview() {
  latestWeaningDayPreview = null;
  if (weaningDayApplyButton) weaningDayApplyButton.disabled = true;
  if (weaningDayPreview) weaningDayPreview.classList.add("hidden");
}

function setWeaningDaySubmitting(isSubmitting, mode = "preview") {
  weaningDayPreviewButton.disabled = isSubmitting;
  weaningDayApplyButton.disabled = isSubmitting || !latestWeaningDayPreview;
  weaningDayPreviewButton.textContent = isSubmitting && mode === "preview" ? "Previewing..." : "Preview Weaning Day";
  weaningDayApplyButton.textContent = isSubmitting && mode === "apply" ? "Saving..." : "Save Weaning Day";
}

function renderWeaningDayPreview(preview) {
  if (!weaningDayPreview) return;
  weaningDayPreview.classList.remove("hidden");
  weaningDayPreview.innerHTML = `
    <div class="bulk-review-header">
      <strong>${preview.dry_run ? "Preview ready" : "Saved"}</strong>
      <span>${preview.active_piglet_count || 0} piglet${preview.active_piglet_count === 1 ? "" : "s"}</span>
    </div>
    <div class="sales-meta-grid">
      <div><span class="history-label">Tags</span><span class="history-value">${preview.tag_count || 0}</span></div>
      <div><span class="history-label">Wean Weights</span><span class="history-value">${preview.wean_weights_captured || 0}</span></div>
      <div><span class="history-label">Treatments</span><span class="history-value">${preview.treatment_count || 0}</span></div>
      <div><span class="history-label">Pen Moves</span><span class="history-value">${preview.movement_count || 0}</span></div>
    </div>
    <p class="form-helper">${escapeHtml(preview.message || "Review the packet before saving.")}</p>
  `;
}

async function previewWeaningDay() {
  clearLitterMessage();
  latestWeaningDayPreview = null;
  if (weaningDayApplyButton) weaningDayApplyButton.disabled = true;
  if (!weaningDayDate.value) {
    showLitterMessage("Choose a wean date before previewing.", "error");
    return;
  }
  setWeaningDaySubmitting(true, "preview");
  try {
    const litterId = getLitterIdFromUrl();
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/weaning-day`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(weaningDayPayload(true)),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.error || "Could not preview weaning day."]).join(" "));
    }
    latestWeaningDayPreview = data;
    renderWeaningDayPreview(data);
  } catch (error) {
    showLitterMessage(error.message || "Could not preview weaning day.", "error");
  } finally {
    setWeaningDaySubmitting(false, "preview");
  }
}

async function submitWeaningDay(event) {
  event.preventDefault();
  clearLitterMessage();
  if (!latestWeaningDayPreview) {
    showLitterMessage("Preview the weaning day packet before saving.", "error");
    return;
  }
  if (!window.confirm("Save this full weaning day packet?")) {
    return;
  }
  setWeaningDaySubmitting(true, "apply");
  try {
    const litterId = getLitterIdFromUrl();
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/weaning-day`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(weaningDayPayload(false)),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.error || "Could not save weaning day."]).join(" "));
    }
    resetWeaningDayPreview();
    renderWeaningDayPreview(data);
    showLitterMessage(data.message || "Weaning day saved.", "success");
    await loadLitterDetail({ keepMessage: true });
  } catch (error) {
    showLitterMessage(error.message || "Could not save weaning day.", "error");
  } finally {
    setWeaningDaySubmitting(false, "apply");
  }
}

async function previewStillbornReclassify() {
  clearLitterMessage();
  latestStillbornReclassifyPreview = null;
  stillbornReclassifyApplyButton.disabled = true;

  setStillbornReclassifySubmitting(true, "preview");
  try {
    const litterId = getLitterIdFromUrl();
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/reclassify-stillborn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(stillbornReclassifyPayload(true)),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.error || "Could not preview Stillborn correction."]).join(" "));
    }
    latestStillbornReclassifyPreview = data;
    renderStillbornReclassifyPreview(data);
  } catch (error) {
    showLitterMessage(error.message || "Could not preview Stillborn correction.", "error");
  } finally {
    setStillbornReclassifySubmitting(false, "preview");
  }
}

async function submitStillbornReclassify(event) {
  event.preventDefault();
  clearLitterMessage();

  if (!latestStillbornReclassifyPreview) {
    showLitterMessage("Preview the Stillborn correction before saving.", "error");
    return;
  }
  if (!window.confirm("Save this Stillborn history correction to PIG_MASTER?")) {
    return;
  }

  setStillbornReclassifySubmitting(true, "apply");
  try {
    const litterId = getLitterIdFromUrl();
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/reclassify-stillborn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(stillbornReclassifyPayload(false)),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.error || "Could not save Stillborn correction."]).join(" "));
    }
    resetStillbornReclassifyPreview();
    showLitterMessage(data.message || "Stillborn correction saved.", "success");
    await loadLitterDetail({ keepMessage: true });
  } catch (error) {
    showLitterMessage(error.message || "Could not save Stillborn correction.", "error");
  } finally {
    setStillbornReclassifySubmitting(false, "apply");
  }
}

async function previewReconcileBirthCounts() {
  clearLitterMessage();
  latestReconcilePreview = null;
  reconcileApplyButton.disabled = true;

  if (!reconcileTargetBornAlive.value) {
    showLitterMessage("Enter the corrected born-alive count before previewing.", "error");
    return;
  }

  setReconcileSubmitting(true, "preview");
  try {
    const litterId = getLitterIdFromUrl();
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/reconcile-birth-counts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reconcilePayload(true)),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.error || "Could not preview correction."]).join(" "));
    }
    latestReconcilePreview = data;
    renderReconcilePreview(data);
  } catch (error) {
    showLitterMessage(error.message || "Could not preview correction.", "error");
  } finally {
    setReconcileSubmitting(false, "preview");
  }
}

async function submitReconcileBirthCounts(event) {
  event.preventDefault();
  clearLitterMessage();

  if (!latestReconcilePreview) {
    showLitterMessage("Preview the correction before saving.", "error");
    return;
  }
  if (!window.confirm("Save this litter birth-count correction to LITTERS?")) {
    return;
  }

  setReconcileSubmitting(true, "apply");
  try {
    const litterId = getLitterIdFromUrl();
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/reconcile-birth-counts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reconcilePayload(false)),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.error || "Could not save correction."]).join(" "));
    }
    resetReconcilePreview();
    showLitterMessage(data.message || "Litter birth count was reconciled.", "success");
    await loadLitterDetail({ keepMessage: true });
  } catch (error) {
    showLitterMessage(error.message || "Could not save correction.", "error");
  } finally {
    setReconcileSubmitting(false, "apply");
  }
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

function renderPigletDeathPanel(litter) {
  const hasActivePiglets = manualActionAvailability(litter).canRecordPigletDeath;
  if (pigletDeathPanel) {
    pigletDeathPanel.classList.toggle("hidden", !hasActivePiglets || !manualActionsExpanded);
  }
  if (pigletDeathDate && !pigletDeathDate.value) {
    pigletDeathDate.value = todayIsoDate();
  }
}

function renderSexCountPanel(litter) {
  const hasUnsexedPiglets = manualActionAvailability(litter).canRecordSexCounts;
  if (sexCountPanel) {
    sexCountPanel.classList.toggle("hidden", !hasUnsexedPiglets || !manualActionsExpanded);
  }
  if (sexCountDate && !sexCountDate.value) {
    sexCountDate.value = todayIsoDate();
  }
}

function renderTagNumbersPanel(litter) {
  const availability = manualActionAvailability(litter);
  const attentionAction = ((litter.attention || {}).action_type || "") === "assign_tag_numbers";
  const showPanel = availability.canAssignTagNumbers && (manualActionsExpanded || attentionAction);
  if (tagNumbersForm) {
    tagNumbersForm.classList.toggle("hidden", !showPanel);
  }
  if (tagNumbersDate && !tagNumbersDate.value) {
    tagNumbersDate.value = todayIsoDate();
  }
  if (tagNumbersText) {
    tagNumbersText.textContent = `Type tags directly in the ${availability.activeUntaggedCount} editable piglet row${availability.activeUntaggedCount === 1 ? "" : "s"}, then preview before saving.`;
  }
}

function pigletDeathPayload(dryRun) {
  return {
    event_date: pigletDeathDate.value,
    reason: pigletDeathReason.value,
    count: pigletDeathCount.value,
    male_count: pigletDeathMaleCount.value,
    female_count: pigletDeathFemaleCount.value,
    changed_by: pigletDeathRecordedBy.value || "web_app",
    notes: pigletDeathNotes.value,
    dry_run: dryRun,
  };
}

function renderPigletDeathPreview(preview) {
  if (!pigletDeathPreview) return;
  pigletDeathPreview.classList.remove("hidden");
  const selected = preview.selected_piglets || [];
  const rows = selected.map((piglet) => `
    <tr>
      <td>${escapeHtml(piglet.tag_number || piglet.pig_id || "-")}</td>
      <td>${escapeHtml(piglet.pig_id || "-")}</td>
      <td>${escapeHtml(piglet.sex || "-")}</td>
    </tr>
  `).join("");
  pigletDeathPreview.innerHTML = `
    <div class="bulk-review-header">
      <strong>Preview ready</strong>
      <span>${preview.piglet_count || 0} piglet${preview.piglet_count === 1 ? "" : "s"} will be marked dead</span>
    </div>
    <div class="simple-table-wrap">
      <table class="simple-table compact-table">
        <thead>
          <tr>
            <th>Piglet</th>
            <th>Pig ID</th>
            <th>Sex</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function resetPigletDeathPreview() {
  latestPigletDeathPreview = null;
  if (pigletDeathApplyButton) pigletDeathApplyButton.disabled = true;
  if (pigletDeathPreview) pigletDeathPreview.classList.add("hidden");
}

function setPigletDeathSubmitting(isSubmitting, mode = "preview") {
  pigletDeathPreviewButton.disabled = isSubmitting;
  pigletDeathApplyButton.disabled = isSubmitting || !latestPigletDeathPreview;
  pigletDeathPreviewButton.textContent = isSubmitting && mode === "preview" ? "Previewing..." : "Preview";
  pigletDeathApplyButton.textContent = isSubmitting && mode === "apply" ? "Saving..." : "Save Piglet Deaths";
}

function sexCountPayload(dryRun) {
  return {
    action_date: sexCountDate.value,
    male_count: sexCountMale.value,
    female_count: sexCountFemale.value,
    changed_by: sexCountRecordedBy.value || "web_app",
    notes: sexCountNotes.value,
    dry_run: dryRun,
  };
}

function renderSexCountPreview(preview) {
  if (!sexCountPreview) return;
  sexCountPreview.classList.remove("hidden");
  const selected = preview.selected_piglets || [];
  const rows = selected.map((piglet) => `
    <tr>
      <td>${escapeHtml(piglet.tag_number || piglet.pig_id || "-")}</td>
      <td>${escapeHtml(piglet.pig_id || "-")}</td>
      <td>${escapeHtml(piglet.sex || "-")}</td>
    </tr>
  `).join("");
  sexCountPreview.innerHTML = `
    <div class="bulk-review-header">
      <strong>Preview ready</strong>
      <span>${escapeHtml(preview.summary || `${preview.piglet_count || 0} piglet(s) will be updated`)}</span>
    </div>
    <div class="simple-table-wrap">
      <table class="simple-table compact-table">
        <thead>
          <tr>
            <th>Piglet</th>
            <th>Pig ID</th>
            <th>New Sex</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function resetSexCountPreview() {
  latestSexCountPreview = null;
  if (sexCountApplyButton) sexCountApplyButton.disabled = true;
  if (sexCountPreview) sexCountPreview.classList.add("hidden");
}

function setSexCountSubmitting(isSubmitting, mode = "preview") {
  sexCountPreviewButton.disabled = isSubmitting;
  sexCountApplyButton.disabled = isSubmitting || !latestSexCountPreview;
  sexCountPreviewButton.textContent = isSubmitting && mode === "preview" ? "Previewing..." : "Preview";
  sexCountApplyButton.textContent = isSubmitting && mode === "apply" ? "Saving..." : "Save Sex Counts";
}

function tagNumbersPayload(dryRun) {
  const assignments = Array.from(document.querySelectorAll(".piglet-tag-input"))
    .map((input) => ({
      pig_id: input.dataset.pigId || "",
      tag_number: input.value.trim(),
    }));
  return {
    action_date: tagNumbersDate.value,
    assignments,
    changed_by: tagNumbersRecordedBy.value || "web_app",
    notes: tagNumbersNotes.value,
    dry_run: dryRun,
  };
}

function renderTagNumbersPreview(preview) {
  if (!tagNumbersPreview) return;
  tagNumbersPreview.classList.remove("hidden");
  const selected = preview.selected_piglets || [];
  const rows = selected.map((piglet) => `
    <tr>
      <td>${escapeHtml(piglet.pig_id || "-")}</td>
      <td>${escapeHtml(piglet.sex || "-")}</td>
      <td><strong>${escapeHtml(piglet.tag_number || "-")}</strong></td>
    </tr>
  `).join("");
  tagNumbersPreview.innerHTML = `
    <div class="bulk-review-header">
      <strong>Preview ready</strong>
      <span>${preview.piglet_count || 0} tag number${preview.piglet_count === 1 ? "" : "s"} will be saved</span>
    </div>
    <div class="simple-table-wrap">
      <table class="simple-table compact-table">
        <thead>
          <tr>
            <th>Pig ID</th>
            <th>Sex</th>
            <th>New Tag</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="form-helper">Tags are assigned to active untagged piglets in the order shown here.</p>
  `;
}

function resetTagNumbersPreview() {
  latestTagNumbersPreview = null;
  if (tagNumbersApplyButton) tagNumbersApplyButton.disabled = true;
  if (tagNumbersPreview) tagNumbersPreview.classList.add("hidden");
}

function setTagNumbersSubmitting(isSubmitting, mode = "preview") {
  tagNumbersPreviewButton.disabled = isSubmitting;
  tagNumbersApplyButton.disabled = isSubmitting || !latestTagNumbersPreview;
  tagNumbersPreviewButton.textContent = isSubmitting && mode === "preview" ? "Previewing..." : "Preview";
  tagNumbersApplyButton.textContent = isSubmitting && mode === "apply" ? "Saving..." : "Save Tag Numbers";
}

async function previewTagNumbers() {
  clearLitterMessage();
  latestTagNumbersPreview = null;
  tagNumbersApplyButton.disabled = true;

  if (!tagNumbersDate.value) {
    showLitterMessage("Choose an action date before previewing.", "error");
    return;
  }
  const payload = tagNumbersPayload(true);
  if (!payload.assignments.some((assignment) => assignment.tag_number)) {
    showLitterMessage("Enter tag numbers in the piglet table before previewing.", "error");
    return;
  }

  setTagNumbersSubmitting(true, "preview");
  try {
    const litterId = getLitterIdFromUrl();
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/tag-numbers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.error || "Could not preview tag numbers."]).join(" "));
    }
    latestTagNumbersPreview = data;
    renderTagNumbersPreview(data);
  } catch (error) {
    showLitterMessage(error.message || "Could not preview tag numbers.", "error");
  } finally {
    setTagNumbersSubmitting(false, "preview");
  }
}

async function submitTagNumbers(event) {
  event.preventDefault();
  clearLitterMessage();

  if (!latestTagNumbersPreview) {
    showLitterMessage("Preview the tag numbers before saving.", "error");
    return;
  }
  if (!window.confirm("Save the previewed tag numbers to these piglet rows?")) {
    return;
  }

  setTagNumbersSubmitting(true, "apply");
  try {
    const litterId = getLitterIdFromUrl();
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/tag-numbers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(tagNumbersPayload(false)),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.error || "Could not save tag numbers."]).join(" "));
    }
    resetTagNumbersPreview();
    showLitterMessage(data.message || "Tag numbers saved.", "success");
    await loadLitterDetail({ keepMessage: true });
  } catch (error) {
    showLitterMessage(error.message || "Could not save tag numbers.", "error");
  } finally {
    setTagNumbersSubmitting(false, "apply");
  }
}

async function previewSexCount() {
  clearLitterMessage();
  latestSexCountPreview = null;
  sexCountApplyButton.disabled = true;

  if (!sexCountDate.value) {
    showLitterMessage("Choose an action date before previewing.", "error");
    return;
  }
  if (!sexCountMale.value && !sexCountFemale.value) {
    showLitterMessage("Enter at least one male or female count before previewing.", "error");
    return;
  }

  setSexCountSubmitting(true, "preview");
  try {
    const litterId = getLitterIdFromUrl();
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/sex-counts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sexCountPayload(true)),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.error || "Could not preview sex-count action."]).join(" "));
    }
    latestSexCountPreview = data;
    renderSexCountPreview(data);
  } catch (error) {
    showLitterMessage(error.message || "Could not preview sex-count action.", "error");
  } finally {
    setSexCountSubmitting(false, "preview");
  }
}

async function submitSexCount(event) {
  event.preventDefault();
  clearLitterMessage();

  if (!latestSexCountPreview) {
    showLitterMessage("Preview the sex-count action before saving.", "error");
    return;
  }
  if (!window.confirm("Save the previewed male/female sex counts to the selected piglet rows?")) {
    return;
  }

  setSexCountSubmitting(true, "apply");
  try {
    const litterId = getLitterIdFromUrl();
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/sex-counts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sexCountPayload(false)),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.error || "Could not save sex-count action."]).join(" "));
    }
    resetSexCountPreview();
    showLitterMessage(data.message || "Sex-count action saved.", "success");
    await loadLitterDetail({ keepMessage: true });
  } catch (error) {
    showLitterMessage(error.message || "Could not save sex-count action.", "error");
  } finally {
    setSexCountSubmitting(false, "apply");
  }
}

async function previewPigletDeath() {
  clearLitterMessage();
  latestPigletDeathPreview = null;
  pigletDeathApplyButton.disabled = true;

  if (!pigletDeathDate.value) {
    showLitterMessage("Choose an event date before previewing.", "error");
    return;
  }
  if (!pigletDeathCount.value && !pigletDeathMaleCount.value && !pigletDeathFemaleCount.value) {
    showLitterMessage("Enter a count, or male/female counts if sex has already been captured.", "error");
    return;
  }

  setPigletDeathSubmitting(true, "preview");
  try {
    const litterId = getLitterIdFromUrl();
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/piglet-deaths`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pigletDeathPayload(true)),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.error || "Could not preview piglet death action."]).join(" "));
    }
    latestPigletDeathPreview = data;
    renderPigletDeathPreview(data);
  } catch (error) {
    showLitterMessage(error.message || "Could not preview piglet death action.", "error");
  } finally {
    setPigletDeathSubmitting(false, "preview");
  }
}

async function submitPigletDeath(event) {
  event.preventDefault();
  clearLitterMessage();

  if (!latestPigletDeathPreview) {
    showLitterMessage("Preview the piglet death action before saving.", "error");
    return;
  }
  if (!window.confirm("Mark the previewed piglets as dead and off farm?")) {
    return;
  }

  setPigletDeathSubmitting(true, "apply");
  try {
    const litterId = getLitterIdFromUrl();
    const response = await fetch(`/api/pig-weights/litter/${encodeURIComponent(litterId)}/piglet-deaths`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pigletDeathPayload(false)),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.error || "Could not save piglet death action."]).join(" "));
    }
    resetPigletDeathPreview();
    showLitterMessage(data.message || "Piglet death action saved.", "success");
    await loadLitterDetail({ keepMessage: true });
  } catch (error) {
    showLitterMessage(error.message || "Could not save piglet death action.", "error");
  } finally {
    setPigletDeathSubmitting(false, "apply");
  }
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
        use_latest_weights_as_wean_weights: markWeanedUseLatestWeights ? markWeanedUseLatestWeights.checked : false,
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
  const state = detailState(window.currentLitterDetail || {});
  const weight = state === "active" ? piglet.current_weight_kg : piglet.wean_weight_kg;
  return weight !== null && weight !== undefined && weight !== ""
    ? `${formatNumber(weight, 2)} kg`
    : "No weight";
}

function pigletStatusText(piglet) {
  const exitReason = String(piglet.exit_reason || "").toLowerCase().replace(/[-_]/g, " ");
  if (exitReason === "stillborn") return "Stillborn";
  return piglet.status || "-";
}

function pigletWeanWeightText(piglet) {
  return piglet.wean_weight_kg !== null && piglet.wean_weight_kg !== undefined && piglet.wean_weight_kg !== ""
    ? `${formatNumber(piglet.wean_weight_kg, 2)} kg`
    : "-";
}

function buildPigletTable(piglets) {
  const litterId = getLitterIdFromUrl();
  const litterIsActive = detailState(window.currentLitterDetail || {}) === "active";
  const rows = piglets.map((piglet) => {
    const profileHref = pigProfileHref(piglet.pig_id, litterId);
    const canEditTag = litterIsActive && piglet.status === "Active" && piglet.on_farm === "Yes" && !piglet.tag_number;
    const tagCell = canEditTag
      ? `<input class="piglet-tag-input" data-pig-id="${escapeHtml(piglet.pig_id || "")}" type="text" placeholder="Add tag" aria-label="Tag number for ${escapeHtml(piglet.pig_id || "piglet")}" />`
      : `<strong>${escapeHtml(piglet.tag_number || "-")}</strong>`;
    return `
      <tr class="litter-piglet-row" data-pig-profile="${profileHref}" tabindex="0">
        <td>
          <strong>${escapeHtml(piglet.pig_id || "-")}</strong>
          <span class="table-subtext">${escapeHtml(piglet.calculated_stage || "-")}</span>
        </td>
        <td>${tagCell}</td>
        <td>${escapeHtml(piglet.sex || "-")}</td>
        <td>${escapeHtml(pigletWeightText(piglet))}</td>
        <td>${escapeHtml(piglet.wean_date || "-")}</td>
        <td>${escapeHtml(pigletWeanWeightText(piglet))}</td>
        <td>${escapeHtml(pigletStatusText(piglet))}</td>
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
            <th>Pig ID</th>
            <th>Tag Number</th>
            <th>Sex</th>
            <th>Weight</th>
            <th>Wean Date</th>
            <th>Wean Weight</th>
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
      if (event.target.closest("a, input, button, select, textarea")) return;
      window.location.href = row.dataset.pigProfile;
    });
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        window.location.href = row.dataset.pigProfile;
      }
    });
  });
  document.querySelectorAll(".piglet-tag-input").forEach((input) => {
    input.addEventListener("input", resetTagNumbersPreview);
    input.addEventListener("change", resetTagNumbersPreview);
    input.addEventListener("input", resetWeaningDayPreview);
    input.addEventListener("change", resetWeaningDayPreview);
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
    window.currentLitterDetail = litter;

    document.getElementById("litter_title").textContent = `Litter - ${litter.litter_id}`;
    const state = detailState(litter);
    const stateLabel = state === "completed" ? "Completed litter" : state === "weaned" ? "Weaned litter" : "Active litter";
    document.getElementById("litter_subtitle").textContent = `${stateLabel} - ${litter.count} piglet(s) linked to this litter`;

    setText("litter_id_value", litter.litter_id);
    setText("litter_status_value", litter.litter_status || "Unknown");
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
    renderStateSummary(litter);

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
    renderReconcilePanel(litter);
    renderStillbornReclassifyPanel(litter);
    renderManualActionsPanel(litter);
    renderWeaningDayPanel(litter);
    renderPigletDeathPanel(litter);
    renderSexCountPanel(litter);
    renderTagNumbersPanel(litter);
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
pigletDeathPreviewButton.addEventListener("click", previewPigletDeath);
pigletDeathForm.addEventListener("submit", submitPigletDeath);
sexCountPreviewButton.addEventListener("click", previewSexCount);
sexCountForm.addEventListener("submit", submitSexCount);
tagNumbersPreviewButton.addEventListener("click", previewTagNumbers);
tagNumbersForm.addEventListener("submit", submitTagNumbers);
weaningDayPreviewButton.addEventListener("click", previewWeaningDay);
weaningDayForm.addEventListener("submit", submitWeaningDay);
reconcilePreviewButton.addEventListener("click", previewReconcileBirthCounts);
reconcileForm.addEventListener("submit", submitReconcileBirthCounts);
stillbornReclassifyPreviewButton.addEventListener("click", previewStillbornReclassify);
stillbornReclassifyForm.addEventListener("submit", submitStillbornReclassify);
manualActionsToggle.addEventListener("click", () => {
  manualActionsExpanded = !manualActionsExpanded;
  renderManualActionsPanel(window.currentLitterDetail || {});
  renderWeaningDayPanel(window.currentLitterDetail || {});
  renderPigletDeathPanel(window.currentLitterDetail || {});
  renderSexCountPanel(window.currentLitterDetail || {});
  renderTagNumbersPanel(window.currentLitterDetail || {});
});
[
  weaningDayDate,
  weaningDayTargetPen,
  weaningDayAntiparasitic,
  weaningDayDeworming,
  weaningDayVaccination,
  weaningDayNotes,
].forEach((element) => {
  if (element) element.addEventListener("change", resetWeaningDayPreview);
});
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
[
  pigletDeathDate,
  pigletDeathReason,
  pigletDeathCount,
  pigletDeathMaleCount,
  pigletDeathFemaleCount,
  pigletDeathNotes,
].forEach((element) => {
  if (element) element.addEventListener("change", resetPigletDeathPreview);
});
[
  sexCountDate,
  sexCountMale,
  sexCountFemale,
  sexCountNotes,
].forEach((element) => {
  if (element) element.addEventListener("change", resetSexCountPreview);
});
[
  tagNumbersDate,
  tagNumbersNotes,
].forEach((element) => {
  if (element) element.addEventListener("change", resetTagNumbersPreview);
  if (element) element.addEventListener("input", resetTagNumbersPreview);
});
[
  reconcileTargetBornAlive,
  reconcileChangedBy,
  reconcileReason,
].forEach((element) => {
  if (element) element.addEventListener("change", resetReconcilePreview);
});
[
  stillbornReclassifyChangedBy,
  stillbornReclassifyReason,
].forEach((element) => {
  if (element) element.addEventListener("change", resetStillbornReclassifyPreview);
});
loadLitterDetail();
updateBackLinkFromQuery();
