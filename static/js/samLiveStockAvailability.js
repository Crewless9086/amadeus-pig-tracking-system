(() => {
  "use strict";

  const root = document.getElementById("sam-live-stock-availability");
  if (!root) return;

  const value = (id) => String(document.getElementById(id)?.value || "").trim();
  const previewButton = document.getElementById("previewAvailability");
  const confirmButton = document.getElementById("confirmAvailability");
  const confirmation = document.getElementById("availabilityConfirmed");
  const previewNode = document.getElementById("availabilityPreview");
  const resultNode = document.getElementById("availabilityResult");
  let preview = null;

  const observedAtIso = () => {
    const raw = value("availabilityObservedAt");
    if (!raw) return "";
    const sast = `${raw.length === 16 ? `${raw}:00` : raw}+02:00`;
    const parsed = new Date(sast);
    return Number.isNaN(parsed.getTime()) ? "" : parsed.toISOString();
  };

  const requestJson = async (path, payload) => {
    const response = await fetch(`/api/sales/channels/chatwoot/sam-live-stock/${path}`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.status || `HTTP ${response.status}`);
    return body;
  };

  const appendTextElement = (parent, tag, content) => {
    const node = document.createElement(tag);
    node.textContent = content;
    parent.appendChild(node);
    return node;
  };

  const renderPreview = (data) => {
    previewNode.replaceChildren();
    appendTextElement(previewNode, "p", `Observed: ${data.observed_at_utc}`);
    appendTextElement(previewNode, "p", `Expires: ${data.expires_at_utc}`);
    appendTextElement(previewNode, "p", `Unresolved rows: ${data.unresolved_count}`);
    appendTextElement(previewNode, "h3", "Proposed totals");
    const totals = document.createElement("ul");
    Object.entries(data.eligible_totals || {}).forEach(([category, counts]) => {
      appendTextElement(
        totals,
        "li",
        `${category}: ${counts.all} total; ${counts.female} female; ${counts.male} male; ${counts.unknown} unknown`,
      );
    });
    previewNode.appendChild(totals);
    appendTextElement(previewNode, "h3", "Exclusions");
    const exclusions = document.createElement("ul");
    const exclusionEntries = Object.entries(data.exclusions || {});
    if (!exclusionEntries.length) appendTextElement(exclusions, "li", "None");
    exclusionEntries.forEach(([reason, count]) => {
      appendTextElement(exclusions, "li", `${reason}: ${count}`);
    });
    previewNode.appendChild(exclusions);
  };

  previewButton?.addEventListener("click", async () => {
    preview = null;
    confirmButton.disabled = true;
    try {
      preview = await requestJson("availability/preview", {
        observed_at: observedAtIso(),
        max_age_hours: Number(value("availabilityMaxAge") || 24),
      });
      renderPreview(preview);
      confirmButton.disabled = !confirmation.checked;
    } catch (error) {
      previewNode.textContent = `Preview unavailable: ${error.message}`;
    }
  });

  confirmation?.addEventListener("change", () => {
    confirmButton.disabled = !(confirmation.checked && preview);
  });

  confirmButton?.addEventListener("click", async () => {
    confirmButton.disabled = true;
    resultNode.textContent = "Recording exact observation evidence...";
    try {
      const recorded = await requestJson("availability/confirm", {
        observed_at: observedAtIso(),
        max_age_hours: Number(value("availabilityMaxAge") || 24),
        cohort_hash: preview.cohort_hash,
        source: "owner_weighing_review",
        owner_confirmed: true,
      });
      const card = await requestJson("availability/recommendation", {
        observation_event_id: recorded.observation_event_id,
        cohort_hash: recorded.cohort_hash,
        observed_at_utc: recorded.observed_at_utc,
        expires_at_utc: recorded.expires_at_utc,
        account_id: value("availabilityAccountId"),
        conversation_id: value("availabilityConversationId"),
        contact_id: value("availabilityContactId"),
        inbox_id: value("availabilityInboxId"),
        latest_inbound_id: value("availabilityInboundId"),
        customer_name: value("availabilityCustomerName"),
      });
      resultNode.replaceChildren();
      appendTextElement(resultNode, "p", `Evidence: ${recorded.observation_event_id}`);
      appendTextElement(resultNode, "p", `Valid until: ${recorded.expires_at_utc}`);
      appendTextElement(resultNode, "h3", "Owner-review recommendation");
      appendTextElement(resultNode, "pre", card.recommendation);
      appendTextElement(
        resultNode,
        "p",
        "No customer message was sent. No animals were reserved or changed.",
      );
    } catch (error) {
      resultNode.textContent = `Stopped fail-closed: ${error.message}`;
    }
  });
})();
