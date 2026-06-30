(function () {
  const state = {
    missions: [],
    reviewMissions: [],
    counts: {},
    loading: false,
    pendingMedia: [],
  };
  const MAX_MEDIA_ITEMS = 3;
  const MAX_MEDIA_BYTES = 650 * 1024;
  const IMAGE_MEDIA_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);
  const runnerControlCommandFallbacks = {
    status: ".\\venv\\Scripts\\python.exe scripts\\charlie_runner_control.py status",
    start: ".\\venv\\Scripts\\python.exe scripts\\charlie_runner_control.py start",
    stop: ".\\venv\\Scripts\\python.exe scripts\\charlie_runner_control.py stop",
  };

  const els = {
    statusLine: document.getElementById("charlie_status_line"),
    message: document.getElementById("charlie_message"),
    list: document.getElementById("charlie_mission_list"),
    reviewList: document.getElementById("charlie_review_list"),
    reviewLoadedAt: document.getElementById("charlie_review_loaded_at"),
    refresh: document.getElementById("charlie_refresh"),
    filter: document.getElementById("charlie_status_filter"),
    loadedAt: document.getElementById("charlie_loaded_at"),
    createForm: document.getElementById("charlie_mission_create_form"),
    newTitle: document.getElementById("charlie_new_title"),
    newConcept: document.getElementById("charlie_new_concept"),
    newOutcome: document.getElementById("charlie_new_outcome"),
    newMedia: document.getElementById("charlie_new_media"),
    newMediaDrop: document.getElementById("charlie_new_media_drop"),
    newMediaFile: document.getElementById("charlie_new_media_file"),
    newMediaPreviews: document.getElementById("charlie_new_media_previews"),
    newUrgency: document.getElementById("charlie_new_urgency"),
    newType: document.getElementById("charlie_new_type"),
    runner: {
      state: document.getElementById("charlie_runner_state"),
      message: document.getElementById("charlie_runner_message"),
      active: document.getElementById("charlie_runner_active"),
      next: document.getElementById("charlie_runner_next"),
      releaseNext: document.getElementById("charlie_runner_release_next"),
      local: document.getElementById("charlie_runner_local"),
      seen: document.getElementById("charlie_runner_seen"),
      command: document.getElementById("charlie_runner_command"),
      controls: document.getElementById("charlie_runner_control_commands"),
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
      const [summary, missions, reviewReady, blocked] = await Promise.all([
        fetchJson("/api/charlie/build-relay/missions/summary"),
        fetchJson(`/api/charlie/build-relay/missions${query}`),
        fetchJson("/api/charlie/build-relay/missions?status=pr_ready&limit=20"),
        fetchJson("/api/charlie/build-relay/missions?status=blocked&limit=20"),
      ]);
      state.missions = missions.missions || [];
      state.reviewMissions = uniqueMissions([...(reviewReady.missions || []), ...(blocked.missions || [])]);
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
      const releaseNext = data.next_release_approved_mission || {};
      const local = data.local_runner || {};
      const runnerIsRemoteBlind = data.local_runner_scope === "render_cannot_see_laptop_runner";
      els.runner.state.textContent = runnerStateLabel(data.status);
      els.runner.message.textContent = data.next_action || "Runner handoff status loaded.";
      els.runner.active.textContent = active.mission_id ? `${shortId(active.mission_id)} | ${active.title || active.status || "active"}` : "None";
      els.runner.next.textContent = next.mission_id ? `${shortId(next.mission_id)} | ${next.title || next.status || "approved"}` : "None";
      if (els.runner.releaseNext) els.runner.releaseNext.textContent = releaseNext.mission_id ? `${shortId(releaseNext.mission_id)} | ${releaseNext.title || releaseNext.status || "release approved"}` : "None";
      if (els.runner.local) els.runner.local.textContent = runnerIsRemoteBlind ? "Local-only; unavailable on Render" : local.active ? `Active (PID ${local.pid || "--"})` : "Not active";
      if (els.runner.seen) els.runner.seen.textContent = runnerIsRemoteBlind ? "Check local dashboard or runner_control.py" : local.last_seen ? `${formatDate(local.last_seen)} (${local.age_seconds || 0}s ago)` : "Never";
      if (data.local_runner_command) els.runner.command.textContent = data.local_runner_command;
      if (els.runner.controls && data.local_runner_control_commands) {
        const commands = Object.assign({}, runnerControlCommandFallbacks, data.local_runner_control_commands || {});
        els.runner.controls.textContent = [
          `Status: ${commands.status}`,
          `Start: ${commands.start}`,
          `Stop: ${commands.stop}`,
        ].join("\n");
      }
    } catch (error) {
      els.runner.state.textContent = "Unavailable";
      els.runner.message.textContent = error.message || "Runner handoff status could not be loaded.";
    }
  }

  function runnerStateLabel(status) {
    if (status === "active_mission_in_progress") return "In Progress";
    if (status === "release_approved_waiting_for_local_release_bridge") return "Release Approved";
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
      renderReview();
      return;
    }
    els.list.innerHTML = "";
    state.missions.forEach((mission) => {
      els.list.appendChild(missionCard(mission));
    });
    renderReview();
  }

  function renderReview() {
    if (els.reviewLoadedAt) els.reviewLoadedAt.textContent = `Loaded ${new Date().toLocaleTimeString()}`;
    if (!els.reviewList) return;
    if (!state.reviewMissions.length) {
      els.reviewList.innerHTML = '<p class="charlie-empty">No missions are waiting at owner review.</p>';
      return;
    }
    els.reviewList.innerHTML = "";
    state.reviewMissions.forEach((mission) => {
      els.reviewList.appendChild(reviewCard(mission));
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

  function reviewCard(mission) {
    const card = document.createElement("article");
    card.className = "charlie-mission-card charlie-review-card";
    const missionId = safeText(mission.mission_id);
    const title = safeText(mission.title || mission.raw_text || "Untitled mission");
    const metadata = mission.metadata || {};
    const reviewPacket = metadata.review_packet || {};
    const localPreview = reviewPacket.local_preview || {};
    const links = reviewPacket.links || {};
    const workflow = Array.isArray(mission.agent_workflow) ? mission.agent_workflow : [];
    card.innerHTML = `
      <div class="charlie-mission-card-header">
        <div>
          <span class="status-pill">${escapeHtml(safeText(mission.status || "review"))}</span>
          <h3>${escapeHtml(title)}</h3>
        </div>
        <code>${escapeHtml(shortId(missionId))}</code>
      </div>
      <dl class="charlie-mission-meta">
        <div><dt>Local view</dt><dd>${reviewLink(localPreview.url || localPreview.path || localPreview.command || links.local_preview)}</dd></div>
        <div><dt>PR / diff</dt><dd>${reviewLink(links.pr || links.diff || reviewPacket.pr_url || reviewPacket.diff_url)}</dd></div>
        <div><dt>Tests</dt><dd>${escapeHtml(firstReviewText(reviewPacket.test_evidence, "Not captured yet."))}</dd></div>
        <div><dt>Updated</dt><dd>${escapeHtml(formatDate(mission.updated_at))}</dd></div>
      </dl>
      <div class="charlie-agent-strip" aria-label="Review workflow">${workflow.map(agentBadge).join("")}</div>
      <details open>
        <summary>Mission findings and review packet</summary>
        <div class="charlie-review-packet" data-review-packet>
          ${reviewPacketMarkup(mission, reviewPacket)}
        </div>
      </details>
      <label for="review_comments_${escapeHtml(missionId)}">Owner comments</label>
      <textarea id="review_comments_${escapeHtml(missionId)}" rows="3" data-review-comments placeholder="Comments for final approval or send-back"></textarea>
      <div class="charlie-form-row">
        <label>
          Return stage
          <select data-review-target-stage>
            <option value="builder">Builder</option>
            <option value="tester">Tester</option>
            <option value="reviewer">Reviewer</option>
            <option value="planner">Planner</option>
            <option value="architect">Architect</option>
          </select>
        </label>
        <button type="button" data-review-refresh>Refresh Evidence</button>
      </div>
      <div class="charlie-mission-actions charlie-review-actions">
        <button type="button" data-review-decision="approve_final_release">Approve Final</button>
        <button type="button" data-review-decision="send_back">Send Back</button>
        <button type="button" data-review-decision="pause">Pause</button>
        <button type="button" data-review-decision="reject">Reject</button>
        <button type="button" data-review-decision="mark_done">Mark Done</button>
      </div>
    `;
    card.querySelector("[data-review-refresh]").addEventListener("click", () => loadReviewPacket(missionId, card));
    card.querySelectorAll("[data-review-decision]").forEach((button) => {
      button.addEventListener("click", () => recordReviewDecision(missionId, button.dataset.reviewDecision, card));
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
    const mediaItems = mediaMarkup(media, "No media/reference links captured yet.");
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

  function mediaMarkup(items, fallback) {
    const list = Array.isArray(items) ? items.filter(Boolean) : [];
    if (!list.length) return `<p class="charlie-muted">${escapeHtml(fallback)}</p>`;
    return `<div class="charlie-media-reference-list">${list.map(mediaReferenceMarkup).join("")}</div>`;
  }

  function mediaReferenceMarkup(item) {
    const label = safeText(item.label || "Mission media");
    const reference = safeText(item.reference || "");
    if (isImageDataReference(item)) {
      return `
        <figure class="charlie-media-reference">
          <img src="${escapeHtml(reference)}" alt="${escapeHtml(label)}" loading="lazy">
          <figcaption>${escapeHtml(label)}</figcaption>
        </figure>
      `;
    }
    return `
      <div class="charlie-media-reference charlie-media-reference-text">
        <strong>${escapeHtml(label)}</strong>
        <span>${reviewLink(reference)}</span>
      </div>
    `;
  }

  function reviewPacketMarkup(mission, packet) {
    const vault = mission.vault || {};
    const decisions = mission.metadata && Array.isArray(mission.metadata.owner_review_decisions) ? mission.metadata.owner_review_decisions : [];
    return `
      <strong>Summary</strong>
      <p>${escapeHtml(safeText(packet.summary || vault.desired_outcome || mission.raw_text || "Not captured yet."))}</p>
      <strong>Findings</strong>${listMarkup(packet.findings || workflowFindings(mission.agent_workflow), "No findings captured yet.")}
      <strong>Errors / bugs</strong>${listMarkup([...(packet.errors || []), ...(packet.bugs || [])], "No errors or bugs captured yet.")}
      <strong>Changed files</strong>${listMarkup(packet.changed_files, "No changed files captured yet.")}
      <strong>Release notes</strong>${listMarkup(packet.release_notes, "No release notes captured yet.")}
      <strong>Owner review history</strong>${listMarkup(decisions.map((item) => `${item.decision || "decision"}: ${item.comments || "no comments"}`), "No owner review decisions yet.")}
    `;
  }

  function workflowFindings(workflow) {
    return (Array.isArray(workflow) ? workflow : [])
      .map((item) => item && item.findings ? `${item.agent || "agent"}: ${item.findings}` : "")
      .filter(Boolean);
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

  async function loadReviewPacket(missionId, card) {
    if (!missionId || !card) return;
    setMessage("Loading review packet...", "info");
    try {
      const data = await fetchJson(`/api/charlie/build-relay/missions/${encodeURIComponent(missionId)}/review`);
      const container = card.querySelector("[data-review-packet]");
      if (container) container.innerHTML = reviewPacketDetailMarkup(data.review_packet || {});
      setMessage("Review packet loaded.", "success");
    } catch (error) {
      setMessage(error.message || "Review packet could not be loaded.", "error");
    }
  }

  async function recordReviewDecision(missionId, decision, card) {
    if (!missionId || !decision || !card) return;
    const comments = safeText(card.querySelector("[data-review-comments]") && card.querySelector("[data-review-comments]").value).trim();
    const targetStage = safeText(card.querySelector("[data-review-target-stage]") && card.querySelector("[data-review-target-stage]").value).trim() || "builder";
    setMessage(`Recording review decision ${decision}...`, "info");
    try {
      await fetchJson(`/api/charlie/build-relay/missions/${encodeURIComponent(missionId)}/review`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          decision,
          comments,
          target_stage: targetStage,
        }),
      });
      setMessage("Review decision recorded.", "success");
      await loadMissions();
    } catch (error) {
      setMessage(error.message || "Review decision was not recorded.", "error");
    }
  }

  function reviewPacketDetailMarkup(packet) {
    const mission = packet.mission || {};
    return `
      <strong>${escapeHtml(safeText(mission.title || mission.mission_id || "Review packet"))}</strong>
      <p>${escapeHtml(safeText(packet.summary || "No summary captured yet."))}</p>
      <strong>Findings</strong>${listMarkup(packet.findings, "No findings captured yet.")}
      <strong>Errors / bugs</strong>${listMarkup([...(packet.errors || []), ...(packet.bugs || [])], "No errors or bugs captured yet.")}
      <strong>Changed files</strong>${listMarkup(packet.changed_files, "No changed files captured yet.")}
      <strong>Test evidence</strong>${listMarkup(packet.test_evidence, "No test evidence captured yet.")}
      <strong>Release notes</strong>${listMarkup(packet.release_notes, "No release notes captured yet.")}
      <strong>Execution boundary</strong>
      <p>${escapeHtml(safeText(packet.execution_boundary || "Dashboard records review decisions only."))}</p>
    `;
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
          media_references: collectMediaReferences(),
        }),
      });
      els.createForm.reset();
      clearPendingMedia();
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

  function collectMediaReferences() {
    return [
      ...parseMediaReferences(els.newMedia && els.newMedia.value),
      ...state.pendingMedia.map((item) => ({
        label: item.label,
        reference: item.reference,
        media_type: "image",
        source: item.source || "dashboard_clipboard",
      })),
    ];
  }

  function setupMediaCapture() {
    if (!els.newMediaDrop) return;
    els.newMediaDrop.addEventListener("paste", handleMediaPaste);
    els.newMediaDrop.addEventListener("dragover", (event) => {
      event.preventDefault();
      els.newMediaDrop.classList.add("is-drag-over");
    });
    els.newMediaDrop.addEventListener("dragleave", () => els.newMediaDrop.classList.remove("is-drag-over"));
    els.newMediaDrop.addEventListener("drop", handleMediaDrop);
    els.newMediaDrop.addEventListener("click", () => {
      if (els.newMediaFile) els.newMediaFile.click();
    });
    els.newMediaDrop.addEventListener("keydown", (event) => {
      if ((event.key === "Enter" || event.key === " ") && els.newMediaFile) {
        event.preventDefault();
        els.newMediaFile.click();
      }
    });
    if (els.newMediaFile) {
      els.newMediaFile.addEventListener("change", () => addMediaFiles(els.newMediaFile.files, "dashboard_file"));
    }
    document.addEventListener("paste", (event) => {
      if (isInsideMissionForm(event.target)) handleMediaPaste(event);
    });
    renderPendingMedia();
  }

  function handleMediaPaste(event) {
    if (event.defaultPrevented) return;
    const files = Array.from((event.clipboardData && event.clipboardData.files) || [])
      .filter((file) => IMAGE_MEDIA_TYPES.has(file.type));
    if (!files.length) return;
    event.preventDefault();
    addMediaFiles(files, "dashboard_clipboard");
  }

  function handleMediaDrop(event) {
    event.preventDefault();
    els.newMediaDrop.classList.remove("is-drag-over");
    addMediaFiles(event.dataTransfer && event.dataTransfer.files, "dashboard_drop");
  }

  async function addMediaFiles(fileList, source) {
    const files = Array.from(fileList || []).filter((file) => IMAGE_MEDIA_TYPES.has(file.type));
    if (!files.length) {
      setMessage("Only PNG, JPG, WebP, or GIF screenshots can be attached here.", "error");
      return;
    }
    for (const file of files) {
      if (state.pendingMedia.length >= MAX_MEDIA_ITEMS) {
        setMessage(`Mission media is limited to ${MAX_MEDIA_ITEMS} images for this no-migration version.`, "error");
        break;
      }
      if (file.size > MAX_MEDIA_BYTES) {
        setMessage(`${file.name || "Screenshot"} is too large. Keep each image under 650 KB for mission metadata storage.`, "error");
        continue;
      }
      const reference = await readFileAsDataUrl(file);
      state.pendingMedia.push({
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        label: file.name || `Pasted screenshot ${state.pendingMedia.length + 1}`,
        reference,
        source,
      });
    }
    if (els.newMediaFile) els.newMediaFile.value = "";
    renderPendingMedia();
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(safeText(reader.result));
      reader.onerror = () => reject(new Error("Screenshot could not be read."));
      reader.readAsDataURL(file);
    });
  }

  function renderPendingMedia() {
    if (!els.newMediaPreviews) return;
    if (!state.pendingMedia.length) {
      els.newMediaPreviews.innerHTML = '<p class="charlie-muted">No screenshots attached yet.</p>';
      return;
    }
    els.newMediaPreviews.innerHTML = state.pendingMedia.map((item) => `
      <figure class="charlie-media-preview">
        <img src="${escapeHtml(item.reference)}" alt="${escapeHtml(item.label)}">
        <figcaption>${escapeHtml(item.label)}</figcaption>
        <button type="button" data-remove-media="${escapeHtml(item.id)}" aria-label="Remove ${escapeHtml(item.label)}">Remove</button>
      </figure>
    `).join("");
    els.newMediaPreviews.querySelectorAll("[data-remove-media]").forEach((button) => {
      button.addEventListener("click", () => {
        state.pendingMedia = state.pendingMedia.filter((item) => item.id !== button.dataset.removeMedia);
        renderPendingMedia();
      });
    });
  }

  function clearPendingMedia() {
    state.pendingMedia = [];
    renderPendingMedia();
  }

  function isInsideMissionForm(target) {
    return Boolean(els.createForm && target && els.createForm.contains(target));
  }

  function isImageDataReference(item) {
    return item && item.media_type === "image" && /^data:image\/(png|jpeg|jpg|webp|gif);base64,/i.test(safeText(item.reference));
  }

  function reviewLink(value) {
    const text = safeText(value).trim();
    if (!text) return "Not captured";
    if (/^https?:\/\//i.test(text)) {
      return `<a href="${escapeHtml(text)}" target="_blank" rel="noopener noreferrer">${escapeHtml(text)}</a>`;
    }
    return escapeHtml(text);
  }

  function firstReviewText(items, fallback) {
    if (Array.isArray(items) && items.length) return safeText(items[0]);
    return fallback;
  }

  function uniqueMissions(missions) {
    const seen = new Set();
    return missions.filter((mission) => {
      const id = mission && mission.mission_id;
      if (!id || seen.has(id)) return false;
      seen.add(id);
      return true;
    });
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
  setupMediaCapture();
  loadMissions();
})();
