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
    createForm: document.getElementById("charlie_mission_create_form"),
    newTitle: document.getElementById("charlie_new_title"),
    newConcept: document.getElementById("charlie_new_concept"),
    newOutcome: document.getElementById("charlie_new_outcome"),
    newMedia: document.getElementById("charlie_new_media"),
    newUrgency: document.getElementById("charlie_new_urgency"),
    newType: document.getElementById("charlie_new_type"),
    runner: {
      state: document.getElementById("charlie_runner_state"),
      message: document.getElementById("charlie_runner_message"),
      active: document.getElementById("charlie_runner_active"),
      next: document.getElementById("charlie_runner_next"),
      command: document.getElementById("charlie_runner_command"),
    },
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
      loadRunnerStatus();
    } catch (error) {
      setMessage(error.message || "Could not load CHARLIE missions.", "error");
      if (els.statusLine) els.statusLine.textContent = "Mission queue unavailable.";
    } finally {
      state.loading = false;
    }
  }

  async function loadRunnerStatus() {
    if (!els.runner.state) return;
    try {
      const data = await fetchJson("/api/charlie/build-relay/runner/status");
      const active = data.active_mission || {};
      const next = data.next_approved_mission || {};
      els.runner.state.textContent = runnerStateLabel(data.status);
      els.runner.message.textContent = data.next_action || "Runner handoff status loaded.";
      els.runner.active.textContent = active.mission_id ? `${shortId(active.mission_id)} | ${active.title || active.status || "active"}` : "None";
      els.runner.next.textContent = next.mission_id ? `${shortId(next.mission_id)} | ${next.title || next.status || "approved"}` : "None";
      if (data.local_runner_command) els.runner.command.textContent = data.local_runner_command;
    } catch (error) {
      els.runner.state.textContent = "Unavailable";
      els.runner.message.textContent = error.message || "Runner handoff status could not be loaded.";
    }
  }

  function runnerStateLabel(status) {
    if (status === "active_mission_in_progress") return "In Progress";
    if (status === "approved_waiting_for_local_runner") return "Waiting Pickup";
    if (status === "idle_no_approved_mission") return "Idle";
    return safeText(status || "Unknown");
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
    const vault = mission.vault || {};
    const workflow = Array.isArray(mission.agent_workflow) ? mission.agent_workflow : [];
    const media = Array.isArray(mission.media_references) ? mission.media_references : [];
    const contextPack = mission.mission_context_pack || {};
    card.innerHTML = `
      <div class="charlie-mission-card-header">
        <div>
          <span class="status-pill">${safeText(mission.status || "unknown")}</span>
          <h3>${escapeHtml(title)}</h3>
        </div>
        <code>${escapeHtml(shortId(missionId))}</code>
      </div>
      <p>${escapeHtml(safeText(mission.raw_text || title)).slice(0, 280)}</p>
      <div class="charlie-vault-summary">
        <strong>Mission Vault</strong>
        <span>Stage: ${escapeHtml(safeText(vault.mission_stage || "intake"))}</span>
        <span>Confidence target: ${escapeHtml(safeText(vault.confidence_target || "98% before release review"))}</span>
      </div>
      <div class="charlie-agent-strip" aria-label="Agent workflow">${workflow.map(agentBadge).join("")}</div>
      <div class="charlie-workflow-actions" aria-label="Mission workflow actions">
        <button type="button" data-agent-step="planner">Planner Done</button>
        <button type="button" data-agent-step="architect">Architect Done</button>
        <button type="button" data-agent-step="builder">Builder Done</button>
        <button type="button" data-agent-step="tester">Tester Done</button>
        <button type="button" data-agent-step="reviewer">Reviewer Done</button>
      </div>
      <dl class="charlie-mission-meta">
        <div><dt>Urgency</dt><dd>${escapeHtml(safeText(mission.urgency || "--"))}</dd></div>
        <div><dt>Type</dt><dd>${escapeHtml(safeText(mission.mission_type || "--"))}</dd></div>
        <div><dt>Approval</dt><dd>${escapeHtml(safeText(mission.approval_level || "--"))}</dd></div>
        <div><dt>Updated</dt><dd>${escapeHtml(formatDate(mission.updated_at))}</dd></div>
      </dl>
      <div class="charlie-mission-actions">
        <button type="button" data-vault-stage="planned">Mark Planned</button>
        <button type="button" data-vault-stage="review_ready">Review Ready</button>
        <button type="button" data-action="approved" data-level="LEVEL 1">Approve L1</button>
        <button type="button" data-action="approved" data-level="LEVEL 3">Approve L3</button>
        <button type="button" data-action="approved" data-level="LEVEL 4">Approve L4</button>
        <button type="button" data-action="paused">Pause</button>
        <button type="button" data-action="rejected">Reject</button>
        <button type="button" data-action="blocked">Block</button>
        <button type="button" data-action="done">Done</button>
      </div>
      <details>
        <summary>Mission vault details</summary>
        ${vaultDetails(vault, media, contextPack)}
      </details>
      <details>
        <summary>Technical details</summary>
        <pre>${escapeHtml(JSON.stringify(mission, null, 2))}</pre>
      </details>
    `;
    card.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", () => recordDecision(missionId, button.dataset.action, button.dataset.level || ""));
    });
    card.querySelectorAll("[data-vault-stage]").forEach((button) => {
      button.addEventListener("click", () => updateVaultStage(mission, button.dataset.vaultStage || "planned"));
    });
    card.querySelectorAll("[data-agent-step]").forEach((button) => {
      button.addEventListener("click", () => updateWorkflowStep(missionId, button.dataset.agentStep || "planner"));
    });
    return card;
  }

  function agentBadge(agent) {
    const name = safeText(agent.agent || "agent");
    const status = safeText(agent.status || "pending");
    return `<span class="status-pill status-pill-muted">${escapeHtml(name)}: ${escapeHtml(status)}</span>`;
  }

  function vaultDetails(vault, media, contextPack) {
    const criteria = listMarkup(vault.acceptance_criteria, "No acceptance criteria captured yet.");
    const tests = listMarkup(vault.test_plan, "No test plan captured yet.");
    const forbidden = listMarkup(vault.forbidden_actions, "Default safety gates apply.");
    const mediaItems = listMarkup((media || []).map((item) => `${item.label || "Reference"}: ${item.reference || ""}`), "No media/reference links captured yet.");
    const docs = listMarkup(contextPack.active_truth_docs, "Default start-here docs apply.");
    const sharedRules = listMarkup(contextPack.shared_data_rules, "Shared mission rules are loaded from CHARLIE protocol.");
    return `
      <dl class="charlie-mission-meta charlie-vault-detail">
        <div><dt>Problem</dt><dd>${escapeHtml(safeText(vault.problem_statement || "Not captured yet."))}</dd></div>
        <div><dt>Outcome</dt><dd>${escapeHtml(safeText(vault.desired_outcome || "Codex scopes and completes the mission under the approved level."))}</dd></div>
      </dl>
      <strong>Acceptance</strong>${criteria}
      <strong>Tests</strong>${tests}
      <strong>Forbidden</strong>${forbidden}
      <strong>Media / references</strong>${mediaItems}
      <strong>Shared context docs</strong>${docs}
      <strong>Shared data rules</strong>${sharedRules}
    `;
  }

  function listMarkup(items, fallback) {
    const list = Array.isArray(items) ? items.filter(Boolean) : [];
    if (!list.length) return `<p class="charlie-muted">${escapeHtml(fallback)}</p>`;
    return `<ul>${list.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
  }

  async function recordDecision(missionId, status, approvalLevel) {
    if (!missionId || !status) return;
    const levelLabel = approvalLevel ? ` ${approvalLevel}` : "";
    setMessage(`Recording ${status}${levelLabel}...`, "info");
    try {
      await fetchJson(`/api/charlie/build-relay/missions/${encodeURIComponent(missionId)}/decision`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          status,
          approval_level: approvalLevel,
          owner_decision: `Owner set mission status to ${status}${levelLabel} from CHARLIE Mission Control.`,
        }),
      });
      setMessage(`Mission marked ${status}${levelLabel}.`, "success");
      await loadMissions();
    } catch (error) {
      setMessage(error.message || "Decision was not recorded.", "error");
    }
  }

  async function createMission(event) {
    event.preventDefault();
    const concept = safeText(els.newConcept && els.newConcept.value).trim();
    if (!concept) {
      setMessage("Add a concept, issue, or idea before creating a mission.", "error");
      return;
    }
    setMessage("Creating mission...", "info");
    try {
      await fetchJson("/api/charlie/build-relay/missions", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          title: safeText(els.newTitle && els.newTitle.value).trim() || concept.slice(0, 90),
          raw_text: concept,
          desired_outcome: safeText(els.newOutcome && els.newOutcome.value).trim(),
          urgency: els.newUrgency ? els.newUrgency.value : "P2",
          mission_type: els.newType ? els.newType.value : "feature build",
          approval_level: "LEVEL 3",
          media_references: parseMediaReferences(els.newMedia && els.newMedia.value),
        }),
      });
      els.createForm.reset();
      setMessage("Mission created in CHARLIE vault.", "success");
      await loadMissions();
    } catch (error) {
      setMessage(error.message || "Mission was not created.", "error");
    }
  }

  async function updateVaultStage(mission, stage) {
    const missionId = safeText(mission.mission_id);
    if (!missionId) return;
    const vault = Object.assign({}, mission.vault || {}, {mission_stage: stage});
    const workflow = updateWorkflowForStage(mission.agent_workflow || [], stage);
    setMessage(`Updating mission vault to ${stage}...`, "info");
    try {
      await fetchJson(`/api/charlie/build-relay/missions/${encodeURIComponent(missionId)}/vault`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          mission_vault: vault,
          agent_workflow: workflow,
          notes: `Mission vault stage changed to ${stage} from CHARLIE Mission Control.`,
        }),
      });
      setMessage(`Mission vault marked ${stage}.`, "success");
      await loadMissions();
    } catch (error) {
      setMessage(error.message || "Mission vault was not updated.", "error");
    }
  }

  async function updateWorkflowStep(missionId, agent) {
    if (!missionId || !agent) return;
    setMessage(`Marking ${agent} complete...`, "info");
    try {
      await fetchJson(`/api/charlie/build-relay/missions/${encodeURIComponent(missionId)}/workflow`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          agent,
          step_status: "complete",
          findings: `${agent} step completed from CHARLIE Mission Control.`,
        }),
      });
      setMessage(`${agent} handoff recorded.`, "success");
      await loadMissions();
    } catch (error) {
      setMessage(error.message || "Workflow handoff was not recorded.", "error");
    }
  }

  function updateWorkflowForStage(workflow, stage) {
    const stages = {
      planned: ["planner", "architect"],
      review_ready: ["planner", "architect", "builder", "tester", "reviewer"],
    };
    const completed = new Set(stages[stage] || []);
    return (Array.isArray(workflow) ? workflow : []).map((item) => {
      const agent = safeText(item.agent);
      return Object.assign({}, item, {status: completed.has(agent) ? "complete" : (item.status || "pending")});
    });
  }

  function parseMediaReferences(value) {
    return safeText(value).split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => ({label: line.slice(0, 80), reference: line, media_type: "reference"}));
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
  if (els.createForm) els.createForm.addEventListener("submit", createMission);
  loadMissions();
})();
