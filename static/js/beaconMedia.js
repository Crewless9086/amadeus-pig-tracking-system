(() => {
  const state = {
    policy: null,
    assets: [],
    selectedAssetId: "",
    latestPublishPacket: null,
    facebookPostingPolicy: null,
    performanceEvents: [],
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

  async function loadCampaignSelection() {
    const params = new URLSearchParams({
      limit: "25",
      campaign_lane: elements.campaignLane?.value || "live_stock_awareness",
    });
    const selection = await fetchJson(`/api/beacon/campaign-draft-selection?${params.toString()}`);
    const laneLabel = selection.campaign_lane === "meat_launch" ? "meat launch" : "live-stock awareness";
    elements.campaignSelectionStatus.textContent = `${selection.approved_media_count || 0} approved media asset${selection.approved_media_count === 1 ? "" : "s"} available for ${laneLabel} draft pairing. Public posting remains locked.`;
    renderCampaignSelection(selection);
    renderPublishPacketOptions(selection);
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
    elements.publishAssetId.innerHTML = [
      `<option value="">Text only for now</option>`,
      ...assets.map((asset) => `<option value="${escapeHtml(asset.asset_id)}">${escapeHtml(safe(asset.title || asset.asset_id))}</option>`),
    ].join("");
    if (pairings[0] && !elements.publishChannel.value) {
      elements.publishChannel.value = pairings[0].channel || "";
    }
  }

  async function preparePublishPacket() {
    clearMessage();
    const payload = {
      campaign_lane: elements.campaignLane?.value || "live_stock_awareness",
      draft_id: elements.publishDraftId.value,
      asset_id: elements.publishAssetId.value,
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
    const asset = packet.selected_asset || {};
    elements.publishResult.innerHTML = `
      <div class="beacon-publish-packet-card">
        <strong>${escapeHtml(packet.publish_packet_id)}</strong>
        <span>${escapeHtml(packet.selected_draft?.channel || "")} | ${escapeHtml(packet.approval_status || "")}</span>
        <p>Asset: ${escapeHtml(safe(asset.title || asset.asset_id, "Text only"))}</p>
        <pre>${escapeHtml(packet.selected_draft?.exact_text || "")}</pre>
        <small>Checks: preorder ${checks.draft_is_limited_preorder ? "yes" : "no"} | forbidden promises ${checks.draft_has_no_forbidden_promise ? "clear" : "review"} | posting ${checks.no_public_send_or_post ? "locked" : "enabled"}</small>
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
    elements.facebookPostPacketId.value = packet.publish_packet_id || "";
    elements.facebookPostAssetId.value = packet.selected_asset?.asset_id || "";
    elements.facebookPostExactText.value = packet.selected_draft?.exact_text || "";
  }

  async function loadFacebookPostingPolicy() {
    const policy = await fetchJson("/api/beacon/facebook-posting-policy");
    state.facebookPostingPolicy = policy;
    const ready = Boolean(policy.enabled && policy.page_id_configured && policy.page_access_token_configured);
    elements.facebookPostPolicyStatus.textContent = ready
      ? "Facebook posting gate is armed. Exact owner confirmation is still required."
      : "Facebook posting is locked until Render envs and owner confirmation are present.";
    elements.facebookPostExecute.disabled = !ready;
    return policy;
  }

  async function loadFacebookPostExecutions() {
    const data = await fetchJson("/api/beacon/facebook-post-executions?limit=8");
    renderFacebookPostExecutions(data.execution_events || []);
  }

  async function executeFacebookPost() {
    clearMessage();
    const payload = {
      publish_packet_id: elements.facebookPostPacketId.value,
      channel: "Facebook",
      exact_text: elements.facebookPostExactText.value,
      asset_id: elements.facebookPostAssetId.value,
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
        <small>${escapeHtml(safe(event.post_kind || result.facebook_result?.post_kind || "feed"))} | media ${escapeHtml(safe(event.selected_media?.asset_id || result.facebook_result?.selected_media?.asset_id, "text only"))}</small>
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
        <small>${escapeHtml(safe(event.post_kind || "feed"))} | ${escapeHtml(safe(event.selected_media?.title || event.selected_media?.asset_id, "text only"))}</small>
        <small>${escapeHtml(safe(event.created_at))}</small>
      </div>
    `).join("");
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

  function normalizedWindow(value) {
    return safe(value, "").toLowerCase().replace(/\s+/g, " ").trim();
  }

  function recommendationFor(event) {
    const result = event.server_recommendation || {};
    return [safe(result.classification, "CHANGE"), safe(result.reason, "Server recommendation unavailable."), safe(result.truth_state, "blocked")];
  }

  function renderCommandBrief(events) {
    if (!events.length) {
      elements.commandTruth.textContent = "No evidence";
      elements.commandTruth.dataset.state = "unavailable";
      elements.commandUpdated.textContent = "Last updated: no campaign evidence recorded";
      elements.weeklySpend.textContent = "R 0.00";
      elements.weeklyLeads.textContent = "0";
      elements.ownerAlerts.innerHTML = "<strong>Evidence needed</strong><span>Record a campaign measurement window before comparing or preparing a decision.</span>";
      elements.ownerAlerts.dataset.state = "blocked";
      elements.comparisonWindow.textContent = "Insufficient data";
      elements.campaignComparison.innerHTML = '<div class="table-empty">No campaign evidence is available. Revenue and targets remain unavailable.</div>';
      elements.recommendationList.innerHTML = '<div class="table-empty">No owner decision can be prepared without evidence.</div>';
      elements.decisionCount.textContent = "0";
      return;
    }
    const latest = events[0];
    const windowName = normalizedWindow(latest.measurement_window);
    const seenCampaigns = new Set();
    const compatible = events.filter((event) => {
      if (normalizedWindow(event.measurement_window) !== windowName || safe(event.spend_currency, "ZAR") !== safe(latest.spend_currency, "ZAR")) return false;
      const campaignKey = `${safe(event.publish_packet_id, event.manual_post_event_id || event.channel)}|${windowName}`;
      if (seenCampaigns.has(campaignKey)) return false;
      seenCampaigns.add(campaignKey);
      return true;
    });
    const spend = compatible.reduce((sum, event) => sum + Number(event.spend_amount || 0), 0);
    const leads = compatible.reduce((sum, event) => sum + Number(event.qualified_buyer_leads || 0), 0);
    const recommendations = compatible.map((event) => ({ event, result: recommendationFor(event) }));
    const zeroLeadSpend = recommendations.some(({ event }) => Number(event.spend_amount || 0) > 0 && Number(event.qualified_buyer_leads || 0) === 0);
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
        <span><small>Spend</small><strong>${escapeHtml(safe(event.spend_currency, "ZAR"))} ${Number(event.spend_amount || 0).toFixed(2)}</strong></span>
        <span><small>Qualified leads</small><strong>${Number(event.qualified_buyer_leads || 0)}</strong></span>
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
    elements.commandTruth.textContent = brief.truth_state === "comparable" ? "Comparable evidence" : "Limited evidence";
    elements.commandTruth.dataset.state = brief.truth_state === "comparable" ? "ready" : "stale";
    elements.commandUpdated.textContent = `Last updated: ${safe(brief.last_updated_at, "source time unavailable")}`;
    elements.comparisonWindow.textContent = safe(comparison.measurement_window, "Window unavailable");
    elements.comparisonWindow.dataset.state = comparison.status === "compatible" ? "ready" : "stale";
    elements.ownerAlerts.dataset.state = hasStop ? "blocked" : "review";
    elements.ownerAlerts.innerHTML = hasStop
      ? "<strong>Spend or safety blocker</strong><span>Stop and review the affected campaign before any later paid action.</span>"
      : `<strong>${recommendations.length} recommendation${recommendations.length === 1 ? "" : "s"} awaiting owner review</strong><span>Revenue remains unattributed and no action executes from this brief.</span>`;
    elements.campaignComparison.innerHTML = campaigns.map((event) => `
      <article class="beacon-comparison-row">
        <div><strong>${escapeHtml(safe(event.channel, "Unknown channel"))}</strong><small>${escapeHtml(safe(event.publish_packet_id, event.performance_event_id))}</small></div>
        <span><small>Spend</small><strong>${escapeHtml(safe(event.spend_currency, "ZAR"))} ${Number(event.spend_amount || 0).toFixed(2)}</strong></span>
        <span><small>Qualified leads</small><strong>${Number(event.qualified_buyer_leads || 0)}</strong></span>
        <span><small>Cost / lead</small><strong>${event.cost_per_qualified_lead == null ? "Unavailable" : `R ${Number(event.cost_per_qualified_lead).toFixed(2)}`}</strong></span>
      </article>`).join("");
    elements.recommendationList.innerHTML = recommendations.map((item, index) => `
      <article class="beacon-recommendation-card" data-action="${item.classification.toLowerCase()}">
        <div class="beacon-recommendation-title"><span>${item.classification}</span><small>${item.truth_state === "blocked" ? "Blocked" : "Owner decision required"}</small></div>
        <p>${escapeHtml(safe(item.reason))}</p>
        <small>Source: ${escapeHtml(safe(item.performance_event_id))}</small>
        <div class="beacon-decision-actions">
          <button type="button" class="button-link beacon-prepare-decision" data-index="${index}" data-destination="campaign_decision">Campaign decision</button>
          <button type="button" class="button-link button-link-secondary beacon-prepare-decision" data-index="${index}" data-destination="core_work">CORE work brief</button>
        </div>
      </article>`).join("");
    elements.decisionCount.textContent = String(recommendations.length);
    elements.recommendationList.querySelectorAll(".beacon-prepare-decision").forEach((button) => {
      button.addEventListener("click", async () => {
        const item = recommendations[Number(button.dataset.index)];
        const result = await fetchJson("/api/beacon/weekly-command-brief/prepare-decision", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ recommendation: item, destination: button.dataset.destination }),
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
    valueElement.textContent = isSpend ? `${safe(target.currency, "ZAR")} ${value.toFixed(2)}` : String(value);
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
    elements.performanceList.innerHTML = events.map((event) => `
      <div class="beacon-performance-item">
        <strong>${escapeHtml(event.recommended_action || event.performance_event_id)}</strong>
        <span>${escapeHtml(safe(event.channel))} | ${escapeHtml(safe(event.measurement_window))} | ${escapeHtml(safe(event.created_at))}</span>
        <small>Messages ${escapeHtml(String(event.messages_to_sam ?? 0))} | qualified leads ${escapeHtml(String(event.qualified_buyer_leads ?? 0))} | spend ${escapeHtml(safe(event.spend_currency, "ZAR"))} ${escapeHtml(String(event.spend_amount ?? 0))}</small>
        <small>${escapeHtml(safe(event.recommendation_reason))}</small>
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
    elements.refresh.addEventListener("click", () => loadBeaconMedia().catch((error) => showMessage(error.message)));
    elements.campaignSelectionRefresh.addEventListener("click", () => loadCampaignSelection().catch((error) => showMessage(error.message)));
    elements.campaignLane.addEventListener("change", () => loadCampaignSelection().catch((error) => showMessage(error.message)));
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
