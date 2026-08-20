const attentionEscape = value => String(value ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");
async function loadOwnerAttentionAll() {
  const target = document.getElementById("owner_attention_all");
  const status = document.getElementById("owner_attention_status");
  try {
    const response = await fetch("/api/oom-sakkie/owner-attention", {headers:{Accept:"application/json"}});
    const data = await response.json();
    if (!response.ok || data.success === false) throw new Error(data.message || "Unavailable");
    const labels = {needs_you:"Needs you",farm_work_ready:"Farm work ready",oom_sakkie_checking:"Oom Sakkie is checking",watch:"Watch",recently_completed:"Recently completed"};
    const order = ["needs_you","farm_work_ready","oom_sakkie_checking","watch","recently_completed"];
    const friendly = value => String(value || "Unknown").replace(/_/g," ").replace(/\b\w/g, letter => letter.toUpperCase());
    const renderItem = item => `<article role="listitem" class="attention-all-item"><span class="attention-emoji" aria-hidden="true">${attentionEscape(item.semantic_emoji)}</span><span><strong>${attentionEscape(item.title)}</strong><small>Status: ${attentionEscape(friendly(item.operational_status))} · Owner: ${attentionEscape(item.assigned_to)} · ${attentionEscape(friendly(item.freshness))}</small><em>${attentionEscape(item.exact_owner_action)}</em><details><summary>Details</summary><p><a href="${attentionEscape(item.detail_target)}">Open focused detail</a></p><p>Reference: ${attentionEscape(item.secondary_reference)}</p><p>Source: ${attentionEscape(item.specialist_owner)}</p><p>Provenance: ${attentionEscape((item.provenance || []).join(" · "))}</p></details></span></article>`;
    target.innerHTML = order.map(group => { const items = data.groups?.[group] || []; if (!items.length) return ""; const open = group === "needs_you" || group === "farm_work_ready"; return `<details class="attention-group" ${open ? "open" : ""}><summary><strong>${labels[group]}</strong><span>${items.length}</span></summary><section role="list">${items.map(renderItem).join("")}</section></details>`; }).join("");
    const total = Math.max(0, Number(data.total_count || 0)); const context = Math.max(0, Number(data.open_context_count || 0));
    const contextual = Math.max(0, context - total);
    status.textContent = total ? `${total} owner action${total === 1 ? "" : "s"}; ${contextual} contextual item${contextual === 1 ? "" : "s"}.` : `No owner action is supported; ${context} contextual item${context === 1 ? "" : "s"} remain available.`;
  } catch (error) { target.innerHTML = ""; status.textContent = "Shared attention is temporarily unavailable. No specialist work was inferred."; }
}
loadOwnerAttentionAll();
