(function () {
  const state = {
    missions: [],
    counts: {},
    loading: false,
  };

  const els = {
    statusLine: document.getElementById("charlie_status_line"),
    message: document.getElementById("charlie_message"),
    list: document.getElementById("charlie_mission_list"),
    refresh: document.getElementById("charlie_refresh"),
    filter: document.getElementById("charlie_status_filter"),
    loadedAt: document.getElementById("charlie_loaded_at"),
    counts: {
      new: document.getElementById("charlie_count_new"),
      approved: document.getElementById("charlie_count_approved"),
      in_progress: document.getElementById("charlie_count_in_progress"),
      blocked: document.getElementById("charlie_count_blocked"),
    },
  };

  function setMessage(text, type) {
    if (!els.message) return;
    els.message.textContent = text || "";
    els.message.classList.toggle("hidden", !text);
    els.message.dataset.type = type || "info";
  }

  function safeText(value) {
    return String(value == null ? "" : value);
  }

  function formatDate(value) {
    if (!value) return "unknown";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? safeText(value) : date.toLocaleString();
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options || {});
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      throw new Error(`Server returned ${response.status} without JSON.`);
    }
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.status || data.error || `Request failed (${response.status})`);
    }
    return data;
  }

  async function loadMissions() {
    if (state.loading) return;
    state.loading = true;
    setMessage("", "info");
    const status = els.filter ? els.filter.value : "";
    const query = status ? `?status=${encodeURIComponent(status)}&limit=30` : "?limit=30";
    try {
      const [summary, missions] = await Promise.all([
        fetchJson("/api/charlie/build-relay/missions/summary"),
        fetchJson(`/api/charlie/build-relay/missions${query}`),
      ]);
      state.missions = missions.missions || [];
      state.counts = summary.counts || {};
      render();
    } catch (error) {
      setMessage(error.message || "Could not load CHARLIE missions.", "error");
      if (els.statusLine) els.statusLine.textContent = "Mission queue unavailable.";
    } finally {
      state.loading = false;
    }
  }

  function render() {
    if (els.statusLine) {
      els.statusLine.textContent = `${state.missions.length} mission records loaded. Decisions here update mission state only.`;
    }
    Object.keys(els.counts).forEach((key) => {
      if (els.counts[key]) els.counts[key].textContent = state.counts[key] || 0;
    });
    if (els.loadedAt) els.loadedAt.textContent = `Loaded ${new Date().toLocaleTimeString()}`;
    if (!els.list) return;
    if (!state.missions.length) {
      els.list.innerHTML = '<p class="charlie-empty">No missions found for this filter.</p>';
      return;
    }
    els.list.innerHTML = "";
    state.missions.forEach((mission) => {
      els.list.appendChild(missionCard(mission));
    });
  }

  function missionCard(mission) {
    const card = document.createElement("article");
    card.className = "charlie-mission-card";
    const missionId = safeText(mission.mission_id);
    const title = safeText(mission.title || mission.raw_text || "Untitled mission");
    card.innerHTML = `
      <div class="charlie-mission-card-header">
        <div>
          <span class="status-pill">${safeText(mission.status || "unknown")}</span>
          <h3>${escapeHtml(title)}</h3>
        </div>
        <code>${escapeHtml(shortId(missionId))}</code>
      </div>
      <p>${escapeHtml(safeText(mission.raw_text || title)).slice(0, 280)}</p>
      <dl class="charlie-mission-meta">
        <div><dt>Urgency</dt><dd>${escapeHtml(safeText(mission.urgency || "--"))}</dd></div>
        <div><dt>Type</dt><dd>${escapeHtml(safeText(mission.mission_type || "--"))}</dd></div>
        <div><dt>Approval</dt><dd>${escapeHtml(safeText(mission.approval_level || "--"))}</dd></div>
        <div><dt>Updated</dt><dd>${escapeHtml(formatDate(mission.updated_at))}</dd></div>
      </dl>
      <div class="charlie-mission-actions">
        <button type="button" data-action="approved">Approve</button>
        <button type="button" data-action="paused">Pause</button>
        <button type="button" data-action="rejected">Reject</button>
        <button type="button" data-action="blocked">Block</button>
        <button type="button" data-action="done">Done</button>
      </div>
      <details>
        <summary>Technical details</summary>
        <pre>${escapeHtml(JSON.stringify(mission, null, 2))}</pre>
      </details>
    `;
    card.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", () => recordDecision(missionId, button.dataset.action));
    });
    return card;
  }

  async function recordDecision(missionId, status) {
    if (!missionId || !status) return;
    setMessage(`Recording ${status}...`, "info");
    try {
      await fetchJson(`/api/charlie/build-relay/missions/${encodeURIComponent(missionId)}/decision`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          status,
          owner_decision: `Owner set mission status to ${status} from CHARLIE Mission Control.`,
        }),
      });
      setMessage(`Mission marked ${status}.`, "success");
      await loadMissions();
    } catch (error) {
      setMessage(error.message || "Decision was not recorded.", "error");
    }
  }

  function shortId(value) {
    return value ? value.slice(-8) : "no-id";
  }

  function escapeHtml(value) {
    return safeText(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  if (els.refresh) els.refresh.addEventListener("click", loadMissions);
  if (els.filter) els.filter.addEventListener("change", loadMissions);
  loadMissions();
})();
