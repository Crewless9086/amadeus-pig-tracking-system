(() => {
  const state = {
    policy: null,
    assets: [],
    selectedAssetId: "",
    latestPublishPacket: null,
    facebookPostingPolicy: null,
    salesTruthReady: false,
    meatOfferEnabled: false,
    meatCapReady: false,
    exactImageReady: false,
    performanceEvents: [],
    metaImportPacket: null,
  };

  const byId = (id) => document.getElementById(id);
  const elements = {
    message: byId("beacon_media_message"),
    refresh: byId("beacon_media_refresh"),
    policyStatus: byId("beacon_media_policy_status"),
    policyFlags: byId("beacon_media_policy_flags"),
    campaignLane: byId("beacon_campaign_lane"),
    campaignSelectionStatus: byId("beacon_campaign_selection_status"),
    campaignSelectionRefresh: byId("beacon_campaign_selection_refresh"),
    campaignSelectionList: byId("beacon_campaign_selection_list"),
    laneBoundary: byId("beacon_lane_boundary"),
    laneBadge: byId("beacon_lane_badge"),
    laneTitle: byId("beacon_lane_title"),
    laneDescription: byId("beacon_lane_description"),
    salesTruth: byId("beacon_sales_truth"),
    salesTruthStatus: byId("beacon_sales_truth_status"),
    salesTruthFacts: byId("beacon_sales_truth_facts"),
    salesTruthBlocker: byId("beacon_sales_truth_blocker"),
    meatReadiness: byId("beacon_meat_readiness"),
    meatReadinessStatus: byId("beacon_meat_readiness_status"),
    meatOfferState: byId("beacon_meat_offer_state"),
    meatCapState: byId("beacon_meat_cap_state"),
    meatReadinessBlocker: byId("beacon_meat_readiness_blocker"),
    publishDraftId: byId("beacon_publish_draft_id"),
    publishAssetId: byId("beacon_publish_asset_id"),
    publishChannel: byId("beacon_publish_channel"),
    publishCap: byId("beacon_publish_cap"),
    publishNotes: byId("beacon_publish_notes"),
    publishPrepare: byId("beacon_publish_prepare"),
    publishResult: byId("beacon_publish_packet_result"),
    facebookPostRefresh: byId("beacon_facebook_post_refresh"),
    facebookPostPolicyStatus: byId("beacon_facebook_post_policy_status"),
    facebookPostPacketId: byId("beacon_facebook_post_packet_id"),
    facebookPostConfirmation: byId("beacon_facebook_post_confirmation"),
    facebookPostAssetId: byId("beacon_facebook_post_asset_id"),
    facebookPostExactText: byId("beacon_facebook_post_exact_text"),
    facebookPostImage: byId("beacon_facebook_post_image"),
    facebookPostImageStatus: byId("beacon_facebook_post_image_status"),
    facebookPostImageEmpty: byId("beacon_facebook_post_image_empty"),
    checkOffer: byId("beacon_check_offer"), checkCap: byId("beacon_check_cap"), checkText: byId("beacon_check_text"), checkImage: byId("beacon_check_image"), checkConfig: byId("beacon_check_config"),
    facebookPostExecute: byId("beacon_facebook_post_execute"),
    facebookPostResult: byId("beacon_facebook_post_result"),
    facebookPostList: byId("beacon_facebook_post_execution_list"),
    manualPostRefresh: byId("beacon_manual_post_refresh"),
    manualPostPacketId: byId("beacon_manual_post_packet_id"),
    manualPostChannel: byId("beacon_manual_post_channel"),
    manualPostUrl: byId("beacon_manual_post_url"),
    manualPostPostedAt: byId("beacon_manual_post_posted_at"),
    manualPostPostedBy: byId("beacon_manual_post_posted_by"),
    manualPostCampaignLabel: byId("beacon_manual_post_campaign_label"),
    manualPostReactions: byId("beacon_manual_post_reactions"),
    manualPostComments: byId("beacon_manual_post_comments"),
    manualPostShares: byId("beacon_manual_post_shares"),
    manualPostMessages: byId("beacon_manual_post_messages"),
    manualPostNotes: byId("beacon_manual_post_notes"),
    manualPostRecord: byId("beacon_manual_post_record"),
    manualPostList: byId("beacon_manual_post_evidence_list"),
    performanceRefresh: byId("beacon_performance_refresh"),
    performanceManualPostId: byId("beacon_performance_manual_post_id"),
    performancePublishPacketId: byId("beacon_performance_publish_packet_id"),
    performanceChannel: byId("beacon_performance_channel"),
    performanceWindow: byId("beacon_performance_window"),
    performanceSpend: byId("beacon_performance_spend"),
    performanceReach: byId("beacon_performance_reach"),
    performanceMessages: byId("beacon_performance_messages"),
    performanceQualified: byId("beacon_performance_qualified"),
    performanceRecommendedSpend: byId("beacon_performance_recommended_spend"),
    performanceDuration: byId("beacon_performance_duration"),
    performanceFulfillmentRisk: byId("beacon_performance_fulfillment_risk"),
    performanceSafetyRisk: byId("beacon_performance_safety_risk"),
    performanceNotes: byId("beacon_performance_notes"),
    performanceRecord: byId("beacon_performance_record"),
    boostPacketResult: byId("beacon_boost_packet_result"),
    performanceList: byId("beacon_performance_event_list"),
    historyImport: byId("beacon_history_import"), historyImportStatus: byId("beacon_history_import_status"),
    correctionPanel: byId("beacon_correction_panel"), correctionContext: byId("beacon_correction_context"), correctionSourceId: byId("beacon_correction_source_id"),
    correctionMetric: byId("beacon_correction_metric"), correctionValue: byId("beacon_correction_value"), correctionReference: byId("beacon_correction_reference"), correctionNotes: byId("beacon_correction_notes"), correctionSave: byId("beacon_correction_save"),
    commandRefresh: byId("beacon_command_refresh"),
    commandTruth: byId("beacon_command_truth"),
    commandUpdated: byId("beacon_command_updated"),
    ownerAlerts: byId("beacon_owner_alerts"),
    weeklySpend: byId("beacon_weekly_spend"),
    weeklyLeads: byId("beacon_weekly_leads"),
    weeklySpendStatus: byId("beacon_weekly_spend_status"),
    weeklySpendTarget: byId("beacon_weekly_spend_target"),
    weeklyLeadsStatus: byId("beacon_weekly_leads_status"),
    weeklyLeadsTarget: byId("beacon_weekly_leads_target"),
    comparisonWindow: byId("beacon_comparison_window"),
    campaignComparison: byId("beacon_campaign_comparison"),
    recommendationList: byId("beacon_recommendation_list"),
    decisionCount: byId("beacon_decision_count"),
    decisionResult: byId("beacon_decision_result"),
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
    uploadRelevance: byId("beacon_media_upload_relevance"),
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
    contentState: byId("beacon_content_state"),
    contentRefresh: byId("beacon_content_refresh"),
    runtimeState: byId("beacon_runtime_state"),
    rankedIdeas: byId("beacon_ranked_ideas"),
    contentEvidence: byId("beacon_content_evidence"),
    contentExplanations: byId("beacon_content_explanations"),
    packetStatus: byId("beacon_packet_status"),
    packetMedia: byId("beacon_packet_media"),
    packetCopy: byId("beacon_packet_copy"),
    packetOptions: byId("beacon_packet_options"),
    packetMeta: byId("beacon_packet_meta"),
    metaPreviewState: byId("beacon_meta_preview_state"),
    metaPreviewRefresh: byId("beacon_meta_preview_refresh"),
    metaPreviewStart: byId("beacon_meta_preview_start"),
    metaPreviewEnd: byId("beacon_meta_preview_end"),
    metaPreviewLevel: byId("beacon_meta_preview_level"),
    metaPreviewConnection: byId("beacon_meta_preview_connection"),
    metaPreviewCounts: byId("beacon_meta_preview_counts"),
    metaPreviewMetrics: byId("beacon_meta_preview_metrics"),
    metaPreviewBlockers: byId("beacon_meta_preview_blockers"),
    metaPreviewEvents: byId("beacon_meta_preview_events"),
    metaImportState: byId("beacon_meta_import_state"),
    metaImportPrepare: byId("beacon_meta_import_prepare"),
    metaImportSummary: byId("beacon_meta_import_summary"),
    metaImportApproval: byId("beacon_meta_import_approval"),
    metaImportExecute: byId("beacon_meta_import_execute"),
    metaImportResult: byId("beacon_meta_import_result"),
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
    await loadFacebookPostingPolicy();
    await loadFacebookPostExecutions();
    await loadManualPostEvidence();
    await loadCampaignPerformance();
    if (state.selectedAssetId && !state.assets.some((asset) => asset.asset_id === state.selectedAssetId)) {
      state.selectedAssetId = "";
      renderDetail(null);
    } else {
      renderDetail(selectedAsset());
    }
  }

  function renderContentOperations(payload) {
    const quality = payload.evidence_quality || {};
    const packet = payload.featured_owner_review_packet || payload.owner_review_packet || {};
    const media = packet.media || {};
    const runtime = payload.runtime_status || {};
    const ideas = payload.ranked_ideas || [];
    const explanations = payload.owner_explanations || {};
    const mediaSummary = payload.media_summary || {};
    elements.contentState.textContent = payload.status === "owner_review_packet_ready"
      ? "Owner-review draft ready"
      : safe(payload.status, "Evidence incomplete");
    elements.contentState.dataset.state = payload.status === "owner_review_packet_ready" ? "ready" : "blocked";
    elements.runtimeState.innerHTML = [
      ["Endpoint available", runtime.endpoint_available],
      ["Owner read authenticated", runtime.owner_authenticated_read_succeeded],
      ["Packet generated", runtime.packet_generated],
      ["Current opportunity read", runtime.current_opportunity_read],
      ["Writes performed", runtime.writes_performed],
      ["Publishing performed", runtime.publishing_performed],
    ].map(([label, value]) => (
      `<span data-state="${value ? "ready" : "blocked"}"><strong>${escapeHtml(label)}</strong>${value ? "Yes" : "No"}</span>`
    )).join("");
    elements.rankedIdeas.innerHTML = ideas.length ? ideas.map((idea, index) => `
      <article class="beacon-recommendation-card">
        <div class="beacon-recommendation-title"><span>#${index + 1} · ${escapeHtml(idea.title)}</span><small>Score ${escapeHtml(idea.score)}</small></div>
        <p>${escapeHtml(idea.angle)}</p>
        <small>${escapeHtml(idea.why)}</small>
        <strong class="beacon-decision-blocker">${escapeHtml(safe(idea.owner_note, "Evidence review required."))}</strong>
        ${(idea.risk_flags || []).length ? `<details><summary>Technical diagnostics</summary><code>${(idea.risk_flags || []).map(escapeHtml).join(", ")}</code></details>` : ""}
      </article>
    `).join("") : '<div class="table-empty">No safely ranked ideas are available.</div>';
    elements.contentEvidence.innerHTML = `
      <div><strong>${escapeHtml(quality.historical_post_count || 0)}</strong><span>Historical posts · style/topic only</span></div>
      <div><strong>${escapeHtml(quality.verified_performance_event_count || 0)}</strong><span>Usable performance events</span></div>
      <div><strong>${escapeHtml(quality.unusable_performance_event_count || 0)}</strong><span>Excluded performance events</span></div>
      <p>${escapeHtml(quality.performance_evidence_status)}</p>
      <p>${escapeHtml(safe(mediaSummary.explanation, "Media eligibility has not been checked."))}</p>
    `;
    const metricSummary = quality.metric_summary || {};
    elements.contentEvidence.innerHTML += `<div class="beacon-metric-grid">${Object.entries(metricSummary).map(([name, metric]) => (
      `<span class="beacon-metric-chip" data-state="${metric.verified_event_count ? "verified" : "not_yet_imported"}"><strong>${escapeHtml(name.replaceAll("_", " "))}</strong> ${escapeHtml(metric.display)}</span>`
    )).join("")}</div>`;
    elements.contentExplanations.innerHTML = `
      <p><strong>Current facts:</strong> ${escapeHtml(safe(explanations.current_facts, "Current fact status unavailable."))}</p>
      <p><strong>Opportunity:</strong> ${escapeHtml(safe(explanations.current_opportunity, "Current opportunity status unavailable."))}</p>
      <p><strong>Performance:</strong> ${escapeHtml(safe(explanations.performance, "Performance import status unavailable."))}</p>
    `;
    elements.packetStatus.textContent = safe(packet.review_status, "Unavailable");
    elements.packetStatus.dataset.state = ["awaiting_owner_review", "awaiting_exact_owner_review"].includes(packet.review_status) ? "proposed" : "blocked";
    elements.packetMedia.innerHTML = media.status === "approved_media_sequence_selected"
      ? `<div class="beacon-content-media-sequence">${(media.assets || []).map((asset) => `
          <figure>
            <img src="${escapeHtml(asset.thumbnail_url)}" alt="${escapeHtml(asset.visual)}" loading="lazy" />
            <figcaption><strong>${escapeHtml(String(asset.order))}. ${escapeHtml(asset.title)}</strong><span>${escapeHtml(asset.dimensions_display)} · approved public use · trusted server hash</span></figcaption>
          </figure>
        `).join("")}</div>`
      : media.status === "approved_media_selected"
      ? `<strong>${escapeHtml(media.title)}</strong><span>${escapeHtml(media.media_type)} · ${escapeHtml(media.asset_id)}</span><small>Approved public use · ${escapeHtml(media.content_hash_provenance)}</small>`
      : `<strong>Media gap</strong><span>${escapeHtml(media.reason || "Exact media sequence unavailable.")}</span>`;
    elements.packetCopy.textContent = safe(packet.draft_copy, "No exact copy available.");
    elements.packetOptions.innerHTML = (packet.draft_options || []).map((option) => `
      <article class="beacon-recommendation-card">
        <div class="beacon-recommendation-title"><span>#${escapeHtml(option.rank)} · ${escapeHtml(option.title)}</span><small>Owner-review option</small></div>
        <pre class="beacon-packet-copy">${escapeHtml(option.draft_copy)}</pre>
      </article>
    `).join("");
    elements.packetMeta.innerHTML = `
      <div><strong>${escapeHtml(packet.channel)}</strong><span>${escapeHtml(packet.audience)}</span></div>
      <div><strong>Packet</strong><span>${escapeHtml(packet.packet_id)} · ${escapeHtml(packet.canonical_sha256)}</span></div>
      <div><strong>Objective</strong><span>${escapeHtml(packet.measurable_objective?.metric)} · ${escapeHtml(packet.measurable_objective?.measurement_window)}</span></div>
      <div><strong>Safety</strong><span>Publish false · Meta call false · send false · spend false · writes false</span></div>
      <p>${escapeHtml(packet.next_gate)}</p>
    `;
  }

  async function loadContentOperations() {
    elements.contentState.textContent = "Loading evidence";
    elements.contentState.dataset.state = "loading";
    const payload = await fetchJson("/api/beacon/content-operations");
    renderContentOperations(payload);
  }

  async function loadCampaignSelection() {
    renderLaneBoundary();
    const params = new URLSearchParams({
      limit: "25",
      campaign_lane: elements.campaignLane?.value || "live_stock_awareness",
    });
    let selection;
    try {
      selection = await fetchJson(`/api/beacon/campaign-draft-selection?${params.toString()}`);
    } catch (error) {
      if (elements.campaignLane.value === "live_stock_sales") {
        elements.salesTruthStatus.textContent = "Sales lane blocked";
        elements.salesTruthStatus.dataset.state = "blocked";
        elements.salesTruthBlocker.textContent = "The authoritative live-stock sales read model is not available. No suggestion or publish packet can be prepared.";
      }
      throw error;
    }
    const laneLabel = selection.campaign_lane === "meat_launch" ? "meat launch" : selection.campaign_lane === "live_stock_sales" ? "live-stock sales" : "live-stock awareness";
    elements.campaignSelectionStatus.textContent = `${selection.approved_media_count || 0} approved media asset${selection.approved_media_count === 1 ? "" : "s"} available for ${laneLabel} draft pairing. Public posting remains locked.`;
    renderCampaignSelection(selection);
    renderPublishPacketOptions(selection);
    renderSalesTruth(selection);
    renderMeatReadiness(selection);
  }

  function renderLaneBoundary() {
    const lane = elements.campaignLane.value;
    const isSales = lane === "live_stock_sales";
    const isMeat = lane === "meat_launch";
    elements.laneBoundary.dataset.lane = lane;
    elements.laneBadge.textContent = isSales ? "Sales" : lane === "meat_launch" ? "Meat" : "Awareness";
    elements.laneBadge.dataset.state = isSales ? "proposed" : "ready";
    elements.salesTruth.classList.toggle("hidden", !isSales);
    elements.meatReadiness.classList.toggle("hidden", !isMeat);
    elements.laneTitle.textContent = isSales ? "Direct sales offer with source-backed facts" : lane === "meat_launch" ? "Separate meat campaign lane" : "Farm-life content, not a sales offer";
    elements.laneDescription.textContent = isSales
      ? "Price, stock and quantity may appear only after current eligibility, capacity and sheet lineage pass. Buyer responses carry Beacon attribution to SAM Live Stock."
      : lane === "meat_launch" ? "Meat copy and media stay separate from live animals and awareness content." : "No price, availability, quantity, booking language, or call to buy. Buyer questions still route to SAM Live Stock.";
    elements.publishPrepare.textContent = isSales || isMeat ? "Prepare Exact Facebook Packet" : "Prepare Publish Packet";
    elements.publishCap.readOnly = !isMeat;
    if (!isMeat && !isSales) elements.publishCap.value = "";
    state.salesTruthReady = false;
    if (isSales) {
      elements.salesTruthStatus.textContent = "Checking source truth";
      elements.salesTruthStatus.dataset.state = "loading";
      elements.publishPrepare.disabled = true;
    } else if (!isMeat) {
      elements.publishPrepare.disabled = elements.publishChannel.value === "WhatsApp";
    } else {
      elements.publishPrepare.disabled = true;
    }
    updateFacebookActionState();
  }

  function positiveWholeCap(value) { return /^\d+$/.test(String(value || "").trim()) && Number(value) > 0; }

  function renderMeatReadiness(selection) {
    if (selection.campaign_lane !== "meat_launch") return;
    const readiness = selection.meat_launch_readiness || selection.readiness || {};
    state.meatOfferEnabled = readiness.owner_offer_enabled === true;
    state.meatCapReady = positiveWholeCap(elements.publishCap.value);
    elements.meatOfferState.textContent = state.meatOfferEnabled ? "Owner enabled" : "Not enabled";
    elements.meatReadinessStatus.textContent = state.meatOfferEnabled && state.meatCapReady ? "Ready to prepare" : "Pilot blocked";
    elements.meatReadinessStatus.dataset.state = state.meatOfferEnabled && state.meatCapReady ? "ready" : "blocked";
    elements.meatCapState.textContent = state.meatCapReady ? `${elements.publishCap.value.trim()} maximum` : "Enter an explicit cap";
    elements.meatReadinessBlocker.textContent = state.meatOfferEnabled ? (state.meatCapReady ? "Readiness gates passed. Choose the exact approved image and review the canonical text." : "Enter a positive whole-number cap; no default will be supplied.") : "The server-side owner offer flag is off. No meat launch packet can be prepared.";
    elements.publishPrepare.disabled = !(state.meatOfferEnabled && state.meatCapReady && elements.publishChannel.value !== "WhatsApp");
    updateFacebookActionState();
  }

  function renderSalesTruth(selection) {
    if (selection.campaign_lane !== "live_stock_sales") return;
    const truth = selection.sales_truth || selection.source_truth || {};
    const facts = [
      ["Sale eligibility", truth.sale_eligible === true ? "Eligible" : "Blocked", truth.eligibility_source || "Supabase allocation readiness required"],
      ["Fulfilment cap", truth.fulfilment_cap > 0 ? `${truth.fulfilment_cap} ${truth.fulfilment_unit || "animals"}` : "Not available", truth.fulfilment_as_of || "Must be positive and current"],
      ["Stock lineage", truth.stock_lineage_approved ? "Sheet-backed" : "Not verified", truth.stock_source || "Approved sheet lineage required"],
      ["Effective price", truth.price_lineage_approved ? safe(truth.price_display, "Verified") : "Not verified", truth.price_source || "SALES_PRICING lineage required"],
    ];
    const ready = Boolean(truth.sale_eligible && truth.fulfilment_cap > 0 && truth.stock_lineage_approved && truth.price_lineage_approved);
    state.salesTruthReady = ready;
    elements.salesTruthStatus.textContent = ready ? "Sales evidence ready" : "Sales lane blocked";
    elements.salesTruthStatus.dataset.state = ready ? "ready" : "blocked";
    elements.salesTruthFacts.innerHTML = facts.map(([label, value, source]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(source)}</small></article>`).join("");
    elements.salesTruthBlocker.textContent = ready ? "Current source checks passed. Review the cap, price, copy and approved image before preparing the exact packet." : safe(truth.blocker, "Sales suggestions stay locked until all four checks pass.");
    elements.publishPrepare.disabled = !ready || elements.publishChannel.value === "WhatsApp";
    if (truth.fulfilment_cap > 0) elements.publishCap.value = `${truth.fulfilment_cap} ${truth.fulfilment_unit || "animals"}`;
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

  function renderPublishPacketOptions(selection) {
    const pairings = selection.channel_draft_pairings || [];
    const assets = selection.ranked_media_assets || [];
    elements.publishDraftId.innerHTML = pairings.map((pairing) => `
      <option value="${escapeHtml(pairing.draft_id)}">${escapeHtml(safe(pairing.draft_label || pairing.draft_id))}</option>
    `).join("");
    elements.publishAssetId.innerHTML = assets.map((asset) =>
      `<option value="${escapeHtml(asset.asset_id)}">${escapeHtml(safe(asset.title || asset.asset_id))} (${escapeHtml(safe(asset.media_type, "media"))})</option>`
    ).join("");
    elements.publishAssetId.required = true;
    if (pairings[0] && !elements.publishChannel.value) {
      elements.publishChannel.value = pairings[0].channel || "";
    }
  }

  async function preparePublishPacket() {
    clearMessage();
    const assetIds = Array.from(elements.publishAssetId.selectedOptions).map((option) => option.value).filter(Boolean);
    if (!assetIds.length) {
      showMessage("Choose at least one owner-approved media asset before preparing the packet.");
      elements.publishAssetId.focus();
      return;
    }
    const payload = {
      campaign_lane: elements.campaignLane?.value || "live_stock_awareness",
      draft_id: elements.publishDraftId.value,
      asset_id: assetIds[0],
      asset_ids: assetIds,
      channel: elements.publishChannel.value,
      pilot_cap: elements.publishCap.value,
      owner_notes: elements.publishNotes.value,
    };
    const packet = await fetchJson("/api/beacon/campaign-publish-packet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.latestPublishPacket = packet;
    renderPublishPacket(packet);
    primeManualPostEvidence(packet);
    primeFacebookPostExecution(packet);
    showMessage(`Publish packet prepared for owner review: ${packet.publish_packet_id}`, "success");
  }

  function renderPublishPacket(packet) {
    const checks = packet.safety_checks || {};
    const assets = Array.isArray(packet.selected_assets) ? packet.selected_assets : packet.selected_asset ? [packet.selected_asset] : [];
    const salesTruth = packet.sales_truth || packet.source_truth || {};
    const isSales = packet.campaign_lane === "live_stock_sales";
    const checkSummary = isSales
      ? `Eligibility ${salesTruth.sale_eligible ? "verified" : "blocked"} | cap ${escapeHtml(safe(salesTruth.fulfilment_cap, "not verified"))} | price lineage ${salesTruth.price_lineage_approved ? "verified" : "blocked"} | posting ${checks.no_public_send_or_post ? "locked" : "exact gate only"}`
      : `Forbidden promises ${checks.draft_has_no_forbidden_promise ? "clear" : "review"} | posting ${checks.no_public_send_or_post ? "locked" : "exact gate only"}`;
    elements.publishResult.innerHTML = `
      <div class="beacon-publish-packet-card">
        <strong>${escapeHtml(packet.publish_packet_id)}</strong>
        <span>${escapeHtml(packet.campaign_lane || "")} | ${escapeHtml(packet.selected_draft?.channel || "")} | ${escapeHtml(packet.approval_status || "")}</span>
        <p>Media: ${escapeHtml(assets.map((asset) => safe(asset.title || asset.asset_id)).join(" → ") || "Text only")}</p>
        <pre>${escapeHtml(packet.selected_draft?.exact_text || "")}</pre>
        <small>Checks: ${checkSummary}</small>
      </div>
    `;
  }

  function primeManualPostEvidence(packet) {
    elements.manualPostPacketId.value = packet.publish_packet_id || "";
    elements.manualPostChannel.value = packet.selected_draft?.channel || elements.publishChannel.value || "";
    elements.performancePublishPacketId.value = packet.publish_packet_id || "";
    elements.performanceChannel.value = packet.selected_draft?.channel || elements.publishChannel.value || "Facebook";
    if (!elements.manualPostCampaignLabel.value) {
    elements.manualPostCampaignLabel.value = packet.campaign?.name || "";
    }
  }

  function primeFacebookPostExecution(packet) {
    const assets = Array.isArray(packet.selected_assets) ? packet.selected_assets : packet.selected_asset ? [packet.selected_asset] : [];
    elements.facebookPostPacketId.value = packet.publish_packet_id || "";
    elements.facebookPostAssetId.value = assets.map((asset) => asset.asset_id).join(", ");
    elements.facebookPostExactText.value = packet.selected_draft?.exact_text || "";
    const mixedMedia = assets.length > 1 && new Set(assets.map((asset) => asset.media_type)).size > 1;
    elements.facebookPostExecute.dataset.manualMediaRequired = mixedMedia ? "true" : "false";
    if (mixedMedia) {
      elements.facebookPostPolicyStatus.textContent = "Photo + video packet ready. Post this combination with Facebook's manual composer; automatic posting is locked.";
      elements.facebookPostResult.innerHTML = `<div class="beacon-facebook-post-card"><strong>Manual Facebook composer required</strong><span>Use the exact text above and add the selected photo and video in the displayed order.</span><small>Beacon approved and bound both assets. No Meta call has been made.</small></div>`;
    }
    updateFacebookActionState();

    const asset = packet.selected_asset || {};
    const previewUrl = asset.preview_url || asset.signed_preview_url || "";
    state.exactImageReady = Boolean(asset.asset_id && previewUrl);
    elements.facebookPostImage.classList.toggle("hidden", !state.exactImageReady);
    elements.facebookPostImageEmpty.classList.toggle("hidden", state.exactImageReady);
    elements.facebookPostImage.removeAttribute("src");
    if (state.exactImageReady) elements.facebookPostImage.src = previewUrl;
    elements.facebookPostImageStatus.textContent = state.exactImageReady ? `${safe(asset.title, asset.asset_id)} · approved public use` : "Approved image preview unavailable; execution remains locked.";
    updateFacebookActionState();
  }

  function setChecklistState(element, ready) { element.dataset.state = ready ? "ready" : "blocked"; }

  function updateFacebookActionState() {
    const policy = state.facebookPostingPolicy || {};
    const ready = Boolean(policy.enabled && policy.page_id_configured && policy.page_access_token_configured);
    const exactConfirmation = elements.facebookPostConfirmation.value === "POST EXACT BEACON PACKET";
    const meatLane = (state.latestPublishPacket?.campaign_lane || elements.campaignLane.value) === "meat_launch";
    const exactPacketReady = Boolean(elements.facebookPostPacketId.value && elements.facebookPostExactText.value);
    const meatReady = !meatLane || (state.meatOfferEnabled && state.meatCapReady && state.exactImageReady);
    setChecklistState(elements.checkOffer, !meatLane || state.meatOfferEnabled); setChecklistState(elements.checkCap, !meatLane || state.meatCapReady);
    setChecklistState(elements.checkText, Boolean(elements.facebookPostExactText.value)); setChecklistState(elements.checkImage, !meatLane || state.exactImageReady); setChecklistState(elements.checkConfig, ready);
    const manualMediaRequired = elements.facebookPostExecute.dataset.manualMediaRequired === "true";
    elements.facebookPostExecute.disabled = manualMediaRequired || !(ready && exactConfirmation && exactPacketReady && meatReady);
  }

  async function loadFacebookPostingPolicy() {
    const policy = await fetchJson("/api/beacon/facebook-posting-policy");
    state.facebookPostingPolicy = policy;
    const ready = Boolean(policy.enabled && policy.page_id_configured && policy.page_access_token_configured);
    elements.facebookPostPolicyStatus.textContent = ready
      ? "Facebook posting gate is armed. Exact owner confirmation is still required."
      : "Facebook posting is locked until Render envs and owner confirmation are present.";
    updateFacebookActionState();
    return policy;
  }

  async function loadFacebookPostExecutions() {
    const data = await fetchJson("/api/beacon/facebook-post-executions?limit=8");
    renderFacebookPostExecutions(data.execution_events || []);
  }

  async function executeFacebookPost() {
    clearMessage();
    const assets = Array.isArray(state.latestPublishPacket?.selected_assets)
      ? state.latestPublishPacket.selected_assets
      : state.latestPublishPacket?.selected_asset ? [state.latestPublishPacket.selected_asset] : [];
    const payload = {
      campaign_lane: state.latestPublishPacket?.campaign_lane || "",
      publish_packet_id: elements.facebookPostPacketId.value,
      channel: "Facebook",
      exact_text: elements.facebookPostExactText.value,
      asset_id: assets[0]?.asset_id || "",
      asset_ids: assets.map((asset) => asset.asset_id),
      pilot_cap: state.latestPublishPacket?.pilot_cap || "",
      owner_confirmation: elements.facebookPostConfirmation.value,
      recorded_by: "farm_app_beacon_facebook_post_gate",
    };
    const result = await fetchJson("/api/beacon/facebook-post-executions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderFacebookPostResult(result);
    showMessage(`Facebook post gate result: ${result.status}`, result.success ? "success" : "error");
    await loadFacebookPostExecutions();
  }

  function renderFacebookPostResult(result) {
    const event = result.execution_event || {};
    elements.facebookPostResult.innerHTML = `
      <div class="beacon-facebook-post-card">
        <strong>${escapeHtml(result.status || event.execution_status || "not_attempted")}</strong>
        <span>Post ID: ${escapeHtml(safe(result.facebook_post_id || event.facebook_post_id, "Not posted"))}</span>
        <small>${escapeHtml(safe(event.post_kind || result.facebook_result?.post_kind || "feed"))} | media ${escapeHtml(mediaSummary(event.selected_media || result.facebook_result?.selected_media))}</small>
        <small>Public post ${result.posts_publicly ? "executed" : "locked"} | Meta call ${result.calls_meta ? "executed" : "locked"} | paid boost locked</small>
      </div>
    `;
  }

  function renderFacebookPostExecutions(events) {
    if (!events.length) {
      elements.facebookPostList.innerHTML = `<div class="table-empty">No Facebook post execution evidence recorded yet.</div>`;
      return;
    }
    elements.facebookPostList.innerHTML = events.map((event) => `
      <div class="beacon-facebook-post-item">
        <strong>${escapeHtml(event.execution_status || event.execution_event_id)}</strong>
        <span>${escapeHtml(safe(event.publish_packet_id))} | ${escapeHtml(safe(event.facebook_post_id, "No post id"))}</span>
        <small>${escapeHtml(safe(event.post_kind || "feed"))} | ${escapeHtml(mediaSummary(event.selected_media))}</small>
        <small>${escapeHtml(safe(event.created_at))}</small>
      </div>
    `).join("");
  }

  function mediaSummary(media) {
    if (Array.isArray(media?.assets)) return media.assets.map((asset) => safe(asset.title || asset.asset_id)).join(" + ");
    return safe(media?.title || media?.asset_id, "text only");
  }

  async function loadManualPostEvidence() {
    const data = await fetchJson("/api/beacon/manual-post-evidence?limit=12");
    renderManualPostEvidence(data.manual_post_events || []);
  }

  async function recordManualPostEvidence() {
    clearMessage();
    const payload = {
      publish_packet_id: elements.manualPostPacketId.value,
      channel: elements.manualPostChannel.value,
      post_url: elements.manualPostUrl.value,
      posted_at: elements.manualPostPostedAt.value,
      posted_by: elements.manualPostPostedBy.value,
      campaign_label: elements.manualPostCampaignLabel.value,
      evidence_notes: elements.manualPostNotes.value,
      reactions: elements.manualPostReactions.value,
      comments: elements.manualPostComments.value,
      shares: elements.manualPostShares.value,
      messages: elements.manualPostMessages.value,
    };
    const result = await fetchJson("/api/beacon/manual-post-evidence", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showMessage(`Manual post evidence recorded: ${result.manual_post_event_id}`, "success");
    elements.performanceManualPostId.value = result.manual_post_event_id || "";
    elements.performancePublishPacketId.value = result.manual_post_event?.publish_packet_id || elements.manualPostPacketId.value;
    elements.performanceChannel.value = result.manual_post_event?.channel || elements.manualPostChannel.value || "Facebook";
    await loadManualPostEvidence();
  }

  function renderManualPostEvidence(events) {
    if (!events.length) {
      elements.manualPostList.innerHTML = `<div class="table-empty">No manual post evidence recorded yet.</div>`;
      return;
    }
    elements.manualPostList.innerHTML = events.map((event) => {
      const metrics = event.initial_metrics || {};
      const metricText = [
        ["reactions", metrics.reactions],
        ["comments", metrics.comments],
        ["shares", metrics.shares],
        ["messages", metrics.messages],
        ["leads", metrics.leads],
      ].filter(([, value]) => value).map(([label, value]) => `${label}: ${value}`).join(" | ");
      return `
        <div class="beacon-manual-post-item">
          <strong>${escapeHtml(event.publish_packet_id || event.manual_post_event_id)}</strong>
          <span>${escapeHtml(safe(event.channel))} | ${escapeHtml(safe(event.posted_at || event.created_at))}</span>
          <small>${escapeHtml(safe(event.post_url || "No public URL recorded"))}</small>
          <small>${escapeHtml(metricText || "No initial metrics recorded")}</small>
          <p>${escapeHtml(safe(event.evidence_notes, ""))}</p>
          <button type="button" class="button-link button-link-secondary beacon-use-performance-source" data-manual-post-id="${escapeHtml(event.manual_post_event_id)}" data-publish-packet-id="${escapeHtml(event.publish_packet_id)}" data-channel="${escapeHtml(event.channel)}">Use For Performance</button>
        </div>
      `;
    }).join("");
    elements.manualPostList.querySelectorAll(".beacon-use-performance-source").forEach((button) => {
      button.addEventListener("click", () => {
        elements.performanceManualPostId.value = button.dataset.manualPostId || "";
        elements.performancePublishPacketId.value = button.dataset.publishPacketId || "";
        elements.performanceChannel.value = button.dataset.channel || "Facebook";
      });
    });
  }

  async function loadCampaignPerformance() {
    const data = await fetchJson("/api/beacon/campaign-performance?limit=12");
    state.performanceEvents = data.performance_events || [];
    renderCampaignPerformance(state.performanceEvents);
    const commandData = await fetchJson("/api/beacon/weekly-command-brief?limit=100");
    renderServerCommandBrief(commandData.weekly_command_brief || {});
    if (data.latest_boost_packet?.recommended_action) {
      renderBoostPacket(data.latest_boost_packet);
    }
  }

  async function importFacebookHistory() {
    elements.historyImport.disabled = true;
    elements.historyImportStatus.textContent = "Retrieving...";
    elements.historyImportStatus.dataset.state = "stale";
    try {
      const result = await fetchJson("/api/beacon/facebook-history-import", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({max_posts: 5000})});
      elements.historyImportStatus.textContent = `${result.performance_imported_count || 0} new · ${result.performance_already_imported_count || 0} unchanged`;
      elements.historyImportStatus.dataset.state = result.failed_count ? "blocked" : "ready";
      await loadCampaignPerformance();
    } finally { elements.historyImport.disabled = false; }
  }

  function evidenceItems(event) {
    const evidence = event.metric_evidence || {};
    return Object.entries(evidence).map(([name, item]) => ({name, ...(item || {})}));
  }

  function renderMetaAdsPreview(payload) {
    const configuration = payload.configuration || {};
    const connection = payload.connection || {};
    const counts = payload.resource_counts || {};
    const metrics = payload.metric_summary || {};
    const idempotency = payload.idempotency_preview || {};
    const window = payload.reporting_window || {};
    elements.metaPreviewState.textContent = payload.status === "preview_ready"
      ? "Read-only preview ready"
      : payload.status === "partial" ? "Partial preview" : "Preview blocked";
    elements.metaPreviewState.dataset.state = payload.status === "preview_ready" ? "ready" : "blocked";
    elements.metaPreviewConnection.innerHTML = [
      ["Ad account configured", configuration.ad_account_id_configured, true],
      ["Ads read token configured", configuration.ads_read_token_configured, true],
      ["Graph version available", configuration.graph_version_configured || configuration.uses_default_graph_version, true],
      ["Account read succeeded", connection.account_read_status === "verified", true],
      ["Token exposed", false, false],
      ["Anything imported", false, false],
    ].map(([label, value, expected]) => (
      `<span data-state="${value === expected ? "ready" : "blocked"}"><strong>${escapeHtml(label)}</strong>${value ? "Yes" : "No"}</span>`
    )).join("");
    elements.metaPreviewCounts.innerHTML = `
      <div><strong>${escapeHtml(safe(payload.account_currency?.value, "Not verified"))}</strong><span>Account currency</span></div>
      <div><strong>${escapeHtml(counts.campaigns ?? "Not requested")}</strong><span>Campaigns</span></div>
      <div><strong>${escapeHtml(counts.adsets ?? "Not requested")}</strong><span>Ad sets</span></div>
      <div><strong>${escapeHtml(counts.ads ?? "Not requested")}</strong><span>Ads</span></div>
      <div><strong>${escapeHtml(payload.proposed_append_only_event_count ?? 0)}</strong><span>Proposed append-only events</span></div>
      <p>${escapeHtml(safe(window.start, "Unknown"))} to ${escapeHtml(safe(window.end, "Unknown"))} · ${escapeHtml(safe(window.level, "Unknown"))} level</p>
    `;
    elements.metaPreviewMetrics.innerHTML = Object.entries(metrics).map(([name, metric]) => {
      const value = metric.aggregate_value == null ? metric.aggregate_status : metric.aggregate_value;
      return `<span class="beacon-metric-chip" data-state="${escapeHtml(metric.aggregate_status)}"><strong>${escapeHtml(name.replaceAll("_", " "))}</strong> ${escapeHtml(value)}</span>`;
    }).join("");
    const blockers = payload.blockers || [];
    elements.metaPreviewBlockers.innerHTML = blockers.length
      ? `<p><strong>Preview blockers:</strong> ${blockers.map(escapeHtml).join(" · ")}</p>`
      : "<p>No API or permission blocker was reported by this bounded preview.</p>";
    elements.metaPreviewEvents.innerHTML = `
      <p><strong>Preview only — nothing imported.</strong></p>
      <p>${escapeHtml(payload.proposed_append_only_event_count ?? 0)} proposed event(s); ${escapeHtml(idempotency.duplicate_key_count ?? 0)} duplicate key(s) inside this response.</p>
      <p>Stable key preview: ${(idempotency.keys || []).slice(0, 5).map(escapeHtml).join(", ") || "No keys proposed."}</p>
      <p>Existing database duplicate check: ${escapeHtml(safe(idempotency.existing_database_duplicate_check, "Not performed"))}.</p>
    `;
  }

  async function loadMetaAdsPreview() {
    elements.metaPreviewRefresh.disabled = true;
    elements.metaPreviewState.textContent = "Reading Meta evidence";
    elements.metaPreviewState.dataset.state = "loading";
    const params = new URLSearchParams({
      start: elements.metaPreviewStart.value,
      end: elements.metaPreviewEnd.value,
      level: elements.metaPreviewLevel.value,
    });
    try {
      const response = await fetch(`/api/beacon/meta-ads-insights-preview?${params.toString()}`, {method: "GET"});
      const payload = await response.json().catch(() => ({}));
      renderMetaAdsPreview(payload);
    } finally {
      elements.metaPreviewRefresh.disabled = false;
    }
  }

  function renderMetaImportPacket(payload) {
    state.metaImportPacket = payload.success ? payload : null;
    elements.metaImportState.textContent = payload.success ? "Exact packet ready" : "Packet blocked";
    elements.metaImportState.dataset.state = payload.success ? "ready" : "blocked";
    elements.metaImportApproval.checked = false;
    elements.metaImportApproval.disabled = !payload.success;
    elements.metaImportExecute.disabled = true;
    if (!payload.success) {
      elements.metaImportSummary.innerHTML = `<p>${escapeHtml(safe(payload.status, "Packet preparation failed"))}</p>`;
      return;
    }
    const packet = payload.packet || {};
    const database = packet.database_snapshot || {};
    elements.metaImportSummary.innerHTML = `
      <p><strong>Exact packet hash:</strong> <code>${escapeHtml(payload.packet_hash)}</code></p>
      <p><strong>Expires:</strong> ${escapeHtml(payload.approval_expires_at)}</p>
      <p>${escapeHtml(payload.proposed_insert_count)} proposed insert(s); ${escapeHtml(payload.existing_duplicate_count)} duplicate(s) withheld; ${escapeHtml(payload.correction_supersession_count)} correction/supersession(s); ${escapeHtml(payload.excluded_count)} exclusion(s).</p>
      <p>False-zero exclusions: ${escapeHtml(payload.false_zero_exclusion_count)}. Compatibility-only scalar fields: ${escapeHtml((payload.compatibility_placeholder_fields || []).join(", ") || "None")}.</p>
      <p>Existing performance rows: ${escapeHtml(database.total_performance_rows)}; legacy rows protected: ${escapeHtml(database.legacy_row_count)}.</p>
      <p><strong>Nothing imported by preparation.</strong> Missing remains distinct from verified zero. Meta actions are not leads, sales or revenue.</p>
    `;
  }

  async function prepareMetaImportPacket() {
    elements.metaImportPrepare.disabled = true;
    elements.metaImportState.textContent = "Preparing bounded packet";
    elements.metaImportState.dataset.state = "loading";
    const params = new URLSearchParams({
      start: elements.metaPreviewStart.value,
      end: elements.metaPreviewEnd.value,
      level: elements.metaPreviewLevel.value,
    });
    try {
      const response = await fetch(`/api/beacon/meta-ads-import-packet?${params.toString()}`, {method: "GET"});
      const payload = await response.json().catch(() => ({}));
      renderMetaImportPacket(payload);
    } finally {
      elements.metaImportPrepare.disabled = false;
    }
  }

  async function executeMetaImportPacket() {
    const prepared = state.metaImportPacket;
    if (!prepared || !elements.metaImportApproval.checked) throw new Error("Approve the exact prepared packet first.");
    elements.metaImportExecute.disabled = true;
    const response = await fetch("/api/beacon/meta-ads-import-packet/execute", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        owner_approved: true,
        packet: prepared.packet,
        packet_hash: prepared.packet_hash,
        approved_packet_hash: prepared.packet_hash,
        approval_signature: prepared.approval_signature,
      }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(safe(result.status, "Import rejected"));
    state.metaImportPacket = null;
    elements.metaImportApproval.checked = false;
    elements.metaImportApproval.disabled = true;
    elements.metaImportState.textContent = "Approved evidence appended";
    elements.metaImportState.dataset.state = "ready";
    elements.metaImportResult.innerHTML = `<p>${escapeHtml(result.created_count)} event(s) appended; ${escapeHtml(result.duplicate_withheld_count)} duplicate(s) withheld. Legacy rows untouched: ${result.legacy_rows_untouched ? "Yes" : "No"}.</p>`;
  }

  function verifiedMetric(event, name) {
    const item = event?.metric_evidence?.[name];
    if (!item || !["verified", "owner_correction"].includes(item.status)) return null;
    if (item.value == null || !safe(item.source, "") || !safe(item.source_reference, "") || Number.isNaN(Date.parse(item.retrieved_at))) return null;
    return item.value;
  }

  function metricDisplay(event, name) {
    const value = verifiedMetric(event, name);
    if (value != null) return String(value);
    return event?.metric_evidence?.[name] ? "Not verified" : "Not imported";
  }

  function openCorrection(event, missing) {
    elements.correctionPanel.classList.remove("hidden");
    elements.correctionSourceId.value = event.performance_event_id;
    elements.correctionContext.textContent = `Append-only correction for ${event.performance_event_id}. Original evidence remains unchanged.`;
    elements.correctionMetric.innerHTML = missing.map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name.replaceAll("_", " "))} · ${escapeHtml(item.status)}</option>`).join("");
    elements.correctionPanel.scrollIntoView({behavior: "smooth", block: "nearest"});
  }

  async function saveCorrection() {
    const source = state.performanceEvents.find((event) => event.performance_event_id === elements.correctionSourceId.value);
    if (!source || !elements.correctionReference.value.trim() || elements.correctionValue.value === "") throw new Error("Evidence value and source reference are required.");
    const metric = elements.correctionMetric.value;
    const metricEvidence = {...(source.metric_evidence || {}), [metric]: {status: "owner_correction", value: Number(elements.correctionValue.value), source: "owner_correction", source_reference: elements.correctionReference.value.trim(), retrieved_at: new Date().toISOString()}};
    const result = await fetchJson("/api/beacon/campaign-performance", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({manual_post_event_id: source.manual_post_event_id, publish_packet_id: source.publish_packet_id, channel: source.channel, measurement_window: source.measurement_window, source_reference: elements.correctionReference.value.trim(), supersedes_event_id: source.performance_event_id, metric_evidence: metricEvidence, notes: elements.correctionNotes.value, recorded_by: "authenticated_owner_admin_correction"})});
    showMessage(`Correction appended: ${result.performance_event_id}`, "success");
    elements.correctionPanel.classList.add("hidden");
    await loadCampaignPerformance();
  }

  function normalizedWindow(value) {
    return safe(value, "").toLowerCase().replace(/\s+/g, " ").trim();
  }

  function recommendationFor(event) {
    const result = event.server_recommendation || {};
    return [safe(result.classification, "CHANGE"), safe(result.reason, "Server recommendation unavailable."), safe(result.truth_state, "blocked")];
  }

  function renderCommandBrief(events) {
    const comparableEvents = events.filter((event) => (
      verifiedMetric(event, "spend_amount") != null
      && verifiedMetric(event, "qualified_buyer_leads") != null
    ));
    if (!comparableEvents.length) {
      elements.commandTruth.textContent = "No evidence";
      elements.commandTruth.dataset.state = "unavailable";
      elements.commandUpdated.textContent = "Last updated: no campaign evidence recorded";
      elements.weeklySpend.textContent = "Not imported";
      elements.weeklyLeads.textContent = "Not verified";
      elements.ownerAlerts.innerHTML = "<strong>Evidence needed</strong><span>Record a campaign measurement window before comparing or preparing a decision.</span>";
      elements.ownerAlerts.dataset.state = "blocked";
      elements.comparisonWindow.textContent = "Insufficient data";
      elements.campaignComparison.innerHTML = '<div class="table-empty">No campaign evidence is available. Revenue and targets remain unavailable.</div>';
      elements.recommendationList.innerHTML = '<div class="table-empty">No owner decision can be prepared without evidence.</div>';
      elements.decisionCount.textContent = "0";
      return;
    }
    const latest = comparableEvents[0];
    const windowName = normalizedWindow(latest.measurement_window);
    const seenCampaigns = new Set();
    const compatible = comparableEvents.filter((event) => {
      if (normalizedWindow(event.measurement_window) !== windowName || safe(event.spend_currency, "ZAR") !== safe(latest.spend_currency, "ZAR")) return false;
      const campaignKey = `${safe(event.publish_packet_id, event.manual_post_event_id || event.channel)}|${windowName}`;
      if (seenCampaigns.has(campaignKey)) return false;
      seenCampaigns.add(campaignKey);
      return true;
    });
    const spend = compatible.reduce((sum, event) => sum + Number(verifiedMetric(event, "spend_amount")), 0);
    const leads = compatible.reduce((sum, event) => sum + Number(verifiedMetric(event, "qualified_buyer_leads")), 0);
    const recommendations = compatible.map((event) => ({ event, result: recommendationFor(event) }));
    const zeroLeadSpend = recommendations.some(({ event }) => Number(verifiedMetric(event, "spend_amount")) > 0 && Number(verifiedMetric(event, "qualified_buyer_leads")) === 0);
    elements.commandTruth.textContent = compatible.length > 1 ? "Comparable evidence" : "Limited evidence";
    elements.commandTruth.dataset.state = compatible.length > 1 ? "ready" : "stale";
    elements.commandUpdated.textContent = `Last updated: ${safe(latest.created_at, "source time unavailable")}`;
    elements.weeklySpend.textContent = `R ${spend.toFixed(2)}`;
    elements.weeklyLeads.textContent = String(leads);
    elements.comparisonWindow.textContent = safe(latest.measurement_window, "Window unavailable");
    elements.comparisonWindow.dataset.state = compatible.length > 1 ? "ready" : "stale";
    elements.ownerAlerts.dataset.state = zeroLeadSpend ? "blocked" : "review";
    elements.ownerAlerts.innerHTML = zeroLeadSpend
      ? "<strong>Spend without qualified leads</strong><span>Stop and review the affected campaign before any later paid action.</span>"
      : `<strong>${recommendations.length} recommendation${recommendations.length === 1 ? "" : "s"} awaiting owner review</strong><span>Revenue remains unattributed and no action executes from this brief.</span>`;
    elements.campaignComparison.innerHTML = compatible.map((event) => `
      <article class="beacon-comparison-row">
        <div><strong>${escapeHtml(safe(event.channel, "Unknown channel"))}</strong><small>${escapeHtml(safe(event.publish_packet_id, event.performance_event_id))}</small></div>
        <span><small>Spend</small><strong>${escapeHtml(safe(event.spend_currency, "ZAR"))} ${Number(verifiedMetric(event, "spend_amount")).toFixed(2)}</strong></span>
        <span><small>Qualified leads</small><strong>${Number(verifiedMetric(event, "qualified_buyer_leads"))}</strong></span>
        <span><small>Cost / lead</small><strong>${event.cost_per_qualified_lead == null ? "Unavailable" : `R ${Number(event.cost_per_qualified_lead).toFixed(2)}`}</strong></span>
      </article>`).join("");
    elements.recommendationList.innerHTML = recommendations.map(({ event, result }, index) => `
      <article class="beacon-recommendation-card" data-action="${result[0].toLowerCase()}">
        <div class="beacon-recommendation-title"><span>${result[0]}</span><small>${result[2] === "blocked" ? "Blocked" : "Owner decision required"}</small></div>
        <strong>${escapeHtml(safe(event.channel, "Campaign"))} · ${escapeHtml(safe(event.measurement_window))}</strong>
        <p>${escapeHtml(result[1])}</p>
        <small>Source: ${escapeHtml(safe(event.performance_event_id))}</small>
        <button type="button" class="button-link beacon-prepare-decision" data-index="${index}">Prepare decision brief</button>
      </article>`).join("");
    elements.decisionCount.textContent = String(recommendations.length);
    elements.recommendationList.querySelectorAll(".beacon-prepare-decision").forEach((button) => {
      button.addEventListener("click", () => {
        const item = recommendations[Number(button.dataset.index)];
        elements.decisionResult.innerHTML = `<strong>${item.result[0]} brief prepared for owner review.</strong><span>No campaign approval, CORE mission, spend, post, send, reservation, or operational write occurred.</span>`;
      });
    });
  }

  function renderServerCommandBrief(brief) {
    const comparison = brief.comparison || {};
    const campaigns = comparison.campaigns || [];
    const recommendations = brief.recommendations || [];
    const alerts = Array.isArray(brief.alerts) ? brief.alerts : [];
    const targets = brief.targets || {};
    renderTarget("spend", targets.spend || { status: "unavailable", actual: 0 });
    renderTarget("qualified_leads", targets.qualified_leads || { status: "unavailable", actual: 0 });
    if (!campaigns.length) {
      elements.commandTruth.textContent = "No evidence";
      elements.commandTruth.dataset.state = "unavailable";
      elements.commandUpdated.textContent = "Last updated: no campaign evidence recorded";
      elements.ownerAlerts.innerHTML = "<strong>Evidence needed</strong><span>Record a campaign measurement window before comparing or preparing a decision.</span>";
      elements.ownerAlerts.dataset.state = "blocked";
      elements.comparisonWindow.textContent = "Insufficient data";
      elements.campaignComparison.innerHTML = '<div class="table-empty">No campaign evidence is available. Revenue and targets remain unavailable.</div>';
      elements.recommendationList.innerHTML = '<div class="table-empty">No owner decision can be prepared without evidence.</div>';
      elements.decisionCount.textContent = "0";
      return;
    }
    const hasStop = recommendations.some((item) => item.classification === "STOP");
    const alertCodes = new Set(alerts.map((alert) => safe(alert.code, "")));
    const evidenceBlocked = alertCodes.has("missing_evidence") || alertCodes.has("stale_evidence");
    const alertCopy = {
      missing_evidence: "Campaign evidence is missing. Record a supported measurement before preparing a decision.",
      stale_evidence: "The latest campaign evidence is stale. Refresh or record current evidence before preparing a decision.",
      stop_recommendation_waiting: "A STOP recommendation is waiting for owner review. No paid or public action is authorized.",
      recommendations_waiting: `${recommendations.length} recommendation${recommendations.length === 1 ? "" : "s"} awaiting owner review.`,
    };
    elements.commandTruth.textContent = brief.truth_state === "comparable" ? "Comparable evidence" : "Limited evidence";
    elements.commandTruth.dataset.state = brief.truth_state === "comparable" ? "ready" : "stale";
    elements.commandUpdated.textContent = `Last updated: ${safe(brief.last_updated_at, "source time unavailable")}`;
    elements.comparisonWindow.textContent = safe(comparison.measurement_window, "Window unavailable");
    elements.comparisonWindow.dataset.state = comparison.status === "compatible" ? "ready" : "stale";
    elements.ownerAlerts.dataset.state = evidenceBlocked || hasStop ? "blocked" : "review";
    elements.ownerAlerts.innerHTML = alerts.length
      ? `<strong>${evidenceBlocked ? "Evidence blocks decision preparation" : hasStop ? "Owner attention required" : "Owner review required"}</strong><span>${alerts.map((alert) => escapeHtml(alertCopy[alert.code] || safe(alert.code).replace(/_/g, " "))).join(" ")} Revenue remains unattributed and no action executes from this brief.</span>`
      : `<strong>${recommendations.length} recommendation${recommendations.length === 1 ? "" : "s"} awaiting owner review</strong><span>Revenue remains unattributed and no action executes from this brief.</span>`;
    elements.campaignComparison.innerHTML = campaigns.map((event) => `
      <article class="beacon-comparison-row">
        <div><strong>${escapeHtml(safe(event.channel, "Unknown channel"))}</strong><small>${escapeHtml(safe(event.publish_packet_id, event.performance_event_id))}</small></div>
        <span><small>Spend</small><strong>${event.spend_amount == null ? "Not verified" : `${escapeHtml(safe(event.spend_currency, "ZAR"))} ${Number(event.spend_amount).toFixed(2)}`}</strong></span>
        <span><small>Qualified leads</small><strong>${event.qualified_buyer_leads == null ? "Not verified" : Number(event.qualified_buyer_leads)}</strong></span>
        <span><small>Cost / lead</small><strong>${event.cost_per_qualified_lead == null ? "Unavailable" : `R ${Number(event.cost_per_qualified_lead).toFixed(2)}`}</strong></span>
      </article>`).join("");
    elements.recommendationList.innerHTML = recommendations.map((item, index) => {
      const sourceAvailable = Boolean(safe(item.performance_event_id, ""));
      const preparationBlocked = evidenceBlocked || !sourceAvailable;
      const blockReason = evidenceBlocked ? "Current source evidence is required before preparation." : "A source performance event is required before preparation.";
      return `
      <article class="beacon-recommendation-card" data-action="${item.classification.toLowerCase()}">
        <div class="beacon-recommendation-title"><span>${item.classification}</span><small>${item.truth_state === "blocked" ? "Blocked" : "Owner decision required"}</small></div>
        <p>${escapeHtml(safe(item.reason))}</p>
        <small>Source: ${escapeHtml(safe(item.performance_event_id, "Unavailable"))}</small>
        ${preparationBlocked ? `<small class="beacon-decision-blocker" role="status">${escapeHtml(blockReason)}</small>` : ""}
        <div class="beacon-decision-actions">
          <button type="button" class="button-link beacon-prepare-decision" data-index="${index}" data-destination="campaign_decision" ${preparationBlocked ? "disabled" : ""}>Campaign decision</button>
          <button type="button" class="button-link button-link-secondary beacon-prepare-decision" data-index="${index}" data-destination="core_work" ${preparationBlocked ? "disabled" : ""}>CORE work brief</button>
        </div>
      </article>`;
    }).join("");
    elements.decisionCount.textContent = String(recommendations.length);
    elements.recommendationList.querySelectorAll(".beacon-prepare-decision").forEach((button) => {
      button.addEventListener("click", async () => {
        const item = recommendations[Number(button.dataset.index)];
        if (evidenceBlocked || !item || !safe(item.performance_event_id, "")) return;
        const result = await fetchJson("/api/beacon/weekly-command-brief/prepare-decision", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ performance_event_id: item.performance_event_id, destination: button.dataset.destination }),
        });
        elements.decisionResult.innerHTML = `<strong>${escapeHtml(result.classification)} ${escapeHtml(result.destination)} packet prepared.</strong><span>Next gate: ${escapeHtml(result.next_gate)}. No approval, mission creation, spend, post, send, reservation, or operational write occurred.</span>`;
      });
    });
  }

  function renderTarget(kind, target) {
    const isSpend = kind === "spend";
    const status = safe(target.status, "unavailable");
    const label = status.replace(/_/g, " ");
    const value = Number(target.actual || 0);
    const valueElement = isSpend ? elements.weeklySpend : elements.weeklyLeads;
    const statusElement = isSpend ? elements.weeklySpendStatus : elements.weeklyLeadsStatus;
    const targetElement = isSpend ? elements.weeklySpendTarget : elements.weeklyLeadsTarget;
    valueElement.textContent = status === "unavailable"
      ? (isSpend ? "Not imported" : "Not verified")
      : isSpend ? `${safe(target.currency, "ZAR")} ${value.toFixed(2)}` : String(value);
    statusElement.textContent = label;
    statusElement.dataset.state = status;
    targetElement.textContent = status === "unavailable" ? "Target unavailable · no owner-approved source" : `${label} target: ${target.target ?? "not set"}${target.blocker ? ` · ${target.blocker}` : ""}`;
  }

  async function recordCampaignPerformance() {
    clearMessage();
    const payload = {
      manual_post_event_id: elements.performanceManualPostId.value,
      publish_packet_id: elements.performancePublishPacketId.value,
      channel: elements.performanceChannel.value,
      measurement_window: elements.performanceWindow.value,
      spend_amount: elements.performanceSpend.value,
      reach: elements.performanceReach.value,
      messages_to_sam: elements.performanceMessages.value,
      qualified_buyer_leads: elements.performanceQualified.value,
      recommended_spend_amount: elements.performanceRecommendedSpend.value,
      recommended_duration_days: elements.performanceDuration.value,
      fulfillment_risk: elements.performanceFulfillmentRisk.value,
      safety_risk: elements.performanceSafetyRisk.value,
      notes: elements.performanceNotes.value,
      recorded_by: "farm_app_beacon_performance",
    };
    const result = await fetchJson("/api/beacon/campaign-performance", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderBoostPacket(result.boost_packet || {});
    showMessage(`Performance evidence recorded: ${result.performance_event_id}`, "success");
    await loadCampaignPerformance();
  }

  function renderBoostPacket(packet) {
    if (!packet.recommended_action) {
      elements.boostPacketResult.innerHTML = "";
      return;
    }
    const metrics = packet.primary_metrics || {};
    elements.boostPacketResult.innerHTML = `
      <div class="beacon-boost-packet-card">
        <strong>${escapeHtml(packet.recommended_action)}</strong>
        <span>${escapeHtml(safe(packet.channel))} | owner review only | no Meta call | no spend</span>
        <p>${escapeHtml(safe(packet.recommendation_reason))}</p>
        <small>Spend: ${escapeHtml(safe(packet.currency, "ZAR"))} ${escapeHtml(String(packet.recommended_spend_amount ?? 0))} / cap ${escapeHtml(String(packet.max_spend_cap_amount ?? 500))} | ${escapeHtml(String(packet.recommended_duration_days ?? 0))} days</small>
        <small>Messages: ${escapeHtml(String(metrics.messages_to_sam ?? 0))} | Qualified leads: ${escapeHtml(String(metrics.qualified_buyer_leads ?? 0))} | Cost/lead: ${escapeHtml(String(metrics.cost_per_qualified_lead ?? "--"))}</small>
      </div>
    `;
  }

  function renderCampaignPerformance(events) {
    if (!events.length) {
      elements.performanceList.innerHTML = `<div class="table-empty">No campaign performance evidence recorded yet.</div>`;
      return;
    }
    elements.performanceList.innerHTML = events.map((event, index) => {
      const items = evidenceItems(event);
      const missing = items.filter((item) => item.status !== "verified" && item.status !== "owner_correction");
      return `
      <div class="beacon-performance-item">
        <strong>${escapeHtml(event.recommended_action || event.performance_event_id)}</strong>
        <span>${escapeHtml(safe(event.channel))} | ${escapeHtml(safe(event.measurement_window))} | ${escapeHtml(safe(event.created_at))}</span>
        <small>Messages ${escapeHtml(metricDisplay(event, "messages_to_sam"))} | qualified leads ${escapeHtml(metricDisplay(event, "qualified_buyer_leads"))} | spend ${escapeHtml(metricDisplay(event, "spend_amount"))}</small>
        <small>${escapeHtml(safe(event.recommendation_reason))}</small>
        <div class="beacon-metric-grid">${items.map((item) => `<span class="beacon-metric-chip" data-state="${escapeHtml(item.status)}"><strong>${escapeHtml(item.name.replaceAll("_", " "))}</strong> ${item.value == null ? escapeHtml(item.status) : escapeHtml(String(item.value))} · ${escapeHtml(item.source || "source unavailable")}</span>`).join("")}</div>
        ${missing.length ? `<button type="button" class="button-link button-link-secondary beacon-correct-evidence" data-index="${index}">Correct ${missing.length} missing metric${missing.length === 1 ? "" : "s"}</button>` : ""}
      </div>`;
    }).join("");
    elements.performanceList.querySelectorAll(".beacon-correct-evidence").forEach((button) => button.addEventListener("click", () => {
      const event = events[Number(button.dataset.index)];
      openCorrection(event, evidenceItems(event).filter((item) => item.status !== "verified" && item.status !== "owner_correction"));
    }));
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
    formData.append("sale_stream_relevance", elements.uploadRelevance?.value || elements.campaignLane?.value || "live_stock_awareness");
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
    elements.metaPreviewRefresh.addEventListener("click", () => loadMetaAdsPreview().catch((error) => {
      elements.metaPreviewState.textContent = "Preview unavailable";
      elements.metaPreviewState.dataset.state = "blocked";
      showMessage(error.message);
    }));
    elements.metaImportPrepare.addEventListener("click", () => prepareMetaImportPacket().catch((error) => {
      elements.metaImportState.textContent = "Packet unavailable";
      elements.metaImportState.dataset.state = "blocked";
      showMessage(error.message);
    }));
    elements.metaImportApproval.addEventListener("change", () => {
      elements.metaImportExecute.disabled = !elements.metaImportApproval.checked || !state.metaImportPacket;
    });
    elements.metaImportExecute.addEventListener("click", () => executeMetaImportPacket().catch((error) => showMessage(error.message)));
    elements.contentRefresh.addEventListener("click", () => loadContentOperations().catch((error) => {
      elements.contentState.textContent = "Evidence unavailable";
      elements.contentState.dataset.state = "blocked";
      showMessage(error.message);
    }));
    elements.refresh.addEventListener("click", () => loadBeaconMedia().catch((error) => showMessage(error.message)));
    elements.campaignSelectionRefresh.addEventListener("click", () => loadCampaignSelection().catch((error) => showMessage(error.message)));
    elements.campaignLane.addEventListener("change", () => loadCampaignSelection().catch((error) => showMessage(error.message)));
    elements.facebookPostConfirmation.addEventListener("input", updateFacebookActionState);
    elements.publishCap.addEventListener("input", () => renderMeatReadiness({ campaign_lane: elements.campaignLane.value, meat_launch_readiness: { owner_offer_enabled: state.meatOfferEnabled } }));
    elements.publishChannel.addEventListener("change", () => {
      const whatsapp = elements.publishChannel.value === "WhatsApp";
      const sales = elements.campaignLane.value === "live_stock_sales";
      elements.publishPrepare.disabled = whatsapp || (sales && !state.salesTruthReady);
      if (whatsapp) showMessage("WhatsApp is suggestion-only. No send or publish action is available.", "success");
    });
    elements.publishPrepare.addEventListener("click", () => preparePublishPacket().catch((error) => showMessage(error.message)));
    elements.facebookPostRefresh.addEventListener("click", () => Promise.all([loadFacebookPostingPolicy(), loadFacebookPostExecutions()]).catch((error) => showMessage(error.message)));
    elements.facebookPostExecute.addEventListener("click", () => executeFacebookPost().catch((error) => showMessage(error.message)));
    elements.manualPostRefresh.addEventListener("click", () => loadManualPostEvidence().catch((error) => showMessage(error.message)));
    elements.manualPostRecord.addEventListener("click", () => recordManualPostEvidence().catch((error) => showMessage(error.message)));
    elements.performanceRefresh.addEventListener("click", () => loadCampaignPerformance().catch((error) => showMessage(error.message)));
    elements.commandRefresh.addEventListener("click", () => loadCampaignPerformance().catch((error) => {
      elements.commandTruth.textContent = "Evidence unavailable";
      elements.commandTruth.dataset.state = "blocked";
      elements.ownerAlerts.innerHTML = `<strong>Could not load campaign evidence</strong><span>${escapeHtml(error.message)}</span>`;
      elements.ownerAlerts.dataset.state = "blocked";
    }));
    elements.performanceRecord.addEventListener("click", () => recordCampaignPerformance().catch((error) => showMessage(error.message)));
    elements.historyImport.addEventListener("click", () => importFacebookHistory().catch((error) => { elements.historyImportStatus.textContent = error.message; elements.historyImportStatus.dataset.state = "blocked"; showMessage(error.message); }));
    elements.correctionSave.addEventListener("click", () => saveCorrection().catch((error) => showMessage(error.message)));
    elements.statusFilter.addEventListener("change", () => loadBeaconMedia().catch((error) => showMessage(error.message)));
    elements.typeFilter.addEventListener("change", () => loadBeaconMedia().catch((error) => showMessage(error.message)));
    elements.uploadForm.addEventListener("submit", (event) => uploadAsset(event).catch((error) => showMessage(error.message)));
    elements.saveNote.addEventListener("click", () => recordReviewEvent("review_note").catch((error) => showMessage(error.message)));
    elements.approve.addEventListener("click", () => recordReviewEvent("approved_public_use").catch((error) => showMessage(error.message)));
    elements.reject.addEventListener("click", () => recordReviewEvent("rejected_public_use").catch((error) => showMessage(error.message)));
    elements.archive.addEventListener("click", () => recordReviewEvent("archived").catch((error) => showMessage(error.message)));
    setReviewDisabled(true);
    await loadContentOperations().catch((error) => {
      elements.contentState.textContent = "Evidence unavailable";
      elements.contentState.dataset.state = "blocked";
      showMessage(error.message);
    });
    await loadBeaconMedia().catch((error) => showMessage(error.message));
  });
})();
