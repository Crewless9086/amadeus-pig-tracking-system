(() => {
  "use strict";
  const state = { packet: null, loading: false };
  const el = {
    summary: document.getElementById("summary"), identity: document.getElementById("identityChip"), runner: document.getElementById("runnerChip"),
    messages: document.getElementById("messages"), decisions: document.getElementById("decisionBody"), footer: document.getElementById("footer"),
    notice: document.getElementById("coreNotice"), refresh: document.getElementById("refreshBtn"), composer: document.getElementById("composer"),
    input: document.getElementById("messageInput"), send: document.getElementById("sendBtn"), voice: document.getElementById("voiceBtn"),
  };
  const esc = (v) => String(v == null ? "" : v).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const count = (key) => Number(state.packet?.missions?.counts?.[key] || 0);
  const time = (value) => value ? new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "--";

  async function load() {
    if (state.loading) return;
    state.loading = true; el.refresh.disabled = true;
    try {
      const response = await fetch("/api/charlie/private/dashboard?limit=50", { credentials: "same-origin" });
      const packet = await response.json().catch(() => ({}));
      if (!response.ok || !packet.success) throw new Error(packet.status || `HTTP ${response.status}`);
      state.packet = packet; render();
    } catch (error) {
      el.notice.className = "status-band warn"; el.notice.textContent = `CHARLIE evidence unavailable: ${error.message}`;
    } finally { state.loading = false; el.refresh.disabled = false; }
  }

  function render() {
    const p = state.packet, privateState = p.private || {}, evaluation = privateState.evaluation || {}, runner = p.runner || {};
    const executiveContext = privateState.owner?.open_context || {};
    const successRate = evaluation.tool_runs ? Math.round((evaluation.tool_successes / evaluation.tool_runs) * 100) : 0;
    const metrics = [
      ["CORE active", count("in_progress"), `${count("approved")} approved`], ["Owner review", count("pr_ready"), `${privateState.decisions?.length || 0} private decisions`],
      ["Blocked", count("blocked"), "CHARLIE filters genuine decisions"], ["Tool success", `${successRate}%`, `${evaluation.tool_runs || 0} durable runs`],
      ["Follow-ups", executiveContext.pending_follow_ups?.filter((item) => item.status === "pending").length || 0, `${evaluation.clarifications || 0} clarifications`], ["Recoveries", p.executive?.open_recoveries || 0, "executive control plane"],
    ];
    el.summary.innerHTML = metrics.map(([label, value, note]) => `<div class="metric"><span>${esc(label)}</span><b>${esc(value)}</b><small>${esc(note)}</small></div>`).join("");
    el.identity.className = `chip ${p.policy?.enabled ? "green" : "red"}`; el.identity.innerHTML = `<span class="dot"></span>${p.policy?.enabled ? "Private identity active" : "Identity incomplete"}`;
    const cloudRunnerUnknown = runner.local_runner_scope === "render_cannot_see_laptop_runner";
    const runnerHealthy = runner.active === true || (runner.process_alive === true && runner.heartbeat_fresh === true);
    const runnerLabel = cloudRunnerUnknown ? "local status unknown" : (runner.active === true ? "working" : (runnerHealthy ? "ready" : "stopped"));
    el.runner.className = `chip ${runnerHealthy ? "green" : (cloudRunnerUnknown ? "" : "red")}`; el.runner.innerHTML = `<span class="dot"></span>CORE ${runnerLabel}`;
    const goalNote = executiveContext.goal ? ` Current goal: ${executiveContext.goal}` : "";
    el.notice.className = `status-band ${count("blocked") ? "warn" : ""}`; el.notice.textContent = (cloudRunnerUnknown ? `Render cannot inspect the laptop heartbeat. Supabase shows ${count("in_progress")} active mission(s), ${count("blocked")} blocked and ${count("pr_ready")} ready for review.` : (runnerHealthy ? `CORE is ${runnerLabel}. ${count("blocked")} blocked mission(s); ${count("pr_ready")} ready for review.` : "CORE runner is not healthy. CHARLIE will surface a genuine recovery decision if required.")) + goalNote;
    renderMessages(privateState.messages || []); renderDecisions(privateState.decisions || [], privateState.preferences || [], executiveContext.commitments || []);
    el.footer.innerHTML = `<div><span>Telegram</span><b>${p.policy?.enabled ? "Private webhook" : "Setup needed"}</b></div><div><span>Executive state</span><b>${esc(executiveContext.stage || (privateState.owner ? "Durable" : "Waiting owner"))}</b></div><div><span>ANALYST</span><b>${esc(p.analyst?.scorecard?.pending_proposals || 0)} proposals</b></div><div><span>Updated</span><b>${new Date().toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})}</b></div>`;
  }

  function renderMessages(messages) {
    el.messages.innerHTML = messages.length ? messages.map((m) => `<div class="message ${m.role === "owner" ? "owner" : ""}">${esc(m.content)}<div class="meta">${esc(m.role)} | ${esc(time(m.created_at))}</div></div>`).join("") : '<div class="empty">Start by asking CHARLIE for your executive brief.</div>';
    el.messages.scrollTop = el.messages.scrollHeight;
  }

  function renderDecisions(decisions, preferences, commitments) {
    const decisionHtml = decisions.length ? decisions.map((d) => {
      const packet = d.decisions && !Array.isArray(d.decisions) ? d.decisions : {};
      const args = packet.args && typeof packet.args === "object" ? packet.args : {};
      const requested = args.action_summary || d.summary || "No requested action supplied";
      const protectedAction = packet.intent === "protected_business_action";
      const hasTarget = ["mission_id", "order_id", "customer_id", "conversation_id", "chat_id"].some((key) => args[key]);
      const incomplete = protectedAction && !hasTarget;
      const recommendation = d.recommendation?.recommended || "review manually";
      const warning = incomplete ? "No customer, order, conversation or mission target is attached. Reject this item and give CHARLIE a complete instruction." : "Approval records your authority only. The domain executor still reloads and validates current state before acting.";
      return `<article class="decision"><h3>${esc(d.title)}</h3><p>${esc(d.summary)}</p><div class="decision-detail ${incomplete ? "warn" : ""}"><b>Requested action</b>${esc(requested)}</div><p><strong>Recommendation:</strong> ${esc(recommendation)}<br>${esc(warning)}</p><small>Bundle ${esc(d.bundle_id)} | Expires ${esc(time(d.expires_at))}</small><div class="decision-actions"><button data-bundle="${esc(d.bundle_id)}" data-decision="approve" ${incomplete ? "disabled title=\"Missing action target\"" : ""}>Authorize</button><button class="reject" data-bundle="${esc(d.bundle_id)}" data-decision="reject">Reject</button><button class="later" data-bundle="${esc(d.bundle_id)}" data-decision="defer">Later</button></div></article>`;
    }).join("") : '<div class="empty">No genuine owner decisions are waiting.</div>';
    const preferenceHtml = preferences.length ? `<div class="section-label">Approved preferences</div>${preferences.map((p) => `<div class="preference"><strong>${esc(p.key)}</strong><br>${esc(typeof p.value === "string" ? p.value : JSON.stringify(p.value))}</div>`).join("")}` : "";
    const commitmentHtml = commitments.length ? `<div class="section-label">CHARLIE commitments</div>${commitments.map((item) => `<div class="commitment"><strong>${esc(item.goal || item.type)}</strong><span>${esc(item.status || "monitoring")}</span><small>${esc(item.mission_id ? `CORE ${item.mission_id}` : item.next_check || "")}</small></div>`).join("")}` : "";
    el.decisions.innerHTML = decisionHtml + commitmentHtml + preferenceHtml;
    el.decisions.querySelectorAll("[data-bundle]").forEach((button) => button.addEventListener("click", () => decide(button.dataset.bundle, button.dataset.decision)));
  }

  async function send(text) {
    el.send.disabled = true; el.input.disabled = true;
    el.messages.insertAdjacentHTML("beforeend", `<div class="message owner">${esc(text)}<div class="meta">owner | sending</div></div>`); el.messages.scrollTop = el.messages.scrollHeight;
    try {
      const response = await fetch("/api/charlie/private/message", { method: "POST", credentials: "same-origin", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ text }) });
      const result = await response.json().catch(() => ({})); if (!response.ok) throw new Error(result.status || `HTTP ${response.status}`);
      el.input.value = ""; if (result.reply) { el.messages.insertAdjacentHTML("beforeend", `<div class="message">${esc(result.reply)}<div class="meta">charlie | now</div></div>`); el.messages.scrollTop = el.messages.scrollHeight; } load();
    } catch (error) { el.notice.className = "status-band warn"; el.notice.textContent = `CHARLIE could not respond: ${error.message}`; }
    finally { el.send.disabled = false; el.input.disabled = false; el.input.focus(); }
  }
  async function decide(bundle, decision) {
    const response = await fetch(`/api/charlie/private/decisions/${encodeURIComponent(bundle)}`, { method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json"}, body:JSON.stringify({decision}) });
    const result = await response.json().catch(() => ({})); if (!response.ok) { el.notice.className="status-band warn"; el.notice.textContent=result.status || `Decision failed (${response.status})`; return; } await load();
  }
  function setupVoice() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!el.voice || !Recognition) { if (el.voice) el.voice.classList.add("hidden"); return; }
    const recognition = new Recognition(); recognition.lang = "en-ZA"; recognition.interimResults = false; recognition.continuous = false;
    recognition.addEventListener("start", () => { el.voice.classList.add("listening"); el.voice.textContent = "Listening"; });
    recognition.addEventListener("end", () => { el.voice.classList.remove("listening"); el.voice.textContent = "Voice"; });
    recognition.addEventListener("result", (event) => { const transcript = event.results?.[0]?.[0]?.transcript || ""; if (transcript) { el.input.value = transcript; el.input.focus(); } });
    recognition.addEventListener("error", () => { el.notice.className = "status-band warn"; el.notice.textContent = "Voice capture was unavailable. Type the instruction or use a Telegram voice note."; });
    el.voice.addEventListener("click", () => recognition.start());
  }
  el.composer.addEventListener("submit", (event) => { event.preventDefault(); const text = el.input.value.trim(); if (text) send(text); });
  document.querySelectorAll("[data-command]").forEach((button) => button.addEventListener("click", () => send(button.dataset.command)));
  el.refresh.addEventListener("click", load); setupVoice(); load(); setInterval(load, 30000);
})();
