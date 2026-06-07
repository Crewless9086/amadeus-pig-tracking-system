(function () {
  const form = document.getElementById("oom_form");
  const input = document.getElementById("oom_text");
  const statusText = document.getElementById("oom_status_text");
  const userText = document.getElementById("oom_user_text");
  const answer = document.getElementById("oom_answer");
  const warnings = document.getElementById("oom_warnings");
  const safetyNotes = document.getElementById("oom_safety_notes");
  const links = document.getElementById("oom_links");
  const traceId = document.getElementById("oom_trace_id");
  const toolUsed = document.getElementById("oom_tool_used");
  const riskLevel = document.getElementById("oom_risk_level");
  const voiceButton = document.getElementById("oom_voice_button");
  const voiceAskButton = document.getElementById("oom_voice_ask_button");
  const voiceStatus = document.getElementById("oom_voice_status");
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
  const toolCatalog = document.getElementById("oom_tool_catalog");
  const refreshTools = document.getElementById("oom_refresh_tools");
  const policyStatus = document.getElementById("oom_policy_status");
  const refreshPolicy = document.getElementById("oom_refresh_policy");
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
  const feedbackOptions = [
    ["", "Mark review"],
    ["correct", "Correct"],
    ["wrong_tool", "Wrong tool"],
    ["stale_or_missing_data", "Stale/missing data"],
    ["bad_wording", "Bad wording"],
    ["needs_follow_up", "Needs follow-up"],
  ];

  function setStatus(value) {
    statusText.textContent = value;
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
      setStatus("Listening");
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
      setStatus("Voice error");
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
      if (statusText.textContent === "Listening") setStatus("Idle");
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
      setStatus("Idle");
    }
    setVoiceStatus(message || "Conversation stopped. Mic stayed off.");
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
        setStatus("Error");
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
      setStatus("Speaking");
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
        setVoiceStatus("Speech finished. Listening for the next question.");
        logVoiceEvent("Continuing", `turn ${voiceLoopTurnCount} of ${MAX_CONTINUE_TURNS}`);
        updateConversationStopVisibility();
        startVoiceAskCapture(false);
        return;
      }
      voiceLoopTurnCount = 0;
      if (statusText.textContent === "Speaking") setStatus("Answered");
      logVoiceEvent("Speech finished", "mic stayed off");
      setVoiceStatus("Speech finished. Mic stayed off.");
      updateConversationStopVisibility();
    };
    speechUtterance.onerror = () => {
      if (currentSpeechRunId !== speechRunId) return;
      speechUtterance = null;
      voiceLoopTurnCount = 0;
      setStatus("Speech error");
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
    if (statusText.textContent === "Speaking") setStatus("Answered");
    logVoiceEvent("Speech stopped", "manual stop");
    setVoiceStatus("Speech stopped. Mic stayed off.");
    updateConversationStopVisibility();
  }

  async function ask(text) {
    clearVoiceAutoSubmit();
    if (!preserveVoiceLoopCountForAsk()) {
      voiceLoopTurnCount = 0;
    }
    if (speechSynthesisApi) {
      speechRunId += 1;
      speechSynthesisApi.cancel();
    }
    setStatus("Checking");
    userText.textContent = text;
    answer.textContent = "Checking the farm system...";
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
    renderWarnings(data.stale_warnings || []);
    renderSafetyNotes(data.safety_notes || []);
    renderLinks(data.links || []);
    setStatus(data.needs_clarification ? "Needs clarification" : "Answered");
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
    guard.textContent = `${data.mode || "advisory_only"} | auto-marking ${data.autonomous_marking_enabled ? "enabled" : "off"} | writes feedback ${data.writes_feedback ? "yes" : "no"}`;
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
    [
      ["Mode", data.mode || "unknown"],
      ["Backend brain", data.backend_as_brain ? "on" : "off"],
      ["Kiosk max risk", `${policy.max_risk_level ?? 0}: ${policy.allowed_risk_label || "READ_ONLY"}`],
      ["Tools", `${toolCounts.read_only || 0}/${toolCounts.total || 0} read-only`],
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

  function refreshReviewData() {
    loadReviewSummary();
    loadRecentTraces();
    loadReviewAdvisor();
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
        setStatus("Error");
      });
    });
  }

  if (refreshTraces) {
    refreshTraces.addEventListener("click", refreshReviewData);
  }

  if (refreshAdvisor) {
    refreshAdvisor.addEventListener("click", loadReviewAdvisor);
  }

  if (refreshTools) {
    refreshTools.addEventListener("click", loadToolCatalog);
  }

  if (refreshPolicy) {
    refreshPolicy.addEventListener("click", loadPolicyStatus);
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
        setVoiceStatus("Continue conversation is on. Spoken replies will listen for the next question after they finish.");
      } else {
        voiceLoopTurnCount = 0;
        setVoiceStatus("Continue conversation is off.");
      }
      updateConversationStopVisibility();
    });
  }

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
        setStatus("Error");
      });
    });
  });

  setActiveReviewFilter("all");
  renderVoiceReadiness();
  renderVoiceEvents();
  loadToolCatalog();
  loadPolicyStatus();
  refreshReviewData();
})();
