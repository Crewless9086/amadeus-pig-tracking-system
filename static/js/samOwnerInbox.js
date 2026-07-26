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
    const chronology = document.createElement("p");
    text(chronology, `${item.unanswered_count || 0} unanswered · chronology ${String(item.chronology_hash || "").slice(0, 12)}`);
    const reasons = document.createElement("p");
    reasons.className = "reasons";
    text(reasons, (item.withheld_reasons_json || []).join(" · ") || "Authoritative owner review required");
    const link = document.createElement("a");
    link.href = `https://app.chatwoot.com/app/accounts/${encodeURIComponent(item.account_id)}/conversations/${encodeURIComponent(item.conversation_id)}`;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    text(link, "Open exact Chatwoot conversation");
    article.append(heading, classification, chronology, reasons, link);
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
      text(statusNode, items.length ? `${items.length} exact conversation work items.` : "No persisted work items yet.");
    } catch (error) {
      itemsNode.replaceChildren();
      text(statusNode, `Queue unavailable: ${error.message}`);
    }
  }

  document.getElementById("refresh-owner-inbox").addEventListener("click", load);
  load();
}());
