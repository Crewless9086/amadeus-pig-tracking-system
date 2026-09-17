(function () {
  "use strict";

  const endpoint = "/api/sales/channels/chatwoot/sam/owner-inbox?include_withheld=true";
  const itemsNode = document.getElementById("owner-inbox-items");
  const statusNode = document.getElementById("owner-inbox-status");
  const ownershipEndpoint = "/api/sales/channels/chatwoot/sam/owner-inbox/ownership";

  function text(node, value) {
    node.textContent = String(value == null ? "" : value);
  }

  function itemCard(item) {
    const article = document.createElement("article");
    article.className = `work-item lane-${String(item.lane || "general").toLowerCase()}`;
    const heading = document.createElement("h2");
    text(heading, `Conversation ${item.conversation_id}`);
    const classification = document.createElement("p");
    classification.className = "classification";
    text(classification, item.classification);
    const ownership = document.createElement("p");
    ownership.className = "ownership-state";
    const ownershipException = item.classification === "OWNERSHIP_DECISION_REQUIRED";
    text(
      ownership,
      ownershipException
        ? "Ownership decision required · Reply and Send Reply disabled"
        : `Ownership ${item.ownership_mode || "unavailable"}`
    );
    const chronology = document.createElement("p");
    const reviewCurrent = item.review_event_id
      && item.reviewed_inbound_message_id
      && item.reviewed_inbound_message_id === item.latest_inbound_message_id;
    text(
      chronology,
      `${item.unanswered_count || 0} unanswered · latest inbound ${item.latest_message_at || "unavailable"} · review ${reviewCurrent ? "current" : "missing/stale"} · chronology ${String(item.chronology_hash || "").slice(0, 12)}`
    );
    const windowState = document.createElement("p");
    windowState.className = `window-state band-${String(item.alert_band || "none").toLowerCase()}`;
    const remaining = Number.isFinite(Number(item.remaining_seconds))
      ? `${Math.max(0, Math.floor(Number(item.remaining_seconds) / 60))} min remaining`
      : "remaining time unavailable";
    const expiry = item.expires_at_johannesburg
      ? new Date(item.expires_at_johannesburg).toLocaleString("en-ZA", {timeZone: "Africa/Johannesburg"})
      : "unavailable";
    text(windowState, `${item.window_state || "unavailable"} · ${remaining} · expires ${expiry} SAST`);
    const reasons = document.createElement("p");
    reasons.className = "reasons";
    text(reasons, (item.withheld_reasons_json || []).join(" · ") || "Authoritative owner review required");
    const link = document.createElement("a");
    link.href = `https://app.chatwoot.com/app/accounts/${encodeURIComponent(item.account_id)}/conversations/${encodeURIComponent(item.conversation_id)}`;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    text(link, "Open exact Chatwoot conversation");
    article.append(heading, classification, ownership, windowState, chronology, reasons);
    if (ownershipException) article.append(ownershipDecision(item));
    article.append(link);
    return article;
  }

  function ownershipDecision(item) {
    const section = document.createElement("section");
    section.className = "ownership-decision";
    const evidence = document.createElement("p");
    text(
      evidence,
      `Confirm conversation ${item.conversation_id} · inbound ${item.latest_inbound_message_id} · ${item.unanswered_count} unanswered · review ${item.review_event_id || "unavailable"} · window ${item.window_state || "unavailable"}`
    );
    const select = document.createElement("select");
    select.setAttribute("aria-label", `Ownership for conversation ${item.conversation_id}`);
    ["HUMAN", "AUTO_GENERAL", "AUTO_SPECIALIST"].forEach(mode => {
      const option = document.createElement("option");
      option.value = mode;
      text(option, mode);
      select.append(option);
    });
    const button = document.createElement("button");
    button.type = "button";
    text(button, "Confirm ownership");
    button.addEventListener("click", async () => {
      const targetMode = select.value;
      if (!window.confirm(`Set conversation ${item.conversation_id} to ${targetMode}? This sends no customer message.`)) return;
      button.disabled = true;
      try {
        const payload = {
          work_item_id: item.work_item_id,
          work_event_id: item.work_event_id,
          account_id: item.account_id,
          conversation_id: item.conversation_id,
          contact_id: item.contact_id,
          inbox_id: item.inbox_id,
          observation_hash: item.observation_hash,
          chronology_hash: item.chronology_hash,
          latest_inbound_message_id: item.latest_inbound_message_id,
          unanswered_count: item.unanswered_count,
          review_event_id: item.review_event_id,
          window_evidence_hash: item.window_evidence_hash,
          target_mode: targetMode
        };
        const response = await fetch(ownershipEndpoint, {
          method: "POST",
          credentials: "same-origin",
          headers: {"Accept": "application/json", "Content-Type": "application/json"},
          body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (!response.ok || result.success !== true) throw new Error(result.status || "ownership_resolution_failed");
        await load();
      } catch (error) {
        text(statusNode, `Ownership unchanged or safely withheld: ${error.message}`);
        button.disabled = false;
      }
    });
    section.append(evidence, select, button);
    return section;
  }

  function count(items, predicate) {
    return items.filter(predicate).length;
  }

  async function load() {
    text(statusNode, "Loading authoritative queue…");
    try {
      const response = await fetch(endpoint, {credentials: "same-origin", headers: {"Accept": "application/json"}});
      const payload = await response.json();
      if (!response.ok || payload.success !== true) throw new Error(payload.status || "queue_unavailable");
      const items = Array.isArray(payload.items) ? payload.items : [];
      itemsNode.replaceChildren(...items.map(itemCard));
      text(document.getElementById("actionable-count"), count(items, item => item.actionable === true));
      text(document.getElementById("protected-count"), count(items, item => item.lane === "PROTECTED"));
      text(document.getElementById("specialist-count"), count(items, item => item.lane === "SPECIALIST"));
      text(document.getElementById("withheld-count"), count(items, item => item.actionable !== true));
      text(document.getElementById("expiring-count"), count(items, item => ["warning", "urgent"].includes(item.alert_band)));
      text(document.getElementById("ownership-count"), count(items, item => item.classification === "OWNERSHIP_DECISION_REQUIRED"));
      text(statusNode, items.length ? `${items.length} exact conversation work items.` : "No persisted work items yet.");
    } catch (error) {
      itemsNode.replaceChildren();
      text(statusNode, `Queue unavailable: ${error.message}`);
    }
  }

  document.getElementById("refresh-owner-inbox").addEventListener("click", load);
  load();
}());
