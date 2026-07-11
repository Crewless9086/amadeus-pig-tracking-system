(() => {
  "use strict";

  const state = { packet: null, selectedId: "sam-live-stock", loading: false, firstLoad: true };
  const elements = {
    summary: document.getElementById("summaryStrip"),
    list: document.getElementById("agentList"),
    map: document.getElementById("systemMap"),
    detail: document.getElementById("detailBody"),
    detailState: document.getElementById("detailState"),
    rosterCount: document.getElementById("rosterCount"),
    sourceStatus: document.getElementById("sourceStatus"),
    footer: document.getElementById("footerStatus"),
    updated: document.getElementById("lastUpdated"),
    loading: document.getElementById("loadingMask"),
    refresh: document.getElementById("refreshBtn"),
  };

  const esc = (value) => String(value == null ? "" : value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const clamp = (value) => Math.max(0, Math.min(100, Number(value) || 0));
  const title = (value) => String(value || "unknown").replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const pct = (value) => `${Math.round((Number(value) || 0) * 100)}%`;

  async function fetchPacket(forceRefresh = false) {
    if (state.loading) return;
    state.loading = true;
    elements.refresh.disabled = true;
    try {
      const response = await fetch(`/api/charlie/agent-workforce?limit=500${forceRefresh ? "&refresh=1" : ""}`, { credentials: "same-origin" });
      const packet = await response.json().catch(() => ({}));
      if (!response.ok || !packet.success) throw new Error(packet.status || `HTTP ${response.status}`);
      state.packet = packet;
      if (!packet.agents.some((agent) => agent.id === state.selectedId)) state.selectedId = packet.agents[0]?.id || "";
      render();
      elements.sourceStatus.innerHTML = '<span class="status-dot" style="background:#45b982"></span>Live evidence';
      elements.updated.textContent = `Updated ${new Date(packet.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
    } catch (error) {
      elements.sourceStatus.innerHTML = '<span class="status-dot" style="background:#d85c52"></span>Evidence unavailable';
      if (!state.packet) {
        elements.list.innerHTML = `<div class="empty">Could not load workforce evidence.<br>${esc(error.message)}</div>`;
        elements.detail.innerHTML = '<div class="empty">No agent evidence is available.</div>';
      }
    } finally {
      state.loading = false;
      state.firstLoad = false;
      elements.refresh.disabled = false;
      elements.loading.classList.add("hidden");
    }
  }

  function render() {
    renderSummary();
    renderRoster();
    renderMap();
    renderDetail();
    renderFooter();
  }

  function renderSummary() {
    const summary = state.packet.summary || {};
    const measured = summary.measured_agents || 0;
    const total = summary.agents_total || 0;
    const items = [
      ["Workforce", total, `${measured} with measured evidence`],
      ["Training", measured, "agents reporting live metrics"],
      ["Candidates", summary.graduation_candidates || 0, "owner decision required"],
      ["Active missions", summary.active_missions || 0, "CHARLIE execution queue"],
      ["Owner attention", summary.attention_needed || 0, "agents with blockers"],
    ];
    elements.summary.innerHTML = items.map(([label, value, note]) => `
      <div class="summary-item" title="${esc(note)}">
        <div class="summary-label">${esc(label)}</div>
        <div class="summary-value">${esc(value)}</div>
        <div class="summary-note">${esc(note)}</div>
      </div>`).join("");
  }

  function renderRoster() {
    const agents = state.packet.agents || [];
    elements.rosterCount.textContent = `${agents.length} agents`;
    elements.list.innerHTML = agents.map((agent) => {
      const evidence = agent.evidence || {};
      const measured = evidence.measured && evidence.progress_percent != null;
      const score = measured ? `${Math.round(evidence.progress_percent)}%` : "--";
      const portrait = agent.portrait
        ? `<img class="agent-avatar" src="${esc(agent.portrait)}" alt="">`
        : `<span class="agent-avatar fallback">${esc(initials(agent.name))}</span>`;
      return `<button class="agent-row ${agent.id === state.selectedId ? "active" : ""}" data-agent-id="${esc(agent.id)}" title="${esc(agent.role)}">
        ${portrait}
        <span>
          <span class="agent-name">${esc(agent.name)}</span>
          <span class="agent-meta">${esc(agent.team)} · ${esc(title(agent.stage))}</span>
          <span class="mini-track"><span style="width:${measured ? clamp(evidence.progress_percent) : 0}%"></span></span>
        </span>
        <span class="agent-score">${score}<small>${measured ? "evidence" : "not measured"}</small></span>
      </button>`;
    }).join("");
    elements.list.querySelectorAll("[data-agent-id]").forEach((button) => {
      button.addEventListener("click", () => selectAgent(button.dataset.agentId));
    });
  }

  function renderMap() {
    const agents = new Map((state.packet.agents || []).map((agent) => [agent.id, agent]));
    const tiers = [
      [{ id: "owner", name: "Owner", type: "owner", state: "Final authority" }],
      [{ id: "charlie-core", name: "CHARLIE CORE", type: "command" }],
      ["codex-builder", "review-qa", "sam-live-stock", "sam-meat", "oom-sakkie"].map((id) => nodeFromAgent(agents.get(id))),
      ["herdmaster", "fred", "ledger", "beacon"].map((id) => nodeFromAgent(agents.get(id))),
      [
        { id: "supabase", name: "Supabase", type: "system", state: "Source of truth" },
        { id: "chatwoot", name: "Chatwoot", type: "system", state: "Conversations" },
        { id: "telegram", name: "Telegram", type: "system", state: "Owner control" },
      ],
    ];
    elements.map.innerHTML = tiers.map((tier) => `<div class="map-tier">${tier.filter(Boolean).map(mapNode).join("")}</div>`).join("")
      + '<p class="map-caption">Lines show control flow by tier. Click an agent node to inspect evidence; external systems remain read-only here.</p>';
    elements.map.querySelectorAll("[data-agent-id]").forEach((button) => {
      button.addEventListener("click", () => selectAgent(button.dataset.agentId));
    });
  }

  function nodeFromAgent(agent) {
    if (!agent) return null;
    return { id: agent.id, name: agent.name, type: agent.id === "charlie-core" ? "command" : "agent", state: title(agent.stage), measured: agent.evidence?.measured };
  }

  function mapNode(node) {
    const isAgent = node.type === "agent" || node.type === "command";
    const tag = isAgent ? "button" : "div";
    const active = node.id === state.selectedId ? " active" : "";
    const data = isAgent ? ` data-agent-id="${esc(node.id)}"` : "";
    return `<${tag} class="map-node ${esc(node.type)}${active}"${data} title="${esc(node.state || "")}">
      ${isAgent ? `<span class="node-indicator ${node.measured ? "measured" : ""}"></span>` : ""}
      <span class="node-name">${esc(node.name)}</span><span class="node-state">${esc(node.state || "Connected")}</span>
    </${tag}>`;
  }

  function renderDetail() {
    const agent = (state.packet.agents || []).find((item) => item.id === state.selectedId);
    if (!agent) {
      elements.detail.innerHTML = '<div class="empty">Select an agent to inspect training and trust.</div>';
      return;
    }
    const evidence = agent.evidence || {};
    const measured = evidence.measured && evidence.progress_percent != null;
    const portrait = agent.portrait
      ? `<img class="agent-avatar" src="${esc(agent.portrait)}" alt="">`
      : `<span class="agent-avatar fallback">${esc(initials(agent.name))}</span>`;
    elements.detailState.textContent = title(agent.stage);
    elements.detail.innerHTML = `
      <div class="detail-hero">${portrait}<div><h3 class="detail-name">${esc(agent.name)}</h3><p class="detail-role">${esc(agent.role)}</p></div></div>
      <div class="stage-row"><span class="stage-pill ${agent.candidate_count ? "candidate" : ""}">${esc(title(agent.stage))}</span><span class="stage-pill">Trust: ${esc(agent.trust_tier || "watch")}</span></div>
      <section class="evidence-block">
        <h4 class="section-label">Evidence progress</h4>
        <div class="large-score"><strong>${measured ? `${Math.round(evidence.progress_percent)}%` : "--"}</strong><span>${esc(evidence.label || "Not measured")}</span></div>
        <div class="progress-track"><span style="width:${measured ? clamp(evidence.progress_percent) : 0}%"></span></div>
        <div class="metric-grid">${(agent.metrics || []).map(metricCard).join("") || '<div class="metric"><div class="metric-label">No metrics reported</div></div>'}</div>
      </section>
      ${replyClasses(agent)}
      <section class="evidence-block"><h4 class="section-label">Current attention</h4>${attention(agent)}</section>
      <section class="evidence-block"><h4 class="section-label">Owner action</h4><div class="authority"><strong>${esc(agent.owner_action || "No action required")}</strong></div></section>
      <section class="evidence-block"><h4 class="section-label">Authority boundary</h4><div class="authority">${esc(agent.authority_boundary)}</div></section>`;
  }

  function metricCard(metric) {
    let value = metric.value;
    let target = metric.target;
    if (metric.kind === "rate") { value = pct(value); target = target == null ? null : pct(target); }
    return `<div class="metric" title="${target == null ? "Observed value" : `Target: ${esc(target)}`}"><div class="metric-value">${esc(value)}</div><div class="metric-label">${esc(metric.label)}${target == null ? "" : ` · target ${esc(target)}`}</div></div>`;
  }

  function replyClasses(agent) {
    const rows = agent.reply_classes || [];
    if (!rows.length) return "";
    return `<section class="evidence-block"><h4 class="section-label">Reply-class graduation</h4><div class="reply-list">${rows.map((row) => `
      <div class="reply-row" title="A class becomes a candidate after 20 consecutive safe accepted replies and at least 80% unchanged.">
        <div class="reply-top"><span>${esc(title(row.name))}</span><span>${row.candidate ? "Candidate" : `${pct(row.unchanged_rate)} unchanged`}</span></div>
        <div class="reply-meta">${esc(row.events)} reviewed · ${esc(row.safe_streak)} safe streak</div>
      </div>`).join("")}</div></section>`;
  }

  function attention(agent) {
    const blockers = agent.blockers || [];
    if (!blockers.length) return '<div class="authority">No current blocker reported.</div>';
    return blockers.map((blocker) => `<div class="attention">${esc(blocker)}</div>`).join("");
  }

  function renderFooter() {
    const sources = state.packet.sources || {};
    const sourceText = Object.entries(sources).map(([name, source]) => `<span><strong>${esc(title(name))}</strong> ${Number(source.status_code) < 400 ? "live" : "unavailable"}</span>`).join("");
    elements.footer.innerHTML = sourceText + `<span><strong>Authority</strong> owner activation required</span>`;
  }

  function selectAgent(id) {
    if (!id || id === state.selectedId) return;
    state.selectedId = id;
    renderRoster();
    renderMap();
    renderDetail();
  }

  function initials(name) {
    return String(name || "AI").split(/\s+/).slice(0, 2).map((word) => word[0]).join("").toUpperCase();
  }

  elements.refresh.addEventListener("click", () => fetchPacket(true));
  document.addEventListener("visibilitychange", () => { if (!document.hidden) fetchPacket(); });
  window.setInterval(() => { if (!document.hidden) fetchPacket(); }, 30000);
  fetchPacket();
})();
