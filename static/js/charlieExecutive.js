(() => {
  "use strict";
  const state = { packet: null, loading: false };
  const el = {
    summary: document.getElementById("summary"), identity: document.getElementById("identityChip"), runner: document.getElementById("runnerChip"),
    messages: document.getElementById("messages"), decisions: document.getElementById("decisionBody"), footer: document.getElementById("footer"),
    notice: document.getElementById("coreNotice"), refresh: document.getElementById("refreshBtn"), composer: document.getElementById("composer"),
    input: document.getElementById("messageInput"), send: document.getElementById("sendBtn"),
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
    const successRate = evaluation.tool_runs ? Math.round((evaluation.tool_successes / evaluation.tool_runs) * 100) : 0;
    const metrics = [
      ["CORE active", count("in_progress"), `${count("approved")} approved`], ["Owner review", count("pr_ready"), `${privateState.decisions?.length || 0} private decisions`],
      ["Blocked", count("blocked"), "CHARLIE filters genuine decisions"], ["Tool success", `${successRate}%`, `${evaluation.tool_runs || 0} durable runs`],
      ["Clarifications", evaluation.clarifications || 0, `${evaluation.intents || 0} interpreted intents`], ["Recoveries", p.executive?.open_recoveries || 0, "executive control plane"],
    ];
    el.summary.innerHTML = metrics.map(([label, value, note]) => `<div class="metric"><span>${esc(label)}</span><b>${esc(value)}</b><small>${esc(note)}</small></div>`).join("");
    el.identity.className = `chip ${p.policy?.enabled ? "green" : "red"}`; el.identity.innerHTML = `<span class="dot"></span>${p.policy?.enabled ? "Private identity active" : "Identity incomplete"}`;
    const runnerActive = runner.active === true; el.runner.className = `chip ${runnerActive ? "green" : "red"}`; el.runner.innerHTML = `<span class="dot"></span>CORE ${runnerActive ? "active" : "stopped"}`;
    el.notice.className = `status-band ${count("blocked") ? "warn" : ""}`; el.notice.textContent = runnerActive ? `CORE is ${runner.operating_state || "active"}. ${count("blocked")} blocked mission(s); ${count("pr_ready")} ready for review.` : "CORE is intentionally stopped while notification separation is being completed.";
    renderMessages(privateState.messages || []); renderDecisions(privateState.decisions || [], privateState.preferences || []);
    el.footer.innerHTML = `<div><span>Telegram</span><b>${p.policy?.enabled ? "Private webhook" : "Setup needed"}</b></div><div><span>Memory</span><b>${privateState.owner ? "Durable" : "Waiting owner"}</b></div><div><span>ANALYST</span><b>${esc(p.analyst?.scorecard?.pending_proposals || 0)} proposals</b></div><div><span>Updated</span><b>${new Date().toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})}</b></div>`;
  }

  function renderMessages(messages) {
    el.messages.innerHTML = messages.length ? messages.map((m) => `<div class="message ${m.role === "owner" ? "owner" : ""}">${esc(m.content)}<div class="meta">${esc(m.role)} | ${esc(time(m.created_at))}</div></div>`).join("") : '<div class="empty">Start by asking CHARLIE for your executive brief.</div>';
    el.messages.scrollTop = el.messages.scrollHeight;
  }

  function renderDecisions(decisions, preferences) {
    const decisionHtml = decisions.length ? decisions.map((d) => `<article class="decision"><h3>${esc(d.title)}</h3><p>${esc(d.summary)}</p><small>Expires ${esc(time(d.expires_at))}</small><div class="decision-actions"><button data-bundle="${esc(d.bundle_id)}" data-decision="approve">Approve</button><button class="reject" data-bundle="${esc(d.bundle_id)}" data-decision="reject">Reject</button><button class="later" data-bundle="${esc(d.bundle_id)}" data-decision="defer">Later</button></div></article>`).join("") : '<div class="empty">No genuine owner decisions are waiting.</div>';
    const preferenceHtml = preferences.length ? `<div class="section-label">Approved preferences</div>${preferences.map((p) => `<div class="preference"><strong>${esc(p.key)}</strong><br>${esc(typeof p.value === "string" ? p.value : JSON.stringify(p.value))}</div>`).join("")}` : "";
    el.decisions.innerHTML = decisionHtml + preferenceHtml;
    el.decisions.querySelectorAll("[data-bundle]").forEach((button) => button.addEventListener("click", () => decide(button.dataset.bundle, button.dataset.decision)));
  }

  async function send(text) {
    el.send.disabled = true; el.input.disabled = true;
    try {
      const response = await fetch("/api/charlie/private/message", { method: "POST", credentials: "same-origin", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ text }) });
      const result = await response.json().catch(() => ({})); if (!response.ok) throw new Error(result.status || `HTTP ${response.status}`);
      el.input.value = ""; await load();
    } catch (error) { el.notice.className = "status-band warn"; el.notice.textContent = `CHARLIE could not respond: ${error.message}`; }
    finally { el.send.disabled = false; el.input.disabled = false; el.input.focus(); }
  }
  async function decide(bundle, decision) {
    const response = await fetch(`/api/charlie/private/decisions/${encodeURIComponent(bundle)}`, { method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json"}, body:JSON.stringify({decision}) });
    const result = await response.json().catch(() => ({})); if (!response.ok) { el.notice.className="status-band warn"; el.notice.textContent=result.status || `Decision failed (${response.status})`; return; } await load();
  }
  el.composer.addEventListener("submit", (event) => { event.preventDefault(); const text = el.input.value.trim(); if (text) send(text); });
  document.querySelectorAll("[data-command]").forEach((button) => button.addEventListener("click", () => send(button.dataset.command)));
  el.refresh.addEventListener("click", load); load(); setInterval(load, 30000);
})();
