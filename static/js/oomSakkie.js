(function () {
  const form = document.getElementById("oom_form");
  const input = document.getElementById("oom_text");
  const statusBadge = document.getElementById("oom_status");
  const statusText = document.getElementById("oom_status_text");
  const presenceOrb = document.getElementById("oom_presence_orb");
  const presenceLine = document.getElementById("oom_presence_line");
  const agentControllerState = document.getElementById("oom_agent_controller_state");
  const activeAgentWorkspace = document.getElementById("oom_active_agent_workspace");
  const activeAgentName = document.getElementById("oom_active_agent_name");
  const activeAgentTitle = document.getElementById("oom_active_agent_title");
  const activeAgentDetail = document.getElementById("oom_active_agent_detail");
  const activeAgentGuard = document.getElementById("oom_active_agent_guard");
  const agentHandoffLane = document.getElementById("oom_agent_handoff_lane");
  const agentCrewSequence = document.getElementById("oom_agent_crew_sequence");
  const userText = document.getElementById("oom_user_text");
  const answer = document.getElementById("oom_answer");
  const warnings = document.getElementById("oom_warnings");
  const safetyNotes = document.getElementById("oom_safety_notes");
  const links = document.getElementById("oom_links");
  const traceId = document.getElementById("oom_trace_id");
  const toolUsed = document.getElementById("oom_tool_used");
  const riskLevel = document.getElementById("oom_risk_level");
  const routeSource = document.getElementById("oom_route_source");
  const answerSource = document.getElementById("oom_answer_source");
  const pipelineState = document.getElementById("oom_pipeline_state");
  const intentConfidence = document.getElementById("oom_intent_confidence");
  const intentReason = document.getElementById("oom_intent_reason");
  const voiceButton = document.getElementById("oom_voice_button");
  const voiceAskButton = document.getElementById("oom_voice_ask_button");
  const voiceStatus = document.getElementById("oom_voice_status");
  const voiceLoopCounter = document.getElementById("oom_voice_loop_counter");
  const cancelVoiceSendButton = document.getElementById("oom_cancel_voice_send");
  const stopConversationButton = document.getElementById("oom_stop_conversation");
  const voiceChecks = document.getElementById("oom_voice_checks");
  const voiceEvents = document.getElementById("oom_voice_events");
  const clearVoiceEvents = document.getElementById("oom_clear_voice_events");
  const speakAnswerButton = document.getElementById("oom_speak_answer");
  const stopSpeechButton = document.getElementById("oom_stop_speech");
  const autoSpeak = document.getElementById("oom_auto_speak");
  const continueConversation = document.getElementById("oom_continue_conversation");
  const reviewSummary = document.getElementById("oom_review_summary");
  const reviewAdvisor = document.getElementById("oom_review_advisor");
  const refreshAdvisor = document.getElementById("oom_refresh_advisor");
  const learningAdvisor = document.getElementById("oom_learning_advisor");
  const learningPacket = document.getElementById("oom_learning_packet");
  const refreshLearning = document.getElementById("oom_refresh_learning");
  const runLearningAnalysis = document.getElementById("oom_run_learning_analysis");
  const implementationQueue = document.getElementById("oom_implementation_queue");
  const refreshImplementationQueue = document.getElementById("oom_refresh_implementation_queue");
  const workbenchNextAction = document.getElementById("oom_workbench_next_action");
  const buildRequests = document.getElementById("oom_build_requests");
  const forgeHandoff = document.getElementById("oom_forge_handoff");
  const refreshBuildRequests = document.getElementById("oom_refresh_build_requests");
  const patchBuildRequestId = document.getElementById("oom_patch_build_request_id");
  const patchProposalText = document.getElementById("oom_patch_proposal_text");
  const recordPatchProposalButton = document.getElementById("oom_record_patch_proposal");
  const patchProposals = document.getElementById("oom_patch_proposals");
  const refreshPatchProposals = document.getElementById("oom_refresh_patch_proposals");
  const deployPatchProposalId = document.getElementById("oom_deploy_patch_proposal_id");
  const deployVerificationSummary = document.getElementById("oom_deploy_verification_summary");
  const approveManualDeployButton = document.getElementById("oom_approve_manual_deploy");
  const deferDeployButton = document.getElementById("oom_defer_deploy");
  const deployDecisions = document.getElementById("oom_deploy_decisions");
  const refreshDeployDecisions = document.getElementById("oom_refresh_deploy_decisions");
  const toolCatalog = document.getElementById("oom_tool_catalog");
  const refreshTools = document.getElementById("oom_refresh_tools");
  const policyStatus = document.getElementById("oom_policy_status");
  const refreshPolicy = document.getElementById("oom_refresh_policy");
  const agentCrew = document.getElementById("oom_agent_crew");
  const refreshAgents = document.getElementById("oom_refresh_agents");
  const agentRoadmap = document.getElementById("oom_agent_roadmap");
  const refreshAgentRoadmap = document.getElementById("oom_refresh_agent_roadmap");
  const requestSentinelDryRunButton = document.getElementById("oom_request_sentinel_dry_run");
  const requestPrismDryRunButton = document.getElementById("oom_request_prism_dry_run");
  const agentDryRunRequests = document.getElementById("oom_agent_dry_run_requests");
  const refreshAgentDryRunRequests = document.getElementById("oom_refresh_agent_dry_run_requests");
  const agentDryRunHandoff = document.getElementById("oom_agent_dry_run_handoff");
  const agentDryRunResultRequestId = document.getElementById("oom_agent_dry_run_result_request_id");
  const agentDryRunResultText = document.getElementById("oom_agent_dry_run_result_text");
  const agentDryRunResultFindings = document.getElementById("oom_agent_dry_run_result_findings");
  const recordAgentDryRunResultButton = document.getElementById("oom_record_agent_dry_run_result");
  const agentResultReviews = document.getElementById("oom_agent_result_reviews");
  const refreshAgentResultReviews = document.getElementById("oom_refresh_agent_result_reviews");
  const agentLearningLedger = document.getElementById("oom_agent_learning_ledger");
  const refreshAgentLearningLedger = document.getElementById("oom_refresh_agent_learning_ledger");
  const recentTraces = document.getElementById("oom_recent_traces");
  const refreshTraces = document.getElementById("oom_refresh_traces");
  const traceSearch = document.getElementById("oom_trace_search");
  const clearTraceSearch = document.getElementById("oom_clear_trace_search");
  const quickAskButtons = Array.from(document.querySelectorAll("[data-quick-ask]"));
  const reviewFilterButtons = Array.from(document.querySelectorAll("[data-review-filter]"));
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const speechSynthesisApi = window.speechSynthesis || null;
  const MAX_CONTINUE_TURNS = 5;
  const MAX_VOICE_EVENTS = 12;
  const SESSION_STORAGE_KEY = "oom_sakkie_session_id";
  let activeReviewFilter = "all";
  let traceSearchTimer = null;
  let recognition = null;
  let isListening = false;
  let voiceAutoSubmitMode = false;
  let voiceAutoSubmitTimer = null;
  let lastAnswerText = "";
  let speechUtterance = null;
  let speechRunId = 0;
  let voiceLoopTurnCount = 0;
  let voiceEventLog = [];
  let latestBuildRequestsData = null;
  let latestPatchProposalsData = null;
  let latestDeployDecisionsData = null;
  let latestAgentDryRunRequestsData = null;
  let latestAgentDryRunResultsData = null;
  const feedbackOptions = [
    ["", "Mark review"],
    ["correct", "Correct"],
    ["wrong_tool", "Wrong tool"],
    ["stale_or_missing_data", "Stale/missing data"],
    ["bad_wording", "Bad wording"],
    ["needs_follow_up", "Needs follow-up"],
  ];

  function setStatus(value, state) {
    statusText.textContent = value;
    if (statusBadge && state) statusBadge.dataset.state = state;
    setPresenceState(state || "idle", value);
  }

  function setPresenceState(state, label) {
    const normalized = state || "idle";
    const lines = {
      idle: "Standing by for a read-only farm check.",
      listening: "Listening now. One utterance at a time.",
      checking: "Checking the farm systems.",
      answered: "Answer ready.",
      speaking: "Speaking. Mic is paused.",
      blocked: "Blocked safely. No action was taken.",
      clarifying: "I need a clearer target before checking.",
      error: "Something failed. No farm action was taken.",
    };
    if (presenceOrb) presenceOrb.dataset.state = normalized;
    if (presenceLine) presenceLine.textContent = lines[normalized] || label || lines.idle;
  }

  function renderAgentActivity(data) {
    const activity = (data && data.agent_activity) || null;
    if (!activeAgentWorkspace || !activeAgentName || !activeAgentTitle || !activeAgentDetail || !activeAgentGuard) return;
    if (!activity || !activity.active_agent) {
      activeAgentWorkspace.dataset.agent = "none";
      if (presenceOrb) presenceOrb.dataset.agent = "none";
      if (agentControllerState) agentControllerState.textContent = "Controller standing by";
      activeAgentName.textContent = "No specialist workspace open";
      activeAgentTitle.textContent = "Ask a question to open a read-only workspace.";
      activeAgentDetail.textContent = "Specialists are visible here before they become live dispatch agents.";
      activeAgentGuard.textContent = "dispatch off | writes off";
      renderAgentHandoffLane([]);
      renderAgentCrewSequence([]);
      return;
    }

    const agent = activity.active_agent || {};
    const workspace = activity.workspace || {};
    const safety = activity.safety || {};
    const slug = agent.slug || "none";
    const color = agent.color || "white";
    activeAgentWorkspace.dataset.agent = color;
    if (presenceOrb) presenceOrb.dataset.agent = color;
    if (agentControllerState) agentControllerState.textContent = `Coordinating ${agent.name || slug}`;
    activeAgentName.textContent = `${agent.name || slug} | ${agent.personality || "specialist"}`;
    activeAgentTitle.textContent = workspace.title || `${agent.name || "Agent"} workspace`;
    activeAgentDetail.textContent = `${workspace.state || "reviewing"} via ${workspace.tool_name || "read-only tool"}; ${workspace.reason || "routing"}.`;
    activeAgentGuard.textContent = `dispatch ${safety.dispatch_enabled ? "on" : "off"} | loops ${safety.autonomous_loops_enabled ? "on" : "off"} | writes ${safety.writes ? "on" : "off"}`;
    renderAgentHandoffLane(activity.handoff_lane || []);
    renderAgentCrewSequence(activity.crew_sequence || []);
  }

  function renderAgentHandoffLane(items) {
    if (!agentHandoffLane) return;
    agentHandoffLane.innerHTML = "";
    if (!items || !items.length) {
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = "Handoff lane opens after a read-only check.";
      agentHandoffLane.appendChild(empty);
      return;
    }
    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "oom-agent-handoff-card";
      const step = document.createElement("span");
      const actor = document.createElement("strong");
      const detail = document.createElement("p");
      const status = document.createElement("code");
      step.textContent = item.step || "step";
      actor.textContent = item.actor || "Unknown";
      detail.textContent = item.detail || "";
      status.textContent = item.status || "visible";
      card.appendChild(step);
      card.appendChild(actor);
      card.appendChild(detail);
      card.appendChild(status);
      agentHandoffLane.appendChild(card);
    });
  }

  function renderAgentCrewSequence(items) {
    if (!agentCrewSequence) return;
    agentCrewSequence.innerHTML = "";
    if (!items || !items.length) {
      agentCrewSequence.hidden = true;
      return;
    }
    agentCrewSequence.hidden = false;
    const heading = document.createElement("p");
    heading.className = "oom-agent-sequence-heading";
    heading.textContent = "Planned specialist sequence";
    agentCrewSequence.appendChild(heading);
    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "oom-agent-sequence-card";
      card.dataset.agent = item.color || "white";
      const order = document.createElement("span");
      const name = document.createElement("strong");
      const detail = document.createElement("p");
      const guard = document.createElement("code");
      order.textContent = `Step ${item.order || "?"}`;
      name.textContent = `${item.name || item.slug || "Agent"} | ${item.personality || "specialist"}`;
      detail.textContent = item.would_inspect || item.role || "planned read-only review";
      guard.textContent = `runs ${item.runs_agent ? "yes" : "no"} | writes ${item.writes ? "yes" : "no"}`;
      card.appendChild(order);
      card.appendChild(name);
      card.appendChild(detail);
      card.appendChild(guard);
      agentCrewSequence.appendChild(card);
    });
  }

  function prettySource(value) {
    const labels = {
      rule: "Rule",
      llm_router: "LLM router",
      deterministic: "Deterministic",
      llm_composer: "LLM composer",
      capability: "Capability",
      action_guard: "Action guard",
      local: "Local",
      unknown: "Unknown",
      empty: "Empty",
      answered: "Answered",
      blocked: "Blocked",
      needs_clarification: "Needs clarification",
      needs_input: "Needs input",
      error: "Error",
    };
    return labels[value] || value || "Waiting";
  }

  function renderPipeline(data) {
    const pipeline = (data && data.pipeline) || {};
    const intent = (data && data.intent) || {};
    if (routeSource) routeSource.textContent = prettySource(pipeline.route_source);
    if (answerSource) answerSource.textContent = prettySource(pipeline.answer_source);
    if (pipelineState) pipelineState.textContent = prettySource(pipeline.state);
    if (intentConfidence) {
      const confidence = Number(intent.confidence);
      intentConfidence.textContent = Number.isFinite(confidence) ? confidence.toFixed(2) : "None";
    }
    if (intentReason) intentReason.textContent = intent.reason || "None";
  }

  function resetPipelineForCheck() {
    if (routeSource) routeSource.textContent = "Routing";
    if (answerSource) answerSource.textContent = "Waiting";
    if (pipelineState) pipelineState.textContent = "Checking";
    if (intentConfidence) intentConfidence.textContent = "None";
    if (intentReason) intentReason.textContent = "None";
  }

  function getSessionId() {
    try {
      const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
      if (existing) return existing;
      const generated = `kiosk-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      window.localStorage.setItem(SESSION_STORAGE_KEY, generated);
      return generated;
    } catch (error) {
      return "";
    }
  }

  function renderLinks(items) {
    links.innerHTML = "";
    (items || []).forEach((item) => {
      const anchor = document.createElement("a");
      anchor.href = item.href || "#";
      anchor.textContent = item.label || item.href || "Open";
      links.appendChild(anchor);
    });
  }

  function renderWarnings(items) {
    warnings.innerHTML = "";
    if (!items || !items.length) {
      warnings.hidden = true;
      return;
    }
    warnings.hidden = false;
    items.forEach((item) => {
      const line = document.createElement("p");
      line.textContent = item;
      warnings.appendChild(line);
    });
  }

  function renderSafetyNotes(items) {
    if (!safetyNotes) return;
    safetyNotes.innerHTML = "";
    if (!items || !items.length) {
      safetyNotes.hidden = true;
      return;
    }
    safetyNotes.hidden = false;
    items.forEach((item) => {
      const line = document.createElement("p");
      line.textContent = item;
      safetyNotes.appendChild(line);
    });
  }

  function renderVoiceReadiness() {
    if (!voiceChecks) return;
    voiceChecks.innerHTML = "";
    const checks = [
      {
        label: "Secure origin",
        ok: window.isSecureContext,
        detail: window.isSecureContext ? "ready" : "needs HTTPS or localhost",
      },
      {
        label: "Speech input",
        ok: !!SpeechRecognition,
        detail: SpeechRecognition ? "available" : "not available",
      },
      {
        label: "Browser TTS",
        ok: !!speechSynthesisApi,
        detail: speechSynthesisApi ? "available" : "not available",
      },
    ];

    checks.forEach((check) => {
      const item = document.createElement("span");
      item.className = check.ok ? "oom-voice-check-ready" : "oom-voice-check-blocked";
      item.textContent = `${check.label}: ${check.detail}`;
      voiceChecks.appendChild(item);
    });
  }

  function setVoiceStatus(value) {
    if (voiceStatus) voiceStatus.textContent = value;
  }

  function renderVoiceLoopCounter() {
    if (!voiceLoopCounter) return;
    const active = !!(continueConversation && continueConversation.checked);
    voiceLoopCounter.hidden = !active;
    voiceLoopCounter.textContent = active
      ? `Voice loop ${Math.min(voiceLoopTurnCount, MAX_CONTINUE_TURNS)} of ${MAX_CONTINUE_TURNS}`
      : "";
  }

  function logVoiceEvent(label, detail) {
    if (!voiceEvents) return;
    const timestamp = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    voiceEventLog.unshift({
      label,
      detail: detail || "",
      timestamp,
    });
    voiceEventLog = voiceEventLog.slice(0, MAX_VOICE_EVENTS);
    renderVoiceEvents();
  }

  function renderVoiceEvents() {
    if (!voiceEvents) return;
    voiceEvents.innerHTML = "";
    if (!voiceEventLog.length) {
      voiceEvents.innerHTML = '<p class="oom-empty">No voice events yet.</p>';
      return;
    }
    voiceEventLog.forEach((event) => {
      const row = document.createElement("p");
      const time = document.createElement("span");
      const text = document.createElement("strong");
      const detail = document.createElement("small");
      time.textContent = event.timestamp;
      text.textContent = event.label;
      detail.textContent = event.detail;
      row.appendChild(time);
      row.appendChild(text);
      if (event.detail) row.appendChild(detail);
      voiceEvents.appendChild(row);
    });
  }

  function ensureRecognition() {
    if (!SpeechRecognition) return null;
    if (recognition) return recognition;

    recognition = new SpeechRecognition();
    recognition.lang = "en-ZA";
    recognition.interimResults = true;
    recognition.continuous = false;

    recognition.onstart = () => {
      isListening = true;
      if (voiceAutoSubmitMode && voiceAskButton) {
        voiceAskButton.textContent = "Listening";
      } else if (voiceButton) {
        voiceButton.textContent = "Listening";
      }
      setStatus("Listening", "listening");
      logVoiceEvent("Listening", voiceAutoSubmitMode ? "Talk & Ask capture started" : "Draft capture started");
      setVoiceStatus(
        voiceAutoSubmitMode
          ? "Listening. Speak one question; you will get a short cancel window before it sends."
          : "Listening. Speak one question, then review the text before sending."
      );
    };

    recognition.onerror = (event) => {
      isListening = false;
      if (voiceButton) voiceButton.textContent = "Talk";
      if (voiceAskButton) voiceAskButton.textContent = "Talk & Ask";
      voiceAutoSubmitMode = false;
      setStatus("Voice error", "error");
      logVoiceEvent("Recognition error", event.error || "unknown error");
      setVoiceStatus(`Speech recognition stopped: ${event.error || "unknown error"}.`);
    };

    recognition.onend = () => {
      isListening = false;
      if (voiceButton) voiceButton.textContent = "Talk";
      if (voiceAskButton) voiceAskButton.textContent = "Talk & Ask";
      if (voiceAutoSubmitMode) {
        voiceAutoSubmitMode = false;
        const text = input ? input.value.trim() : "";
        if (text) {
          if (isVoiceStopCommand(text)) {
            logVoiceEvent("Stop phrase heard", text);
            stopConversation("Voice stop command heard. Conversation stopped.");
            return;
          }
          scheduleVoiceAutoSubmit();
          return;
        }
        setVoiceStatus("No speech was captured. Try again or type the question.");
      }
      if (statusText.textContent === "Listening") setStatus("Idle", "idle");
    };

    recognition.onresult = (event) => {
      let transcript = "";
      for (let index = 0; index < event.results.length; index += 1) {
        transcript += event.results[index][0].transcript;
      }
      transcript = transcript.trim();
      if (transcript && input) {
        input.value = transcript;
        userText.textContent = transcript;
        logVoiceEvent("Transcript", transcript);
        setVoiceStatus("Heard draft. Check the text, then press Ask.");
      }
    };

    return recognition;
  }

  function toggleVoiceDraft() {
    clearVoiceAutoSubmit();
    const activeRecognition = ensureRecognition();
    if (!activeRecognition) {
      setVoiceStatus("Speech recognition is not available in this browser.");
      return;
    }
    if (speechSynthesisApi) {
      speechSynthesisApi.cancel();
    }
    if (isListening) {
      activeRecognition.stop();
      return;
    }
    voiceAutoSubmitMode = false;
    try {
      activeRecognition.start();
    } catch (error) {
      setVoiceStatus("Speech recognition could not start. Try again after the current capture ends.");
    }
  }

  function toggleVoiceAsk() {
    clearVoiceAutoSubmit();
    startVoiceAskCapture(true);
  }

  function startVoiceAskCapture(cancelSpeechFirst) {
    const activeRecognition = ensureRecognition();
    if (!activeRecognition) {
      setVoiceStatus("Speech recognition is not available in this browser.");
      return;
    }
    if (cancelSpeechFirst && speechSynthesisApi) {
      speechRunId += 1;
      speechSynthesisApi.cancel();
    }
    if (isListening) {
      voiceAutoSubmitMode = false;
      activeRecognition.stop();
      return;
    }
    voiceAutoSubmitMode = true;
    updateConversationStopVisibility();
    try {
      activeRecognition.start();
    } catch (error) {
      voiceAutoSubmitMode = false;
      setVoiceStatus("Speech recognition could not start. Try again after the current capture ends.");
    }
  }

  function shouldContinueConversation(allowContinue) {
    return !!(
      allowContinue &&
      continueConversation &&
      continueConversation.checked &&
      autoSpeak &&
      autoSpeak.checked &&
      SpeechRecognition
    );
  }

  function preserveVoiceLoopCountForAsk() {
    return !!(continueConversation && continueConversation.checked && autoSpeak && autoSpeak.checked);
  }

  function isVoiceStopCommand(text) {
    const normalized = (text || "")
      .trim()
      .toLowerCase()
      .replace(/[.!?]+$/g, "")
      .replace(/\s+/g, " ");
    return [
      "stop",
      "stop conversation",
      "stop listening",
      "cancel",
      "cancel send",
      "never mind",
      "nevermind",
      "pause",
      "pause conversation",
    ].includes(normalized);
  }

  function updateConversationStopVisibility() {
    if (!stopConversationButton) return;
    const active = !!(
      (continueConversation && continueConversation.checked) ||
      voiceAutoSubmitTimer ||
      isListening ||
      statusText.textContent === "Speaking"
    );
    stopConversationButton.hidden = !active;
  }

  function stopConversation(message) {
    voiceLoopTurnCount = 0;
    voiceAutoSubmitMode = false;
    clearVoiceAutoSubmit();
    if (continueConversation) continueConversation.checked = false;
    if (recognition && isListening) {
      try {
        recognition.stop();
      } catch (error) {
        // Browser recognition may already be stopping.
      }
    }
    if (speechSynthesisApi) {
      speechRunId += 1;
      speechSynthesisApi.cancel();
    }
    speechUtterance = null;
    if (voiceButton) voiceButton.textContent = "Talk";
    if (voiceAskButton) voiceAskButton.textContent = "Talk & Ask";
    if (statusText.textContent === "Speaking" || statusText.textContent === "Listening") {
      setStatus("Idle", "idle");
    }
    setVoiceStatus(message || "Conversation stopped. Mic stayed off.");
    renderVoiceLoopCounter();
    updateConversationStopVisibility();
  }

  function scheduleVoiceAutoSubmit() {
    if (!input || !input.value.trim()) return;
    if (cancelVoiceSendButton) cancelVoiceSendButton.hidden = false;
    setVoiceStatus("Heard draft. Sending in 2 seconds unless you cancel or edit.");
    logVoiceEvent("Auto-send scheduled", input.value.trim());
    updateConversationStopVisibility();
    voiceAutoSubmitTimer = window.setTimeout(() => {
      voiceAutoSubmitTimer = null;
      if (cancelVoiceSendButton) cancelVoiceSendButton.hidden = true;
      updateConversationStopVisibility();
      const text = input.value.trim();
      if (!text) return;
      ask(text).catch((error) => {
        answer.textContent = "Oom Sakkie could not check that right now.";
        traceId.textContent = "Request failed";
        toolUsed.textContent = error && error.name ? error.name : "Error";
        setStatus("Error", "error");
      });
    }, 2000);
  }

  function clearVoiceAutoSubmit(message) {
    if (voiceAutoSubmitTimer) {
      window.clearTimeout(voiceAutoSubmitTimer);
      voiceAutoSubmitTimer = null;
      logVoiceEvent("Auto-send cancelled", message || "pending voice send cleared");
      if (message) setVoiceStatus(message);
    }
    if (cancelVoiceSendButton) cancelVoiceSendButton.hidden = true;
    updateConversationStopVisibility();
  }

  function stopActiveRecognitionForSpeech() {
    if (recognition && isListening) {
      recognition.stop();
    }
  }

  function speakText(text, automatic) {
    const cleanText = (text || "").trim();
    if (!speechSynthesisApi) {
      setVoiceStatus("Browser speech playback is not available here.");
      return;
    }
    if (!cleanText) {
      setVoiceStatus("There is no answer to speak yet.");
      return;
    }

    stopActiveRecognitionForSpeech();
    speechRunId += 1;
    speechSynthesisApi.cancel();
    const currentSpeechRunId = speechRunId;
    const allowContinue = !!automatic;
    speechUtterance = new SpeechSynthesisUtterance(cleanText);
    speechUtterance.lang = "en-ZA";
    speechUtterance.rate = 0.95;
    speechUtterance.pitch = 1;
    speechUtterance.volume = 1;
    speechUtterance.onstart = () => {
      setStatus("Speaking", "speaking");
      logVoiceEvent("Speaking", automatic ? "automatic reply playback" : "manual answer playback");
      setVoiceStatus(`${automatic ? "Auto-speaking" : "Speaking"} answer. Mic is not listening.`);
    };
    speechUtterance.onend = () => {
      if (currentSpeechRunId !== speechRunId) return;
      speechUtterance = null;
      const continueNow = shouldContinueConversation(allowContinue);
      if (continueNow) {
        voiceLoopTurnCount += 1;
        if (voiceLoopTurnCount > MAX_CONTINUE_TURNS) {
          logVoiceEvent("Loop paused", "maximum continued turns reached");
          stopConversation("Conversation paused after 5 continued turns. Press Talk & Ask to continue.");
          return;
        }
        renderVoiceLoopCounter();
        setVoiceStatus("Speech finished. Listening for the next question.");
        logVoiceEvent("Continuing", `turn ${voiceLoopTurnCount} of ${MAX_CONTINUE_TURNS}`);
        updateConversationStopVisibility();
        startVoiceAskCapture(false);
        return;
      }
      voiceLoopTurnCount = 0;
      renderVoiceLoopCounter();
      if (statusText.textContent === "Speaking") setStatus("Answered", "answered");
      logVoiceEvent("Speech finished", "mic stayed off");
      setVoiceStatus("Speech finished. Mic stayed off.");
      updateConversationStopVisibility();
    };
    speechUtterance.onerror = () => {
      if (currentSpeechRunId !== speechRunId) return;
      speechUtterance = null;
      voiceLoopTurnCount = 0;
      renderVoiceLoopCounter();
      setStatus("Speech error", "error");
      logVoiceEvent("Speech error", "browser playback stopped");
      setVoiceStatus("Browser speech playback stopped before finishing.");
      updateConversationStopVisibility();
    };
    speechSynthesisApi.speak(speechUtterance);
  }

  function speakCurrentAnswer() {
    speakText(lastAnswerText || (answer ? answer.textContent : ""), false);
  }

  function stopSpeech() {
    if (!speechSynthesisApi) return;
    speechRunId += 1;
    speechSynthesisApi.cancel();
    speechUtterance = null;
    voiceLoopTurnCount = 0;
    renderVoiceLoopCounter();
    if (statusText.textContent === "Speaking") setStatus("Answered", "answered");
    logVoiceEvent("Speech stopped", "manual stop");
    setVoiceStatus("Speech stopped. Mic stayed off.");
    updateConversationStopVisibility();
  }

  async function ask(text) {
    clearVoiceAutoSubmit();
    if (!preserveVoiceLoopCountForAsk()) {
      voiceLoopTurnCount = 0;
      renderVoiceLoopCounter();
    }
    if (speechSynthesisApi) {
      speechRunId += 1;
      speechSynthesisApi.cancel();
    }
    setStatus("Checking", "checking");
    userText.textContent = text;
    answer.textContent = "Checking the farm system...";
    resetPipelineForCheck();
    renderAgentActivity(null);
    renderWarnings([]);
    renderSafetyNotes([]);
    renderLinks([]);

    const response = await fetch("/api/oom-sakkie/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        channel: "kiosk",
        session_id: getSessionId(),
      }),
    });
    const data = await response.json();
    lastAnswerText = data.answer || "No answer returned.";
    answer.textContent = lastAnswerText;
    traceId.textContent = data.trace_id || "None";
    toolUsed.textContent = data.tool_used || "None";
    riskLevel.textContent = String(data.risk_level ?? 0);
    renderPipeline(data);
    renderAgentActivity(data);
    renderWarnings(data.stale_warnings || []);
    renderSafetyNotes(data.safety_notes || []);
    renderLinks(data.links || []);
    if (data.action_blocked) {
      setStatus("Blocked", "blocked");
    } else {
      setStatus(
        data.needs_clarification ? "Needs clarification" : "Answered",
        data.needs_clarification ? "clarifying" : "answered"
      );
    }
    logVoiceEvent("Backend answered", data.tool_used || "clarification");
    refreshReviewData();
    if (autoSpeak && autoSpeak.checked) {
      speakText(lastAnswerText, true);
    }
  }

  function renderReviewSummary(data) {
    if (!reviewSummary) return;
    if (!data || !data.success || !data.summary) {
      reviewSummary.innerHTML = '<p class="oom-empty">Review summary is unavailable.</p>';
      return;
    }
    const summary = data.summary;
    reviewSummary.innerHTML = "";

    const metrics = document.createElement("div");
    metrics.className = "oom-review-metrics";
    [
      ["Checks", summary.total_traces],
      ["Reviewed", `${summary.reviewed_traces} (${summary.review_rate_pct}%)`],
      ["Issues", `${summary.problem_traces} (${summary.problem_rate_pct}%)`],
      ["Unreviewed", summary.unreviewed_traces],
    ].forEach(([label, value]) => {
      const card = document.createElement("div");
      const small = document.createElement("span");
      const strong = document.createElement("strong");
      small.textContent = label;
      strong.textContent = String(value);
      card.appendChild(small);
      card.appendChild(strong);
      metrics.appendChild(card);
    });
    reviewSummary.appendChild(metrics);

    const problems = data.recent_problem_traces || [];
    const problemList = document.createElement("div");
    problemList.className = "oom-problem-list";
    if (!problems.length) {
      const clear = document.createElement("p");
      clear.className = "oom-empty";
      clear.textContent = "No reviewed problem traces in the selected window.";
      problemList.appendChild(clear);
    } else {
      problems.forEach((item) => {
        const row = document.createElement("p");
        const feedback = latestFeedbackText(item.latest_feedback);
        row.textContent = `${item.tool_name || "clarification"}: ${feedback} - ${item.user_text || "(empty)"}`;
        problemList.appendChild(row);
      });
    }
    reviewSummary.appendChild(problemList);
  }

  function renderReviewAdvisor(data) {
    if (!reviewAdvisor) return;
    if (!data || !data.success) {
      reviewAdvisor.innerHTML = '<p class="oom-empty">Review advisor is unavailable.</p>';
      return;
    }
    reviewAdvisor.innerHTML = "";

    const guard = document.createElement("p");
    guard.className = "oom-advisor-guard";
    guard.textContent = `${data.mode || "advisory_only"} | last ${data.days || 14} days | auto-marking ${data.autonomous_marking_enabled ? "enabled" : "off"} | writes feedback ${data.writes_feedback ? "yes" : "no"}`;
    reviewAdvisor.appendChild(guard);

    const suggestions = Array.isArray(data.suggested_actions) ? data.suggested_actions : [];
    const suggestionList = document.createElement("ul");
    suggestionList.className = "oom-advisor-suggestions";
    if (!suggestions.length) {
      const item = document.createElement("li");
      item.textContent = "No advisor suggestions returned.";
      suggestionList.appendChild(item);
    } else {
      suggestions.slice(0, 4).forEach((suggestion) => {
        const item = document.createElement("li");
        item.textContent = suggestion;
        suggestionList.appendChild(item);
      });
    }
    reviewAdvisor.appendChild(suggestionList);

    const queue = Array.isArray(data.review_queue) ? data.review_queue : [];
    const queueList = document.createElement("div");
    queueList.className = "oom-advisor-queue";
    if (!queue.length) {
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = "No review queue items right now.";
      queueList.appendChild(empty);
    } else {
      queue.slice(0, 6).forEach((item) => {
        const row = document.createElement("article");
        const title = document.createElement("strong");
        const meta = document.createElement("span");
        const question = document.createElement("p");
        title.textContent = `${item.priority || "normal"} - ${item.reason || "review"}`;
        meta.textContent = `${item.tool_name || "clarification"} | ${item.trace_id || ""}`;
        question.textContent = item.user_text || "(empty)";
        row.appendChild(title);
        row.appendChild(meta);
        row.appendChild(question);
        queueList.appendChild(row);
      });
    }
    reviewAdvisor.appendChild(queueList);
  }

  function renderLearningAdvisor(data) {
    if (!learningAdvisor) return;
    if (!data || !data.success) {
      learningAdvisor.innerHTML = '<p class="oom-empty">Learning queue is unavailable.</p>';
      return;
    }
    learningAdvisor.innerHTML = "";

    const guard = document.createElement("p");
    guard.className = "oom-advisor-guard";
    guard.textContent = `${data.mode || "advisory_only"} | runs LLM ${data.runs_llm ? "yes" : "no"} | writes code ${data.writes_code ? "yes" : "no"} | approval ${data.requires_human_approval ? "required" : "not required"}`;
    learningAdvisor.appendChild(guard);

    const next = document.createElement("p");
    next.className = "oom-learning-next";
    next.textContent = data.suggested_next_step || "No learning step suggested yet.";
    learningAdvisor.appendChild(next);

    learningAdvisor.appendChild(renderLearningProposalList(Array.isArray(data.proposals) ? data.proposals : []));
  }

  function renderLearningAnalysis(data) {
    if (!learningAdvisor) return;
    if (!data || !data.status) {
      learningAdvisor.innerHTML = '<p class="oom-empty">Learning analysis did not return a result.</p>';
      return;
    }
    learningAdvisor.innerHTML = "";

    const guard = document.createElement("p");
    guard.className = "oom-advisor-guard";
    guard.textContent = `${data.mode || "advisory_only"} | runs LLM ${data.runs_llm ? "yes" : "no"} | writes code ${data.writes_code ? "yes" : "no"} | approval ${data.requires_human_approval ? "required" : "not required"} | status ${data.status}`;
    learningAdvisor.appendChild(guard);

    const proposals = Array.isArray(data.llm_proposals) && data.llm_proposals.length
      ? data.llm_proposals
      : (Array.isArray(data.deterministic_proposals) ? data.deterministic_proposals : []);
    learningAdvisor.appendChild(renderLearningProposalList(proposals));
  }

  function renderLearningProposalList(proposals) {
    const list = document.createElement("div");
    list.className = "oom-advisor-queue";
    if (!proposals.length) {
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = "No learning proposals returned. Mark issue traces first or enable the learning analyst.";
      list.appendChild(empty);
    } else {
      proposals.slice(0, 6).forEach((proposal) => {
        const row = document.createElement("article");
        const title = document.createElement("strong");
        const evidence = document.createElement("span");
        const action = document.createElement("p");
        const buildButton = document.createElement("button");
        title.textContent = `${proposal.priority || "normal"} - ${proposal.title || proposal.kind || "learning proposal"}`;
        evidence.textContent = proposal.evidence || "";
        action.textContent = proposal.recommended_action || "";
        buildButton.type = "button";
        buildButton.className = "oom-build-brief-button";
        buildButton.textContent = "Build Brief";
        buildButton.addEventListener("click", () => {
          buildLearningPacket(proposal, buildButton);
        });
        row.appendChild(title);
        row.appendChild(evidence);
        row.appendChild(action);
        row.appendChild(buildButton);
        list.appendChild(row);
      });
    }
    return list;
  }

  function renderLearningPacket(data) {
    if (!learningPacket) return;
    if (!data || !data.success) {
      learningPacket.innerHTML = '<p class="oom-empty">Build brief could not be generated.</p>';
      return;
    }
    learningPacket.innerHTML = "";
    learningPacket.hidden = false;

    const guard = document.createElement("p");
    guard.className = "oom-advisor-guard";
    guard.textContent = `${data.mode || "build_brief_only"} | writes code ${data.writes_code ? "yes" : "no"} | applies changes ${data.applies_changes ? "yes" : "no"} | approval ${data.requires_human_approval ? "required" : "not required"}`;
    learningPacket.appendChild(guard);

    const title = document.createElement("strong");
    title.textContent = ((data.proposal || {}).title) || "Learning Build Brief";
    learningPacket.appendChild(title);

    const files = document.createElement("p");
    files.textContent = `Files: ${(data.recommended_files || []).slice(0, 6).join(", ")}`;
    learningPacket.appendChild(files);

    const brief = document.createElement("pre");
    brief.className = "oom-build-brief";
    brief.textContent = data.brief || "No brief text returned.";
    learningPacket.appendChild(brief);

    const approveButton = document.createElement("button");
    approveButton.type = "button";
    approveButton.className = "oom-approve-build-button";
    approveButton.textContent = "Approve for Build";
    approveButton.addEventListener("click", () => {
      approveBuildRequest(data, approveButton);
    });
    learningPacket.appendChild(approveButton);
  }

  function renderBuildApproval(data) {
    if (!learningPacket) return;
    const panel = document.createElement("div");
    panel.className = "oom-build-approval";
    const guard = document.createElement("p");
    const id = document.createElement("strong");
    const handoff = document.createElement("p");
    guard.className = "oom-advisor-guard";
    guard.textContent = `${data.status || "approved_for_build"} | builder enabled ${data.builder_enabled ? "yes" : "no"} | writes now ${data.writes_code_now ? "yes" : "no"} | applies now ${data.applies_changes_now ? "yes" : "no"}`;
    id.textContent = data.build_request_id || "Build request created";
    handoff.textContent = data.handoff || "Approved for a future builder step. No files changed.";
    panel.appendChild(guard);
    panel.appendChild(id);
    panel.appendChild(handoff);
    if (data.build_request_store) {
      const store = document.createElement("p");
      store.textContent = `Store: ${data.build_request_store.status || "unknown"}`;
      panel.appendChild(store);
    }
    learningPacket.appendChild(panel);
  }

  function renderBuildRequests(data) {
    if (!buildRequests) return;
    if (!data || !data.success) {
      const status = data && data.status ? data.status : "unavailable";
      buildRequests.innerHTML = "";
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = `Build request store: ${status}.`;
      buildRequests.appendChild(empty);
      return;
    }
    buildRequests.innerHTML = "";
    const guard = document.createElement("p");
    guard.className = "oom-advisor-guard";
    guard.textContent = "persistent queue | builder enabled no | writes now no | applies now no";
    buildRequests.appendChild(guard);

    const items = Array.isArray(data.build_requests) ? data.build_requests : [];
    const pendingItems = items.filter((item) => buildRequestStage(item) === "pending");
    const movedItems = items.filter((item) => buildRequestStage(item) !== "pending");
    const list = document.createElement("div");
    list.className = "oom-advisor-queue";
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = "No approved build requests yet.";
      list.appendChild(empty);
    } else {
      appendQueueSection(list, "Needs Forge Handoff / Builder Plan", pendingItems, "No build requests need handoff right now.", renderBuildRequestRow);
      appendQueueSection(list, "Already Moved Or Closed", movedItems.slice(0, 5), "No moved build requests yet.", renderBuildRequestRow);
    }
    buildRequests.appendChild(list);
  }

  function buildRequestStage(item) {
    const latestEvent = item.latest_event || {};
    const eventType = latestEvent.event_type || "";
    const notes = latestEvent.notes || "";
    if (eventType === "ignored") return "closed";
    if (eventType === "review_note" && /patch proposal recorded/i.test(notes)) return "moved_to_patch";
    return "pending";
  }

  function renderBuildRequestRow(item) {
    const row = document.createElement("article");
    const title = document.createElement("strong");
    const badge = document.createElement("span");
    const meta = document.createElement("span");
    const next = document.createElement("p");
    const event = document.createElement("p");
    const actionGroup = document.createElement("div");
    const handoffButton = document.createElement("button");
    const proposalButton = document.createElement("button");
    const ignoreButton = document.createElement("button");
    const proposal = item.proposal || {};
    const latestEvent = item.latest_event || {};
    const stage = buildRequestStage(item);
    row.className = stage === "pending" ? "oom-work-item oom-work-item-active" : "oom-work-item oom-work-item-muted";
    badge.className = "oom-work-badge";
    badge.textContent = stage === "pending" ? "Needs builder handoff" : "Moved/closed";
    title.textContent = proposal.title || proposal.objective || item.build_request_id || "Build request";
    meta.textContent = `${item.build_request_id || ""} | ${item.status || ""} | ${item.created_at || ""}`;
    next.textContent = stage === "pending"
      ? "Next: open Forge Handoff, copy the prompt, then use your separate Builder/Forge tool."
      : "This request is no longer the active build handoff step.";
    event.textContent = latestEvent.event_type
      ? `Latest event: ${latestEvent.event_type} ${latestEvent.notes ? "- " + latestEvent.notes : ""}`
      : "Latest event: none";
    actionGroup.className = "oom-work-actions";
    handoffButton.type = "button";
    handoffButton.className = "oom-build-brief-button";
    handoffButton.textContent = "Open Forge Handoff";
    handoffButton.addEventListener("click", () => {
      buildForgeHandoff(item.build_request_id, handoffButton);
    });
    proposalButton.type = "button";
    proposalButton.className = "oom-build-brief-button";
    proposalButton.textContent = "Prepare Patch Proposal Form";
    proposalButton.addEventListener("click", () => {
      preparePatchProposalForm(item.build_request_id);
    });
    ignoreButton.type = "button";
    ignoreButton.className = "oom-build-brief-button";
    ignoreButton.textContent = "Close";
    ignoreButton.addEventListener("click", () => {
      recordBuildRequestEvent(item.build_request_id, "ignored", "Ignored from kiosk review.", ignoreButton);
    });
    actionGroup.appendChild(handoffButton);
    if (stage === "pending") {
      actionGroup.appendChild(proposalButton);
      actionGroup.appendChild(ignoreButton);
    }
    row.appendChild(badge);
    row.appendChild(title);
    row.appendChild(meta);
    row.appendChild(next);
    row.appendChild(event);
    row.appendChild(actionGroup);
    return row;
  }

  function renderForgeHandoff(data) {
    if (!forgeHandoff) return;
    if (!data || !data.success) {
      forgeHandoff.innerHTML = '<p class="oom-empty">Forge handoff could not be generated.</p>';
      forgeHandoff.hidden = false;
      return;
    }
    forgeHandoff.innerHTML = "";
    forgeHandoff.hidden = false;

    const guard = document.createElement("p");
    guard.className = "oom-advisor-guard";
    guard.textContent = `${data.mode || "forge_handoff_only"} | runs builder ${data.runs_builder ? "yes" : "no"} | writes code ${data.writes_code ? "yes" : "no"} | applies changes ${data.applies_changes ? "yes" : "no"} | deploys ${data.deploys ? "yes" : "no"}`;
    forgeHandoff.appendChild(guard);

    const title = document.createElement("strong");
    title.textContent = `${data.build_request_id || "Build request"} - ${data.objective || "Forge handoff"}`;
    forgeHandoff.appendChild(title);

    const next = document.createElement("p");
    next.textContent = "Next gate: owner must explicitly run Builder/Forge, then separately approve the patch and deploy.";
    forgeHandoff.appendChild(next);

    const prompt = document.createElement("pre");
    prompt.className = "oom-build-brief";
    prompt.textContent = data.prompt || "No handoff prompt returned.";
    forgeHandoff.appendChild(prompt);

    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.className = "oom-build-brief-button";
    copyButton.textContent = "Copy Forge Prompt";
    copyButton.addEventListener("click", () => {
      copyTextToClipboard(data.prompt || "", copyButton, "Copy Forge Prompt");
    });
    forgeHandoff.appendChild(copyButton);

    const prepareButton = document.createElement("button");
    prepareButton.type = "button";
    prepareButton.className = "oom-build-brief-button";
    prepareButton.textContent = "Use This Build Request In Patch Gate";
    prepareButton.addEventListener("click", () => {
      preparePatchProposalForm(data.build_request_id || "");
    });
    forgeHandoff.appendChild(prepareButton);
  }

  async function copyTextToClipboard(text, button, fallbackText) {
    const originalText = button ? button.textContent : fallbackText;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      if (button) button.textContent = "Copied";
    } catch (error) {
      if (button) button.textContent = "Copy failed";
      return;
    }
    window.setTimeout(() => {
      if (button) button.textContent = originalText || fallbackText;
    }, 1400);
  }

  function preparePatchProposalForm(buildRequestId) {
    if (patchBuildRequestId) patchBuildRequestId.value = buildRequestId || "";
    if (patchProposalText) {
      patchProposalText.focus();
      patchProposalText.placeholder = `Paste Builder/Forge proposal for ${buildRequestId || "this build request"}. This records review data only; it does not apply a patch.`;
    }
  }

  function renderPatchProposals(data) {
    if (!patchProposals) return;
    if (!data || !data.success) {
      const status = data && data.status ? data.status : "unavailable";
      patchProposals.innerHTML = "";
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = `Patch proposal store: ${status}.`;
      patchProposals.appendChild(empty);
      return;
    }
    patchProposals.innerHTML = "";
    const guard = document.createElement("p");
    guard.className = "oom-advisor-guard";
    guard.textContent = `${data.mode || "patch_proposal_review_only"} | applies patches ${data.applies_patches ? "yes" : "no"} | deploys ${data.deploys ? "yes" : "no"} | manual owner gate required`;
    patchProposals.appendChild(guard);

    const items = Array.isArray(data.patch_proposals) ? data.patch_proposals : [];
    const pendingItems = items.filter((item) => patchProposalStage(item) === "pending");
    const deployReadyItems = items.filter((item) => patchProposalStage(item) === "ready_for_deploy");
    const closedItems = items.filter((item) => patchProposalStage(item) === "closed");
    const list = document.createElement("div");
    list.className = "oom-advisor-queue";
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = "No patch proposals recorded yet.";
      list.appendChild(empty);
    } else {
      appendQueueSection(list, "Needs Patch Review", pendingItems, "No patch proposals need review right now.", renderPatchProposalRow);
      appendQueueSection(list, "Approved - Ready For Deploy Decision", deployReadyItems, "No approved patches are waiting for deploy decision.", renderPatchProposalRow);
      appendQueueSection(list, "Rejected / Closed", closedItems.slice(0, 5), "No closed patch proposals yet.", renderPatchProposalRow);
    }
    patchProposals.appendChild(list);
  }

  function patchProposalStage(item) {
    const latestEvent = item.latest_event || {};
    if (!latestEvent.event_type) return "pending";
    if (latestEvent.event_type === "approved_for_patch") return "ready_for_deploy";
    return "closed";
  }

  function renderPatchProposalRow(item) {
    const row = document.createElement("article");
    const title = document.createElement("strong");
    const badge = document.createElement("span");
    const meta = document.createElement("span");
    const text = document.createElement("p");
    const risk = document.createElement("p");
    const event = document.createElement("p");
    const actionGroup = document.createElement("div");
    const approveButton = document.createElement("button");
    const rejectButton = document.createElement("button");
    const deployButton = document.createElement("button");
    const latestEvent = item.latest_event || {};
    const stage = patchProposalStage(item);
    row.className = stage === "pending" ? "oom-work-item oom-work-item-active" : "oom-work-item";
    badge.className = "oom-work-badge";
    badge.textContent = stage === "pending" ? "Needs patch review" : stage === "ready_for_deploy" ? "Ready for deploy decision" : "Closed";
    title.textContent = item.patch_proposal_id || "Patch proposal";
    meta.textContent = `${item.build_request_id || ""} | proposed by ${item.proposed_by || "builder"} | ${item.created_at || ""}`;
    text.textContent = (item.proposal_text || "").slice(0, 500);
    risk.textContent = item.risk_notes ? `Risks: ${item.risk_notes}` : "Risks: not supplied";
    event.textContent = latestEvent.event_type
      ? `Latest event: ${latestEvent.event_type} ${latestEvent.notes ? "- " + latestEvent.notes : ""}`
      : "Latest event: none";
    actionGroup.className = "oom-work-actions";
    approveButton.type = "button";
    approveButton.className = "oom-build-brief-button";
    approveButton.textContent = "Approve Patch";
    approveButton.addEventListener("click", () => {
      recordPatchProposalEvent(
        item.patch_proposal_id,
        "approved_for_patch",
        "Approved for manual patch application outside the kiosk. No patch was applied here.",
        approveButton
      );
    });
    rejectButton.type = "button";
    rejectButton.className = "oom-build-brief-button";
    rejectButton.textContent = "Reject";
    rejectButton.addEventListener("click", () => {
      recordPatchProposalEvent(item.patch_proposal_id, "rejected", "Rejected from kiosk review.", rejectButton);
    });
    deployButton.type = "button";
    deployButton.className = "oom-build-brief-button";
    deployButton.textContent = "Prepare Deploy Decision";
    deployButton.addEventListener("click", () => {
      prepareDeployDecisionForm(item.patch_proposal_id);
    });
    if (stage === "pending") {
      actionGroup.appendChild(approveButton);
      actionGroup.appendChild(rejectButton);
    }
    if (stage === "ready_for_deploy") {
      actionGroup.appendChild(deployButton);
    }
    row.appendChild(badge);
    row.appendChild(title);
    row.appendChild(meta);
    row.appendChild(text);
    row.appendChild(risk);
    row.appendChild(event);
    if (stage === "ready_for_deploy") row.appendChild(renderDeployReadyInstructions(item));
    row.appendChild(actionGroup);
    return row;
  }

  function renderDeployReadyInstructions(item) {
    const panel = document.createElement("div");
    const title = document.createElement("strong");
    const list = document.createElement("ol");
    const steps = [
      "Read the patch proposal or diff in your editor.",
      "Apply it manually outside the kiosk only if you are happy.",
      "Run the verification commands from the proposal.",
      "Paste the verification result below, then record Approve Manual Deploy or Defer."
    ];
    panel.className = "oom-deploy-instructions";
    title.textContent = "What this needs now";
    panel.appendChild(title);
    steps.forEach((step) => {
      const itemNode = document.createElement("li");
      itemNode.textContent = step;
      list.appendChild(itemNode);
    });
    panel.appendChild(list);
    const id = document.createElement("p");
    id.textContent = `Patch proposal ID: ${item.patch_proposal_id || "unknown"}`;
    panel.appendChild(id);
    return panel;
  }

  function prepareDeployDecisionForm(patchProposalId) {
    if (deployPatchProposalId) deployPatchProposalId.value = patchProposalId || "";
    if (deployVerificationSummary) {
      deployVerificationSummary.focus();
      deployVerificationSummary.placeholder = `Paste what you verified for ${patchProposalId || "this patch proposal"}: patch reviewed/applied manually, tests run, result. This records approval only; it does not deploy.`;
    }
  }

  function renderDeployDecisions(data) {
    if (!deployDecisions) return;
    if (!data || !data.success) {
      const status = data && data.status ? data.status : "unavailable";
      deployDecisions.innerHTML = "";
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = `Deploy decision store: ${status}.`;
      deployDecisions.appendChild(empty);
      return;
    }
    deployDecisions.innerHTML = "";
    const guard = document.createElement("p");
    guard.className = "oom-advisor-guard";
    guard.textContent = `${data.mode || "deploy_approval_record_only"} | runs deploy ${data.runs_deploy ? "yes" : "no"} | deploys now ${data.deploys_now ? "yes" : "no"} | manual owner gate required`;
    deployDecisions.appendChild(guard);

    const items = Array.isArray(data.deploy_decisions) ? data.deploy_decisions : [];
    const list = document.createElement("div");
    list.className = "oom-advisor-queue";
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = "No deploy decisions recorded yet.";
      list.appendChild(empty);
    } else {
      items.slice(0, 8).forEach((item) => {
        const row = document.createElement("article");
        const title = document.createElement("strong");
        const meta = document.createElement("span");
        const verification = document.createElement("p");
        const notes = document.createElement("p");
        title.textContent = item.deploy_decision_id || "Deploy decision";
        meta.textContent = `${item.patch_proposal_id || ""} | ${item.decision_type || ""} | ${item.environment || "local"} | ${item.created_at || ""}`;
        verification.textContent = item.verification_summary ? `Verification: ${item.verification_summary}` : "Verification: not supplied";
        notes.textContent = item.notes ? `Notes: ${item.notes}` : "Notes: none";
        row.appendChild(title);
        row.appendChild(meta);
        row.appendChild(verification);
        row.appendChild(notes);
        list.appendChild(row);
      });
    }
    deployDecisions.appendChild(list);
  }

  function renderAgentResultReviews(data) {
    if (!agentResultReviews) return;
    if (!data || !data.success) {
      const status = data && data.status ? data.status : "unavailable";
      agentResultReviews.innerHTML = "";
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = `Agent result review queue: ${status}.`;
      agentResultReviews.appendChild(empty);
      return;
    }
    agentResultReviews.innerHTML = "";
    const guard = document.createElement("p");
    guard.className = "oom-advisor-guard";
    guard.textContent = `${data.mode || "dry_run_result_review_queue"} | runs specialist ${data.runs_specialist ? "yes" : "no"} | dispatch ${data.dispatch_enabled ? "yes" : "no"} | writes ${data.writes ? "yes" : "no"} | runtime change ${data.applies_runtime_change ? "yes" : "no"}`;
    agentResultReviews.appendChild(guard);

    const items = Array.isArray(data.dry_run_results) ? data.dry_run_results : [];
    const pendingItems = items.filter((item) => agentResultStage(item) === "pending");
    const closedItems = items.filter((item) => agentResultStage(item) !== "pending");
    const list = document.createElement("div");
    list.className = "oom-advisor-queue";
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = "No Sentinel dry-run results recorded yet.";
      list.appendChild(empty);
    } else {
      appendQueueSection(list, "Needs Owner Review", pendingItems, "No agent results need owner review right now.", renderAgentResultRow);
      appendQueueSection(list, "Reviewed / Closed", closedItems.slice(0, 5), "No reviewed agent results yet.", renderAgentResultRow);
    }
    agentResultReviews.appendChild(list);
  }

  function renderAgentLearningLedger(data) {
    if (!agentLearningLedger) return;
    if (!data || !data.success) {
      const status = data && data.status ? data.status : "unavailable";
      agentLearningLedger.innerHTML = "";
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = `Agent learning ledger: ${status}.`;
      agentLearningLedger.appendChild(empty);
      return;
    }
    agentLearningLedger.innerHTML = "";
    const guard = document.createElement("p");
    guard.className = "oom-advisor-guard";
    guard.textContent = "accepted evidence only | runs specialist no | dispatch no | writes no | runtime change no";
    agentLearningLedger.appendChild(guard);

    const items = Array.isArray(data.dry_run_results) ? data.dry_run_results : [];
    const acceptedItems = items.filter((item) => {
      return (item.latest_event || {}).event_type === "accepted_for_learning";
    });
    const list = document.createElement("div");
    list.className = "oom-advisor-queue";
    if (!acceptedItems.length) {
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = "No accepted agent learning evidence yet.";
      list.appendChild(empty);
    } else {
      acceptedItems.slice(0, 8).forEach((item) => list.appendChild(renderAgentLearningLedgerRow(item)));
    }
    agentLearningLedger.appendChild(list);
  }

  function renderAgentLearningLedgerRow(item) {
    const row = document.createElement("article");
    const title = document.createElement("strong");
    const badge = document.createElement("span");
    const meta = document.createElement("span");
    const result = document.createElement("p");
    const findings = document.createElement("p");
    const note = document.createElement("p");
    const guard = document.createElement("p");
    const latestEvent = item.latest_event || {};
    row.className = "oom-work-item";
    badge.className = "oom-work-badge";
    badge.textContent = "Accepted evidence";
    title.textContent = item.dry_run_result_id || "Accepted agent result";
    meta.textContent = `${item.specialist_slug || "sentinel"} | request ${item.dry_run_request_id || "-"} | accepted ${latestEvent.created_at || "-"}`;
    result.textContent = (item.result_text || "No result text supplied.").slice(0, 620);
    findings.textContent = `Evidence: ${(item.findings || []).slice(0, 5).join("; ") || "none supplied"}`;
    note.textContent = latestEvent.notes ? `Owner note: ${latestEvent.notes}` : "Owner note: none supplied";
    guard.className = "oom-advisor-guard";
    guard.textContent = "learning evidence only | no specialist run | no runtime change";
    row.appendChild(badge);
    row.appendChild(title);
    row.appendChild(meta);
    row.appendChild(result);
    row.appendChild(findings);
    row.appendChild(note);
    row.appendChild(guard);
    return row;
  }

  function renderAgentDryRunRequests(data) {
    if (!agentDryRunRequests) return;
    if (!data || !data.success) {
      const status = data && data.status ? data.status : "unavailable";
      agentDryRunRequests.innerHTML = "";
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = `Agent dry-run request queue: ${status}.`;
      agentDryRunRequests.appendChild(empty);
      return;
    }
    agentDryRunRequests.innerHTML = "";
    const guard = document.createElement("p");
    guard.className = "oom-policy-blocked";
    guard.textContent = `${data.mode || "read_only_dry_run_request_queue"} | dry-run ${data.dry_run_enabled ? "on" : "off"} | dispatch ${data.dispatch_enabled ? "yes" : "no"} | specialist LLM ${data.runs_specialist_llm ? "yes" : "no"} | writes ${data.writes ? "yes" : "no"}`;
    agentDryRunRequests.appendChild(guard);

    const items = Array.isArray(data.dry_run_requests) ? data.dry_run_requests : [];
    const pending = items.filter((item) => agentDryRunRequestStage(item) === "pending");
    const closed = items.filter((item) => agentDryRunRequestStage(item) !== "pending");
    const list = document.createElement("div");
    list.className = "oom-advisor-queue";
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = "No Sentinel dry-run requests recorded yet.";
      list.appendChild(empty);
    } else {
      appendQueueSection(list, "Needs Handoff / Future Result", pending, "No Sentinel dry-run requests need handoff right now.", renderAgentDryRunRequestRow);
      appendQueueSection(list, "Closed / Not Active", closed.slice(0, 5), "No closed Sentinel dry-run requests yet.", renderAgentDryRunRequestRow);
    }
    agentDryRunRequests.appendChild(list);
  }

  function agentDryRunRequestStage(item) {
    const latestEvent = (item && item.latest_event) || {};
    if (latestEvent.event_type === "cancelled") return "closed";
    return "pending";
  }

  function renderAgentDryRunRequestRow(item) {
    const latestEvent = item.latest_event || {};
    const stage = agentDryRunRequestStage(item);
    const row = document.createElement("article");
    row.className = "oom-work-item";
    const badge = document.createElement("span");
    const title = document.createElement("strong");
    const meta = document.createElement("span");
    const purpose = document.createElement("p");
    const guard = document.createElement("p");
    const actions = document.createElement("div");
    const handoffButton = document.createElement("button");
    const useForResultButton = document.createElement("button");
    badge.className = "oom-work-badge";
    badge.textContent = stage === "pending" ? "Needs handoff" : "Closed";
    title.textContent = item.dry_run_request_id || "Sentinel dry-run request";
    meta.textContent = `${item.specialist_slug || "sentinel"} | ${item.created_at || ""}`;
    purpose.textContent = item.purpose || item.owner_text || "Read-only dry-run request.";
    guard.className = "oom-policy-blocked";
    guard.textContent = `dispatch ${item.dispatch_enabled ? "on" : "off"} | specialist LLM ${item.runs_specialist_llm ? "on" : "off"} | tools ${item.runs_specialist_tools ? "on" : "off"} | writes ${item.writes ? "on" : "off"}`;
    actions.className = "oom-work-actions";
    handoffButton.type = "button";
    handoffButton.textContent = "Open Handoff";
    handoffButton.disabled = stage !== "pending";
    handoffButton.addEventListener("click", () => {
      buildAgentDryRunHandoff(item.dry_run_request_id, handoffButton);
    });
    useForResultButton.type = "button";
    useForResultButton.textContent = "Use For Result";
    useForResultButton.addEventListener("click", () => {
      if (agentDryRunResultRequestId) agentDryRunResultRequestId.value = item.dry_run_request_id || "";
    });
    actions.appendChild(handoffButton);
    actions.appendChild(useForResultButton);
    row.appendChild(badge);
    row.appendChild(title);
    row.appendChild(meta);
    row.appendChild(purpose);
    if (latestEvent.event_type) {
      const eventLine = document.createElement("p");
      eventLine.textContent = `Latest event: ${latestEvent.event_type} - ${latestEvent.notes || "no note"}`;
      row.appendChild(eventLine);
    }
    row.appendChild(guard);
    row.appendChild(actions);
    return row;
  }

  function renderAgentDryRunHandoff(data) {
    if (!agentDryRunHandoff) return;
    agentDryRunHandoff.hidden = false;
    agentDryRunHandoff.innerHTML = "";
    if (!data || !data.success) {
      const line = document.createElement("p");
      line.className = "oom-empty";
      line.textContent = "Sentinel dry-run handoff could not be generated.";
      agentDryRunHandoff.appendChild(line);
      return;
    }
    const guard = document.createElement("p");
    guard.className = "oom-policy-blocked";
    guard.textContent = `${data.mode || "agent_dry_run_handoff_only"} | runs specialist ${data.runs_specialist ? "yes" : "no"} | specialist LLM ${data.runs_specialist_llm ? "yes" : "no"} | tools ${data.runs_specialist_tools ? "yes" : "no"} | dispatch ${data.dispatch_enabled ? "yes" : "no"} | writes ${data.writes ? "yes" : "no"}`;
    const title = document.createElement("strong");
    title.textContent = `${data.specialist_name || "Agent"} handoff: ${data.dry_run_request_id || "request"}`;
    const prompt = document.createElement("pre");
    prompt.textContent = data.prompt || "No handoff prompt returned.";
    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.textContent = "Copy Sentinel Handoff";
    copyButton.addEventListener("click", () => {
      copyTextToClipboard(data.prompt || "", copyButton, "Copy Sentinel Handoff");
    });
    if (agentDryRunResultRequestId) agentDryRunResultRequestId.value = data.dry_run_request_id || "";
    agentDryRunHandoff.appendChild(guard);
    agentDryRunHandoff.appendChild(title);
    agentDryRunHandoff.appendChild(prompt);
    agentDryRunHandoff.appendChild(copyButton);
  }

  async function buildAgentDryRunHandoff(dryRunRequestId, button) {
    if (!dryRunRequestId || !agentDryRunHandoff) return;
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "Opening";
    }
    agentDryRunHandoff.hidden = false;
    agentDryRunHandoff.innerHTML = '<p class="oom-empty">Preparing Sentinel dry-run handoff...</p>';
    try {
      const response = await fetch("/api/oom-sakkie/agent-dry-runs/handoff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dry_run_request_id: dryRunRequestId }),
      });
      const data = await response.json();
      renderAgentDryRunHandoff(data);
    } catch (error) {
      agentDryRunHandoff.innerHTML = '<p class="oom-empty">Sentinel dry-run handoff is unavailable.</p>';
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "Open Handoff";
      }
    }
  }

  async function recordAgentDryRunResult(button) {
    if (!agentDryRunResultRequestId || !agentDryRunResultText) return;
    const dryRunRequestId = (agentDryRunResultRequestId.value || "").trim();
    const resultText = (agentDryRunResultText.value || "").trim();
    if (!dryRunRequestId || !resultText) {
      if (agentResultReviews) {
        agentResultReviews.innerHTML = '<p class="oom-empty">Dry-run request ID and result text are required.</p>';
      }
      return;
    }
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "Recording";
    }
    const findings = (agentDryRunResultFindings && agentDryRunResultFindings.value ? agentDryRunResultFindings.value : "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .slice(0, 10);
    try {
      const response = await fetch(`/api/oom-sakkie/agent-dry-runs/${encodeURIComponent(dryRunRequestId)}/results`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          result_text: resultText,
          findings,
          recorded_by: "owner",
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.status || "agent_dry_run_result_failed");
      }
      if (agentDryRunResultText) agentDryRunResultText.value = "";
      if (agentDryRunResultFindings) agentDryRunResultFindings.value = "";
      loadAgentDryRunRequests();
      loadAgentResultReviews();
      loadAgentRoadmap();
    } catch (error) {
      if (agentResultReviews) {
        agentResultReviews.innerHTML = "";
        const line = document.createElement("p");
        line.className = "oom-empty";
        line.textContent = `Agent result could not be recorded: ${(error && error.message) || "unknown error"}.`;
        agentResultReviews.appendChild(line);
      }
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "Record Result For Review";
      }
    }
  }

  function agentResultStage(item) {
    const latestEvent = item.latest_event || {};
    if (!latestEvent.event_type || latestEvent.event_type === "review_note") return "pending";
    return "closed";
  }

  function renderAgentResultRow(item) {
    const row = document.createElement("article");
    const title = document.createElement("strong");
    const badge = document.createElement("span");
    const meta = document.createElement("span");
    const text = document.createElement("p");
    const findings = document.createElement("p");
    const event = document.createElement("p");
    const guard = document.createElement("p");
    const actionGroup = document.createElement("div");
    const openButton = document.createElement("button");
    const acceptButton = document.createElement("button");
    const rejectButton = document.createElement("button");
    const noteButton = document.createElement("button");
    const latestEvent = item.latest_event || {};
    const stage = agentResultStage(item);
    row.className = stage === "pending" ? "oom-work-item oom-work-item-active" : "oom-work-item oom-work-item-muted";
    badge.className = "oom-work-badge";
    badge.textContent = stage === "pending" ? "Needs owner review" : "Reviewed";
    title.textContent = item.dry_run_result_id || "Agent result";
    meta.textContent = `${item.dry_run_request_id || ""} | ${item.specialist_slug || "sentinel"} | ${item.created_at || ""}`;
    text.textContent = (item.result_text || "No result text supplied.").slice(0, 520);
    findings.textContent = `Findings: ${(item.findings || []).slice(0, 3).join("; ") || "none supplied"}`;
    event.textContent = latestEvent.event_type
      ? `Latest event: ${latestEvent.event_type} ${latestEvent.notes ? "- " + latestEvent.notes : ""}`
      : "Latest event: none";
    guard.className = "oom-advisor-guard";
    guard.textContent = "review only | runs specialist no | dispatch no | writes no | runtime change no";
    actionGroup.className = "oom-work-actions";

    openButton.type = "button";
    openButton.className = "oom-build-brief-button";
    openButton.textContent = "Open Review Packet";
    openButton.addEventListener("click", () => {
      openAgentResultPacket(item.dry_run_result_id, openButton);
    });
    acceptButton.type = "button";
    acceptButton.className = "oom-build-brief-button";
    acceptButton.textContent = "Accept For Learning";
    acceptButton.addEventListener("click", () => {
      recordAgentResultEvent(
        item.dry_run_result_id,
        "accepted_for_learning",
        "Accepted for future learning evidence. No specialist ran and no runtime change was applied.",
        acceptButton
      );
    });
    rejectButton.type = "button";
    rejectButton.className = "oom-build-brief-button";
    rejectButton.textContent = "Reject";
    rejectButton.addEventListener("click", () => {
      recordAgentResultEvent(item.dry_run_result_id, "rejected", "Rejected from owner review. No specialist ran.", rejectButton);
    });
    noteButton.type = "button";
    noteButton.className = "oom-build-brief-button";
    noteButton.textContent = "Add Note";
    noteButton.addEventListener("click", () => {
      const note = window.prompt("Review note for this agent result. This records text only; no specialist runs.") || "";
      if (!note.trim()) return;
      recordAgentResultEvent(item.dry_run_result_id, "review_note", note.trim(), noteButton);
    });
    actionGroup.appendChild(openButton);
    if (stage === "pending") {
      actionGroup.appendChild(acceptButton);
      actionGroup.appendChild(rejectButton);
    }
    actionGroup.appendChild(noteButton);

    row.appendChild(badge);
    row.appendChild(title);
    row.appendChild(meta);
    row.appendChild(text);
    row.appendChild(findings);
    row.appendChild(event);
    row.appendChild(guard);
    row.appendChild(actionGroup);
    return row;
  }

  function appendQueueSection(parent, titleText, items, emptyText, renderItem) {
    const section = document.createElement("section");
    const heading = document.createElement("h4");
    section.className = items.length ? "oom-work-section" : "oom-work-section oom-work-section-empty";
    heading.textContent = `${titleText} (${items.length})`;
    section.appendChild(heading);
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = emptyText;
      section.appendChild(empty);
    } else {
      items.forEach((item) => section.appendChild(renderItem(item)));
    }
    parent.appendChild(section);
  }

  function renderWorkbenchNextAction() {
    if (!workbenchNextAction) return;
    const buildItems = latestBuildRequestsData && Array.isArray(latestBuildRequestsData.build_requests)
      ? latestBuildRequestsData.build_requests
      : [];
    const patchItems = latestPatchProposalsData && Array.isArray(latestPatchProposalsData.patch_proposals)
      ? latestPatchProposalsData.patch_proposals
      : [];
    const deployItems = latestDeployDecisionsData && Array.isArray(latestDeployDecisionsData.deploy_decisions)
      ? latestDeployDecisionsData.deploy_decisions
      : [];
    const agentRequestItems = latestAgentDryRunRequestsData && Array.isArray(latestAgentDryRunRequestsData.dry_run_requests)
      ? latestAgentDryRunRequestsData.dry_run_requests
      : [];
    const agentResultItems = latestAgentDryRunResultsData && Array.isArray(latestAgentDryRunResultsData.dry_run_results)
      ? latestAgentDryRunResultsData.dry_run_results
      : [];
    const deployDecidedPatchIds = new Set(deployItems.map((item) => item.patch_proposal_id).filter(Boolean));
    const pendingBuild = buildItems.filter((item) => buildRequestStage(item) === "pending");
    const pendingPatch = patchItems.filter((item) => patchProposalStage(item) === "pending");
    const deployReady = patchItems.filter((item) => {
      return patchProposalStage(item) === "ready_for_deploy" && !deployDecidedPatchIds.has(item.patch_proposal_id);
    });
    const pendingAgentRequests = agentRequestItems.filter((item) => agentDryRunRequestStage(item) === "pending");
    const pendingAgentResults = agentResultItems.filter((item) => agentResultStage(item) === "pending");

    workbenchNextAction.innerHTML = "";
    const title = document.createElement("strong");
    const summary = document.createElement("p");
    const next = document.createElement("p");
    const counts = document.createElement("div");
    title.textContent = "Next action";
    summary.textContent = `${pendingAgentRequests.length} agent handoff, ${pendingAgentResults.length} agent result review, ${pendingBuild.length} build handoff, ${pendingPatch.length} patch review, ${deployReady.length} deploy decision.`;
    if (pendingAgentRequests.length) {
      next.textContent = `Open agent handoff for ${pendingAgentRequests[0].dry_run_request_id || "the oldest dry-run request"}.`;
    } else if (pendingAgentResults.length) {
      next.textContent = `Review Sentinel dry-run result ${pendingAgentResults[0].dry_run_result_id || "waiting for review"}.`;
    } else if (pendingBuild.length) {
      next.textContent = `Start with Forge Handoff for ${pendingBuild[0].build_request_id || "the oldest build request"}.`;
    } else if (pendingPatch.length) {
      next.textContent = `Review patch proposal ${pendingPatch[0].patch_proposal_id || "waiting for review"}.`;
    } else if (deployReady.length) {
      next.textContent = `Verify/apply manually, then record a deploy decision for ${deployReady[0].patch_proposal_id || "the approved patch"}.`;
    } else {
      next.textContent = "No build, patch, or deploy approval is waiting in the current queues.";
    }
    counts.className = "oom-workbench-counts";
    [
      ["Agent handoff", pendingAgentRequests.length],
      ["Agent result", pendingAgentResults.length],
      ["Build", pendingBuild.length],
      ["Patch", pendingPatch.length],
      ["Deploy", deployReady.length],
    ].forEach(([label, value]) => {
      const pill = document.createElement("span");
      pill.textContent = `${label}: ${value}`;
      counts.appendChild(pill);
    });
    workbenchNextAction.appendChild(title);
    workbenchNextAction.appendChild(summary);
    workbenchNextAction.appendChild(next);
    workbenchNextAction.appendChild(counts);
  }

  function renderImplementationQueue(data) {
    if (!implementationQueue) return;
    if (!data || !data.success) {
      implementationQueue.innerHTML = '<p class="oom-empty">Implementation queue is unavailable.</p>';
      return;
    }
    implementationQueue.innerHTML = "";

    const policy = data.auto_prepare_policy || {};
    const guard = document.createElement("p");
    guard.className = "oom-advisor-guard";
    guard.textContent = `${data.mode || "auto_prepared_review_queue"} | writes code ${policy.writes_code ? "yes" : "no"} | applies changes ${policy.applies_changes ? "yes" : "no"} | approval ${policy.requires_human_approval ? "required" : "not required"}`;
    implementationQueue.appendChild(guard);

    const threshold = document.createElement("p");
    threshold.className = "oom-learning-next";
    threshold.textContent = `Auto-prepare threshold: ${policy.threshold || "strong reviewed evidence only"}.`;
    implementationQueue.appendChild(threshold);

    const packets = Array.isArray(data.packets) ? data.packets : [];
    const list = document.createElement("div");
    list.className = "oom-advisor-queue";
    if (!packets.length) {
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = "No implementation briefs are strong enough yet. Keep marking traces.";
      list.appendChild(empty);
    } else {
      packets.forEach((packet) => {
        const row = document.createElement("article");
        const title = document.createElement("strong");
        const evidence = document.createElement("span");
        const action = document.createElement("p");
        const openButton = document.createElement("button");
        const proposal = packet.proposal || {};
        title.textContent = `${proposal.priority || "normal"} - ${proposal.title || "implementation brief"}`;
        evidence.textContent = proposal.evidence || "";
        action.textContent = proposal.recommended_action || "";
        openButton.type = "button";
        openButton.className = "oom-build-brief-button";
        openButton.textContent = "Open Brief";
        openButton.addEventListener("click", () => {
          renderLearningPacket(packet);
        });
        row.appendChild(title);
        row.appendChild(evidence);
        row.appendChild(action);
        row.appendChild(openButton);
        list.appendChild(row);
      });
    }
    implementationQueue.appendChild(list);
  }

  function renderToolCatalog(data) {
    if (!toolCatalog) return;
    const tools = data && Array.isArray(data.tools) ? data.tools : [];
    if (!tools.length) {
      toolCatalog.innerHTML = '<p class="oom-empty">No Oom Sakkie tools are registered.</p>';
      return;
    }
    toolCatalog.innerHTML = "";
    tools.forEach((tool) => {
      const row = document.createElement("article");
      row.className = "oom-tool-row";

      const main = document.createElement("div");
      const name = document.createElement("strong");
      const description = document.createElement("span");
      name.textContent = tool.name || "unknown_tool";
      description.textContent = tool.description || "No description registered.";
      main.appendChild(name);
      main.appendChild(description);

      const meta = document.createElement("div");
      meta.className = "oom-tool-meta";
      const risk = document.createElement("code");
      const confirmation = document.createElement("code");
      risk.textContent = `risk ${tool.risk_level ?? 0}: ${tool.risk_label || "READ_ONLY"}`;
      confirmation.textContent = tool.requires_confirmation ? "confirmation required" : "no confirmation";
      meta.appendChild(risk);
      meta.appendChild(confirmation);

      row.appendChild(main);
      row.appendChild(meta);
      toolCatalog.appendChild(row);
    });
  }

  function renderPolicyStatus(data) {
    if (!policyStatus) return;
    if (!data || !data.success) {
      policyStatus.innerHTML = '<p class="oom-empty">Safety policy is unavailable.</p>';
      return;
    }
    policyStatus.innerHTML = "";
    const toolCounts = data.tool_counts || {};
    const policy = data.kiosk_policy || {};
    const reviewAccess = data.review_endpoints_access || {};
    const messageAccess = data.message_endpoint_access || {};
    const llmRouter = data.llm_router || {};
    const llmAnswer = data.llm_answer || {};
    [
      ["Mode", data.mode || "unknown"],
      ["Backend brain", data.backend_as_brain ? "on" : "off"],
      ["Kiosk max risk", `${policy.max_risk_level ?? 0}: ${policy.allowed_risk_label || "READ_ONLY"}`],
      ["Tools", `${toolCounts.read_only || 0}/${toolCounts.total || 0} read-only`],
      ["LLM fallback", llmRouter.enabled ? "enabled" : "off"],
      ["LLM configured", llmRouter.configured ? "yes" : "no"],
      ["LLM sends text", llmRouter.enabled && llmRouter.sends_user_text_when_enabled ? "yes - outbound" : "off"],
      ["LLM endpoint", llmRouter.enabled ? (llmRouter.outbound_endpoint_when_enabled || "unknown") : "not used"],
      ["LLM answer", llmAnswer.enabled ? "enabled" : "off"],
      ["Answer sends summary", llmAnswer.enabled && llmAnswer.sends_tool_summary_when_enabled ? "yes - outbound" : "off"],
      ["Answer sends context", llmAnswer.enabled && llmAnswer.sends_capped_tool_context_when_enabled ? "yes - capped outbound" : "off"],
      ["Review access", reviewAccess.default || "unknown"],
      ["Message access", messageAccess.default || "unknown"],
      ["Write tools", data.write_tools_enabled ? "enabled" : "off"],
      ["Telegram cutover", data.telegram_cutover_enabled ? "enabled" : "off"],
      ["Voice", data.browser_speech_mode || "unknown"],
      ["Continue cap", `${data.continue_conversation_max_turns || 0} turns`],
      ["Auto-send", `${data.voice_auto_send_ms || 0} ms`],
      ["Always-on mic", data.always_on_mic_enabled ? "enabled" : "off"],
    ].forEach(([label, value]) => {
      const card = document.createElement("div");
      const small = document.createElement("span");
      const strong = document.createElement("strong");
      small.textContent = label;
      strong.textContent = String(value);
      card.appendChild(small);
      card.appendChild(strong);
      policyStatus.appendChild(card);
    });

    const blocked = Array.isArray(data.blocked_capabilities) ? data.blocked_capabilities : [];
    if (blocked.length) {
      const blockedLine = document.createElement("p");
      blockedLine.className = "oom-policy-blocked";
      blockedLine.textContent = `Blocked: ${blocked.join(", ")}`;
      policyStatus.appendChild(blockedLine);
    }
  }

  function renderAgentCrew(data) {
    if (!agentCrew) return;
    const agents = data && Array.isArray(data.agents) ? data.agents : [];
    if (!agents.length) {
      agentCrew.innerHTML = '<p class="oom-empty">Agent crew foundation is unavailable.</p>';
      return;
    }
    agentCrew.innerHTML = "";

    const guard = document.createElement("p");
    guard.className = "oom-policy-blocked";
    guard.textContent = `Runtime ${data.runtime_enabled ? "on" : "off"} | dispatch ${data.dispatch_enabled ? "on" : "off"} | autonomous loops ${data.autonomous_loops_enabled ? "on" : "off"}`;
    agentCrew.appendChild(guard);

    agents.forEach((agent) => {
      const row = document.createElement("article");
      row.className = "oom-tool-row";

      const main = document.createElement("div");
      const name = document.createElement("strong");
      const role = document.createElement("span");
      const tools = document.createElement("span");
      name.textContent = `${agent.name || agent.slug || "Agent"} (${agent.personality || "specialist"})`;
      role.textContent = agent.role || "No role registered.";
      tools.textContent = `Tools: ${(agent.allowed_tools || []).join(", ") || "none yet"}`;
      main.appendChild(name);
      main.appendChild(role);
      main.appendChild(tools);

      const meta = document.createElement("div");
      meta.className = "oom-tool-meta";
      const mode = document.createElement("code");
      const risk = document.createElement("code");
      mode.textContent = agent.dispatch_enabled ? "dispatch enabled" : "advisory only";
      risk.textContent = `risk limit ${agent.risk_limit ?? 0}`;
      meta.appendChild(mode);
      meta.appendChild(risk);

      row.appendChild(main);
      row.appendChild(meta);
      agentCrew.appendChild(row);
    });
  }

  function renderAgentRoadmap(data) {
    if (!agentRoadmap) return;
    if (!data || !data.activation_plan) {
      agentRoadmap.innerHTML = '<p class="oom-empty">Agent roadmap is unavailable.</p>';
      return;
    }
    const plan = data.activation_plan || {};
    const candidate = plan.recommended_first_candidate || {};
    const stages = Array.isArray(plan.stages) ? plan.stages : [];
    const evidence = Array.isArray(data.accepted_learning) ? data.accepted_learning : [];
    const guard = data.review_guard || {};
    agentRoadmap.innerHTML = "";

    const status = document.createElement("p");
    status.className = "oom-policy-blocked";
    status.textContent = `next ${plan.recommended_next_stage || "read-only dry-run"} | accepted evidence ${data.accepted_learning_count || 0} | dispatch ${guard.dispatch_enabled ? "on" : "off"} | writes ${guard.writes ? "on" : "off"}`;
    agentRoadmap.appendChild(status);

    const candidateCard = document.createElement("article");
    candidateCard.className = "oom-work-item";
    const candidateTitle = document.createElement("strong");
    const candidateReason = document.createElement("p");
    const candidateGuard = document.createElement("code");
    candidateTitle.textContent = `First safe candidate: ${candidate.name || candidate.slug || "Sentinel"}`;
    candidateReason.textContent = candidate.reason || "Recommended first because it can review guardrails without touching farm data.";
    candidateGuard.textContent = "planning only | owner approval required | runtime locked";
    candidateCard.appendChild(candidateTitle);
    candidateCard.appendChild(candidateReason);
    candidateCard.appendChild(candidateGuard);
    agentRoadmap.appendChild(candidateCard);

    const stageList = document.createElement("div");
    stageList.className = "oom-work-list";
    stages.forEach((stage) => {
      const item = document.createElement("article");
      item.className = "oom-work-item";
      const title = document.createElement("strong");
      const text = document.createElement("p");
      const code = document.createElement("code");
      title.textContent = stage.stage || "stage";
      text.textContent = stage.summary || "";
      code.textContent = stage.status || "locked";
      item.appendChild(title);
      item.appendChild(text);
      item.appendChild(code);
      stageList.appendChild(item);
    });
    agentRoadmap.appendChild(stageList);

    const learning = document.createElement("div");
    learning.className = "oom-work-list";
    const learningTitle = document.createElement("p");
    learningTitle.className = "oom-label";
    learningTitle.textContent = "Accepted Sentinel learning";
    learning.appendChild(learningTitle);
    if (!evidence.length) {
      const empty = document.createElement("p");
      empty.className = "oom-empty";
      empty.textContent = "No accepted evidence has been approved for planning yet.";
      learning.appendChild(empty);
    } else {
      evidence.slice(0, 3).forEach((item) => {
        const row = document.createElement("article");
        row.className = "oom-work-item";
        const title = document.createElement("strong");
        const text = document.createElement("p");
        const note = document.createElement("code");
        title.textContent = item.dry_run_result_id || "Accepted result";
        text.textContent = item.result_text || "Accepted Sentinel evidence.";
        note.textContent = `accepted ${item.accepted_at || "recorded"} | runtime change no`;
        row.appendChild(title);
        row.appendChild(text);
        row.appendChild(note);
        learning.appendChild(row);
      });
    }
    agentRoadmap.appendChild(learning);
  }

  function renderRecentTraces(items) {
    if (!recentTraces) return;
    if (!items || !items.length) {
      recentTraces.innerHTML = '<p class="oom-empty">No trace history found.</p>';
      return;
    }
    recentTraces.innerHTML = "";
    items.forEach((item) => {
      const row = document.createElement("article");
      row.className = "oom-recent-row";
      const tool = item.tool_name || "clarification";

      const main = document.createElement("div");
      const question = document.createElement("strong");
      const meta = document.createElement("span");
      const feedbackStatus = document.createElement("span");
      feedbackStatus.className = "oom-feedback-status";
      question.textContent = item.user_text || "(empty)";
      meta.textContent = `${tool} | ${item.created_at || ""}`;
      feedbackStatus.textContent = latestFeedbackText(item.latest_feedback);
      main.appendChild(question);
      main.appendChild(meta);
      main.appendChild(feedbackStatus);

      const side = document.createElement("div");
      side.className = "oom-recent-side";
      const code = document.createElement("code");
      code.textContent = item.trace_id || "";
      side.appendChild(code);
      side.appendChild(buildFeedbackControls(item.trace_id || ""));

      row.appendChild(main);
      row.appendChild(side);
      row.appendChild(buildTraceDetails(item));
      recentTraces.appendChild(row);
    });
  }

  function buildTraceDetails(item) {
    const details = document.createElement("details");
    details.className = "oom-recent-details";

    const summary = document.createElement("summary");
    summary.textContent = "Show saved answer";
    details.appendChild(summary);

    const answerText = document.createElement("p");
    answerText.className = "oom-recent-answer";
    answerText.textContent = item.answer || "No saved answer.";
    details.appendChild(answerText);

    const toolSummary = document.createElement("p");
    toolSummary.className = "oom-recent-tool-summary";
    toolSummary.textContent = item.tool_result_summary || "No tool summary stored.";
    details.appendChild(toolSummary);

    const warningsList = buildTraceWarnings(item.stale_warnings || []);
    if (warningsList) details.appendChild(warningsList);

    const safetyList = buildTraceSafetyNotes(item.safety_notes || []);
    if (safetyList) details.appendChild(safetyList);

    const linksList = buildTraceLinks(item.links || []);
    if (linksList) details.appendChild(linksList);

    return details;
  }

  function buildTraceWarnings(items) {
    if (!items.length) return null;
    const list = document.createElement("ul");
    list.className = "oom-recent-warning-list";
    items.forEach((warning) => {
      const item = document.createElement("li");
      item.textContent = warning;
      list.appendChild(item);
    });
    return list;
  }

  function buildTraceSafetyNotes(items) {
    if (!items.length) return null;
    const list = document.createElement("ul");
    list.className = "oom-recent-safety-list";
    items.forEach((note) => {
      const item = document.createElement("li");
      item.textContent = note;
      list.appendChild(item);
    });
    return list;
  }

  function buildTraceLinks(items) {
    if (!items.length) return null;
    const wrap = document.createElement("div");
    wrap.className = "oom-recent-link-list";
    items.forEach((link) => {
      const anchor = document.createElement("a");
      anchor.href = link.href || "#";
      anchor.textContent = link.label || link.href || "Open";
      wrap.appendChild(anchor);
    });
    return wrap;
  }

  function setActiveReviewFilter(value) {
    activeReviewFilter = ["all", "unreviewed", "issues", "reviewed"].includes(value) ? value : "all";
    reviewFilterButtons.forEach((button) => {
      const isActive = button.dataset.reviewFilter === activeReviewFilter;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function latestFeedbackText(feedback) {
    if (!feedback || !feedback.feedback_type) {
      return "Not reviewed yet";
    }
    const label = feedbackOptions.find((option) => option[0] === feedback.feedback_type);
    const text = label ? label[1] : feedback.feedback_type;
    const note = feedback.notes ? ` - ${feedback.notes}` : "";
    return `Reviewed: ${text}${note}`;
  }

  function buildFeedbackControls(traceIdValue) {
    const controls = document.createElement("div");
    controls.className = "oom-feedback-controls";

    const select = document.createElement("select");
    select.setAttribute("aria-label", "Trace feedback type");
    feedbackOptions.forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      select.appendChild(option);
    });

    const note = document.createElement("input");
    note.type = "text";
    note.maxLength = 160;
    note.placeholder = "Optional note";
    note.setAttribute("aria-label", "Trace feedback note");

    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Save";
    button.addEventListener("click", () => {
      saveTraceFeedback(traceIdValue, select.value, note.value, button);
    });

    controls.appendChild(select);
    controls.appendChild(note);
    controls.appendChild(button);
    return controls;
  }

  async function saveTraceFeedback(traceIdValue, feedbackType, notesValue, button) {
    if (!traceIdValue || !feedbackType) return;
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "Saving";
    try {
      const response = await fetch(`/api/oom-sakkie/traces/${encodeURIComponent(traceIdValue)}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          feedback_type: feedbackType,
          notes: notesValue || "",
          reviewed_by: "kiosk",
          channel: "kiosk",
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.status || "feedback_failed");
      }
      refreshReviewData();
    } catch (error) {
      button.textContent = "Error";
      window.setTimeout(() => {
        button.textContent = originalText;
        button.disabled = false;
      }, 1200);
      return;
    }
    button.textContent = originalText;
    button.disabled = false;
  }

  async function loadRecentTraces() {
    if (!recentTraces) return;
    try {
      const search = traceSearch ? traceSearch.value.trim() : "";
      const response = await fetch(`/api/oom-sakkie/traces?channel=kiosk&limit=8&review=${encodeURIComponent(activeReviewFilter)}&q=${encodeURIComponent(search)}`);
      const data = await response.json();
      renderRecentTraces(data.traces || []);
    } catch (error) {
      recentTraces.innerHTML = '<p class="oom-empty">Trace history is unavailable.</p>';
    }
  }

  async function loadReviewSummary() {
    if (!reviewSummary) return;
    try {
      const response = await fetch("/api/oom-sakkie/traces/review-summary?channel=kiosk&days=14");
      const data = await response.json();
      renderReviewSummary(data);
    } catch (error) {
      reviewSummary.innerHTML = '<p class="oom-empty">Review summary is unavailable.</p>';
    }
  }

  async function loadReviewAdvisor() {
    if (!reviewAdvisor) return;
    try {
      const response = await fetch("/api/oom-sakkie/review-advisor?channel=kiosk&days=14&limit=12");
      const data = await response.json();
      renderReviewAdvisor(data);
    } catch (error) {
      reviewAdvisor.innerHTML = '<p class="oom-empty">Review advisor is unavailable.</p>';
    }
  }

  async function loadLearningAdvisor() {
    if (!learningAdvisor) return;
    try {
      const response = await fetch("/api/oom-sakkie/learning-advisor?channel=kiosk&days=14&limit=12");
      const data = await response.json();
      renderLearningAdvisor(data);
    } catch (error) {
      learningAdvisor.innerHTML = '<p class="oom-empty">Learning queue is unavailable.</p>';
    }
  }

  async function analyzeLearningAdvisor() {
    if (!learningAdvisor) return;
    learningAdvisor.innerHTML = '<p class="oom-empty">Running learning analysis...</p>';
    try {
      const response = await fetch("/api/oom-sakkie/learning-advisor/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel: "kiosk", days: 14, limit: 12 }),
      });
      const data = await response.json();
      renderLearningAnalysis(data);
    } catch (error) {
      learningAdvisor.innerHTML = '<p class="oom-empty">Learning analysis is unavailable.</p>';
    }
  }

  async function buildLearningPacket(proposal, button) {
    if (!learningPacket) return;
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "Building...";
    }
    learningPacket.hidden = false;
    learningPacket.innerHTML = '<p class="oom-empty">Building review brief...</p>';
    try {
      const response = await fetch("/api/oom-sakkie/learning-advisor/build-packet", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposal }),
      });
      const data = await response.json();
      renderLearningPacket(data);
    } catch (error) {
      learningPacket.innerHTML = '<p class="oom-empty">Build brief is unavailable.</p>';
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "Build Brief";
      }
    }
  }

  async function approveBuildRequest(packet, button) {
    if (!learningPacket) return;
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "Approving...";
    }
    try {
      const response = await fetch("/api/oom-sakkie/learning-advisor/approve-build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ packet, approved_by: "owner" }),
      });
      const data = await response.json();
      renderBuildApproval(data);
      loadBuildRequests();
    } catch (error) {
      const line = document.createElement("p");
      line.className = "oom-empty";
      line.textContent = "Build approval is unavailable.";
      learningPacket.appendChild(line);
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "Approve for Build";
      }
    }
  }

  async function loadImplementationQueue() {
    if (!implementationQueue) return;
    try {
      const response = await fetch("/api/oom-sakkie/learning-advisor/implementation-queue?channel=kiosk&days=14&limit=12");
      const data = await response.json();
      renderImplementationQueue(data);
    } catch (error) {
      implementationQueue.innerHTML = '<p class="oom-empty">Implementation queue is unavailable.</p>';
    }
  }

  async function loadBuildRequests() {
    if (!buildRequests) return;
    try {
      const response = await fetch("/api/oom-sakkie/build-requests?limit=8");
      const data = await response.json();
      latestBuildRequestsData = data;
      renderBuildRequests(data);
      renderWorkbenchNextAction();
    } catch (error) {
      buildRequests.innerHTML = '<p class="oom-empty">Build request store is unavailable.</p>';
    }
  }

  async function loadPatchProposals() {
    if (!patchProposals) return;
    try {
      const response = await fetch("/api/oom-sakkie/patch-proposals?limit=8");
      const data = await response.json();
      latestPatchProposalsData = data;
      renderPatchProposals(data);
      renderWorkbenchNextAction();
    } catch (error) {
      patchProposals.innerHTML = '<p class="oom-empty">Patch proposal store is unavailable.</p>';
    }
  }

  async function loadDeployDecisions() {
    if (!deployDecisions) return;
    try {
      const response = await fetch("/api/oom-sakkie/deploy-decisions?limit=8");
      const data = await response.json();
      latestDeployDecisionsData = data;
      renderDeployDecisions(data);
      renderWorkbenchNextAction();
    } catch (error) {
      deployDecisions.innerHTML = '<p class="oom-empty">Deploy decision store is unavailable.</p>';
    }
  }

  async function loadAgentResultReviews() {
    if (!agentResultReviews) return;
    try {
      const response = await fetch("/api/oom-sakkie/agent-dry-run-results?limit=8");
      const data = await response.json();
      latestAgentDryRunResultsData = data;
      renderAgentResultReviews(data);
      renderAgentLearningLedger(data);
      renderWorkbenchNextAction();
    } catch (error) {
      agentResultReviews.innerHTML = '<p class="oom-empty">Agent result reviews are unavailable.</p>';
      if (agentLearningLedger) agentLearningLedger.innerHTML = '<p class="oom-empty">Agent learning ledger is unavailable.</p>';
    }
  }

  async function openAgentResultPacket(dryRunResultId, button) {
    if (!dryRunResultId || !agentResultReviews) return;
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "Opening...";
    }
    try {
      const response = await fetch(`/api/oom-sakkie/agent-dry-run-results/${encodeURIComponent(dryRunResultId)}/review-packet`);
      const data = await response.json();
      renderAgentResultPacket(data);
    } catch (error) {
      const line = document.createElement("p");
      line.className = "oom-empty";
      line.textContent = "Agent result packet is unavailable.";
      agentResultReviews.appendChild(line);
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "Open Review Packet";
      }
    }
  }

  function renderAgentResultPacket(data) {
    if (!agentResultReviews) return;
    const panel = document.createElement("article");
    const title = document.createElement("strong");
    const mode = document.createElement("p");
    const result = document.createElement("p");
    const findings = document.createElement("p");
    const guard = document.createElement("p");
    const options = document.createElement("p");
    panel.className = "oom-deploy-instructions";
    title.textContent = data && data.success ? `Review packet: ${data.dry_run_result_id || "agent result"}` : "Review packet unavailable";
    mode.textContent = data && data.status ? `${data.mode || "unknown"} | ${data.status}` : "No packet returned.";
    result.textContent = data && data.result_text ? `Result: ${data.result_text}` : "Result: not supplied.";
    findings.textContent = data && Array.isArray(data.findings)
      ? `Findings: ${data.findings.slice(0, 5).join("; ") || "none supplied"}`
      : "Findings: none supplied.";
    const reviewGuard = data && data.review_guard ? data.review_guard : {};
    guard.textContent = `Guard: review only ${reviewGuard.review_only ? "yes" : "no"} | runs specialist ${reviewGuard.runs_specialist ? "yes" : "no"} | writes ${reviewGuard.writes ? "yes" : "no"} | runtime change ${reviewGuard.applies_runtime_change ? "yes" : "no"}`;
    options.textContent = data && Array.isArray(data.owner_options)
      ? `Owner options: ${data.owner_options.map((item) => item.event_type).join(", ")}`
      : "Owner options: unavailable.";
    panel.appendChild(title);
    panel.appendChild(mode);
    panel.appendChild(result);
    panel.appendChild(findings);
    panel.appendChild(guard);
    panel.appendChild(options);
    agentResultReviews.appendChild(panel);
  }

  async function buildForgeHandoff(buildRequestId, button) {
    if (!buildRequestId) return;
    if (!forgeHandoff) return;
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "Preparing...";
    }
    forgeHandoff.hidden = false;
    forgeHandoff.innerHTML = '<p class="oom-empty">Preparing Forge handoff...</p>';
    try {
      const response = await fetch("/api/oom-sakkie/build-requests/forge-handoff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ build_request_id: buildRequestId }),
      });
      const data = await response.json();
      renderForgeHandoff(data);
    } catch (error) {
      forgeHandoff.innerHTML = '<p class="oom-empty">Forge handoff is unavailable.</p>';
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "Forge Handoff";
      }
    }
  }

  async function recordBuildRequestEvent(buildRequestId, eventType, notes, button) {
    if (!buildRequestId) return;
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "Recording...";
    }
    try {
      await fetch(`/api/oom-sakkie/build-requests/${encodeURIComponent(buildRequestId)}/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_type: eventType, notes, recorded_by: "owner" }),
      });
      loadBuildRequests();
    } catch (error) {
      if (buildRequests) {
        const line = document.createElement("p");
        line.className = "oom-empty";
        line.textContent = "Build request event could not be recorded.";
        buildRequests.appendChild(line);
      }
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "Ignore";
      }
    }
  }

  async function recordPatchProposal(button) {
    if (!patchBuildRequestId || !patchProposalText) return;
    const buildRequestId = patchBuildRequestId.value.trim();
    const proposalText = patchProposalText.value.trim();
    if (!buildRequestId || !proposalText) {
      if (patchProposals) {
        patchProposals.innerHTML = '<p class="oom-empty">Build request ID and proposal text are required. This does not apply a patch.</p>';
      }
      return;
    }
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "Recording...";
    }
    try {
      const response = await fetch(`/api/oom-sakkie/build-requests/${encodeURIComponent(buildRequestId)}/patch-proposals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          proposal_text: proposalText,
          proposed_by: "builder",
          risk_notes: "Owner review required before manual patch application.",
          files_touched: [],
          verification: [],
        }),
      });
      const data = await response.json();
      if (patchProposals && !data.success) {
        patchProposals.innerHTML = "";
        const line = document.createElement("p");
        line.className = "oom-empty";
        line.textContent = `Patch proposal could not be recorded: ${data.status || "unknown"}.`;
        patchProposals.appendChild(line);
      }
      if (data.success) {
        patchProposalText.value = "";
        await recordBuildRequestEvent(
          buildRequestId,
          "review_note",
          "Patch proposal recorded; moved to Patch Proposal Gate.",
          null
        );
      }
      loadPatchProposals();
      loadBuildRequests();
    } catch (error) {
      if (patchProposals) {
        patchProposals.innerHTML = '<p class="oom-empty">Patch proposal could not be recorded.</p>';
      }
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "Record Patch Proposal";
      }
    }
  }

  async function recordPatchProposalEvent(patchProposalId, eventType, notes, button) {
    if (!patchProposalId) return;
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "Recording...";
    }
    try {
      await fetch(`/api/oom-sakkie/patch-proposals/${encodeURIComponent(patchProposalId)}/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_type: eventType, notes, recorded_by: "owner" }),
      });
      loadPatchProposals();
      loadDeployDecisions();
    } catch (error) {
      if (patchProposals) {
        const line = document.createElement("p");
        line.className = "oom-empty";
        line.textContent = "Patch proposal event could not be recorded.";
        patchProposals.appendChild(line);
      }
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "Review";
      }
    }
  }

  async function recordAgentResultEvent(dryRunResultId, eventType, notes, button) {
    if (!dryRunResultId) return;
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "Recording...";
    }
    try {
      await fetch(`/api/oom-sakkie/agent-dry-run-results/${encodeURIComponent(dryRunResultId)}/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_type: eventType, notes, recorded_by: "owner" }),
      });
      loadAgentResultReviews();
    } catch (error) {
      if (agentResultReviews) {
        const line = document.createElement("p");
        line.className = "oom-empty";
        line.textContent = "Agent result review event could not be recorded.";
        agentResultReviews.appendChild(line);
      }
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "Review";
      }
    }
  }

  async function recordDeployDecision(decisionType, button) {
    if (!deployPatchProposalId) return;
    const patchProposalId = deployPatchProposalId.value.trim();
    const verificationSummary = deployVerificationSummary ? deployVerificationSummary.value.trim() : "";
    if (!patchProposalId) {
      if (deployDecisions) {
        deployDecisions.innerHTML = '<p class="oom-empty">Patch proposal ID is required. This does not deploy.</p>';
      }
      return;
    }
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "Recording...";
    }
    try {
      const response = await fetch(`/api/oom-sakkie/patch-proposals/${encodeURIComponent(patchProposalId)}/deploy-decisions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          decision_type: decisionType,
          environment: "local",
          verification_summary: verificationSummary,
          notes: decisionType === "approved_for_manual_deploy"
            ? "Approved for manual deploy outside the kiosk. No deploy was run here."
            : "Deploy deferred from kiosk review. No deploy was run here.",
          approved_by: "owner",
        }),
      });
      const data = await response.json();
      if (deployDecisions && !data.success) {
        deployDecisions.innerHTML = "";
        const line = document.createElement("p");
        line.className = "oom-empty";
        line.textContent = `Deploy decision could not be recorded: ${data.status || "unknown"}.`;
        deployDecisions.appendChild(line);
      }
      loadDeployDecisions();
      loadPatchProposals();
    } catch (error) {
      if (deployDecisions) {
        deployDecisions.innerHTML = '<p class="oom-empty">Deploy decision could not be recorded.</p>';
      }
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "Record Deploy Decision";
      }
    }
  }

  async function loadToolCatalog() {
    if (!toolCatalog) return;
    try {
      const response = await fetch("/api/oom-sakkie/tools");
      const data = await response.json();
      renderToolCatalog(data);
    } catch (error) {
      toolCatalog.innerHTML = '<p class="oom-empty">Tool registry is unavailable.</p>';
    }
  }

  async function loadPolicyStatus() {
    if (!policyStatus) return;
    try {
      const response = await fetch("/api/oom-sakkie/policy");
      const data = await response.json();
      renderPolicyStatus(data);
    } catch (error) {
      policyStatus.innerHTML = '<p class="oom-empty">Safety policy is unavailable.</p>';
    }
  }

  async function loadAgentCrew() {
    if (!agentCrew) return;
    try {
      const response = await fetch("/api/oom-sakkie/agents");
      const data = await response.json();
      renderAgentCrew(data);
    } catch (error) {
      agentCrew.innerHTML = '<p class="oom-empty">Agent crew foundation is unavailable.</p>';
    }
  }

  async function loadAgentRoadmap() {
    if (!agentRoadmap) return;
    try {
      const response = await fetch("/api/oom-sakkie/agents/activation-plan?limit=20");
      const data = await response.json();
      renderAgentRoadmap(data);
    } catch (error) {
      agentRoadmap.innerHTML = '<p class="oom-empty">Agent roadmap is unavailable.</p>';
    }
  }

  async function loadAgentDryRunRequests() {
    if (!agentDryRunRequests) return;
    try {
      const response = await fetch("/api/oom-sakkie/agent-dry-runs?limit=8");
      const data = await response.json();
      latestAgentDryRunRequestsData = data;
      renderAgentDryRunRequests(data);
      renderWorkbenchNextAction();
    } catch (error) {
      agentDryRunRequests.innerHTML = '<p class="oom-empty">Agent dry-run request queue is unavailable.</p>';
    }
  }

  function dryRunRequestPayload(specialistSlug) {
    if (specialistSlug === "prism") {
      return {
        specialist_slug: "prism",
        requested_by: "kiosk",
        owner_text: "Owner requested a Prism read-only dry-run from the Agent Roadmap panel.",
        purpose: "Create an append-only approval record for a future Prism kiosk/interface review. Do not run Prism.",
        guardrails: [
          "No live specialist dispatch.",
          "No specialist LLM execution from this request.",
          "No specialist tool execution from this request.",
          "No generated assets, code edits, patch application, or deploy.",
          "Owner must review any future dry-run result manually.",
        ],
      };
    }
    return {
      specialist_slug: "sentinel",
      requested_by: "kiosk",
      owner_text: "Owner requested the first Sentinel read-only dry-run from the Agent Roadmap panel.",
      purpose: "Create an append-only approval record for a future Sentinel dry-run review. Do not run Sentinel.",
      guardrails: [
        "No live specialist dispatch.",
        "No specialist LLM execution from this request.",
        "No specialist tool execution from this request.",
        "No write, post, sale, control, patch, or deploy.",
        "Owner must review any future dry-run result manually.",
      ],
    };
  }

  async function requestAgentDryRun(button, specialistSlug) {
    if (!button || !agentRoadmap) return;
    const payload = dryRunRequestPayload(specialistSlug);
    const specialistName = payload.specialist_slug === "prism" ? "Prism" : "Sentinel";
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "Requesting";
    try {
      const response = await fetch("/api/oom-sakkie/agent-dry-runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.status || "agent_dry_run_request_failed");
      }
      renderAgentRoadmapRequestResult(data);
      loadAgentRoadmap();
      loadAgentDryRunRequests();
      loadAgentResultReviews();
      button.textContent = "Requested";
    } catch (error) {
      const line = document.createElement("p");
      line.className = "oom-empty";
      line.textContent = `${specialistName} dry-run request failed: ${(error && error.message) || "unknown error"}.`;
      agentRoadmap.prepend(line);
      button.textContent = "Error";
    } finally {
      window.setTimeout(() => {
        button.disabled = false;
        button.textContent = originalText || `Request ${specialistName} Dry-Run`;
      }, 1400);
    }
  }

  async function requestSentinelDryRun(button) {
    return requestAgentDryRun(button, "sentinel");
  }

  async function requestPrismDryRun(button) {
    return requestAgentDryRun(button, "prism");
  }

  function renderAgentRoadmapRequestResult(data) {
    if (!agentRoadmap) return;
    const card = document.createElement("article");
    card.className = "oom-work-item";
    const title = document.createElement("strong");
    const detail = document.createElement("p");
    const guard = document.createElement("code");
    const specialistName = (data.specialist_slug || "sentinel").replace(/^\w/, (letter) => letter.toUpperCase());
    title.textContent = `${specialistName} dry-run request recorded: ${data.dry_run_request_id || "new request"}`;
    detail.textContent = `This only records owner approval intent for a future review. ${specialistName} did not run.`;
    guard.textContent = `dispatch ${data.dispatch_enabled ? "on" : "off"} | specialist LLM ${data.runs_specialist_llm ? "on" : "off"} | tools ${data.runs_specialist_tools ? "on" : "off"} | writes ${data.writes ? "on" : "off"}`;
    card.appendChild(title);
    card.appendChild(detail);
    card.appendChild(guard);
    agentRoadmap.prepend(card);
  }

  function refreshReviewData() {
    loadReviewSummary();
    loadRecentTraces();
    loadReviewAdvisor();
    loadLearningAdvisor();
    loadImplementationQueue();
    loadBuildRequests();
    loadPatchProposals();
    loadDeployDecisions();
    loadAgentResultReviews();
    loadAgentRoadmap();
    loadAgentDryRunRequests();
  }

  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const text = (input.value || "").trim();
      if (!text) return;
      ask(text).catch((error) => {
        answer.textContent = "Oom Sakkie could not check that right now.";
        traceId.textContent = "Request failed";
        toolUsed.textContent = error && error.name ? error.name : "Error";
        setStatus("Error", "error");
      });
    });
  }

  if (refreshTraces) {
    refreshTraces.addEventListener("click", refreshReviewData);
  }

  if (refreshAdvisor) {
    refreshAdvisor.addEventListener("click", loadReviewAdvisor);
  }

  if (refreshLearning) {
    refreshLearning.addEventListener("click", loadLearningAdvisor);
  }

  if (runLearningAnalysis) {
    runLearningAnalysis.addEventListener("click", analyzeLearningAdvisor);
  }

  if (refreshImplementationQueue) {
    refreshImplementationQueue.addEventListener("click", loadImplementationQueue);
  }

  if (refreshBuildRequests) {
    refreshBuildRequests.addEventListener("click", loadBuildRequests);
  }

  if (refreshPatchProposals) {
    refreshPatchProposals.addEventListener("click", loadPatchProposals);
  }

  if (recordPatchProposalButton) {
    recordPatchProposalButton.addEventListener("click", () => recordPatchProposal(recordPatchProposalButton));
  }

  if (refreshDeployDecisions) {
    refreshDeployDecisions.addEventListener("click", loadDeployDecisions);
  }

  if (approveManualDeployButton) {
    approveManualDeployButton.addEventListener("click", () => {
      recordDeployDecision("approved_for_manual_deploy", approveManualDeployButton);
    });
  }

  if (deferDeployButton) {
    deferDeployButton.addEventListener("click", () => {
      recordDeployDecision("deferred", deferDeployButton);
    });
  }

  if (refreshTools) {
    refreshTools.addEventListener("click", loadToolCatalog);
  }

  if (refreshPolicy) {
    refreshPolicy.addEventListener("click", loadPolicyStatus);
  }

  if (refreshAgents) {
    refreshAgents.addEventListener("click", loadAgentCrew);
  }

  if (refreshAgentRoadmap) {
    refreshAgentRoadmap.addEventListener("click", loadAgentRoadmap);
  }

  if (requestSentinelDryRunButton) {
    requestSentinelDryRunButton.addEventListener("click", () => requestSentinelDryRun(requestSentinelDryRunButton));
  }
  if (requestPrismDryRunButton) {
    requestPrismDryRunButton.addEventListener("click", () => requestPrismDryRun(requestPrismDryRunButton));
  }

  if (refreshAgentDryRunRequests) {
    refreshAgentDryRunRequests.addEventListener("click", loadAgentDryRunRequests);
  }

  if (recordAgentDryRunResultButton) {
    recordAgentDryRunResultButton.addEventListener("click", () => recordAgentDryRunResult(recordAgentDryRunResultButton));
  }

  if (refreshAgentResultReviews) {
    refreshAgentResultReviews.addEventListener("click", loadAgentResultReviews);
  }

  if (refreshAgentLearningLedger) {
    refreshAgentLearningLedger.addEventListener("click", loadAgentResultReviews);
  }

  if (voiceButton) {
    voiceButton.disabled = !SpeechRecognition;
    voiceButton.addEventListener("click", toggleVoiceDraft);
  }

  if (voiceAskButton) {
    voiceAskButton.disabled = !SpeechRecognition;
    voiceAskButton.addEventListener("click", toggleVoiceAsk);
  }

  if (cancelVoiceSendButton) {
    cancelVoiceSendButton.addEventListener("click", () => {
      clearVoiceAutoSubmit("Voice send cancelled. Review the text, then press Ask if it is right.");
    });
  }

  if (stopConversationButton) {
    stopConversationButton.addEventListener("click", () => {
      stopConversation("Conversation stopped. Mic stayed off.");
    });
  }

  if (input) {
    input.addEventListener("input", () => {
      clearVoiceAutoSubmit("Voice send cancelled because the text changed. Press Ask when ready.");
    });
  }

  if (speakAnswerButton) {
    speakAnswerButton.disabled = !speechSynthesisApi;
    speakAnswerButton.addEventListener("click", speakCurrentAnswer);
  }

  if (stopSpeechButton) {
    stopSpeechButton.disabled = !speechSynthesisApi;
    stopSpeechButton.addEventListener("click", stopSpeech);
  }

  if (autoSpeak) {
    autoSpeak.disabled = !speechSynthesisApi;
  }

  if (continueConversation) {
    continueConversation.disabled = !speechSynthesisApi || !SpeechRecognition;
    continueConversation.addEventListener("change", () => {
      if (continueConversation.checked && autoSpeak) {
        autoSpeak.checked = true;
        voiceLoopTurnCount = 0;
        renderVoiceLoopCounter();
        setVoiceStatus("Continue conversation is on. Spoken replies will listen for the next question after they finish.");
      } else {
        voiceLoopTurnCount = 0;
        renderVoiceLoopCounter();
        setVoiceStatus("Continue conversation is off.");
      }
      updateConversationStopVisibility();
    });
  }

  renderVoiceLoopCounter();

  reviewFilterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setActiveReviewFilter(button.dataset.reviewFilter || "all");
      loadRecentTraces();
    });
  });

  if (traceSearch) {
    traceSearch.addEventListener("input", () => {
      window.clearTimeout(traceSearchTimer);
      traceSearchTimer = window.setTimeout(loadRecentTraces, 220);
    });
  }

  if (clearTraceSearch) {
    clearTraceSearch.addEventListener("click", () => {
      if (traceSearch) traceSearch.value = "";
      loadRecentTraces();
    });
  }

  if (clearVoiceEvents) {
    clearVoiceEvents.addEventListener("click", () => {
      voiceEventLog = [];
      renderVoiceEvents();
    });
  }

  quickAskButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const text = (button.dataset.quickAsk || "").trim();
      if (!text) return;
      if (input) input.value = text;
      ask(text).catch((error) => {
        answer.textContent = "Oom Sakkie could not check that right now.";
        traceId.textContent = "Request failed";
        toolUsed.textContent = error && error.name ? error.name : "Error";
        setStatus("Error", "error");
      });
    });
  });

  setActiveReviewFilter("all");
  renderVoiceReadiness();
  renderVoiceEvents();
  loadToolCatalog();
  loadPolicyStatus();
  loadAgentCrew();
  loadAgentRoadmap();
  loadAgentDryRunRequests();
  refreshReviewData();
})();
