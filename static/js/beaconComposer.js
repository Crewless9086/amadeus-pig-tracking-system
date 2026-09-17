(() => {
  const state = { assets: [], selected: new Set(), packet: null };
  const $ = (id) => document.getElementById(id);
  const el = {
    files: $("beacon_quick_files"), upload: $("beacon_quick_upload"), uploadStatus: $("beacon_quick_upload_status"),
    media: $("beacon_quick_media"), lane: $("beacon_quick_lane"), brief: $("beacon_quick_brief"),
    suggest: $("beacon_quick_suggest"), learning: $("beacon_quick_learning"), suggestions: $("beacon_quick_suggestions"),
    caption: $("beacon_quick_caption"), revision: $("beacon_quick_revision"), revise: $("beacon_quick_revise"), revisionStatus: $("beacon_quick_revision_status"),
    safety: $("beacon_quick_safety"), preview: $("beacon_quick_preview"), previewMedia: $("beacon_quick_preview_media"),
    prepare: $("beacon_quick_prepare"), publish: $("beacon_quick_publish"), manual: $("beacon_quick_manual"), postUrl: $("beacon_quick_post_url"), recordUrl: $("beacon_quick_record_url"),
    actionTitle: $("beacon_quick_action_title"), actionNote: $("beacon_quick_action_note"), result: $("beacon_quick_result"), status: $("beacon_compose_state"),
  };
  if (!el.files) return;
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  async function api(url, options = {}) {
    const response = await fetch(url, {credentials: "same-origin", ...options});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.success === false) throw new Error(data.status || data.error || `Request failed (${response.status})`);
    return data;
  }
  const statusOf = (asset) => asset.effective_approval_status || asset.approval_status || "needs_review";
  async function loadAssets() {
    const data = await api("/api/beacon/media-assets?limit=100");
    state.assets = data.assets || [];
    renderAssets();
    el.status.textContent = `${state.assets.length} media files`;
    el.status.dataset.state = "ready";
  }
  function renderAssets() {
    if (!state.assets.length) { el.media.innerHTML = '<div class="table-empty">Upload your first photo or video.</div>'; return; }
    el.media.innerHTML = state.assets.map((asset) => {
      const approved = statusOf(asset) === "approved";
      const checked = state.selected.has(asset.asset_id) ? "checked" : "";
      return `<div class="beacon-quick-asset"><input type="checkbox" data-select="${esc(asset.asset_id)}" ${checked} ${approved ? "" : "disabled"}/><div><strong>${esc(asset.title || asset.original_filename || asset.asset_id)}</strong><small>${esc(asset.media_type)} · ${approved ? "approved" : "needs approval"}</small></div>${approved ? "" : `<button type="button" data-approve="${esc(asset.asset_id)}">Approve</button>`}</div>`;
    }).join("");
    el.media.querySelectorAll("[data-select]").forEach((box) => box.addEventListener("change", () => { box.checked ? state.selected.add(box.dataset.select) : state.selected.delete(box.dataset.select); updatePreview(); }));
    el.media.querySelectorAll("[data-approve]").forEach((button) => button.addEventListener("click", () => approveAsset(button.dataset.approve)));
  }
  async function approveAsset(assetId) {
    await api(`/api/beacon/media-assets/${encodeURIComponent(assetId)}/events`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({event_type:"approved_public_use", approval_status:"approved", privacy_risk:"low", notes:"Approved from Beacon quick composer"})});
    state.selected.add(assetId); await loadAssets(); el.uploadStatus.textContent = "Media approved and selected.";
  }
  async function uploadFiles() {
    const files = Array.from(el.files.files || []); if (!files.length) { el.uploadStatus.textContent = "Choose at least one photo or video."; return; }
    el.upload.disabled = true;
    try {
      for (let i=0;i<files.length;i++) {
        el.uploadStatus.textContent = `Saving ${i+1} of ${files.length}: ${files[i].name}`;
        const form = new FormData(); form.append("file", files[i]); form.append("title", files[i].name.replace(/\.[^.]+$/, "")); form.append("source", "beacon_quick_composer"); form.append("sale_stream_relevance", el.lane.value);
        await api("/api/beacon/media-assets/upload", {method:"POST", body:form});
      }
      el.files.value = ""; el.uploadStatus.textContent = `${files.length} file${files.length === 1 ? "" : "s"} saved privately. Click Approve beside the files you want to use.`;
    } catch (error) { el.uploadStatus.textContent = error.message; } finally { el.upload.disabled = false; await loadAssets().catch(() => {}); }
  }
  async function suggestCaptions() {
    el.suggest.disabled = true; el.learning.textContent = "Beacon is reading past approved posts...";
    try {
      const data = await api("/api/beacon/post-composer/suggestions", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({campaign_lane:el.lane.value, brief:el.brief.value})});
      el.learning.textContent = `${data.historical_example_count || 0} past approved posts informed these suggestions · ${data.suggestion_source === "beacon_llm_with_historical_examples" ? "AI composed" : "safe local fallback"}`;
      el.suggestions.innerHTML = (data.suggestions || []).map((text, i) => `<button type="button" class="beacon-caption-option" data-caption="${i}"><strong>Option ${i+1}</strong><p>${esc(text)}</p></button>`).join("");
      el.suggestions.querySelectorAll("[data-caption]").forEach((button) => button.addEventListener("click", () => { el.caption.value = data.suggestions[Number(button.dataset.caption)]; updatePreview(); }));
      if (data.suggestions?.length) { el.caption.value = data.suggestions[0]; updatePreview(); }
    } catch (error) { el.learning.textContent = error.message; } finally { el.suggest.disabled = false; }
  }
  async function reviseCaption() {
    const instruction = el.revision.value.trim();
    if (!instruction || !el.caption.value.trim()) { el.revisionStatus.textContent = "Choose a caption and describe the change first."; return; }
    el.revise.disabled = true; el.revisionStatus.textContent = "Revising in your established post style...";
    try {
      const data = await api("/api/beacon/post-composer/revision", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({campaign_lane:el.lane.value, caption:el.caption.value, revision_instruction:instruction, brief:el.brief.value})});
      el.caption.value = data.caption || data.revised_caption || ""; el.revision.value = ""; updatePreview();
      el.revisionStatus.textContent = "Caption revised. Review or edit it directly before posting.";
    } catch (error) { el.revisionStatus.textContent = `${error.message}. Your current caption is unchanged.`; } finally { el.revise.disabled = false; }
  }
  function localIssues() {
    const text = el.caption.value.toLowerCase(); if (!text.trim()) return ["Add or select a caption."];
    if (el.lane.value !== "live_stock_awareness") return [];
    const blocked = ["buy","sale","available","stock","price","cost","discount","special","order","book","reserve","dm to buy","message to buy"];
    return blocked.filter((term) => new RegExp(`(^|\\W)${term}(?=$|\\W)`, "i").test(text)).map((term) => `Remove “${term}” from livestock awareness copy.`);
  }
  function updatePreview() {
    const issues = localIssues(); el.preview.textContent = el.caption.value || "Your final caption will appear here.";
    const selected = Array.from(state.selected).map((id) => state.assets.find((asset) => asset.asset_id === id)).filter(Boolean);
    el.previewMedia.innerHTML = selected.length ? selected.map((asset, index) => `<div class="beacon-preview-media-item" data-type="${esc(asset.media_type)}"><span>${asset.media_type === "video" ? "▶" : "▧"}</span><div><strong>${index + 1}. ${esc(asset.title || asset.original_filename || "Farm media")}</strong><small>${esc(asset.media_type)} · exact post order</small></div></div>`).join("") : "<p>Select approved media to see the exact post order.</p>";
    el.safety.dataset.state = issues.length ? "blocked" : "ready";
    el.safety.innerHTML = issues.length ? `<strong>Needs attention</strong><span>${esc(issues.join(" "))}</span>` : "<strong>Awareness safety check passed</strong><span>No direct livestock sales wording detected.</span>";
    state.packet = null; el.publish.classList.add("hidden"); el.manual.classList.add("hidden"); el.prepare.classList.remove("hidden");
  }
  async function preparePost() {
    const issues = localIssues(); if (issues.length) { updatePreview(); return; }
    const assetIds = Array.from(state.selected); if (!assetIds.length) { el.result.textContent = "Select at least one approved photo or video."; return; }
    el.prepare.disabled = true;
    try {
      const data = await api("/api/beacon/campaign-publish-packet", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({campaign_lane:el.lane.value, draft_id:el.lane.value === "live_stock_awareness" ? "facebook_awareness_post" : "facebook_post", asset_ids:assetIds, asset_id:assetIds[0], channel:"Facebook", owner_exact_text:el.caption.value})});
      state.packet = data; const media = data.selected_assets || [];
      const mixed = media.some((a) => a.media_type === "video") && media.some((a) => a.media_type === "image");
      el.prepare.classList.add("hidden");
      if (mixed) { el.actionTitle.textContent = "Manual Facebook handoff"; el.actionNote.textContent = "Facebook requires mixed photo and video posts to be assembled in its composer."; el.result.textContent = "Exact caption copied. Add the selected media in the order shown above."; el.manual.classList.remove("hidden"); await navigator.clipboard?.writeText(el.caption.value).catch(() => {}); }
      else { el.actionTitle.textContent = "Exact post ready"; el.actionNote.textContent = "This is the one owner-confirmed public action."; el.result.textContent = "Caption, media order and safety check are locked for your confirmation."; el.publish.classList.remove("hidden"); }
    } catch (error) { el.result.textContent = error.message; } finally { el.prepare.disabled = false; }
  }
  async function publishPost() {
    if (!state.packet || !window.confirm("Publish this exact caption and selected media to the Amadeus Facebook Page?")) return;
    el.publish.disabled = true;
    try {
      const assetIds = state.packet.asset_ids || [];
      const data = await api("/api/beacon/facebook-post-executions", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({campaign_lane:state.packet.campaign_lane, publish_packet_id:state.packet.publish_packet_id, channel:"Facebook", exact_text:state.packet.selected_draft.exact_text, asset_ids:assetIds, asset_id:assetIds[0], owner_confirmation:"POST EXACT BEACON PACKET"})});
      el.result.textContent = `Published to Facebook${data.facebook_post_id ? ` · Post ${data.facebook_post_id}` : ""}. Evidence was recorded automatically.`; el.publish.classList.add("hidden");
    } catch (error) { el.result.textContent = error.message; } finally { el.publish.disabled = false; }
  }
  async function recordManualUrl() {
    if (!state.packet || !el.postUrl.value.trim()) { el.result.textContent = "Paste the Facebook post URL first."; return; }
    el.recordUrl.disabled = true;
    try { await api("/api/beacon/manual-post-evidence", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({publish_packet_id:state.packet.publish_packet_id, channel:"Facebook", post_url:el.postUrl.value.trim(), evidence_notes:`Exact text: ${el.caption.value}`})}); el.result.textContent = "Post URL saved. Beacon can now learn from this post."; }
    catch (error) { el.result.textContent = error.message; } finally { el.recordUrl.disabled = false; }
  }
  el.upload.addEventListener("click", uploadFiles); el.suggest.addEventListener("click", suggestCaptions); el.revise.addEventListener("click", reviseCaption); el.caption.addEventListener("input", updatePreview); el.lane.addEventListener("change", updatePreview); el.prepare.addEventListener("click", preparePost); el.publish.addEventListener("click", publishPost); el.recordUrl.addEventListener("click", recordManualUrl);
  loadAssets().catch((error) => { el.status.textContent = error.message; el.status.dataset.state = "blocked"; });
})();
