(function () {
  "use strict";

  const API = {
    commandCenter: "/api/charlie/build-relay/command-center",
    missionControl: "/api/charlie/build-relay/mission-control",
    runner: "/api/charlie/build-relay/runner/status",
    policy: "/api/charlie/build-relay/policy",
    missions: "/api/charlie/build-relay/missions",
    summary: "/api/charlie/build-relay/missions/summary",
  };

  const tabs = [
    { id: "active", label: "Active", statuses: ["in_progress", "release_in_progress"] },
    { id: "new", label: "New", statuses: ["new"] },
    { id: "approved", label: "Approved", statuses: ["approved"] },
    { id: "review", label: "Review", statuses: ["pr_ready", "release_approved"] },
    { id: "blocked", label: "Blocked", statuses: ["blocked"] },
    { id: "done", label: "Done", statuses: ["done", "merged", "deployed"] },
  ];

  const state = {
    buckets: {},
    counts: {},
    runner: null,
    policy: null,
    activeTab: "active",
    selectedId: "",
    lastUpdated: null,
    polling: true,
    loading: false,
    initialized: false,
  };

  const el = {
    runnerChip: document.getElementById("runnerChip"),
    telegramChip: document.getElementById("telegramChip"),
    lastUpdatedChip: document.getElementById("lastUpdatedChip"),
    refreshBtn: document.getElementById("refreshBtn"),
    queueRefreshBtn: document.getElementById("queueRefreshBtn"),
    newMissionBtn: document.getElementById("newMissionBtn"),
    tabs: document.getElementById("tabs"),
    queueList: document.getElementById("queueList"),
    workflowSub: document.getElementById("workflowSub"),
    selectedStatusChip: document.getElementById("selectedStatusChip"),
    workflowPanel: document.getElementById("workflowPanel"),
    actionPanel: document.getElementById("actionPanel"),
    systemStrip: document.getElementById("systemStrip"),
    missionSummaryStrip: document.getElementById("missionSummaryStrip"),
    queueHealthChip: document.getElementById("queueHealthChip"),
    activeAgentChip: document.getElementById("activeAgentChip"),
    newMissionDrawer: document.getElementById("newMissionDrawer"),
    newMissionForm: document.getElementById("newMissionForm"),
    newMissionResult: document.getElementById("newMissionResult"),
    reviewDrawer: document.getElementById("reviewDrawer"),
    reviewDrawerTitle: document.getElementById("reviewDrawerTitle"),
    reviewDrawerBody: document.getElementById("reviewDrawerBody"),
  };

  function text(value, fallback = "") {
    const result = String(value == null ? "" : value).trim();
    return result || fallback;
  }

  function shortId(mission) {
    const id = text(mission.mission_id, "MISSION");
    return id.length > 14 ? id.slice(-12) : id;
  }

  function titleOf(mission) {
    return text(mission.title, text(mission.raw_text, text(mission.mission_id, "Untitled mission"))).slice(0, 140);
  }

  function statusClass(status) {
    return `status-${text(status, "unknown").replace(/[^a-z0-9_]+/gi, "_")}`;
  }

  function chipClass(status) {
    const value = text(status).toLowerCase();
    if (["done", "merged", "deployed"].includes(value)) return "green";
    if (["blocked", "rejected"].includes(value)) return "red";
    if (["pr_ready", "release_approved"].includes(value)) return "purple";
    if (["approved", "new", "paused"].includes(value)) return "amber";
    if (["in_progress", "release_in_progress"].includes(value)) return "green";
    return "";
  }

  function missionReviewPacket(mission) {
    const metadata = mission && typeof mission.metadata === "object" ? mission.metadata : {};
    return metadata && typeof metadata.review_packet === "object" ? metadata.review_packet : {};
  }

  function missionGovernance(mission) {
    const metadata = mission && mission.metadata && typeof mission.metadata === "object" ? mission.metadata : {};
    return metadata.mission_governance && typeof metadata.mission_governance === "object" ? metadata.mission_governance : {};
  }

  function missionFamily(mission) {
    const metadata = mission && mission.metadata && typeof mission.metadata === "object" ? mission.metadata : {};
    return metadata.mission_family && typeof metadata.mission_family === "object" ? metadata.mission_family : {};
  }

  function familyOrdered(missions) {
    const rows = Array.from(missions || []);
    const byId = new Map(rows.map((mission) => [mission.mission_id, mission]));
    return rows.sort((left, right) => {
      const leftFamily = missionFamily(left);
      const rightFamily = missionFamily(right);
      const leftRoot = leftFamily.root_mission_id || left.mission_id;
      const rightRoot = rightFamily.root_mission_id || right.mission_id;
      if (leftRoot !== rightRoot) return 0;
      if (left.mission_id === leftRoot) return -1;
      if (right.mission_id === rightRoot) return 1;
      return Number(leftFamily.sequence || 999) - Number(rightFamily.sequence || 999);
    });
  }

  function progressPct(mission) {
    const missionStatus = text(mission.status).toLowerCase();
    if (["done", "merged", "deployed", "pr_ready", "release_approved"].includes(missionStatus)) return 100;
    const workflow = Array.isArray(mission.agent_workflow) ? mission.agent_workflow : [];
    if (!workflow.length) {
      if (["done", "merged", "deployed"].includes(text(mission.status).toLowerCase())) return 100;
      if (text(mission.status).toLowerCase() === "pr_ready") return 100;
      return 0;
    }
    const complete = workflow.filter((item) => {
      const status = text(item.status).toLowerCase();
      return ["complete", "completed", "done", "pass", "passed"].includes(status);
    }).length;
    const activeBonus = workflow.some((item) => ["active", "running", "in_progress"].includes(text(item.status).toLowerCase())) ? 0.4 : 0;
    return Math.max(0, Math.min(100, Math.round(((complete + activeBonus) / workflow.length) * 100)));
  }

  function missionTelemetry(mission) {
    const metadata = mission && mission.metadata && typeof mission.metadata === "object" ? mission.metadata : {};
    const memory = metadata.mission_memory && typeof metadata.mission_memory === "object" ? metadata.mission_memory : {};
    return memory.telemetry && typeof memory.telemetry === "object" ? memory.telemetry : {};
  }

  function stageTelemetry(mission) {
    const metadata = mission && mission.metadata && typeof mission.metadata === "object" ? mission.metadata : {};
    return metadata.stage_telemetry && typeof metadata.stage_telemetry === "object" ? metadata.stage_telemetry : { stages: [] };
  }

  function ownerActionGuidance(mission) {
    const metadata = mission && mission.metadata && typeof mission.metadata === "object" ? mission.metadata : {};
    return metadata.owner_action_guidance && typeof metadata.owner_action_guidance === "object" ? metadata.owner_action_guidance : {};
  }

  function formatDuration(seconds) {
    const value = Math.max(0, Number(seconds || 0));
    if (!value) return "--";
    if (value < 60) return `${Math.round(value)}s`;
    const minutes = Math.floor(value / 60);
    const remainder = Math.floor(value % 60);
    if (minutes < 60) return `${minutes}m ${String(remainder).padStart(2, "0")}s`;
    return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  }

  function stageRuntime(row) {
    if (Number(row && row.duration_seconds) > 0) return Number(row.duration_seconds);
    const started = Date.parse(text(row && row.started_at));
    if (!Number.isFinite(started)) return 0;
    const status = text(row && row.status).toLowerCase();
    const endpoint = ["active", "running", "in_progress"].includes(status)
      ? Date.now()
      : Date.parse(text(row && (row.completed_at || row.updated_at)));
    return Number.isFinite(endpoint) ? Math.max(0, Math.round((endpoint - started) / 1000)) : 0;
  }

  function stageTelemetryRow(mission, agent) {
    const rows = Array.isArray(stageTelemetry(mission).stages) ? stageTelemetry(mission).stages : [];
    return rows.find((row) => text(row.agent).toLowerCase() === text(agent).toLowerCase()) || {};
  }

  function stageLabel(mission) {
    const review = missionReviewPacket(mission);
    const status = text(mission.status).toLowerCase();
    if (status === "blocked") return text(review.blocked_agent, text(mission.vault && mission.vault.mission_stage, "blocked"));
    if (status === "pr_ready") return "owner review";
    if (status === "approved") return "waiting runner";
    if (status === "new") return "needs approval";
    const workflow = Array.isArray(mission.agent_workflow) ? mission.agent_workflow : [];
    const active = workflow.find((item) => ["active", "running", "in_progress"].includes(text(item.status).toLowerCase()));
    return text(active && active.agent, text(mission.vault && mission.vault.current_agent, text(mission.vault && mission.vault.mission_stage, status || "not started")));
  }

  function headlineReason(mission) {
    const review = missionReviewPacket(mission);
    return text(
      review.blocked_reason,
      text(review.recommended_next_action, text(mission.selected_next_step, text(mission.owner_decision, text(mission.raw_text, ""))))
    ).slice(0, 170);
  }

  function allLoadedMissions() {
    const map = new Map();
    Object.values(state.buckets).flat().forEach((mission) => {
      if (mission && mission.mission_id) map.set(mission.mission_id, mission);
    });
    return Array.from(map.values());
  }

  function selectedMission() {
    return allLoadedMissions().find((mission) => mission.mission_id === state.selectedId) || null;
  }

  async function fetchJson(url, options) {
    const timeoutMs = Number((options && options.timeoutMs) || 10000);
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    const requestOptions = { ...(options || {}) };
    delete requestOptions.timeoutMs;
    let response;
    try {
      response = await fetch(url, { credentials: "same-origin", signal: controller.signal, ...requestOptions });
    } finally {
      window.clearTimeout(timer);
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.status || `HTTP ${response.status}`);
      error.data = data;
      error.status = response.status;
      throw error;
    }
    return data;
  }

  async function refreshAll() {
    if (state.loading) return;
    state.loading = true;
    try {
      el.refreshBtn.disabled = true;
      el.queueRefreshBtn.disabled = true;
      const runnerPromise = fetchJson(API.runner, { timeoutMs: 18000 }).then((runner) => {
        state.runner = runner;
        if (state.initialized) {
          renderHeader();
          renderActionPanel();
          renderStrip();
        }
      }).catch(() => null);
      const [snapshot, policy] = await Promise.all([
        fetchJson(API.missionControl, { timeoutMs: 18000 }).catch(() => null),
        fetchJson(API.policy, { timeoutMs: 18000 }).catch(() => ({ charlie_build_relay: state.policy || {} })),
      ]);
      if (snapshot && snapshot.counts) state.counts = snapshot.counts;
      if (snapshot && snapshot.buckets) state.buckets = mergeBuckets(state.buckets, snapshot.buckets);
      state.policy = policy.charlie_build_relay || {};
      if (!state.initialized && !(state.buckets[state.activeTab] || []).length) {
        const usefulTab = firstUsefulTab();
        if (usefulTab !== state.activeTab) {
          state.activeTab = usefulTab;
        }
      }
      state.lastUpdated = new Date();
      ensureSelection();
      state.initialized = true;
      render();
      void runnerPromise;
    } catch (error) {
      renderError(error);
    } finally {
      state.loading = false;
      el.refreshBtn.disabled = false;
      el.queueRefreshBtn.disabled = false;
    }
  }

  async function loadMissionBuckets() {
    const plan = {
      active: ["in_progress", "release_in_progress"],
      new: ["new"],
      approved: ["approved"],
      review: ["pr_ready", "release_approved"],
      blocked: ["blocked"],
      done: [],
    };
    const loaded = {};
    await Promise.all(Object.entries(plan).map(async ([key, statuses]) => {
      if (!statuses.length) {
        loaded[key] = state.buckets[key] || [];
        return;
      }
      const missions = [];
      const results = await Promise.allSettled(statuses.map((status) => (
        fetchJson(`${API.missions}?status=${encodeURIComponent(status)}&compact=1&limit=30`, { timeoutMs: 18000 })
      )));
      let fulfilled = 0;
      results.forEach((result) => {
        if (result.status === "fulfilled") {
          fulfilled += 1;
          missions.push(...(result.value.missions || []));
        }
      });
      loaded[key] = fulfilled ? dedupe(missions) : (state.buckets[key] || []);
    }));
    return loaded;
  }

  function mergeBuckets(current, incoming) {
    const merged = { ...(current || {}) };
    Object.entries(incoming || {}).forEach(([key, value]) => {
      if (Array.isArray(value)) merged[key] = value;
    });
    return merged;
  }

  function applyCommandCenter(command) {
    state.counts = command.counts || {};
  }

  async function refreshTab(tabId) {
    const tab = tabs.find((item) => item.id === tabId);
    if (!tab) return;
    const results = await Promise.all(tab.statuses.map((status) => (
      fetchJson(`${API.missions}?status=${encodeURIComponent(status)}&compact=1&limit=30`, { timeoutMs: 18000 })
    )));
    const loaded = results.flatMap((data) => data.missions || []);
    state.buckets[tabId] = dedupe(loaded);
  }

  function filterStatuses(missions, statuses) {
    const allowed = new Set(statuses);
    return (missions || []).filter((mission) => allowed.has(text(mission.status).toLowerCase()));
  }

  async function ensureTabLoaded(tabId) {
    const tab = tabs.find((item) => item.id === tabId);
    if (!tab || (state.buckets[tabId] && state.buckets[tabId].length)) return;
    await refreshTab(tabId);
  }

  function dedupe(missions) {
    const map = new Map();
    (missions || []).forEach((mission) => {
      if (mission && mission.mission_id) map.set(mission.mission_id, mission);
    });
    return Array.from(map.values());
  }

  function ensureSelection() {
    const activeList = state.buckets[state.activeTab] || [];
    if (selectedMission() && activeList.some((mission) => mission.mission_id === state.selectedId)) return;
    const order = activeList.length ? [state.activeTab, "blocked", "review", "new", "approved", "active", "done"] : ["blocked", "review", "new", "approved", "active", "done"];
    for (const key of order) {
      const mission = (state.buckets[key] || [])[0];
      if (mission) {
        state.activeTab = key;
        state.selectedId = mission.mission_id;
        return;
      }
    }
    state.selectedId = "";
  }

  function render() {
    renderHeader();
    renderMissionSummary();
    renderTabs();
    renderQueue();
    renderWorkflow();
    renderActionPanel();
    renderStrip();
  }

  function firstUsefulTab() {
    const preference = ["blocked", "review", "active", "new", "approved", "done"];
    return preference.find((tabId) => countForTab(tabs.find((tab) => tab.id === tabId)) > 0) || "active";
  }

  function renderMissionSummary() {
    const mission = selectedMission();
    const activeCount = Number(state.counts.in_progress || 0) + Number(state.counts.release_in_progress || 0);
    const reviewCount = Number(state.counts.pr_ready || 0) + Number(state.counts.release_approved || 0);
    const blockedCount = Number(state.counts.blocked || 0);
    const approvedCount = Number(state.counts.approved || 0);
    const currentAgent = mission ? stageLabel(mission) : (activeCount ? "Loading active mission" : "None");
    const items = [
      ["Active", activeCount, currentAgent],
      ["Approved queue", approvedCount, approvedCount ? "waiting for runner" : "queue clear"],
      ["Owner review", reviewCount, reviewCount ? "decision required" : "no review backlog"],
      ["Blocked", blockedCount, blockedCount ? "attention required" : "no blocked missions"],
      ["Selected progress", mission ? `${progressPct(mission)}%` : "--", mission ? titleOf(mission) : "no mission selected"],
    ];
    el.missionSummaryStrip.innerHTML = items.map(([label, value, note]) => `<div class="summary-item" title="${escapeAttr(note)}">
      <div class="summary-label">${escapeHtml(label)}</div><div class="summary-value">${escapeHtml(value)}</div><div class="summary-note">${escapeHtml(note)}</div>
    </div>`).join("");
    el.queueHealthChip.className = `chip ${blockedCount ? "red" : reviewCount ? "purple" : "green"}`;
    el.queueHealthChip.textContent = blockedCount ? `${blockedCount} blocked` : reviewCount ? `${reviewCount} review` : "Queue healthy";
    el.activeAgentChip.className = `chip ${mission && ["blocked"].includes(text(mission.status).toLowerCase()) ? "red" : mission ? "green" : ""}`;
    el.activeAgentChip.textContent = mission ? cleanAgentName(stageLabel(mission)) : "No agent";
  }

  function renderHeader() {
    const runner = state.runner || {};
    const local = runner.local_runner || {};
    const scope = text(runner.local_runner_scope);
    let cls = "amber";
    let label = "Runner unknown";
    if (scope === "render_cannot_see_laptop_runner") {
      label = runner.active_mission
        ? `DB active: ${shortId(runner.active_mission)}`
        : "Laptop runner hidden from Render";
    } else if (local.active) {
      cls = "green";
      label = `${operatingStateLabel(local.operating_state)} | ${text(local.age_seconds, "0")}s`;
    } else if (local.status) {
      cls = "red";
      label = "Runner stale/off";
    }
    if (local.notify_failing) {
      cls = "red";
      label = "Telegram notify failing";
    }
    el.runnerChip.className = `chip ${cls}`;
    el.runnerChip.innerHTML = `<span class="dot"></span>${escapeHtml(label)}`;

    const policy = state.policy || {};
    el.telegramChip.className = `chip ${policy.enabled ? "green" : "amber"}`;
    el.telegramChip.innerHTML = `<span class="dot"></span>${policy.enabled ? "Telegram ready" : "Telegram check"}`;
    el.lastUpdatedChip.textContent = state.lastUpdated ? `Last update ${state.lastUpdated.toLocaleTimeString()}` : "Last update --";
  }

  function renderTabs() {
    el.tabs.innerHTML = tabs.map((tab) => {
      const count = countForTab(tab);
      return `<button class="tab ${state.activeTab === tab.id ? "active" : ""}" data-tab="${tab.id}">
        ${escapeHtml(tab.label)} <b>${count}</b>
      </button>`;
    }).join("");
  }

  function countForTab(tab) {
    if (!tab) return 0;
    if (state.buckets[tab.id]) return state.buckets[tab.id].length;
    return tab.statuses.reduce((total, status) => total + Number(state.counts[status] || 0), 0);
  }

  function renderQueue() {
    const missions = familyOrdered(dedupe(state.buckets[state.activeTab] || []));
    if (!missions.length) {
      el.queueList.innerHTML = `<div class="notice">No ${escapeHtml(state.activeTab)} missions are visible. Use another tab or create a mission.</div>`;
      return;
    }
    el.queueList.innerHTML = missions.map((mission) => {
      const status = text(mission.status, "unknown");
      const pct = progressPct(mission);
      const governance = missionGovernance(mission);
      const family = missionFamily(mission);
      const telemetry = missionTelemetry(mission);
      const matrixCounts = governance.acceptance_counts || {};
      const familyLabel = family.parent_mission_id ? `Follow-up ${family.sequence || ""}` : "";
      return `<button class="mission-card ${statusClass(status)} ${mission.mission_id === state.selectedId ? "selected" : ""}" data-select="${escapeAttr(mission.mission_id)}">
        <div class="mission-card-title">${familyLabel ? `<span class="family-tag">${escapeHtml(familyLabel)}</span>` : ""}${escapeHtml(titleOf(mission))}</div>
        <div class="mission-card-meta">
          <span>${escapeHtml(shortId(mission))} | ${escapeHtml(text(mission.approval_level, "LEVEL ?"))}</span>
          <span class="chip ${chipClass(status)}">${escapeHtml(statusLabel(status))}</span>
        </div>
        <div class="bar"><span style="width:${pct}%"></span></div>
        <div class="mission-card-meta">
          <span>${pct}%</span>
          <span>${escapeHtml(stageLabel(mission))}</span>
        </div>
        <div class="mission-card-runs">Matrix ${Number(matrixCounts.passed || 0)}/${Number(matrixCounts.passed || 0) + Number(matrixCounts.failed || 0) + Number(matrixCounts.pending || 0)} · ${Number(governance.fix_count || 0)} fixes · ${Number(governance.review_runs || 0)} reviews${governance.cycling ? " · CYCLING" : ""}</div>
        <div class="mission-card-runs">${Number(telemetry.attempt_count || 0)} attempts | ${Number(telemetry.recovery_count || 0)} recoveries | ${Number(telemetry.backflow_count || 0)} backflows${Number(telemetry.highest_blocker_repeat || 0) >= 2 ? ` | repeat x${Number(telemetry.highest_blocker_repeat)}` : ""}</div>
        <div class="reason">${escapeHtml(headlineReason(mission) || "No reason recorded yet.")}</div>
      </button>`;
    }).join("");
  }

  function renderWorkflow() {
    const mission = selectedMission();
    if (!mission) {
      el.selectedStatusChip.className = "chip";
      el.selectedStatusChip.textContent = "No mission";
      el.workflowSub.textContent = "Queue is empty or still loading.";
      el.workflowPanel.innerHTML = `<div class="notice">No mission selected. Create or approve missions from the queue on the left.</div>`;
      return;
    }
    const status = text(mission.status, "unknown");
    const pct = progressPct(mission);
    el.selectedStatusChip.className = `chip ${chipClass(status)}`;
    el.selectedStatusChip.textContent = statusLabel(status);
    el.workflowSub.textContent = `${shortId(mission)} | ${text(mission.approval_level, "LEVEL ?")} | ${pct}%`;
    const review = missionReviewPacket(mission);
    const governance = missionGovernance(mission);
    const telemetry = missionTelemetry(mission);
    const execution = stageTelemetry(mission);
    const workflow = Array.isArray(mission.agent_workflow) ? mission.agent_workflow : [];
    const stages = workflow.length ? workflow : placeholderStages(mission);
    el.workflowPanel.innerHTML = `
      <div class="mission-hero">
        <div>
          <h2>${escapeHtml(titleOf(mission))}</h2>
          <p class="muted">${escapeHtml(text(mission.mission_type, "mission"))} | ${escapeHtml(text(mission.urgency, "P?"))}</p>
        </div>
        <span class="chip ${chipClass(status)}">${escapeHtml(statusLabel(status))}</span>
      </div>
      <div class="mission-stats">
        ${metric("Acceptance", `${Number(governance.acceptance_percent || 0)}%`)}
        ${metric("Current", stageLabel(mission))}
        ${metric("Fixes", String(Number(governance.fix_count || 0)))}
        ${metric("Review runs", String(Number(governance.review_runs || 0)))}
        ${metric("Attempts", String(Number(telemetry.attempt_count || 0)))}
        ${metric("Recoveries", String(Number(telemetry.recovery_count || 0)))}
        ${metric("Files changed", String((Array.isArray(execution.stages) ? execution.stages : []).reduce((total, row) => total + Number(row.changed_files_count || 0), 0)))}
        ${metric("Last progress", text(execution.last_progress_at, "not recorded").replace("T", " ").slice(0, 16))}
      </div>
      <div class="bar"><span style="width:${pct}%"></span></div>
      ${renderLiveActivity(mission)}
      ${renderGovernanceSummary(governance, missionFamily(mission))}
      <div class="timeline">${stages.map((stage) => renderStage(stage, mission)).join("")}</div>
      <div class="evidence">
        ${evidenceRow("Why this matters", text(review.summary, text(mission.raw_text, "No mission detail loaded.")))}
        ${evidenceRow("Next action", text(review.recommended_next_action, nextActionText(mission)))}
        ${renderTestEvidence(review)}
      </div>`;
  }

  function operatingStateLabel(value) {
    return ({
      running_agent: "Running agent",
      between_stages: "Between stages",
      waiting_for_queue: "Waiting for queue",
      stale_or_stopped: "Stale or stopped",
    })[text(value).toLowerCase()] || "Runner active";
  }

  function renderLiveActivity(mission) {
    const runner = state.runner || {};
    const local = runner.local_runner || {};
    const ledger = local.agent_ledger && typeof local.agent_ledger === "object" ? local.agent_ledger : {};
    const latest = ledger.latest_stage && typeof ledger.latest_stage === "object" ? ledger.latest_stage : {};
    const sameMission = text(local.last_mission_id) === text(mission.mission_id);
    const cloudOnly = text(runner.local_runner_scope) === "render_cannot_see_laptop_runner";
    const agent = sameMission ? text(local.current_agent, text(latest.agent, stageLabel(mission))) : stageLabel(mission);
    const action = sameMission
      ? text(local.current_action, text(latest.current_action, text(local.last_result_status, "Agent stage running")))
      : nextActionText(mission);
    const runtime = sameMission ? formatDuration(local.elapsed_seconds) : "--";
    const heartbeat = sameMission && local.last_seen
      ? `${text(local.age_seconds, "--")}s ago`
      : text(mission.updated_at, "not recorded").replace("T", " ").slice(0, 19);
    const attempts = sameMission ? Number(latest.attempt || 0) : Number(missionTelemetry(mission).attempt_count || 0);
    const files = sameMission ? Number(local.changed_files_count || (latest.changed_files || []).length || 0) : 0;
    const commands = Array.isArray(latest.commands_run) ? latest.commands_run : [];
    const stateLabel = cloudOnly
      ? "Cloud snapshot"
      : sameMission ? operatingStateLabel(local.operating_state) : statusLabel(mission.status);
    return `<section class="live-activity ${sameMission && local.active ? "live" : cloudOnly ? "snapshot" : ""}">
      <div class="live-head"><span><i></i>${escapeHtml(stateLabel)}</span><b>${escapeHtml(cleanAgentName(agent))}</b><small>${escapeHtml(heartbeat)}</small></div>
      <div class="live-grid">
        ${metric("Current action", action)}
        ${metric("Stage runtime", runtime)}
        ${metric("Attempt", attempts ? String(attempts) : "--")}
        ${metric("Files changed", files ? String(files) : "--")}
      </div>
      ${commands.length ? `<div class="live-command"><strong>Latest check</strong><span>${escapeHtml(text(commands[commands.length - 1]))}</span></div>` : ""}
      ${cloudOnly ? '<p>Render shows persisted Supabase progress. Open the local dashboard for second-by-second laptop heartbeat and commands.</p>' : ""}
    </section>`;
  }

  function renderGovernanceSummary(governance, family) {
    const matrix = Array.isArray(governance.acceptance_matrix) ? governance.acceptance_matrix : [];
    const budget = governance.budget || {};
    const children = family && Array.isArray(family.children) ? family.children : [];
    if (!matrix.length) return "";
    return `<section class="governance-block ${governance.cycling ? "cycling" : ""}">
      <div class="governance-head"><strong>Acceptance Matrix</strong><span>${Number(governance.acceptance_counts && governance.acceptance_counts.passed || 0)}/${matrix.length} passed · ${Number(governance.backflow_count || 0)}/${Number(budget.mission_limit || 4)} correction budget · ${Number(governance.followup_count || 0)} follow-ups</span></div>
      <div class="matrix-list">${matrix.map((row) => `<div class="matrix-row ${escapeAttr(text(row.status, "pending"))}" title="${escapeAttr(text(row.evidence_required, "Focused evidence required"))}"><span class="matrix-dot"></span><b>${escapeHtml(text(row.requirement, "Requirement"))}</b><span>${escapeHtml(statusLabel(row.status))}</span></div>`).join("")}</div>
      ${governance.cycling ? '<div class="cycle-note">Correction budget reached. New non-red findings become linked follow-up missions instead of reopening this parent.</div>' : ""}
      ${children.length ? `<div class="family-children"><strong>Linked follow-ups</strong>${children.map((child) => `<span>${escapeHtml(text(child.title, child.mission_id))} · ${escapeHtml(statusLabel(child.status))}</span>`).join("")}</div>` : ""}
    </section>`;
  }

  function placeholderStages(mission) {
    const status = text(mission.status).toLowerCase();
    return [
      { agent: "intake", status: ["new", "approved"].includes(status) ? "active" : "complete", findings: "Mission captured." },
      { agent: "build", status: status === "in_progress" ? "active" : "pending", findings: "Local runner executes build." },
      { agent: "review", status: status === "pr_ready" ? "active" : "pending", findings: "Owner review gate." },
      { agent: "release", status: status === "release_approved" ? "active" : "pending", findings: "Local release bridge." },
    ];
  }

  function renderStage(stage, mission) {
    const raw = text(stage.status, "pending").toLowerCase();
    let cls = "pending";
    if (["complete", "completed", "done", "pass", "passed"].includes(raw)) cls = "complete";
    if (["active", "running", "in_progress"].includes(raw)) cls = "active";
    if (raw === "blocked" || text(mission.status).toLowerCase() === "blocked" && text(stage.agent).toLowerCase() === text(stageLabel(mission)).toLowerCase()) cls = "blocked";
    if (text(mission.status).toLowerCase() === "pr_ready" && text(stage.agent).toLowerCase().includes("review")) cls = "review";
    const telemetry = stageTelemetryRow(mission, stage.agent);
    const attempt = Number(telemetry.attempt || 0);
    const runtime = formatDuration(stageRuntime({ ...telemetry, status: raw }));
    const files = Number(telemetry.changed_files_count || 0);
    return `<div class="stage ${cls}" title="${escapeAttr(text(telemetry.current_action, text(stage.findings, "No findings yet.")))}">
      <div>
        <div class="stage-name">${escapeHtml(cleanAgentName(stage.agent))}</div>
        <div class="stage-state">${escapeHtml(raw || "pending")}</div>
      </div>
      <div class="stage-telemetry">${attempt ? `Try ${attempt}` : "Not run"} | ${runtime}${files ? ` | ${files} files` : ""}</div>
      <div class="muted">${escapeHtml(text(stage.findings, "No findings yet.").slice(0, 130))}</div>
    </div>`;
  }

  function renderActionPanel() {
    const mission = selectedMission();
    if (!mission) {
      el.actionPanel.innerHTML = runnerBox();
      return;
    }
    const status = text(mission.status, "unknown").toLowerCase();
    const review = missionReviewPacket(mission);
    const governance = missionGovernance(mission);
    const family = missionFamily(mission);
    const telemetry = missionTelemetry(mission);
    const guidance = ownerActionGuidance(mission);
    el.actionPanel.innerHTML = `
      <div class="summary-block">
        <h3 class="summary-title">${escapeHtml(titleOf(mission))}</h3>
        ${field("Mission", `${shortId(mission)} | ${text(mission.approval_level, "LEVEL ?")}`)}
        ${field("State", `${statusLabel(status)} | ${stageLabel(mission)} | ${progressPct(mission)}%`)}
        ${field("Delivery", `${Number(governance.acceptance_percent || 0)}% matrix | ${Number(governance.fix_count || 0)} fixes | ${Number(governance.review_runs || 0)} reviews`)}
        ${field("Runtime history", `${Number(telemetry.execution_session_count || 0)} sessions | ${Number(telemetry.attempt_count || 0)} attempts | ${Number(telemetry.backflow_count || 0)} backflows | ${Number(telemetry.recovery_count || 0)} recoveries`)}
        ${Number(telemetry.highest_blocker_repeat || 0) >= 2 ? field("Repeated blocker", `x${Number(telemetry.highest_blocker_repeat)} | ${text(telemetry.last_restart_reason, "internal recovery capped")}`) : ""}
        ${family.parent_mission_id ? field("Mission family", `Child of ${family.parent_mission_id} | ${text(family.finding_family, "follow-up")}`) : field("Discovered work", `${Number(governance.followup_count || 0)} linked follow-ups`)}
        ${field("Reason", headlineReason(mission) || "No reason recorded.")}
        ${renderOwnerGuidance(mission, guidance)}
        ${actionButtons(mission)}
        ${runnerBox()}
        <details class="disclosure"><summary>Mission brief and review context</summary><div>${field("Brief", text(review.summary, text(mission.raw_text, "No brief loaded.")))}</div></details>
      </div>`;
  }

  function renderOwnerGuidance(mission, guidance) {
    if (text(mission.status).toLowerCase() !== "blocked" || !text(guidance.recommended_action)) return "";
    return `<section class="decision-guidance">
      <span>Recommended action</span>
      <strong>${escapeHtml(text(guidance.button_label, "Review mission"))}</strong>
      ${guidance.target_stage ? `<b>Target: ${escapeHtml(cleanAgentName(guidance.target_stage))}</b>` : ""}
      <p>${escapeHtml(text(guidance.reason, "CORE recorded no decision explanation."))}</p>
      <small>${escapeHtml(text(guidance.what_happens, "Mission evidence is preserved."))}</small>
    </section>`;
  }

  function actionButtons(mission) {
    const status = text(mission.status).toLowerCase();
    if (status === "new") {
      return `<div class="button-grid">
        <button class="primary ok" data-decision="approved">Approve</button>
        <button class="warn" data-decision="paused">Pause</button>
        <button class="danger wide" data-decision="rejected">Reject</button>
      </div>`;
    }
    if (status === "blocked") {
      const guidance = ownerActionGuidance(mission);
      const sendBack = text(guidance.recommended_action) === "send_back";
      const primary = sendBack
        ? `<button class="primary ok wide" data-review-decision="send_back">${escapeHtml(text(guidance.button_label, "Send Back"))}</button>`
        : `<button class="primary ok wide" data-decision="approved">${escapeHtml(text(guidance.button_label, "Approve Rerun"))}</button>`;
      return `${primary}<details class="disclosure alternatives"><summary>Alternative actions</summary><div class="button-grid">
        ${sendBack ? '<button class="warn wide" data-decision="approved">Approve Rerun Instead</button>' : '<button class="warn wide" data-review-decision="send_back">Choose Agent and Send Back</button>'}
        <button class="warn" data-decision="paused">Pause</button>
        <button class="danger" data-decision="rejected">Reject</button>
      </div></details>`;
    }
    if (status === "pr_ready") {
      return `<div class="button-grid">
        <button class="primary wide" data-open-review>Open Review</button>
        <button class="ok" data-review-decision="approve_final_release">Approve Final</button>
        <button class="warn" data-review-decision="send_back">Send Back</button>
        <button class="danger" data-review-decision="reject">Reject</button>
      </div>`;
    }
    if (status === "approved") {
      return `<div class="notice">Approved and waiting for the local runner. Start the runner if it is stale.</div>`;
    }
    if (status === "in_progress" || status === "release_in_progress") {
      return `<div class="notice">Observe only while the local runner is executing. Do not change mission state mid-run.</div>`;
    }
    if (status === "release_approved") {
      return `<div class="notice">Final approval is recorded. The local release bridge handles merge/release evidence.</div>`;
    }
    return `<div class="notice">No owner action is needed for this status.</div>`;
  }

  function runnerBox() {
    const runner = state.runner || {};
    const local = runner.local_runner || {};
    const scope = text(runner.local_runner_scope);
    const command = text(runner.local_runner_command, ".\\venv\\Scripts\\python.exe scripts\\charlie_mission_pickup.py --watch --continuous --notify --execute-codex --watch-release --auto-merge-pr --interval-seconds 30");
    const activeMission = runner.active_mission || {};
    const label = scope === "render_cannot_see_laptop_runner"
      ? (activeMission.mission_id ? `Cloud sees active mission ${shortId(activeMission)}` : "Cloud cannot see the laptop runner")
      : (local.active ? `${operatingStateLabel(local.operating_state)} (${text(local.age_seconds, "0")}s heartbeat)` : "Stale/off");
    const visibility = scope === "render_cannot_see_laptop_runner"
      ? "Render can read mission status from Supabase, but it cannot see the local laptop process heartbeat. Use the local status command for runner truth."
      : text(runner.local_runner_visibility_note, "Local runner heartbeat is visible here.");
    return `<details class="disclosure"><summary>Runner · ${escapeHtml(label)}</summary><div>
      <div class="field"><span class="muted">${escapeHtml(visibility)}</span><span class="muted">${escapeHtml(text(runner.next_action, text(local.next_action, "Start local runner before expecting approved missions to run.")))}</span><code>${escapeHtml(command)}</code><button data-copy-command="${escapeAttr(command)}">Copy Runner Command</button></div>
    </div></details>`;
  }

  function renderStrip() {
    const runner = state.runner || {};
    const local = runner.local_runner || {};
    const policy = state.policy || {};
    const activeLabel = runner.local_runner_scope === "render_cannot_see_laptop_runner"
      ? (runner.active_mission ? "DB active, laptop hidden" : "Laptop hidden")
      : (local.active ? operatingStateLabel(local.operating_state) : "Stale/off");
    el.systemStrip.innerHTML = [
      strip("Queue", `New ${(state.buckets.new || []).length} | Approved ${(state.buckets.approved || []).length}`),
      strip("Review", `Ready ${(state.buckets.review || []).length} | Blocked ${(state.buckets.blocked || []).length}`),
      strip("Runner", activeLabel),
      strip("Telegram", policy.enabled ? "Ready" : "Check config"),
      strip("Updated", state.lastUpdated ? state.lastUpdated.toLocaleTimeString() : "--"),
    ].join("");
  }

  function metric(label, value) {
    return `<div class="metric"><span class="muted">${escapeHtml(label)}</span><b>${escapeHtml(value)}</b></div>`;
  }

  function field(label, value) {
    return `<div class="field"><label>${escapeHtml(label)}</label><strong>${escapeHtml(value)}</strong></div>`;
  }

  function evidenceRow(label, value) {
    return `<div class="evidence-row"><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</div>`;
  }

  function renderTestEvidence(review) {
    const evidence = Array.isArray(review.test_evidence) ? review.test_evidence : [];
    if (!evidence.length) return evidenceRow("Evidence", "No test evidence is visible in the compact packet.");
    return evidence.map((item, index) => evidenceRow(`Evidence ${index + 1}`, typeof item === "string" ? item : JSON.stringify(item))).join("");
  }

  function strip(label, value) {
    return `<div class="strip-item"><span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b></div>`;
  }

  function nextActionText(mission) {
    const status = text(mission.status).toLowerCase();
    if (status === "new") return "Approve, pause, or reject.";
    if (status === "approved") return "Waiting for local runner.";
    if (status === "blocked") return "Review blocked reason, then send back or approve rerun.";
    if (status === "pr_ready") return "Open review and approve final or send back.";
    if (status === "in_progress") return "Observe local runner.";
    return "No immediate action.";
  }

  function statusLabel(status) {
    return text(status, "unknown").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function cleanAgentName(agent) {
    return text(agent, "stage").replace(/_/g, " ");
  }

  function escapeHtml(value) {
    return text(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/`/g, "&#96;");
  }

  function renderError(error) {
    const message = text(error && error.message, "Unable to load CHARLIE Mission Control.");
    if (state.initialized && allLoadedMissions().length) {
      el.lastUpdatedChip.className = "chip red";
      el.lastUpdatedChip.textContent = `Refresh failed · ${message}`;
      return;
    }
    el.queueList.innerHTML = `<div class="notice">${escapeHtml(message)}</div>`;
    el.workflowPanel.innerHTML = `<div class="notice">${escapeHtml(message)}</div>`;
    el.actionPanel.innerHTML = `<div class="notice">${escapeHtml(message)}</div>`;
  }

  async function setMissionStatus(status) {
    const mission = selectedMission();
    if (!mission) return;
    const approvalLevel = status === "approved" ? text(mission.approval_level, "LEVEL 3") : "";
    await fetchJson(`${API.missions}/${encodeURIComponent(mission.mission_id)}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status,
        approval_level: approvalLevel,
        owner_decision: `Owner set mission status to ${status} from CHARLIE Mission Control v2.`,
      }),
    });
    await refreshAll();
  }

  async function recordReviewDecision(decision, options = {}) {
    const mission = selectedMission();
    if (!mission) return;
    if (decision === "send_back" && !options.confirmed) {
      openSendBackDrawer(mission);
      return;
    }
    const targetStage = text(options.targetStage, text(stageLabel(mission), "builder"));
    const confirmed = decision === "approve_final_release"
      ? window.confirm(`Approve final review for ${titleOf(mission)}? This records owner approval; it does not run shell commands from the browser.`)
      : true;
    if (!confirmed) return;
    await fetchJson(`${API.missions}/${encodeURIComponent(mission.mission_id)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision,
        target_stage: targetStage,
        comments: text(options.comments, `Owner recorded ${decision} from CHARLIE Mission Control.`),
      }),
    });
    await refreshAll();
  }

  function openSendBackDrawer(mission) {
    const workflow = Array.isArray(mission.agent_workflow) ? mission.agent_workflow : [];
    const agents = Array.from(new Set(workflow.map((item) => text(item.agent)).filter(Boolean)));
    const guidance = ownerActionGuidance(mission);
    const fallback = text(guidance.target_stage, text(stageLabel(mission), "builder"));
    if (!agents.includes("builder")) agents.unshift("builder");
    if (!agents.includes(fallback)) agents.unshift(fallback);
    el.reviewDrawerTitle.textContent = `Send Back ${shortId(mission)}`;
    el.reviewDrawerBody.innerHTML = `<div class="notice">Return this mission with a clear reason. CHARLIE will preserve this instruction in the review packet.</div>
      <div class="form-grid">
        <label>Return to stage<select id="sendBackStage">${agents.map((agent) => `<option value="${escapeAttr(agent)}" ${agent === fallback ? "selected" : ""}>${escapeHtml(cleanAgentName(agent))}</option>`).join("")}</select></label>
        <label>What must be corrected<textarea id="sendBackComments" required placeholder="State the exact issue and expected correction."></textarea></label>
        <button class="warn" data-confirm-send-back>Send Back to Agent</button>
      </div>`;
    openDrawer(el.reviewDrawer);
  }

  async function openReviewDrawer() {
    const mission = selectedMission();
    if (!mission) return;
    el.reviewDrawerTitle.textContent = `Review ${shortId(mission)}`;
    el.reviewDrawerBody.innerHTML = `<div class="notice">Loading review packet...</div>`;
    openDrawer(el.reviewDrawer);
    try {
      const data = await fetchJson(`${API.missions}/${encodeURIComponent(mission.mission_id)}/review?compact=1`, { timeoutMs: 25000 });
      const packet = data.review_packet || data.packet || data || {};
      const tests = Array.isArray(packet.test_evidence) ? packet.test_evidence : [];
      el.reviewDrawerBody.innerHTML = `
        ${field("Mission", `${titleOf(mission)} | ${shortId(mission)}`)}
        ${field("Status", statusLabel(mission.status))}
        ${field("Summary", text(packet.summary, text(packet.blocked_reason, "No review summary returned.")))}
        ${field("Recommended", text(packet.recommended_next_action, "No recommendation recorded."))}
        ${field("Blocked agent", text(packet.blocked_agent, "n/a"))}
        <details class="disclosure"><summary>Test evidence (${tests.length})</summary><div>${tests.length ? tests.map((item, index) => field(`Evidence ${index + 1}`, typeof item === "string" ? item : JSON.stringify(item))).join("") : '<div class="notice">No test evidence was recorded.</div>'}</div></details>
        <div class="button-grid">
          <button class="ok" data-review-decision="approve_final_release">Approve Final</button>
          <button class="warn" data-review-decision="send_back">Send Back</button>
          <button class="danger" data-review-decision="reject">Reject</button>
        </div>`;
    } catch (error) {
      el.reviewDrawerBody.innerHTML = `<div class="notice">${escapeHtml(error.message)}</div>`;
    }
  }

  async function createMission(event) {
    event.preventDefault();
    const form = new FormData(el.newMissionForm);
    const payload = Object.fromEntries(form.entries());
    el.newMissionResult.classList.remove("hidden");
    el.newMissionResult.textContent = "Creating mission...";
    try {
      const data = await fetchJson(API.missions, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      el.newMissionResult.textContent = `Created ${data.mission_id || "mission"}.`;
      el.newMissionForm.reset();
      await refreshAll();
    } catch (error) {
      el.newMissionResult.textContent = error.message;
    }
  }

  function openDrawer(drawer) {
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
    state.polling = false;
  }

  function closeDrawers() {
    document.querySelectorAll(".drawer.open").forEach((drawer) => {
      drawer.classList.remove("open");
      drawer.setAttribute("aria-hidden", "true");
    });
    state.polling = true;
  }

  function bindEvents() {
    el.refreshBtn.addEventListener("click", refreshAll);
    el.queueRefreshBtn.addEventListener("click", refreshAll);
    el.newMissionBtn.addEventListener("click", () => openDrawer(el.newMissionDrawer));
    el.newMissionForm.addEventListener("submit", createMission);
    document.addEventListener("click", async (event) => {
      const tab = event.target.closest("[data-tab]");
      if (tab) {
        state.activeTab = tab.dataset.tab;
        await ensureTabLoaded(state.activeTab);
        ensureSelection();
        render();
        return;
      }
      const select = event.target.closest("[data-select]");
      if (select) {
        state.selectedId = select.dataset.select;
        render();
        return;
      }
      const decision = event.target.closest("[data-decision]");
      if (decision) {
        await setMissionStatus(decision.dataset.decision);
        return;
      }
      const reviewDecision = event.target.closest("[data-review-decision]");
      if (reviewDecision) {
        const decisionValue = reviewDecision.dataset.reviewDecision;
        if (decisionValue === "send_back") {
          openSendBackDrawer(selectedMission());
          return;
        }
        await recordReviewDecision(decisionValue);
        closeDrawers();
        return;
      }
      if (event.target.closest("[data-confirm-send-back]")) {
        const comments = text(document.getElementById("sendBackComments") && document.getElementById("sendBackComments").value);
        const targetStage = text(document.getElementById("sendBackStage") && document.getElementById("sendBackStage").value, "builder");
        if (!comments) {
          document.getElementById("sendBackComments").focus();
          return;
        }
        await recordReviewDecision("send_back", { confirmed: true, comments, targetStage });
        closeDrawers();
        return;
      }
      if (event.target.closest("[data-open-review]")) {
        await openReviewDrawer();
        return;
      }
      const copy = event.target.closest("[data-copy-command]");
      if (copy) {
        await navigator.clipboard.writeText(copy.dataset.copyCommand);
        copy.textContent = "Copied";
        return;
      }
      if (event.target.closest("[data-close-drawer]")) {
        closeDrawers();
      }
    });
    document.addEventListener("visibilitychange", () => {
      state.polling = !document.hidden && !document.querySelector(".drawer.open");
    });
  }

  function startPolling() {
    setInterval(() => {
      if (state.polling && !document.hidden) refreshAll();
    }, 15000);
    setInterval(async () => {
      if (!state.polling || document.hidden) return;
      try {
        state.runner = await fetchJson(API.runner);
        renderHeader();
        renderActionPanel();
        renderStrip();
      } catch (error) {
        // Full refresh will surface load errors; runner-only failures should not blank the cockpit.
      }
    }, 10000);
  }

  bindEvents();
  refreshAll();
  startPolling();
}());
