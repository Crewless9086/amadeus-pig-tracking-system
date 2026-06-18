(() => {
  const state = {
    policy: null,
    assets: [],
    selectedAssetId: "",
  };

  const byId = (id) => document.getElementById(id);
  const elements = {
    message: byId("beacon_media_message"),
    refresh: byId("beacon_media_refresh"),
    policyStatus: byId("beacon_media_policy_status"),
    policyFlags: byId("beacon_media_policy_flags"),
    campaignSelectionStatus: byId("beacon_campaign_selection_status"),
    campaignSelectionRefresh: byId("beacon_campaign_selection_refresh"),
    campaignSelectionList: byId("beacon_campaign_selection_list"),
    statusFilter: byId("beacon_media_status_filter"),
    typeFilter: byId("beacon_media_type_filter"),
    assetCount: byId("beacon_media_asset_count"),
    assetList: byId("beacon_media_asset_list"),
    needsReviewCount: byId("beacon_media_needs_review_count"),
    approvedCount: byId("beacon_media_approved_count"),
    rejectedCount: byId("beacon_media_rejected_count"),
    totalCount: byId("beacon_media_total_count"),
    uploadForm: byId("beacon_media_upload_form"),
    uploadFile: byId("beacon_media_upload_file"),
    uploadTitle: byId("beacon_media_upload_title"),
    uploadTags: byId("beacon_media_upload_tags"),
    uploadNotes: byId("beacon_media_upload_notes"),
    uploadButton: byId("beacon_media_upload_button"),
    detailTitle: byId("beacon_media_detail_title"),
    detailStatus: byId("beacon_media_detail_status"),
    facts: byId("beacon_media_asset_facts"),
    reviewTags: byId("beacon_media_review_tags"),
    reviewRelevance: byId("beacon_media_review_relevance"),
    qualityScore: byId("beacon_media_quality_score"),
    privacyRisk: byId("beacon_media_privacy_risk"),
    reviewNotes: byId("beacon_media_review_notes"),
    saveNote: byId("beacon_media_save_note"),
    approve: byId("beacon_media_approve"),
    reject: byId("beacon_media_reject"),
    archive: byId("beacon_media_archive"),
    reviewResult: byId("beacon_media_review_result"),
  };

  const safe = (value, fallback = "--") => {
    const text = String(value || "").trim();
    return text || fallback;
  };

  const listText = (value) => Array.isArray(value) ? value.filter(Boolean).join(", ") : safe(value, "");

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));

  const statusOf = (asset) => asset?.effective_approval_status || asset?.approval_status || "needs_review";

  const showMessage = (message, type = "error") => {
    elements.message.classList.remove("hidden", "message-success", "message-error");
    elements.message.classList.add(type === "success" ? "message-success" : "message-error");
    elements.message.textContent = message;
  };

  const clearMessage = () => {
    elements.message.classList.add("hidden");
    elements.message.classList.remove("message-success", "message-error");
    elements.message.textContent = "";
  };

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.success === false) {
      throw new Error(payload.status || payload.error || `Request failed with ${response.status}`);
    }
    return payload;
  }

  async function loadBeaconMedia() {
    clearMessage();
    const status = elements.statusFilter.value;
    const mediaType = elements.typeFilter.value;
    const params = new URLSearchParams({ limit: "50" });
    if (status) params.set("approval_status", status);
    if (mediaType) params.set("media_type", mediaType);
    const [policy, assetData] = await Promise.all([
      fetchJson("/api/beacon/media-policy"),
      fetchJson(`/api/beacon/media-assets?${params.toString()}`),
    ]);
    state.policy = policy;
    state.assets = assetData.assets || [];
    renderPolicy(policy);
    renderSummary(assetData.counts || {});
    renderAssetList();
    await loadCampaignSelection();
    if (state.selectedAssetId && !state.assets.some((asset) => asset.asset_id === state.selectedAssetId)) {
      state.selectedAssetId = "";
      renderDetail(null);
    } else {
      renderDetail(selectedAsset());
    }
  }

  async function loadCampaignSelection() {
    const selection = await fetchJson("/api/beacon/campaign-draft-selection?limit=25");
    elements.campaignSelectionStatus.textContent = `${selection.approved_media_count || 0} approved media asset${selection.approved_media_count === 1 ? "" : "s"} available for draft pairing. Public posting remains locked.`;
    renderCampaignSelection(selection);
  }

  function renderCampaignSelection(selection) {
    const pairings = selection.channel_draft_pairings || [];
    if (!pairings.length) {
      elements.campaignSelectionList.innerHTML = `<div class="table-empty">No campaign draft pairings are available yet.</div>`;
      return;
    }
    elements.campaignSelectionList.innerHTML = pairings.map((pairing) => `
      <div class="beacon-campaign-selection-item">
        <strong>${escapeHtml(safe(pairing.draft_label || pairing.draft_id))}</strong>
        <span>${escapeHtml(safe(pairing.channel))} | ${escapeHtml(safe(pairing.intent))}</span>
        <small>Asset: ${escapeHtml(safe(pairing.recommended_asset_title || pairing.recommended_asset_id, "No approved asset yet"))}</small>
        <small>${escapeHtml(safe(pairing.selection_reason))}</small>
      </div>
    `).join("");
  }

  function renderPolicy(policy) {
    const uploadReady = Boolean(policy.farm_app_standard_upload_enabled);
    elements.policyStatus.textContent = uploadReady
      ? "Private storage is ready for small Farm App uploads."
      : "Storage is not fully configured for uploads.";
    const flags = [
      ["Upload", uploadReady ? "ready" : "locked", uploadReady ? "Ready" : "Locked"],
      ["Public Use", policy.public_asset_use_enabled ? "ready" : "locked", policy.public_asset_use_enabled ? "Enabled" : "Locked"],
      ["Posting", policy.posts_publicly ? "ready" : "locked", policy.posts_publicly ? "Enabled" : "Locked"],
      ["Paid Spend", policy.automatic_posting_enabled ? "ready" : "locked", policy.automatic_posting_enabled ? "Enabled" : "Locked"],
    ];
    elements.policyFlags.innerHTML = flags.map(([label, stateName, value]) => `
      <div class="beacon-media-policy-item" data-state="${stateName}">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `).join("");
  }

  function renderSummary(counts) {
    elements.needsReviewCount.textContent = String(counts.needs_review ?? 0);
    elements.approvedCount.textContent = String(counts.approved ?? 0);
    elements.rejectedCount.textContent = String(counts.rejected ?? 0);
    elements.totalCount.textContent = String(counts.total ?? state.assets.length);
    elements.assetCount.textContent = `${state.assets.length} asset${state.assets.length === 1 ? "" : "s"} loaded.`;
  }

  function renderAssetList() {
    if (!state.assets.length) {
      elements.assetList.innerHTML = `<div class="table-empty">No Beacon media assets found for this filter.</div>`;
      return;
    }
    elements.assetList.innerHTML = state.assets.map((asset) => {
      const selected = asset.asset_id === state.selectedAssetId ? " is-selected" : "";
      return `
        <button type="button" class="beacon-media-asset-row${selected}" data-asset-id="${escapeHtml(asset.asset_id)}">
          <strong>${escapeHtml(safe(asset.title || asset.original_filename, asset.asset_id))}</strong>
          <span>${escapeHtml(statusOf(asset))} | ${escapeHtml(safe(asset.media_type))} | ${escapeHtml(listText(asset.subject_tags))}</span>
          <span>${escapeHtml(safe(asset.storage_bucket))}/${escapeHtml(safe(asset.storage_path))}</span>
        </button>
      `;
    }).join("");
    elements.assetList.querySelectorAll("[data-asset-id]").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedAssetId = button.dataset.assetId || "";
        renderAssetList();
        renderDetail(selectedAsset());
      });
    });
  }

  function selectedAsset() {
    return state.assets.find((asset) => asset.asset_id === state.selectedAssetId) || null;
  }

  function renderDetail(asset) {
    if (!asset) {
      elements.detailTitle.textContent = "Select an asset";
      elements.detailStatus.textContent = "Review details will show here.";
      elements.facts.innerHTML = `<div class="table-empty">No asset selected.</div>`;
      elements.reviewTags.value = "";
      elements.reviewRelevance.value = "";
      elements.qualityScore.value = "";
      elements.privacyRisk.value = "unknown";
      elements.reviewNotes.value = "";
      elements.reviewResult.innerHTML = "";
      setReviewDisabled(true);
      return;
    }
    setReviewDisabled(false);
    elements.detailTitle.textContent = safe(asset.title || asset.original_filename, asset.asset_id);
    elements.detailStatus.textContent = `${statusOf(asset)} | ${safe(asset.media_type)} | public use ${asset.effective_public_use_approved ? "approved" : "locked"}`;
    elements.facts.innerHTML = [
      ["Asset ID", asset.asset_id],
      ["File", asset.original_filename],
      ["Source", asset.source],
      ["Bucket", asset.storage_bucket],
      ["Path", asset.storage_path],
      ["Tags", listText(asset.subject_tags)],
      ["Relevance", listText(asset.sale_stream_relevance)],
      ["Latest Event", asset.latest_event?.event_type || "none"],
    ].map(([label, value]) => `
      <div class="beacon-media-fact">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(safe(value))}</strong>
      </div>
    `).join("");
    elements.reviewTags.value = listText(asset.subject_tags);
    elements.reviewRelevance.value = listText(asset.sale_stream_relevance);
    elements.qualityScore.value = asset.quality_score ?? "";
    elements.privacyRisk.value = asset.privacy_risk || "unknown";
    elements.reviewNotes.value = asset.notes || asset.latest_event?.notes || "";
    renderReviewResult(asset);
  }

  function setReviewDisabled(disabled) {
    [elements.reviewTags, elements.reviewRelevance, elements.qualityScore, elements.privacyRisk, elements.reviewNotes,
      elements.saveNote, elements.approve, elements.reject, elements.archive].forEach((element) => {
      element.disabled = disabled;
    });
  }

  function renderReviewResult(asset) {
    if (!asset.latest_event?.event_type) {
      elements.reviewResult.innerHTML = "";
      return;
    }
    elements.reviewResult.innerHTML = `
      <div class="ops-list-item">
        <strong>Latest event: ${escapeHtml(asset.latest_event.event_type)}</strong>
        <span>${escapeHtml(asset.latest_event.notes || "No notes recorded.")}</span>
      </div>
    `;
  }

  function reviewPayload(eventType) {
    const payload = {
      event_type: eventType,
      notes: elements.reviewNotes.value,
      recorded_by: "farm_app_beacon_media_review",
      subject_tags: elements.reviewTags.value,
      sale_stream_relevance: elements.reviewRelevance.value,
      privacy_risk: elements.privacyRisk.value,
    };
    if (elements.qualityScore.value !== "") {
      payload.quality_score = elements.qualityScore.value;
    }
    return payload;
  }

  async function recordReviewEvent(eventType) {
    const asset = selectedAsset();
    if (!asset) return;
    clearMessage();
    const payload = reviewPayload(eventType);
    const result = await fetchJson(`/api/beacon/media-assets/${encodeURIComponent(asset.asset_id)}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showMessage(`Beacon media event recorded: ${result.event_id || eventType}`, "success");
    if (eventType === "approved_public_use") elements.statusFilter.value = "approved";
    if (eventType === "rejected_public_use") elements.statusFilter.value = "rejected";
    if (eventType === "archived") elements.statusFilter.value = "archived";
    await loadBeaconMedia();
  }

  async function uploadAsset(event) {
    event.preventDefault();
    clearMessage();
    const file = elements.uploadFile.files[0];
    if (!file) {
      showMessage("Choose a file before uploading.");
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    formData.append("source", "farm_app_upload");
    formData.append("uploader_label", "Farm App");
    formData.append("title", elements.uploadTitle.value);
    formData.append("subject_tags", elements.uploadTags.value);
    formData.append("sale_stream_relevance", "meat");
    formData.append("notes", elements.uploadNotes.value);
    elements.uploadButton.disabled = true;
    try {
      const result = await fetchJson("/api/beacon/media-assets/upload", {
        method: "POST",
        body: formData,
      });
      state.selectedAssetId = result.asset_id || "";
      elements.uploadForm.reset();
      elements.statusFilter.value = "needs_review";
      showMessage(`Uploaded for Beacon review: ${result.asset_id}`, "success");
      await loadBeaconMedia();
    } finally {
      elements.uploadButton.disabled = false;
    }
  }

  document.addEventListener("DOMContentLoaded", async () => {
    elements.refresh.addEventListener("click", () => loadBeaconMedia().catch((error) => showMessage(error.message)));
    elements.campaignSelectionRefresh.addEventListener("click", () => loadCampaignSelection().catch((error) => showMessage(error.message)));
    elements.statusFilter.addEventListener("change", () => loadBeaconMedia().catch((error) => showMessage(error.message)));
    elements.typeFilter.addEventListener("change", () => loadBeaconMedia().catch((error) => showMessage(error.message)));
    elements.uploadForm.addEventListener("submit", (event) => uploadAsset(event).catch((error) => showMessage(error.message)));
    elements.saveNote.addEventListener("click", () => recordReviewEvent("review_note").catch((error) => showMessage(error.message)));
    elements.approve.addEventListener("click", () => recordReviewEvent("approved_public_use").catch((error) => showMessage(error.message)));
    elements.reject.addEventListener("click", () => recordReviewEvent("rejected_public_use").catch((error) => showMessage(error.message)));
    elements.archive.addEventListener("click", () => recordReviewEvent("archived").catch((error) => showMessage(error.message)));
    setReviewDisabled(true);
    await loadBeaconMedia().catch((error) => showMessage(error.message));
  });
})();
