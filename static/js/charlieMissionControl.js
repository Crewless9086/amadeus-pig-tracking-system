(function () {
  const state = {
    missions: [],
    reviewMissions: [],
    improvements: [],
    commandCenter: {},
    runnerStatus: {},
    counts: {},
    loading: false,
    pendingMedia: [],
    activeFilter: "owner_queue",
    openReviewDetails: new Set(),
    activeReviewMissionId: "",
  };
  const AUTO_REFRESH_MS = 8000;
  const AGENT_ORDER = [
    "idea_expander",
    "product_architect",
    "technical_architect",
    "risk_agent",
    "council_synthesis",
    "planner",
    "architect",
    "builder",
    "tester",
    "qa_red_team",
    "product_reviewer",
    "business_reviewer",
    "security_reviewer",
    "evidence_reviewer",
    "reviewer",
    "publisher",
  ];
  const AGENT_LABELS = {
    idea_expander: "Idea Expander",
    concept_strategist: "Concept",
    product_architect: "Product Architect",
    technical_architect: "Technical Architect",
    business_model_agent: "Business",
    risk_agent: "Risk Agent",
    council_synthesis: "Council Synthesis",
    planner: "Planner",
    architect: "Architect",
    builder: "Builder",
    tester: "Tester",
    qa_red_team: "QA Red Team",
    product_reviewer: "Product Review",
    business_reviewer: "Business Review",
    security_reviewer: "Security",
    evidence_reviewer: "Evidence",
    reviewer: "Reviewer",
    publisher: "Publisher",
  };
  const WORKFLOW_VISUAL_STATES = ["is-complete", "is-active", "is-blocked", "is-send-back", "is-review-ready", "is-pending"];
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
    commandCenter: document.getElementById("charlie_command_center"),
    commandCenterLoadedAt: document.getElementById("charlie_command_center_loaded_at"),
    improvementsList: document.getElementById("charlie_improvements_list"),
    improvementsAnalyze: document.getElementById("charlie_improvements_analyze"),
    liveNotice: document.getElementById("charlie_live_notice"),
    workflowMap: document.getElementById("charlie_workflow_map"),
    activeSummary: document.getElementById("charlie_active_summary"),
    reviewModal: document.getElementById("charlie_review_modal"),
    reviewModalTitle: document.getElementById("charlie_review_modal_title"),
    reviewModalBody: document.getElementById("charlie_review_modal_body"),
    reviewModalClose: document.getElementById("charlie_review_modal_close"),
    refresh: document.getElementById("charlie_refresh"),
    addMission: document.getElementById("charlie_add_mission"),
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
      pr_ready: document.getElementById("charlie_count_pr_ready"),
      release: document.getElementById("charlie_count_release"),
      merged: document.getElementById("charlie_count_merged"),
      deployed: document.getElementById("charlie_count_deployed"),
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
    state.activeFilter = status || "";
    const query = status ? `?status=${encodeURIComponent(status)}&limit=30` : "?limit=30";
    try {
      const [summary, missions] = await Promise.all([
        fetchJson("/api/charlie/build-relay/missions/summary"),
        fetchJson(`/api/charlie/build-relay/missions${query}`),
      ]);
      state.missions = missions.missions || [];
      state.counts = summary.counts || {};
      state.reviewMissions = state.missions.filter((mission) => ["pr_ready", "blocked"].includes(mission.status));
      render();
      loadRunnerStatus();
      loadCommandCenter();
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
      state.runnerStatus = data || {};
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
      if (els.runner.seen) {
        const agentLine = local.current_agent ? ` | ${local.current_agent}: ${local.current_action || local.last_result_status || "running"}` : "";
        els.runner.seen.textContent = runnerIsRemoteBlind ? "Check local dashboard or runner_control.py" : local.last_seen ? `${formatDate(local.last_seen)} (${local.age_seconds || 0}s ago)${agentLine}` : "Never";
      }
      if (data.local_runner_command) els.runner.command.textContent = data.local_runner_command;
      if (els.runner.controls && data.local_runner_control_commands) {
        const commands = Object.assign({}, runnerControlCommandFallbacks, data.local_runner_control_commands || {});
        const executionLines = local.agent_runner_version ? [
          `Agent: ${local.current_agent || "--"}`,
          `Action: ${local.current_action || local.last_result_status || "--"}`,
          `Ledger: ${local.agent_ledger_path || "--"}`,
          `Artifact: ${local.execution_artifact || "--"}`,
          `Latest Stage: ${runnerLatestStageLine(local.agent_ledger)}`,
          `Stdout: ${shortOutput(local.stdout_tail || (local.agent_ledger && local.agent_ledger.latest_stage && local.agent_ledger.latest_stage.stdout_tail))}`,
          `Stderr: ${shortOutput(local.stderr_tail || (local.agent_ledger && local.agent_ledger.latest_stage && local.agent_ledger.latest_stage.stderr_tail))}`,
        ] : [];
        els.runner.controls.textContent = [
          `Status: ${commands.status}`,
          `Start: ${commands.start}`,
          `Stop: ${commands.stop}`,
          ...executionLines,
        ].join("\n");
      }
      renderAliveDashboard();
    } catch (error) {
      els.runner.state.textContent = "Unavailable";
      els.runner.message.textContent = error.message || "Runner handoff status could not be loaded.";
      state.runnerStatus = {status: "unavailable", next_action: els.runner.message.textContent};
      renderAliveDashboard();
    }
  }

  async function loadCommandCenter() {
    try {
      const commandCenter = await fetchJson("/api/charlie/build-relay/command-center");
      state.commandCenter = commandCenter || {};
      state.improvements = (((commandCenter || {}).improvements || {}).proposals) || [];
      state.reviewMissions = uniqueMissions([
        ...(((commandCenter.review || {}).ready) || []),
        ...(((commandCenter.review || {}).blocked) || []),
      ]);
      renderCommandCenter(state.commandCenter);
      renderImprovements();
      renderReview();
      renderAliveDashboard();
    } catch (error) {
      if (els.commandCenter) {
        els.commandCenter.innerHTML = `<p class="charlie-muted">${escapeHtml(error.message || "Command center unavailable.")}</p>`;
      }
    }
  }

  function runnerStateLabel(status) {
    if (status === "active_mission_in_progress") return "In Progress";
    if (status === "release_approved_waiting_for_local_release_bridge") return "Release Approved";
    if (status === "approved_waiting_for_local_runner") return "Waiting Pickup";
    if (status === "idle_no_approved_mission") return "Idle";
    return safeText(status || "Unknown");
  }

  function runnerLatestStageLine(ledger) {
    const latest = ledger && ledger.latest_stage ? ledger.latest_stage : {};
    if (!latest.agent) return "--";
    return `${latest.agent} ${latest.status || "running"} attempt ${latest.attempt || 1}`;
  }

  function shortOutput(value) {
    const text = safeText(value).trim();
    if (!text) return "--";
    return text.length > 180 ? `${text.slice(-180)}` : text;
  }

  function render() {
    if (els.statusLine) {
      els.statusLine.textContent = `${state.missions.length} mission records loaded. Decisions here update mission state only.`;
    }
    Object.keys(els.counts).forEach((key) => {
      if (!els.counts[key]) return;
      if (key === "release") {
        els.counts[key].textContent = (state.counts.release_approved || 0) + (state.counts.release_in_progress || 0);
      } else {
        els.counts[key].textContent = state.counts[key] || 0;
      }
    });
    if (els.loadedAt) els.loadedAt.textContent = `Loaded ${new Date().toLocaleTimeString()}`;
    renderCommandCenter();
    renderAliveDashboard();
    if (!els.list) return;
    if (!state.missions.length) {
      els.list.innerHTML = '<p class="charlie-empty">No missions found for this filter.</p>';
      renderReview();
      return;
    }
    els.list.innerHTML = "";
    const ownerMissions = state.missions.filter((mission) => queueClass(mission) === "owner_work");
    const systemMissions = state.missions.filter((mission) => queueClass(mission) !== "owner_work");
    const visibleMissions = ownerMissions.length ? ownerMissions : (state.activeFilter === "owner_queue" ? [] : state.missions);
    if (!visibleMissions.length) {
      els.list.innerHTML = '<p class="charlie-empty">No owner missions found for this filter.</p>';
      renderReview();
      return;
    }
    visibleMissions.forEach((mission) => {
      els.list.appendChild(missionCard(mission));
    });
    if (systemMissions.length && ownerMissions.length) {
      const details = document.createElement("details");
      details.className = "charlie-system-missions";
      details.innerHTML = `<summary>${systemMissions.length} system/test or low-signal mission(s)</summary>`;
      const wrap = document.createElement("div");
      wrap.className = "charlie-system-mission-list";
      systemMissions.forEach((mission) => wrap.appendChild(missionCard(mission)));
      details.appendChild(wrap);
      els.list.appendChild(details);
    }
    renderReview();
  }

  function renderCommandCenter() {
    if (els.commandCenterLoadedAt) els.commandCenterLoadedAt.textContent = `Loaded ${new Date().toLocaleTimeString()}`;
    if (!els.commandCenter) return;
    const data = state.commandCenter || {};
    const release = data.release || {};
    const review = data.review || {};
    const queue = data.queue || {};
    const vault = data.vault || {};
    const core = data.charlie_core || {};
    const recentReadiness = Array.isArray(core.recent_readiness) ? core.recent_readiness : [];
    const readinessAverage = recentReadiness.length
      ? Math.round(recentReadiness.reduce((total, item) => total + Number((item.core_readiness || {}).overall_percent || 0), 0) / recentReadiness.length)
      : 0;
    const vaultHealth = vault.health || {};
    const vaultMissing = Array.isArray(vaultHealth.missing_tables) ? vaultHealth.missing_tables.length : 0;
    const modelRegistry = core.model_registry || {};
    const toolPermissions = core.tool_permissions || {};
    const ownerPreferences = core.owner_preferences || {};
    const autonomy = data.autonomy_readiness || {};
    const runner = data.local_runner || {};
    const improvements = data.improvements || {};
    const retrievalCount = recentReadiness.reduce((total, item) => total + Number((item.vault_retrieval || {}).selected_count || 0), 0);
    els.commandCenter.innerHTML = `
      ${commandCenterTile("Core Readiness", readinessAverage ? `${readinessAverage}% recent` : "No recent score", core.overall_target || "90%+ target")}
      ${commandCenterTile("Autonomy", autonomy.percent != null ? `${autonomy.percent}%` : "Unknown", autonomy.safe_mode || "supervised")}
      ${commandCenterTile("Vault", vault.version || "charlie_vault_v1", vault.storage || "metadata_json active")}
      ${commandCenterTile("Vault Tables", vaultHealth.status || "unknown", vaultMissing ? `${vaultMissing} missing` : "normalized tables ready")}
      ${commandCenterTile("Vault Retrieval", `${retrievalCount} source hits`, recentReadiness.length ? "ranked by mission context" : "waiting for missions")}
      ${commandCenterTile("Owner Rules", `${(ownerPreferences.preferences || []).length} active`, "applied in stage prompts")}
      ${commandCenterTile("Models", `${Object.keys(modelRegistry.models || {}).length} registered`, modelRegistry.safety_note || "Manual routing")}
      ${commandCenterTile("Tool Permissions", `${Object.keys(toolPermissions.agent_tool_allowlist || {}).length} agents`, `${(toolPermissions.red_zone_tools || []).length} red-zone tools`)}
      ${commandCenterTile("Queue", `${(queue.approved || []).length} approved`, queue.ordering || "priority order")}
      ${commandCenterTile("Review", `${(review.ready || []).length} ready`, `${(review.blocked || []).length} blocked`)}
      ${commandCenterTile("Improvements", `${(improvements.pending || []).length} pending`, improvements.status || "proposal store")}
      ${commandCenterTile("Release", `${(release.waiting_final_bridge || []).length} waiting`, `${(release.in_progress || []).length} running`)}
      ${commandCenterTile("Live Verify", release.verify_url_configured ? "Configured" : "Missing URL", release.verify_url_configured ? "Can mark deployed" : "Merged only until URL set")}
      ${commandCenterTile("Merged", `${release.merged_count || (release.merged_waiting_live_verify || []).length || 0} total`, "Needs live proof for deployed")}
      ${commandCenterTile("Deployed", `${release.deployed_count || (release.deployed || []).length || 0} complete`, "Verified live")}
      ${commandCenterTile("Runner", runner.active ? "Active" : "Not active", runner.current_agent ? `${runner.current_agent}: ${runner.current_action || "running"}` : data.local_runner_scope || "local")}
      ${commandCenterTile("Boundary", "Owner gated", data.execution_boundary || "Local runner executes builds")}
      ${recentReadiness.slice(0, 3).map((item) => commandCenterTile(
        shortId(item.mission_id || ""),
        `${Number((item.core_readiness || {}).overall_percent || 0)}% ready`,
        `${item.title || item.status || "recent mission"} | ${(item.vault_retrieval || {}).selected_count || 0} Vault docs`
      )).join("")}
    `;
  }

  function commandCenterTile(label, value, detail) {
    return `
      <article class="charlie-command-center-tile">
        <strong>${escapeHtml(label)}</strong>
        <span>${escapeHtml(value)}</span>
        <code>${escapeHtml(detail || "")}</code>
      </article>
    `;
  }

  function renderReview() {
    if (els.reviewLoadedAt) els.reviewLoadedAt.textContent = `Loaded ${new Date().toLocaleTimeString()}`;
    if (!els.reviewList) return;
    els.reviewList.querySelectorAll("[data-review-details]").forEach((details) => {
      const missionId = safeText(details.dataset.reviewDetails);
      if (!missionId) return;
      if (details.open) state.openReviewDetails.add(missionId);
      else state.openReviewDetails.delete(missionId);
    });
    if (!state.reviewMissions.length) {
      els.reviewList.innerHTML = emptyOwnerReviewMarkup();
      els.reviewList.querySelectorAll("[data-review-empty-action]").forEach((button) => {
        button.addEventListener("click", () => {
          const action = safeText(button.dataset.reviewEmptyAction || "review");
          setMessage(`No owner-review mission is available for ${action}. Refresh evidence or wait for Builder, Tester, QA, and Reviewer to pass the gate.`, "info");
        });
      });
      const refreshButton = els.reviewList.querySelector("[data-review-refresh]");
      if (refreshButton) refreshButton.addEventListener("click", loadMissions);
      return;
    }
    els.reviewList.innerHTML = "";
    state.reviewMissions.forEach((mission) => {
      els.reviewList.appendChild(reviewCard(mission));
    });
  }

  function emptyOwnerReviewMarkup() {
    return `
      <article class="charlie-mission-card charlie-review-card charlie-review-empty-card">
        <div class="charlie-mission-card-header">
          <div>
            <span class="status-pill status-pill-muted">No mission</span>
            <h3>No owner-review packet is ready</h3>
          </div>
          <code>stage-8</code>
        </div>
        <dl class="charlie-mission-meta">
          <div><dt>Runner state</dt><dd>${escapeHtml(runnerStateLabel((state.runnerStatus || {}).status))}</dd></div>
          <div><dt>Review ready</dt><dd>0 missions</dd></div>
          <div><dt>Blocked</dt><dd>${escapeHtml(safeText((((state.commandCenter || {}).review || {}).blocked || []).length || 0))}</dd></div>
          <div><dt>Next action</dt><dd>${escapeHtml(safeText((state.runnerStatus || {}).next_action || "No review packet is available yet."))}</dd></div>
        </dl>
        <details class="charlie-evidence-drawer" open>
          <summary>Evidence and details</summary>
          <p class="charlie-muted">Owner approval controls stay visible, but final decisions require a mission with a captured PR, tests, review packet, and desktop/mobile visual evidence.</p>
          <ul>
            <li>Open Review: unavailable until a mission reaches blocked or review-ready.</li>
            <li>Refresh Evidence: reloads dashboard state, runner heartbeat, and command-center review queues.</li>
            <li>Approve, Send Back, Pause, Reject, and Mark Done: require a mission id so CHARLIE CORE can preserve the audit trail.</li>
          </ul>
        </details>
        <div class="charlie-review-inline-decision">
          <label for="review_empty_comments">Owner comments</label>
          <textarea id="review_empty_comments" rows="3" placeholder="Comments attach only after a mission reaches owner review." disabled></textarea>
          <label>
            Return stage
            <select disabled>
              <option>No mission selected</option>
            </select>
          </label>
        </div>
        <div class="charlie-mission-actions charlie-review-actions">
          <button type="button" data-review-empty-action="Open Review">Open Review</button>
          <button type="button" data-review-refresh>Refresh Evidence</button>
          <button type="button" data-review-empty-action="Approve Final">Approve Final</button>
          <button type="button" data-review-empty-action="Send Back">Send Back</button>
          <button type="button" data-review-empty-action="Pause">Pause</button>
          <button type="button" data-review-empty-action="Reject">Reject</button>
          <button type="button" data-review-empty-action="Mark Done">Mark Done</button>
        </div>
      </article>
    `;
  }

  function renderImprovements() {
    if (!els.improvementsList) return;
    const proposals = Array.isArray(state.improvements) ? state.improvements : [];
    if (!proposals.length) {
      els.improvementsList.innerHTML = '<p class="charlie-empty">No CHARLIE improvement proposals are waiting.</p>';
      return;
    }
    els.improvementsList.innerHTML = proposals.slice(0, 8).map(improvementProposalMarkup).join("");
    els.improvementsList.querySelectorAll("[data-improvement-decision]").forEach((button) => {
      button.addEventListener("click", () => recordImprovementDecision(
        button.dataset.proposalId,
        button.dataset.improvementDecision,
        button.closest(".charlie-improvement-card")
      ));
    });
  }

  function improvementProposalMarkup(proposal) {
    const proposalId = safeText(proposal.artifact_id || proposal.proposal_id);
    const evidence = Array.isArray(proposal.evidence_refs) ? proposal.evidence_refs : [];
    const sourceIds = Array.isArray(proposal.source_mission_ids) ? proposal.source_mission_ids : [];
    return `
      <article class="charlie-improvement-card">
        <div class="charlie-mission-card-header">
          <div>
            <span class="status-pill">${escapeHtml(safeText(proposal.status || "pending"))}</span>
            <h3>${escapeHtml(safeText(proposal.problem_detected || "CHARLIE improvement proposal"))}</h3>
          </div>
          <code>${escapeHtml(shortId(proposalId))}</code>
        </div>
        <dl class="charlie-mission-meta">
          <div><dt>Area</dt><dd>${escapeHtml(safeText(proposal.target_area || "--"))}</dd></div>
          <div><dt>Score</dt><dd>${escapeHtml(safeText(proposal.weakness_score || 0))}</dd></div>
          <div><dt>Recurrence</dt><dd>${escapeHtml(safeText(proposal.recurrence_count || sourceIds.length || 0))}</dd></div>
          <div><dt>Label</dt><dd>${escapeHtml(safeText(proposal.label || "charlie_self_improvement"))}</dd></div>
        </dl>
        <p>${escapeHtml(safeText(proposal.recommendation || "No recommendation captured."))}</p>
        <details>
          <summary>Evidence</summary>
          ${listMarkup(evidence.map((item) => `${item.mission_id || ""}: ${item.evidence || item.title || ""}`), "No evidence references captured.")}
        </details>
        <label>
          Owner comments
          <textarea rows="3" data-improvement-comments placeholder="Optional owner note"></textarea>
        </label>
        <div class="charlie-mission-actions charlie-improvement-actions">
          <button type="button" data-proposal-id="${escapeHtml(proposalId)}" data-improvement-decision="approve">Approve</button>
          <button type="button" data-proposal-id="${escapeHtml(proposalId)}" data-improvement-decision="reject">Reject</button>
          <button type="button" data-proposal-id="${escapeHtml(proposalId)}" data-improvement-decision="send_to_mission">Send To Mission</button>
        </div>
      </article>
    `;
  }

  function renderAliveDashboard() {
    renderWorkflowMap();
    renderActiveSummary();
  }

  function renderWorkflowMap() {
    if (!els.workflowMap) return;
    const activeMission = currentMissionForFlow();
    const workflow = workflowForMission(activeMission);
    const runner = state.runnerStatus || {};
    const local = runner.local_runner || {};
    const latest = (local.agent_ledger && local.agent_ledger.latest_stage) || {};
    const activeAgent = normalizeAgent(local.current_agent || latestLedgerAgent(local.agent_ledger) || workflowActiveAgent(workflow));
    const blockedPacket = reviewPacketForMission(activeMission);
    const blocked = activeMission && (activeMission.status === "blocked" || blockedPacket.review_status === "agent_blocked");
    const reviewReady = activeMission && activeMission.status === "pr_ready";
    const backflowEvents = backflowEventsForMission(activeMission);
    if (els.liveNotice) {
      const remoteBlind = runner.local_runner_scope === "render_cannot_see_laptop_runner";
      els.liveNotice.classList.toggle("is-warning", remoteBlind || Boolean(blocked));
      els.liveNotice.textContent = remoteBlind
        ? "Render cannot see this laptop's .charlie_runner heartbeat. Live local runner data is available only on the local dashboard."
        : runner.next_action || "Local runner heartbeat and mission ledger are feeding this live workflow.";
    }
    const displayAgents = workflowDisplayOrder(workflow);
    const currentStatus = activeMission ? safeText(activeMission.status || "unknown") : "no_mission";
    els.workflowMap.innerHTML = `
      <div class="charlie-flow-title">
        <div>
          <strong>${escapeHtml(activeMission ? activeMission.title || activeMission.raw_text || "Active mission" : "No active mission selected")}</strong>
          <small>${escapeHtml(shortMissionLine(activeMission, runner))}</small>
        </div>
        <span class="charlie-state-token is-${escapeHtml(runnerStateClass(currentStatus, runner.status))}">${escapeHtml(stateLabel(currentStatus, runner.status))}</span>
      </div>
      ${blocked ? blockedReviewBanner(blockedPacket) : ""}
      <div class="charlie-control-hero" data-active-agent="${escapeHtml(activeAgent || "")}">
        <article class="charlie-core-node ${activeAgent ? "is-routing" : ""}">
          <span class="charlie-core-orbit"></span>
          <strong>CHARLIE CORE</strong>
          <small>${escapeHtml(runnerStateLabel(runner.status))}</small>
          <em>${escapeHtml(shortMissionLine(activeMission, runner))}</em>
        </article>
        <div class="charlie-hero-metrics">
          ${runnerMetricMarkup("Runner", runnerStateLabel(runner.status), local.active ? "Local connected" : "Local not active")}
          ${runnerMetricMarkup("Current Agent", agentDisplayName(activeAgent || local.current_agent || latest.agent || "--"), local.current_action || latest.current_action || "--")}
          ${runnerMetricMarkup("Review", reviewReady ? "Ready" : blocked ? "Blocked" : "Not ready", blocked ? "Owner action needed" : "Evidence tracked")}
          ${runnerMetricMarkup("Evidence", evidenceStateForMission(activeMission), artifactStateForMission(activeMission))}
        </div>
      </div>
      <div class="charlie-agent-lane" aria-label="Selected CHARLIE CORE agent order">
      ${displayAgents.map((agent, index) => workflowNodeMarkup(agent, workflow, {
        activeAgent,
        blocked,
        reviewReady,
        index,
      })).join("")}
      </div>
      ${backflowEvents.length ? `<div class="charlie-flow-backflows">${backflowEvents.slice(0, 4).map(backflowLoopMarkup).join("")}</div>` : ""}
    `;
  }

  function renderActiveSummary() {
    if (!els.activeSummary) return;
    const runner = state.runnerStatus || {};
    const local = runner.local_runner || {};
    const activeMission = currentMissionForFlow();
    const reviewPacket = reviewPacketForMission(activeMission);
    const latest = (local.agent_ledger && local.agent_ledger.latest_stage) || {};
    const summary = latest.summary || reviewPacket.summary || (activeMission && (activeMission.raw_text || activeMission.title)) || runner.next_action || "No active local runner work is visible yet.";
    const blocked = activeMission && (activeMission.status === "blocked" || reviewPacket.review_status === "agent_blocked");
    els.activeSummary.innerHTML = `
      ${blocked ? blockedReviewBanner(reviewPacket) : ""}
      <dl class="charlie-mission-meta">
        <div><dt>Agent</dt><dd>${escapeHtml(agentDisplayName(local.current_agent || latest.agent || workflowActiveAgent(workflowForMission(activeMission)) || "--"))}</dd></div>
        <div><dt>Action</dt><dd>${escapeHtml(local.current_action || latest.current_action || local.last_result_status || "--")}</dd></div>
        <div><dt>Ledger</dt><dd>${escapeHtml(local.agent_ledger_path || "--")}</dd></div>
        <div><dt>Artifact</dt><dd>${escapeHtml(local.execution_artifact || "--")}</dd></div>
      </dl>
      <p>${escapeHtml(safeText(summary)).slice(0, 360)}</p>
      <details>
        <summary>Runner details</summary>
        <pre>${escapeHtml([
          `Agent: ${local.current_agent || latest.agent || "--"}`,
          `Action: ${local.current_action || latest.current_action || "--"}`,
          `Latest Stage: ${runnerLatestStageLine(local.agent_ledger)}`,
          `Stdout: ${shortOutput(local.stdout_tail || latest.stdout_tail)}`,
          `Stderr: ${shortOutput(local.stderr_tail || latest.stderr_tail)}`,
        ].join("\n"))}</pre>
      </details>
    `;
  }

  function currentMissionForFlow() {
    const runner = state.runnerStatus || {};
    return runner.active_mission
      || firstMissionFromList((state.commandCenter.queue || {}).approved)
      || firstMissionFromList(state.reviewMissions)
      || firstMissionFromList(state.missions)
      || null;
  }

  function firstMissionFromList(items) {
    return Array.isArray(items) && items.length ? items[0] : null;
  }

  function shortMissionLine(mission, runner) {
    if (mission && mission.mission_id) {
      return `${shortId(mission.mission_id)} | ${mission.urgency || "P2"} | ${mission.approval_level || "LEVEL 3"}`;
    }
    return (runner && runner.next_action) || "waiting for mission";
  }

  function workflowForMission(mission) {
    const workflow = mission && Array.isArray(mission.agent_workflow) ? mission.agent_workflow : [];
    if (workflow.length) return workflow;
    return AGENT_ORDER.map((agent) => ({agent, status: "pending"}));
  }

  function workflowDisplayOrder(workflow) {
    const selected = (Array.isArray(workflow) ? workflow : [])
      .map((entry) => normalizeAgent(entry && entry.agent))
      .filter(Boolean);
    const ordered = AGENT_ORDER.slice();
    const extras = selected.filter((agent) => !ordered.includes(agent));
    return [...ordered, ...extras];
  }

  function runnerMetricMarkup(label, value, detail) {
    return `
      <article class="charlie-runner-metric">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value || "--")}</strong>
        <small>${escapeHtml(detail || "")}</small>
      </article>
    `;
  }

  function stateLabel(missionStatus, runnerStatus) {
    const status = safeText(missionStatus || "").toLowerCase();
    if (!status || status === "no_mission") return "No mission";
    if (status === "pr_ready") return "Review ready";
    if (status === "blocked") return "Blocked";
    if (status === "paused" || status === "rejected") return status.replace(/_/g, " ");
    if (status === "in_progress") return "Running";
    const runnerText = safeText(runnerStatus || "").toLowerCase();
    if (runnerText.includes("stale")) return "Stale";
    return status.replace(/_/g, " ");
  }

  function runnerStateClass(missionStatus, runnerStatus) {
    const status = safeText(missionStatus || "").toLowerCase();
    const runnerText = safeText(runnerStatus || "").toLowerCase();
    if (!status || status === "no_mission") return "no-mission";
    if (runnerText.includes("stale")) return "stale";
    if (status === "blocked") return "blocked";
    if (status === "pr_ready") return "review-ready";
    if (status === "paused" || status === "rejected") return "stopped";
    if (status === "in_progress") return "running";
    return "stopped";
  }

  function evidenceStateForMission(mission) {
    const packet = reviewPacketForMission(mission);
    if (!mission) return "No mission";
    if (packet.visual_review || packet.test_evidence || packet.agent_execution) return "Captured";
    return "Pending";
  }

  function artifactStateForMission(mission) {
    const packet = reviewPacketForMission(mission);
    const changedFiles = Array.isArray(packet.changed_files) ? packet.changed_files.length : 0;
    const pr = packet.pr_url || (packet.links || {}).pr || "";
    if (pr && changedFiles) return `${changedFiles} files + PR`;
    if (pr) return "PR linked";
    if (changedFiles) return `${changedFiles} files`;
    return "Artifacts pending";
  }

  function workflowNodeMarkup(agent, workflow, context) {
    const item = workflow.find((entry) => normalizeAgent(entry.agent) === agent) || {agent, status: "pending"};
    const status = workflowNodeStatus(agent, item, context);
    const label = AGENT_LABELS[agent] || agent;
    return `
      <article class="charlie-flow-node is-${escapeHtml(status)}" data-agent="${escapeHtml(agent)}" style="--agent-index:${Number(context.index || 0)}">
        <span class="charlie-flow-pulse"></span>
        <strong>${escapeHtml(label)}</strong>
        <small>${escapeHtml(status.replace(/-/g, " "))}</small>
        <em>${escapeHtml(shortAgentSummary(item))}</em>
        <span class="charlie-flow-link" aria-hidden="true"></span>
      </article>
    `;
  }

  function workflowNodeStatus(agent, item, context) {
    const rawStatus = safeText(item.status || "pending").toLowerCase().replace(/_/g, "-");
    if (context.blocked && normalizeAgent((reviewPacketForMission(currentMissionForFlow()) || {}).blocked_agent) === agent) return "blocked";
    if (context.activeAgent === agent) return "active";
    if (context.reviewReady && agent === "reviewer") return "review-ready";
    if (rawStatus.includes("send") || rawStatus.includes("back")) return "send-back";
    if (["complete", "completed", "done", "pass", "passed"].includes(rawStatus)) return "complete";
    if (["blocked", "failed", "error"].includes(rawStatus)) return "blocked";
    return "pending";
  }

  function shortAgentSummary(item) {
    return safeText(item.summary || item.findings || item.current_action || item.next_action || "").slice(0, 96);
  }

  function normalizeAgent(value) {
    const text = safeText(value).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
    if (text === "qa" || text === "red_team" || text === "qa_redteam") return "qa_red_team";
    if (text === "product") return "product_architect";
    if (text === "idea") return "idea_expander";
    return text;
  }

  function latestLedgerAgent(ledger) {
    const latest = ledger && ledger.latest_stage ? ledger.latest_stage : {};
    return latest.agent || "";
  }

  function workflowActiveAgent(workflow) {
    const active = (Array.isArray(workflow) ? workflow : []).find((item) => {
      const status = safeText(item.status).toLowerCase();
      return ["active", "running", "in_progress", "working"].includes(status);
    });
    return active ? normalizeAgent(active.agent) : "";
  }

  function reviewPacketForMission(mission) {
    return ((mission || {}).metadata || {}).review_packet || {};
  }

  function backflowEventsForMission(mission) {
    const packet = reviewPacketForMission(mission);
    const execution = packet.agent_execution || {};
    return Array.isArray(packet.backflow_events) ? packet.backflow_events : (Array.isArray(execution.backflow_events) ? execution.backflow_events : []);
  }

  function backflowLoopMarkup(event) {
    return `
      <article class="charlie-return-loop">
        <strong>${escapeHtml(safeText(event.from_agent || "agent"))} return</strong>
        <span aria-hidden="true">Return</span>
        <em>${escapeHtml(safeText(event.to_agent || "builder"))}</em>
        <small>${escapeHtml(safeText(event.reason || "Send-back recorded"))}</small>
      </article>
    `;
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
    const queuePriority = queuePriorityValue(mission);
    const missionQueueClass = queueClass(mission);
    card.innerHTML = `
      <div class="charlie-mission-card-header">
        <div>
          <span class="status-pill">${safeText(mission.status || "unknown")}</span>
          <h3>${escapeHtml(title)}</h3>
        </div>
        <code>${escapeHtml(shortId(missionId))}</code>
      </div>
      <div class="charlie-card-tags">
        <span>${escapeHtml(queueClassLabel(missionQueueClass))}</span>
      </div>
      <p>${escapeHtml(safeText(mission.raw_text || title)).slice(0, 280)}</p>
      <div class="charlie-vault-summary">
        <strong>Mission Vault</strong>
        <span>Stage: ${escapeHtml(safeText(vault.mission_stage || "intake"))}</span>
        <span>Confidence target: ${escapeHtml(safeText(vault.confidence_target || "98% before release review"))}</span>
      </div>
      <div class="charlie-agent-strip" aria-label="Agent workflow">${workflow.map(agentBadge).join("")}</div>
      <div class="charlie-workflow-actions" aria-label="Mission workflow actions">
        <button type="button" data-agent-step="idea_expander">Idea Done</button>
        <button type="button" data-agent-step="product_architect">Product Done</button>
        <button type="button" data-agent-step="planner">Planner Done</button>
        <button type="button" data-agent-step="architect">Architect Done</button>
        <button type="button" data-agent-step="builder">Builder Done</button>
        <button type="button" data-agent-step="tester">Tester Done</button>
        <button type="button" data-agent-step="qa_red_team">QA Done</button>
        <button type="button" data-agent-step="reviewer">Reviewer Done</button>
      </div>
      <dl class="charlie-mission-meta">
        <div><dt>Queue</dt><dd>${escapeHtml(String(queuePriority))}</dd></div>
        <div><dt>Urgency</dt><dd>${escapeHtml(safeText(mission.urgency || "--"))}</dd></div>
        <div><dt>Type</dt><dd>${escapeHtml(safeText(mission.mission_type || "--"))}</dd></div>
        <div><dt>Approval</dt><dd>${escapeHtml(safeText(mission.approval_level || "--"))}</dd></div>
        <div><dt>Updated</dt><dd>${escapeHtml(formatDate(mission.updated_at))}</dd></div>
      </dl>
      <div class="charlie-mission-actions">
        <button type="button" data-queue-priority="${Math.max(1, queuePriority - 10)}">Earlier</button>
        <button type="button" data-queue-priority="${Math.min(999, queuePriority + 10)}">Later</button>
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
      ${mission.status === "new" ? newMissionEditMarkup(mission, vault) : ""}
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
    card.querySelectorAll("[data-queue-priority]").forEach((button) => {
      button.addEventListener("click", () => updateQueuePriority(missionId, button.dataset.queuePriority || queuePriority));
    });
    const editForm = card.querySelector("[data-new-mission-edit-form]");
    if (editForm) editForm.addEventListener("submit", (event) => updateNewMission(event, missionId, editForm));
    return card;
  }

  function queueClass(mission) {
    return safeText((mission && mission.queue_class) || "owner_work") || "owner_work";
  }

  function queueClassLabel(value) {
    if (value === "system_noise") return "System noise";
    if (value === "system_test") return "System test";
    if (value === "low_signal") return "Low signal";
    return "Owner work";
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
    const blocked = mission.status === "blocked" || reviewPacket.review_status === "agent_blocked";
    card.innerHTML = `
      <div class="charlie-mission-card-header">
        <div>
          <span class="status-pill">${escapeHtml(safeText(mission.status || "review"))}</span>
          <h3>${escapeHtml(title)}</h3>
        </div>
        <code>${escapeHtml(shortId(missionId))}</code>
      </div>
      ${blocked ? blockedReviewBanner(reviewPacket) : ""}
      <dl class="charlie-mission-meta">
        <div><dt>Local view</dt><dd>${localPreviewMarkup(localPreview, links)}</dd></div>
        <div><dt>PR / diff</dt><dd>${reviewLink(links.pr || links.diff || reviewPacket.pr_url || reviewPacket.diff_url)}</dd></div>
        <div><dt>Tests</dt><dd>${escapeHtml(firstReviewText(reviewPacket.test_evidence, "Not captured yet."))}</dd></div>
        <div><dt>Updated</dt><dd>${escapeHtml(formatDate(mission.updated_at))}</dd></div>
      </dl>
      <div class="charlie-agent-strip" aria-label="Review workflow">${workflow.map(agentBadge).join("")}</div>
      <p>${escapeHtml(safeText(reviewPacket.summary || mission.raw_text || title)).slice(0, 220)}</p>
      <details class="charlie-evidence-drawer" data-review-details="${escapeHtml(missionId)}"${state.openReviewDetails.has(missionId) || blocked || mission.status === "pr_ready" ? " open" : ""}>
        <summary>Evidence and details</summary>
        ${visualReviewMarkup(reviewPacket.visual_review || {}, localPreview, links)}
        <div class="charlie-review-packet" data-review-packet>${reviewPacketMarkup(mission, reviewPacket)}</div>
      </details>
      <div class="charlie-review-inline-decision">
        <label for="review_inline_comments_${escapeHtml(missionId)}">Owner comments</label>
        <textarea id="review_inline_comments_${escapeHtml(missionId)}" rows="3" data-review-comments placeholder="Optional approval or send-back note"></textarea>
        <label>
          Return stage
          <select data-review-target-stage>
            <option value="builder">Builder</option>
            <option value="tester">Tester</option>
            <option value="qa_red_team">QA / Red Team</option>
            <option value="product_reviewer">Product Reviewer</option>
            <option value="security_reviewer">Security Reviewer</option>
            <option value="evidence_reviewer">Evidence Reviewer</option>
            <option value="reviewer">Reviewer</option>
            <option value="planner">Planner</option>
            <option value="architect">Architect</option>
            <option value="council_synthesis">Council Synthesis</option>
            <option value="risk_agent">Risk Agent</option>
            <option value="technical_architect">Technical Architect</option>
            <option value="product_architect">Product Architect</option>
            <option value="idea_expander">Idea Expander</option>
          </select>
        </label>
      </div>
      <div class="charlie-mission-actions charlie-review-actions">
        <button type="button" data-open-owner-review>Open Review</button>
        <button type="button" data-review-refresh>Refresh Evidence</button>
        <button type="button" data-review-decision="approve_final_release">Approve Final</button>
        <button type="button" data-review-decision="send_back">Send Back</button>
        <button type="button" data-review-decision="pause">Pause</button>
        <button type="button" data-review-decision="reject">Reject</button>
        <button type="button" data-review-decision="mark_done">Mark Done</button>
      </div>
    `;
    card.querySelectorAll("[data-visual-review-open]").forEach((button) => {
      button.addEventListener("click", () => openVisualReviewOverlay(button));
    });
    const details = card.querySelector("[data-review-details]");
    if (details) {
      details.addEventListener("toggle", () => {
        if (details.open) state.openReviewDetails.add(missionId);
        else state.openReviewDetails.delete(missionId);
      });
    }
    card.querySelectorAll("[data-review-decision]").forEach((button) => {
      button.addEventListener("click", () => recordReviewDecision(missionId, button.dataset.reviewDecision, card));
    });
    const refreshButton = card.querySelector("[data-review-refresh]");
    if (refreshButton) refreshButton.addEventListener("click", () => loadReviewPacket(missionId, card));
    card.querySelector("[data-open-owner-review]").addEventListener("click", () => openOwnerReviewModal(mission));
    return card;
  }

  function agentBadge(agent) {
    const name = agentDisplayName(agent.agent || "agent");
    const status = safeText(agent.status || "pending");
    const statusClass = status.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    return `<span class="status-pill status-pill-muted charlie-agent-badge is-${escapeHtml(statusClass)}">${escapeHtml(name)}: ${escapeHtml(status)}</span>`;
  }

  function agentDisplayName(value) {
    const normalized = normalizeAgent(value);
    return AGENT_LABELS[normalized] || safeText(value);
  }

  function openOwnerReviewModal(mission) {
    if (!els.reviewModal || !els.reviewModalBody) return;
    const missionId = safeText(mission.mission_id);
    const title = safeText(mission.title || mission.raw_text || "Owner Review");
    const reviewPacket = reviewPacketForMission(mission);
    state.activeReviewMissionId = missionId;
    if (els.reviewModalTitle) els.reviewModalTitle.textContent = title;
    els.reviewModalBody.innerHTML = focusedReviewMarkup(mission, reviewPacket);
    els.reviewModal.classList.remove("hidden");
    document.body.classList.add("charlie-modal-open");
    els.reviewModalBody.querySelectorAll("[data-visual-review-open]").forEach((button) => {
      button.addEventListener("click", () => openVisualReviewOverlay(button));
    });
    const refreshButton = els.reviewModalBody.querySelector("[data-review-refresh]");
    if (refreshButton) refreshButton.addEventListener("click", () => loadReviewPacket(missionId, els.reviewModalBody));
    els.reviewModalBody.querySelectorAll("[data-review-decision]").forEach((button) => {
      button.addEventListener("click", () => recordReviewDecision(missionId, button.dataset.reviewDecision, els.reviewModalBody));
    });
    if (els.reviewModalClose) els.reviewModalClose.focus();
  }

  function closeOwnerReviewModal() {
    if (!els.reviewModal) return;
    els.reviewModal.classList.add("hidden");
    state.activeReviewMissionId = "";
    document.body.classList.remove("charlie-modal-open");
    if (els.reviewModalBody) els.reviewModalBody.innerHTML = "";
  }

  function focusedReviewMarkup(mission, reviewPacket) {
    const metadata = mission.metadata || {};
    const localPreview = reviewPacket.local_preview || {};
    const links = reviewPacket.links || {};
    return `
      ${mission.status === "blocked" || reviewPacket.review_status === "agent_blocked" ? blockedReviewBanner(reviewPacket) : ""}
      <div class="charlie-review-focus-grid">
        <section>
          <strong>Summary</strong>
          <p>${escapeHtml(safeText(reviewPacket.summary || mission.raw_text || "No summary captured yet."))}</p>
          ${visualReviewMarkup(reviewPacket.visual_review || {}, localPreview, links)}
          <details open>
            <summary>Review packet details</summary>
            <div class="charlie-review-packet" data-review-packet>${reviewPacketMarkup(mission, reviewPacket)}</div>
          </details>
          ${agentExecutionMarkup(reviewPacket.agent_execution || (metadata.agent_execution || {}), reviewPacket)}
        </section>
        <aside>
          <dl class="charlie-mission-meta">
            <div><dt>Local view</dt><dd>${localPreviewMarkup(localPreview, links)}</dd></div>
            <div><dt>PR / diff</dt><dd>${reviewLink(links.pr || links.diff || reviewPacket.pr_url || reviewPacket.diff_url)}</dd></div>
            <div><dt>Tests</dt><dd>${escapeHtml(firstReviewText(reviewPacket.test_evidence, "Not captured yet."))}</dd></div>
            <div><dt>Updated</dt><dd>${escapeHtml(formatDate(mission.updated_at))}</dd></div>
          </dl>
          <label for="review_comments_${escapeHtml(mission.mission_id)}">Owner comments</label>
          <textarea id="review_comments_${escapeHtml(mission.mission_id)}" rows="5" data-review-comments placeholder="Comments for final approval or send-back"></textarea>
          <label>
            Return stage
            <select data-review-target-stage>
              <option value="builder">Builder</option>
              <option value="tester">Tester</option>
              <option value="qa_red_team">QA / Red Team</option>
              <option value="product_reviewer">Product Reviewer</option>
              <option value="security_reviewer">Security Reviewer</option>
              <option value="evidence_reviewer">Evidence Reviewer</option>
              <option value="reviewer">Reviewer</option>
              <option value="planner">Planner</option>
              <option value="architect">Architect</option>
              <option value="council_synthesis">Council Synthesis</option>
              <option value="risk_agent">Risk Agent</option>
              <option value="technical_architect">Technical Architect</option>
              <option value="product_architect">Product Architect</option>
              <option value="idea_expander">Idea Expander</option>
            </select>
          </label>
          <button type="button" data-review-refresh>Refresh Evidence</button>
          <div class="charlie-mission-actions charlie-review-actions">
            <button type="button" data-review-decision="approve_final_release">Approve Final</button>
            <button type="button" data-review-decision="send_back">Send Back</button>
            <button type="button" data-review-decision="pause">Pause</button>
            <button type="button" data-review-decision="reject">Reject</button>
            <button type="button" data-review-decision="mark_done">Mark Done</button>
          </div>
        </aside>
      </div>
    `;
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

  function newMissionEditMarkup(mission, vault) {
    const mediaText = Array.isArray(mission.media_references)
      ? mission.media_references.map((item) => safeText(item.reference || item.label)).filter(Boolean).join("\n")
      : "";
    return `
      <details class="charlie-new-mission-edit">
        <summary>Edit new mission</summary>
        <form data-new-mission-edit-form>
          <label>Title<input name="title" type="text" maxlength="160" value="${escapeHtml(safeText(mission.title || ""))}"></label>
          <label>Concept<textarea name="raw_text" rows="4">${escapeHtml(safeText(mission.raw_text || ""))}</textarea></label>
          <label>Desired outcome<textarea name="desired_outcome" rows="3">${escapeHtml(safeText(vault.desired_outcome || ""))}</textarea></label>
          <label>Media / reference links<textarea name="media_references" rows="3" placeholder="Optional: one screenshot path, URL, or note per line">${escapeHtml(mediaText)}</textarea></label>
          <label>Add screenshots<input name="media_files" type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple data-new-mission-media-files></label>
          <label>Owner comment<textarea name="comment" rows="3" placeholder="Optional note to append before approval"></textarea></label>
          <div class="charlie-mission-actions">
            <button type="submit">Save Edits</button>
          </div>
        </form>
      </details>
    `;
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
      ${packet.review_status === "agent_blocked" ? blockedReviewBanner(packet) : ""}
      <strong>Summary</strong>
      <p>${escapeHtml(safeText(packet.summary || vault.desired_outcome || mission.raw_text || "Not captured yet."))}</p>
      <strong>Findings</strong>${listMarkup(packet.findings || workflowFindings(mission.agent_workflow), "No findings captured yet.")}
      <strong>Errors / bugs</strong>${listMarkup([...(packet.errors || []), ...(packet.bugs || [])], "No errors or bugs captured yet.")}
      <strong>Unresolved blockers</strong>${unresolvedBlockersMarkup(packet.unresolved_blockers || (packet.blocked_summary && packet.blocked_summary.unresolved_blockers))}
      <strong>Changed files</strong>${listMarkup(packet.changed_files, "No changed files captured yet.")}
      <strong>Agent execution</strong>${agentExecutionSummaryMarkup(packet.agent_execution || {})}
      <strong>Quality gates</strong>${qualityGateMarkup(packet.quality_gates)}
      <strong>QA / red-team evidence</strong>${listMarkup(packet.qa_evidence, "No QA/red-team evidence captured yet.")}
      <strong>Handoff reports</strong>${handoffReportMarkup(packet.handoff_reports)}
      <strong>Backflow</strong>${backflowMarkup(packet.backflow_events)}
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

  async function updateQueuePriority(missionId, priority) {
    if (!missionId) return;
    const parsed = Number.parseInt(priority, 10);
    if (!Number.isFinite(parsed) || parsed < 1 || parsed > 999) {
      setMessage("Queue priority must be between 1 and 999.", "error");
      return;
    }
    setMessage(`Updating queue priority to ${parsed}...`, "info");
    try {
      await fetchJson(`/api/charlie/build-relay/missions/${encodeURIComponent(missionId)}/queue`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          priority: parsed,
          notes: `Owner set mission queue priority to ${parsed} from CHARLIE Mission Control.`,
        }),
      });
      setMessage("Queue priority updated.", "success");
      await loadMissions();
    } catch (error) {
      setMessage(error.message || "Queue priority was not updated.", "error");
    }
  }

  async function loadReviewPacket(missionId, card) {
    if (!missionId || !card) return;
    setMessage("Loading review packet...", "info");
    try {
      const data = await fetchJson(`/api/charlie/build-relay/missions/${encodeURIComponent(missionId)}/review`);
      const container = card.querySelector("[data-review-packet]");
      if (container) container.innerHTML = reviewPacketDetailMarkup(data.review_packet || {});
      card.querySelectorAll("[data-visual-review-open]").forEach((button) => {
        button.addEventListener("click", () => openVisualReviewOverlay(button));
      });
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
      ${packet.review_status === "agent_blocked" ? blockedReviewBanner(packet) : ""}
      <p>${escapeHtml(safeText(packet.summary || "No summary captured yet."))}</p>
      <strong>Findings</strong>${listMarkup(packet.findings, "No findings captured yet.")}
      <strong>Errors / bugs</strong>${listMarkup([...(packet.errors || []), ...(packet.bugs || [])], "No errors or bugs captured yet.")}
      <strong>Unresolved blockers</strong>${unresolvedBlockersMarkup(packet.unresolved_blockers || (packet.blocked_summary && packet.blocked_summary.unresolved_blockers))}
      <strong>Changed files</strong>${listMarkup(packet.changed_files, "No changed files captured yet.")}
      <strong>Test evidence</strong>${listMarkup(packet.test_evidence, "No test evidence captured yet.")}
      <strong>Local preview</strong>${localPreviewDetailMarkup(packet.local_preview || {}, packet.links || {})}
      <strong>Visual Review</strong>${visualReviewMarkup(packet.visual_review || {}, packet.local_preview || {}, packet.links || {})}
      <strong>Agent execution</strong>${agentExecutionSummaryMarkup(packet.agent_execution || {})}
      <strong>Quality gates</strong>${qualityGateMarkup(packet.quality_gates)}
      <strong>QA / red-team evidence</strong>${listMarkup(packet.qa_evidence, "No QA/red-team evidence captured yet.")}
      <strong>Handoff reports</strong>${handoffReportMarkup(packet.handoff_reports)}
      <strong>Backflow</strong>${backflowMarkup(packet.backflow_events)}
      <strong>Release notes</strong>${listMarkup(packet.release_notes, "No release notes captured yet.")}
      <strong>Execution boundary</strong>
      <p>${escapeHtml(safeText(packet.execution_boundary || "Dashboard records review decisions only."))}</p>
    `;
  }

  function agentExecutionMarkup(execution, packet) {
    if (!execution || !Array.isArray(execution.stages) || !execution.stages.length) return "";
    return `
      <details class="charlie-agent-execution" open>
        <summary>Agent execution timeline</summary>
        ${agentExecutionSummaryMarkup(execution)}
        <strong>Quality gates</strong>${qualityGateMarkup(packet.quality_gates || execution.quality_gates)}
      <strong>Backflow</strong>${backflowMarkup(packet.backflow_events || execution.backflow_events)}
      <strong>Unresolved blockers</strong>${unresolvedBlockersMarkup(packet.unresolved_blockers || execution.unresolved_blockers)}
      </details>
    `;
  }

  function agentExecutionSummaryMarkup(execution) {
    const stages = Array.isArray(execution.stages) ? execution.stages : [];
    if (!stages.length) return '<p class="charlie-muted">No agent execution ledger captured yet.</p>';
    return `<div class="charlie-agent-timeline">${stages.map((stage) => `
      <article class="charlie-agent-stage">
        <div><strong>${escapeHtml(safeText(stage.agent || "agent"))}</strong> <span>${escapeHtml(safeText(stage.status || "unknown"))}</span> <span>attempt ${escapeHtml(safeText(stage.attempt || 1))}</span></div>
        <p>${escapeHtml(safeText(stage.current_action || (stage.quality_gate && stage.quality_gate.reason) || ""))}</p>
        <dl class="charlie-mission-meta">
          <div><dt>Commands</dt><dd>${escapeHtml(firstReviewText(stage.commands_run, "--"))}</dd></div>
          <div><dt>Files</dt><dd>${escapeHtml(firstReviewText(stage.files_inspected || stage.changed_files, "--"))}</dd></div>
          <div><dt>Gate</dt><dd>${escapeHtml(safeText(stage.quality_gate && stage.quality_gate.reason || "--"))}</dd></div>
        </dl>
        ${(stage.stdout_tail || stage.stderr_tail) ? `<pre>${escapeHtml([stage.stdout_tail, stage.stderr_tail].filter(Boolean).join("\n"))}</pre>` : ""}
      </article>
    `).join("")}</div>`;
  }

  function qualityGateMarkup(items) {
    const gates = Array.isArray(items) ? items : [];
    if (!gates.length) return '<p class="charlie-muted">No quality gates captured yet.</p>';
    return `<ul>${gates.map((gate) => `<li>${escapeHtml(safeText(gate.agent || "agent"))}: ${escapeHtml(safeText(gate.reason || gate.status || "checked"))}</li>`).join("")}</ul>`;
  }

  function handoffReportMarkup(reports) {
    const entries = reports && typeof reports === "object" ? Object.entries(reports) : [];
    if (!entries.length) return '<p class="charlie-muted">No standardized handoff reports captured yet.</p>';
    return `<div class="charlie-agent-timeline">${entries.map(([agent, report]) => `
      <article class="charlie-agent-stage">
        <div><strong>${escapeHtml(agent)}</strong> <span>${escapeHtml(safeText(report.status || "complete"))}</span></div>
        <p>${escapeHtml(safeText(report.summary || ""))}</p>
        <dl class="charlie-mission-meta">
          <div><dt>Commands</dt><dd>${escapeHtml(firstReviewText(report.commands_run, "--"))}</dd></div>
          <div><dt>Files</dt><dd>${escapeHtml(firstReviewText(report.files_inspected || report.changed_files, "--"))}</dd></div>
          <div><dt>Next</dt><dd>${escapeHtml(safeText(report.next_action || "--"))}</dd></div>
          <div><dt>Risks</dt><dd>${escapeHtml(firstReviewText(report.risks, "--"))}</dd></div>
        </dl>
      </article>
    `).join("")}</div>`;
  }

  function backflowMarkup(items) {
    const events = Array.isArray(items) ? items : [];
    if (!events.length) return '<p class="charlie-muted">No agent backflow was needed.</p>';
    return `<div class="charlie-backflow-list">${events.map((event) => {
      const blockers = Array.isArray(event.unresolved_blockers) ? event.unresolved_blockers : [];
      return `<article class="charlie-return-loop">
        <strong>${escapeHtml(safeText(event.from_agent || "agent"))}</strong>
        <span aria-hidden="true">Return</span>
        <em>${escapeHtml(safeText(event.to_agent || "agent"))}</em>
        <small>${escapeHtml(safeText(event.reason || "Send-back recorded"))}</small>
        ${blockers.length ? unresolvedBlockersMarkup(blockers) : ""}
      </article>`;
    }).join("")}</div>`;
  }

  async function analyzeImprovements() {
    setMessage("Analyzing CHARLIE improvement patterns...", "info");
    try {
      await fetchJson("/api/charlie/core/improvements/analyze", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({limit: 50}),
      });
      setMessage("Improvement proposals refreshed.", "success");
      await loadMissions();
    } catch (error) {
      setMessage(error.message || "Improvement analysis was not recorded.", "error");
    }
  }

  async function recordImprovementDecision(proposalId, decision, card) {
    if (!proposalId || !decision || !card) return;
    const comments = safeText(card.querySelector("[data-improvement-comments]") && card.querySelector("[data-improvement-comments]").value).trim();
    setMessage(`Recording improvement decision ${decision}...`, "info");
    try {
      await fetchJson(`/api/charlie/core/improvements/${encodeURIComponent(proposalId)}/decision`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({decision, comments}),
      });
      setMessage("Improvement decision recorded.", "success");
      await loadMissions();
    } catch (error) {
      setMessage(error.message || "Improvement decision was not recorded.", "error");
    }
  }

  function unresolvedBlockersMarkup(items) {
    const blockers = Array.isArray(items) ? items.filter(Boolean) : [];
    if (!blockers.length) return '<p class="charlie-muted">No unresolved blockers captured.</p>';
    return `<div class="charlie-unresolved-blockers">${blockers.slice(0, 6).map((item) => {
      if (typeof item === "string") return `<article><strong>Blocker</strong><span>${escapeHtml(item)}</span></article>`;
      const severity = safeText(item.severity || "medium").toUpperCase();
      const location = [item.file, item.line].filter(Boolean).join(":");
      return `
        <article>
          <strong>${escapeHtml(severity)}</strong>
          <span>${escapeHtml(safeText(item.finding || item.message || item.summary || "Unresolved issue"))}</span>
          ${location ? `<small>${escapeHtml(location)}</small>` : ""}
        </article>
      `;
    }).join("")}</div>`;
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
      planned: ["idea_expander", "product_architect", "planner", "architect"],
      review_ready: ["idea_expander", "product_architect", "planner", "architect", "builder", "tester", "qa_red_team", "reviewer"],
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

  async function updateNewMission(event, missionId, form) {
    event.preventDefault();
    if (!missionId || !form) return;
    const formData = new FormData(form);
    setMessage("Saving mission edits...", "info");
    try {
      const mediaFiles = form.querySelector("[data-new-mission-media-files]");
      const mediaReferences = [
        ...parseMediaReferences(formData.get("media_references")),
        ...(await mediaFilesToReferences(mediaFiles && mediaFiles.files, "dashboard_edit_file")),
      ];
      await fetchJson(`/api/charlie/build-relay/missions/${encodeURIComponent(missionId)}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          updates: {
            title: safeText(formData.get("title")).trim(),
            raw_text: safeText(formData.get("raw_text")).trim(),
            desired_outcome: safeText(formData.get("desired_outcome")).trim(),
            media_references: mediaReferences,
          },
          comment: safeText(formData.get("comment")).trim(),
        }),
      });
      setMessage("Mission edits saved.", "success");
      await loadMissions();
    } catch (error) {
      setMessage(error.message || "Mission edits were not saved.", "error");
    }
  }

  async function mediaFilesToReferences(fileList, source) {
    const files = Array.from(fileList || []);
    if (!files.length) return [];
    const images = files.filter((file) => IMAGE_MEDIA_TYPES.has(file.type));
    if (images.length !== files.length) {
      setMessage("Only PNG, JPG, WebP, or GIF screenshots can be attached here.", "error");
      throw new Error("Only PNG, JPG, WebP, or GIF screenshots can be attached here.");
    }
    if (images.length > MAX_MEDIA_ITEMS) {
      const message = `Mission media is limited to ${MAX_MEDIA_ITEMS} images for this no-migration version.`;
      setMessage(message, "error");
      throw new Error(message);
    }
    const references = [];
    for (const file of images) {
      if (file.size > MAX_MEDIA_BYTES) {
        const message = `${file.name || "Screenshot"} is too large. Keep each image under 650 KB for mission metadata storage.`;
        setMessage(message, "error");
        throw new Error(message);
      }
      references.push({
        label: file.name || `Mission screenshot ${references.length + 1}`,
        reference: await readFileAsDataUrl(file),
        media_type: "image",
        source,
      });
    }
    return references;
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

  function localPreviewMarkup(localPreview, links) {
    const preview = localPreview || {};
    const linkMap = links || {};
    const url = safeText(preview.url || linkMap.local_preview).trim();
    if (url) return reviewLink(url);
    const path = safeText(preview.path).trim();
    if (path) return escapeHtml(path);
    const command = safeText(preview.command).trim();
    if (command) return `<span class="charlie-muted">Preview URL not captured. Command: ${escapeHtml(command)}</span>`;
    return '<span class="charlie-muted">Not captured</span>';
  }

  function localPreviewDetailMarkup(localPreview, links) {
    const preview = localPreview || {};
    const linkMap = links || {};
    const url = safeText(preview.url || linkMap.local_preview).trim();
    const command = safeText(preview.command).trim();
    const path = safeText(preview.path).trim();
    const status = safeText(preview.status || (url ? "captured" : "not_captured"));
    const message = safeText(preview.message || (url ? "Mission-specific local preview URL captured." : "No mission-specific local preview URL was captured."));
    return `
      <dl class="charlie-mission-meta">
        <div><dt>Status</dt><dd>${escapeHtml(status)}</dd></div>
        <div><dt>Open</dt><dd>${url ? reviewLink(url) : '<span class="charlie-muted">Not captured</span>'}</dd></div>
        <div><dt>Command</dt><dd>${command ? escapeHtml(command) : '<span class="charlie-muted">Not captured</span>'}</dd></div>
        <div><dt>Artifact</dt><dd>${path ? escapeHtml(path) : '<span class="charlie-muted">Not captured</span>'}</dd></div>
      </dl>
      <p class="charlie-muted">${escapeHtml(message)}</p>
    `;
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

  function visualReviewMarkup(visualReview, localPreview, links) {
    const review = visualReview && typeof visualReview === "object" ? visualReview : {};
    const media = Array.isArray(review.media) ? review.media.filter(Boolean) : [];
    const preview = review.local_preview && typeof review.local_preview === "object" ? review.local_preview : localPreview;
    const status = safeText(review.status || "not_available");
    const summary = safeText(review.summary || "No visual review packet was captured for this mission.");
    const stageEvidence = Array.isArray(review.stage_evidence) ? review.stage_evidence.filter(Boolean) : [];
    const captureSource = safeText(review.capture_source || (review.capture || {}).capture_source || "");
    const generatedPacket = captureSource === "generated_owner_review_packet" || /control dashboard preview not mission visual/i.test(summary);
    const visualLabel = generatedPacket ? "Generated owner packet, not live screenshot" : "Mission visual evidence";
    return `
      <section class="charlie-visual-review" aria-label="Visual Review">
        <div class="charlie-visual-review-header">
          <div>
            <strong>Visual Review</strong>
            <span>${escapeHtml(status.replace(/_/g, " "))}</span>
            <small>${escapeHtml(visualLabel)}</small>
          </div>
          ${localPreviewMarkup(preview || {}, links || {})}
        </div>
        ${media.length ? `<div class="charlie-visual-review-media">${media.map(visualReviewMediaMarkup).join("")}</div>` : `<p class="charlie-muted">${escapeHtml(summary)}</p>`}
        ${stageEvidence.length ? `<div class="charlie-visual-stage-evidence">${stageEvidence.slice(0, 4).map((item) => `<span>${escapeHtml(safeText(item.agent || "agent"))}: ${escapeHtml(safeText(item.summary || ""))}</span>`).join("")}</div>` : ""}
      </section>
    `;
  }

  function visualReviewMediaMarkup(item) {
    const label = safeText(item.label || item.filename || "Review media");
    const reference = safeText(item.reference || item.url || "");
    const mediaType = safeText(item.media_type || "image");
    if (!reference) return "";
    const thumbnail = mediaType === "video"
      ? `<video src="${escapeHtml(reference)}" muted playsinline preload="metadata"></video>`
      : `<img src="${escapeHtml(reference)}" alt="${escapeHtml(label)}" loading="lazy">`;
    return `
      <button type="button" class="charlie-visual-thumbnail" data-visual-review-open data-media-src="${escapeHtml(reference)}" data-media-label="${escapeHtml(label)}" data-media-type="${escapeHtml(mediaType)}">
        ${thumbnail}
        <span>${escapeHtml(label)}</span>
      </button>
    `;
  }

  function blockedReviewBanner(packet) {
    const execution = packet.agent_execution || {};
    const summary = packet.blocked_summary || {};
    const blockedAgent = packet.blocked_agent || execution.blocked_agent || "agent";
    const blockedReason = packet.blocked_reason || execution.blocked_reason || firstReviewText(packet.errors, "Blocked before owner review.");
    const backflowEvents = Array.isArray(packet.backflow_events) ? packet.backflow_events : (Array.isArray(execution.backflow_events) ? execution.backflow_events : []);
    const attemptsValue = summary.send_back_attempts !== undefined ? Number(summary.send_back_attempts) : backflowEvents.length;
    const attempts = attemptsValue ? `${attemptsValue} send-back attempt${attemptsValue === 1 ? "" : "s"} before block` : "No automatic send-back before block";
    const lastStage = safeText(summary.last_successful_stage || "");
    const recommended = safeText(packet.recommended_next_action || summary.recommended_action || "Use Send Back after reviewing the blockers below.");
    const blockers = packet.unresolved_blockers || summary.unresolved_blockers || execution.unresolved_blockers || [];
    return `
      <div class="charlie-blocked-banner" role="status">
        <strong>Blocked at ${escapeHtml(blockedAgent)}</strong>
        <span>${escapeHtml(blockedReason)}</span>
        <small>${escapeHtml(attempts)}${lastStage ? ` | Last passed: ${escapeHtml(lastStage)}` : ""}</small>
        ${unresolvedBlockersMarkup(blockers)}
        <small>${escapeHtml(recommended)}</small>
      </div>
    `;
  }

  function openVisualReviewOverlay(button) {
    if (!button) return;
    closeVisualReviewOverlay();
    const src = safeText(button.dataset.mediaSrc).trim();
    if (!src) return;
    const label = safeText(button.dataset.mediaLabel || "Visual review media");
    const mediaType = safeText(button.dataset.mediaType || "image");
    const overlay = document.createElement("div");
    overlay.className = "charlie-visual-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", label);
    const media = mediaType === "video"
      ? `<video src="${escapeHtml(src)}" controls autoplay></video>`
      : `<img src="${escapeHtml(src)}" alt="${escapeHtml(label)}">`;
    overlay.innerHTML = `
      <div class="charlie-visual-overlay-panel">
        <button type="button" class="charlie-visual-overlay-close" aria-label="Close visual review">Close</button>
        ${media}
        <strong>${escapeHtml(label)}</strong>
      </div>
    `;
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) closeVisualReviewOverlay();
    });
    overlay.querySelector(".charlie-visual-overlay-close").addEventListener("click", closeVisualReviewOverlay);
    document.body.appendChild(overlay);
    overlay.querySelector(".charlie-visual-overlay-close").focus();
  }

  function closeVisualReviewOverlay() {
    document.querySelectorAll(".charlie-visual-overlay").forEach((overlay) => overlay.remove());
  }

  function queuePriorityValue(mission) {
    const direct = Number.parseInt(mission && mission.queue_priority, 10);
    if (Number.isFinite(direct) && direct >= 1 && direct <= 999) return direct;
    const nested = Number.parseInt(mission && mission.queue && mission.queue.priority, 10);
    if (Number.isFinite(nested) && nested >= 1 && nested <= 999) return nested;
    return 100;
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
  if (els.addMission && els.createForm) {
    els.addMission.addEventListener("click", () => {
      const isCollapsed = els.createForm.classList.toggle("is-collapsed");
      els.addMission.setAttribute("aria-expanded", String(!isCollapsed));
      if (!isCollapsed && els.newTitle) els.newTitle.focus();
    });
  }
  if (els.improvementsAnalyze) els.improvementsAnalyze.addEventListener("click", analyzeImprovements);
  if (els.filter) els.filter.addEventListener("change", loadMissions);
  if (els.createForm) els.createForm.addEventListener("submit", createMission);
  if (els.reviewModalClose) els.reviewModalClose.addEventListener("click", closeOwnerReviewModal);
  if (els.reviewModal) {
    els.reviewModal.addEventListener("click", (event) => {
      if (event.target === els.reviewModal) closeOwnerReviewModal();
    });
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeVisualReviewOverlay();
      closeOwnerReviewModal();
    }
  });
  setupMediaCapture();
  loadMissions();
  window.setInterval(loadMissions, AUTO_REFRESH_MS);
})();
