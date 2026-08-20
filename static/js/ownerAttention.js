const attentionEscape = value => String(value ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");
async function loadOwnerAttentionAll() {
  const target = document.getElementById("owner_attention_all");
  const status = document.getElementById("owner_attention_status");
  try {
    const response = await fetch("/api/oom-sakkie/owner-attention", {headers:{Accept:"application/json"}});
    const data = await response.json();
    if (!response.ok || data.success === false) throw new Error(data.message || "Unavailable");
    target.innerHTML = data.items.map(item => `<a role="listitem" class="attention-all-item" href="${attentionEscape(item.detail_target)}"><span class="attention-emoji" aria-hidden="true">${attentionEscape(item.semantic_emoji)}</span><span><strong>${attentionEscape(item.title)}</strong><small>${attentionEscape(item.specialist_owner)} · ${attentionEscape(item.task_class.replace(/_/g," "))} · ${attentionEscape(item.priority)} · ${attentionEscape(item.freshness)}</small><em>${attentionEscape(item.exact_owner_action)}</em></span></a>`).join("");
    status.textContent = data.items.length ? `${data.items.length} open owner-attention item${data.items.length === 1 ? "" : "s"}.` : "No open owner-attention work is supported by current evidence.";
  } catch (error) { target.innerHTML = ""; status.textContent = "Shared attention is temporarily unavailable. No specialist work was inferred."; }
}
loadOwnerAttentionAll();
