(function () {
  "use strict";

  const API = {
    commandCenter: "/api/charlie/build-relay/command-center",
    runner: "/api/charlie/build-relay/runner/status",
    policy: "/api/charlie/build-relay/policy",
    missions: "/api/charlie/build-relay/missions",
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

  function progressPct(mission) {
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
      const [buckets, command, runner, policy] = await Promise.all([
        loadMissionBuckets().catch(() => state.buckets),
        fetchJson(API.commandCenter, { timeoutMs: 18000 }).catch(() => null),
        fetchJson(API.runner, { timeoutMs: 18000 }).catch(() => state.runner || {}),
        fetchJson(API.policy, { timeoutMs: 18000 }).catch(() => ({ charlie_build_relay: state.policy || {} })),
      ]);
      state.buckets = { ...state.buckets, ...buckets };
      if (command) applyCommandCenter(command);
      state.runner = runner;
      state.policy = policy.charlie_build_relay || {};
      state.lastUpdated = new Date();
      ensureSelection();
      render();
    } catch (error) {
      renderError(error);
    } finally {
      state.loading = false;
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
      const missions = [];
      const results = await Promise.allSettled(statuses.map((status) => (
        fetchJson(`${API.missions}?status=${encodeURIComponent(status)}&compact=1&limit=30`, { timeoutMs: 18000 })
      )));
      results.forEach((result) => {
        if (result.status === "fulfilled") missions.push(...(result.value.missions || []));
      });
      loaded[key] = dedupe(missions);
    }));
    return loaded;
  }

  function applyCommandCenter(command) {
    state.counts = command.counts || {};
    state.buckets.approved = (command.queue && command.queue.approved) || [];
    state.buckets.review = [
      ...((command.review && command.review.ready) || []),
      ...((command.release && command.release.waiting_final_bridge) || []),
    ];
    state.buckets.blocked = (command.review && command.review.blocked) || [];
    state.buckets.active = [
      ...((command.release && command.release.in_progress) || []),
      ...filterStatuses(command.recent_missions || [], ["in_progress", "release_in_progress"]),
    ];
    state.buckets.new = filterStatuses(command.recent_missions || [], ["new"]);
    state.buckets.done = filterStatuses(command.recent_missions || [], ["done", "merged", "deployed"]);
  }

  function filterStatuses(missions, statuses) {
    const allowed = new Set(statuses);
    return (missions || []).filter((mission) => allowed.has(text(mission.status).toLowerCase()));
  }

  async function ensureTabLoaded(tabId) {
    const tab = tabs.find((item) => item.id === tabId);
    if (!tab || (state.buckets[tabId] && state.buckets[tabId].length)) return;
    const loaded = [];
    for (const status of tab.statuses) {
      const data = await fetchJson(`${API.missions}?status=${encodeURIComponent(status)}&compact=1&limit=30`);
      loaded.push(...(data.missions || []));
    }
    state.buckets[tabId] = dedupe(loaded);
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
    renderTabs();
    renderQueue();
    renderWorkflow();
    renderActionPanel();
    renderStrip();
  }

  function renderHeader() {
    const runner = state.runner || {};
    const local = runner.local_runner || {};
    const scope = text(runner.local_runner_scope);
    let cls = "amber";
    let label = "Runner unknown";
    if (scope === "render_cannot_see_laptop_runner") {
      label = "Runner unknown from Render";
    } else if (local.active) {
      cls = "green";
      label = `Runner active ${text(local.age_seconds, "0")}s`;
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
    if (state.buckets[tab.id]) return state.buckets[tab.id].length;
    return tab.statuses.reduce((total, status) => total + Number(state.counts[status] || 0), 0);
  }

  function renderQueue() {
    const missions = dedupe(state.buckets[state.activeTab] || []);
    if (!missions.length) {
      el.queueList.innerHTML = `<div class="notice">No ${escapeHtml(state.activeTab)} missions are visible. Use another tab or create a mission.</div>`;
      return;
    }
    el.queueList.innerHTML = missions.map((mission) => {
      const status = text(mission.status, "unknown");
      const pct = progressPct(mission);
      return `<button class="mission-card ${statusClass(status)} ${mission.mission_id === state.selectedId ? "selected" : ""}" data-select="${escapeAttr(mission.mission_id)}">
        <div class="mission-card-title">${escapeHtml(titleOf(mission))}</div>
        <div class="mission-card-meta">
          <span>${escapeHtml(shortId(mission))} | ${escapeHtml(text(mission.approval_level, "LEVEL ?"))}</span>
          <span class="chip ${chipClass(status)}">${escapeHtml(statusLabel(status))}</span>
        </div>
        <div class="bar"><span style="width:${pct}%"></span></div>
        <div class="mission-card-meta">
          <span>${pct}%</span>
          <span>${escapeHtml(stageLabel(mission))}</span>
        </div>
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
        ${metric("Progress", `${pct}%`)}
        ${metric("Current", stageLabel(mission))}
        ${metric("Status", statusLabel(status))}
        ${metric("Queue", text(mission.queue_class, "owner"))}
      </div>
      <div class="bar"><span style="width:${pct}%"></span></div>
      <div class="timeline">${stages.map((stage) => renderStage(stage, mission)).join("")}</div>
      <div class="evidence">
        ${evidenceRow("Why this matters", text(review.summary, text(mission.raw_text, "No mission detail loaded.")))}
        ${evidenceRow("Next action", text(review.recommended_next_action, nextActionText(mission)))}
        ${renderTestEvidence(review)}
      </div>`;
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
    return `<div class="stage ${cls}">
      <div>
        <div class="stage-name">${escapeHtml(cleanAgentName(stage.agent))}</div>
        <div class="stage-state">${escapeHtml(raw || "pending")}</div>
      </div>
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
    el.actionPanel.innerHTML = `
      <div class="summary-block">
        <h3 class="summary-title">${escapeHtml(titleOf(mission))}</h3>
        ${field("Mission", `${shortId(mission)} | ${text(mission.approval_level, "LEVEL ?")}`)}
        ${field("State", `${statusLabel(status)} | ${stageLabel(mission)} | ${progressPct(mission)}%`)}
        ${field("Reason", headlineReason(mission) || "No reason recorded.")}
        ${actionButtons(mission)}
        ${runnerBox()}
        ${field("Raw Brief", text(review.summary, text(mission.raw_text, "No brief loaded.")))}
      </div>`;
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
      return `<div class="button-grid">
        <button class="primary ok" data-decision="approved">Approve Rerun</button>
        <button class="warn" data-review-decision="send_back">Send Back</button>
        <button class="warn" data-decision="paused">Pause</button>
        <button class="danger" data-decision="rejected">Reject</button>
      </div>`;
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
    const label = scope === "render_cannot_see_laptop_runner"
      ? "Unknown from Render"
      : (local.active ? `Active (${text(local.age_seconds, "0")}s heartbeat)` : "Stale/off");
    return `<div class="field">
      <label>Runner</label>
      <strong>${escapeHtml(label)}</strong>
      <span class="muted">${escapeHtml(text(runner.next_action, text(local.next_action, "Start local runner before expecting approved missions to run.")))}</span>
      <code>${escapeHtml(command)}</code>
      <button data-copy-command="${escapeAttr(command)}">Copy Runner Command</button>
    </div>`;
  }

  function renderStrip() {
    const runner = state.runner || {};
    const local = runner.local_runner || {};
    const policy = state.policy || {};
    const activeLabel = runner.local_runner_scope === "render_cannot_see_laptop_runner"
      ? "Unknown from cloud"
      : (local.active ? "Active" : "Stale/off");
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

  async function recordReviewDecision(decision) {
    const mission = selectedMission();
    if (!mission) return;
    const targetStage = text(stageLabel(mission), "builder");
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
        comments: `Owner recorded ${decision} from CHARLIE Mission Control v2.`,
      }),
    });
    await refreshAll();
  }

  async function openReviewDrawer() {
    const mission = selectedMission();
    if (!mission) return;
    el.reviewDrawerTitle.textContent = `Review ${shortId(mission)}`;
    el.reviewDrawerBody.innerHTML = `<div class="notice">Loading review packet...</div>`;
    openDrawer(el.reviewDrawer);
    try {
      const data = await fetchJson(`${API.missions}/${encodeURIComponent(mission.mission_id)}/review`);
      const packet = data.review_packet || data.packet || data || {};
      el.reviewDrawerBody.innerHTML = `
        ${field("Mission", `${titleOf(mission)} | ${shortId(mission)}`)}
        ${field("Status", statusLabel(mission.status))}
        ${field("Summary", text(packet.summary, text(packet.blocked_reason, "No review summary returned.")))}
        ${field("Recommended", text(packet.recommended_next_action, "No recommendation recorded."))}
        ${field("Blocked agent", text(packet.blocked_agent, "n/a"))}
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
        await recordReviewDecision(reviewDecision.dataset.reviewDecision);
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
