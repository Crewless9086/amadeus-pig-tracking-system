(function () {
  "use strict";

  const endpoint = "/api/sales/channels/chatwoot/sam/owner-inbox?include_withheld=true";
  const itemsNode = document.getElementById("owner-inbox-items");
  const statusNode = document.getElementById("owner-inbox-status");

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
    article.append(heading, classification, ownership, windowState, chronology, reasons, link);
    return article;
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
