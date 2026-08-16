const statusBox = document.getElementById("breeding_detail_status");
const contentBox = document.getElementById("breeding_detail_content");
const UNKNOWN = "Unknown";
const IDENTITY_CONTRACT = "herdmaster_human_identity_v1";

function known(value) {
  return value !== null && value !== undefined && value !== "";
}

function text(value) {
  return known(value) ? String(value) : UNKNOWN;
}

function num(value) {
  return known(value) && !Number.isNaN(Number(value)) ? String(value) : UNKNOWN;
}

function pct(value) {
  return known(value) && !Number.isNaN(Number(value))
    ? `${(Number(value) * 100).toFixed(1)}%`
    : UNKNOWN;
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function safeInternal(value) {
  const path = String(value || "").trim();
  return path.startsWith("/")
    && !path.startsWith("//")
    && !/[\\\u0000-\u001f\u007f]/.test(path)
    ? path
    : "";
}

function safeProfileReturn(value) {
  const path = safeInternal(value);
  return /^\/breeding-analytics(?:\/[^/?#]+)?$/.test(path) ? path : "";
}

function safeDestination(destination = {}, kind) {
  const expectedRoute = kind === "animal" ? "breeding_animal_detail" : "litter_detail";
  if (destination.available !== true || destination.route_identity !== expectedRoute) return "";
  const href = safeInternal(destination.href);
  if (!href) return "";
  let url;
  try {
    url = new URL(href, location.origin);
  } catch (_) {
    return "";
  }
  if (url.origin !== location.origin || url.hash) return "";
  if (kind === "animal") {
    return /^\/breeding-analytics\/[^/?#]+$/.test(url.pathname) && !url.search
      ? url.pathname
      : "";
  }
  if (!/^\/litter\/[^/?#]+$/.test(url.pathname)) return "";
  const returnTo = safeProfileReturn(url.searchParams.get("return_to"));
  return returnTo === location.pathname ? url.pathname + url.search : "";
}

function withReturn(href, label) {
  const safe = safeInternal(href);
  if (!safe) return "";
  const url = new URL(safe, location.origin);
  url.searchParams.set("return_to", location.pathname);
  url.searchParams.set("return_label", label);
  return url.pathname + url.search;
}

function identityName(identity = {}) {
  return identity.name || identity.tag_number || "Naam/Tag onbekend";
}

function roleLabel(value) {
  return ({ sow: "Sog", boar: "Beer", dam: "Moeder", sire: "Vader", offspring: "Nageslag" })[
    String(value || "").toLowerCase()
  ] || text(value);
}

function identityHtml(identity = {}, options = {}) {
  const name = identityName(identity);
  const tag = identity.tag_number;
  const pigId = identity.technical_identity?.pig_id || identity.pig_id;
  return `<div class="merit-related-identity">
    <strong>${esc(name)}</strong>
    ${tag && identity.name ? `<span>Tag ${esc(tag)}</span>` : (!tag ? "<span>Geen tag</span>" : "")}
    ${options.role ? `<span>${esc(roleLabel(options.role))}</span>` : ""}
    ${pigId ? `<small>Pig-ID ${esc(pigId)}</small>` : ""}
  </div>`;
}

function metric(label, value, note = "") {
  return `<div class="merit-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong>${note ? `<small>${esc(note)}</small>` : ""}</div>`;
}

function item(label, value) {
  return `<div><strong>${esc(label)}</strong><p>${esc(value || "No supported conclusion at this cutoff")}</p></div>`;
}

function setState(kind, message) {
  statusBox.className = `merit-status is-${kind}`;
  statusBox.textContent = message;
  contentBox.classList.toggle("hidden", kind !== "ready");
  if (kind === "ready") statusBox.classList.add("hidden");
}

function identityGroup(title, identities) {
  const list = (identities || []).filter(Boolean);
  return `<div class="merit-context-card"><h3>${esc(title)}</h3>${list.length
    ? `<div class="merit-identity-list">${list.map((value) => identityHtml(value, { role: value.role })).join("")}</div>`
    : `<p>${UNKNOWN}</p>`}</div>`;
}

function offspringState(identity = {}) {
  return operationalValue(identity, "current_status");
}

function ownerValue(value) {
  return known(value) ? String(value) : "Onbekend";
}

function operationalValue(identity, field) {
  if (known(identity[field])) return String(identity[field]);
  return ownerValue(identity.operational_evidence_state?.[field]);
}

function offspringHtml(identities, currentName) {
  const rows = [...(identities || [])].filter(Boolean);
  if (!rows.length) return `<div class="merit-empty">Geen kanonieke nageslagidentiteite is beskikbaar nie.</div>`;
  return `<div class="merit-table-wrap"><table class="merit-table merit-offspring-table"><thead><tr><th>Tag / Naam</th><th>Huidige status</th><th>Doel</th><th>Op plaas</th><th>Werpsel</th></tr></thead><tbody>${rows.map((identity) => {
    const base = safeDestination(identity.destination, "animal");
    const href = base ? withReturn(base, `Terug na ${currentName} se profiel`) : "";
    const pigId = identity.technical_identity?.pig_id || identity.pig_id;
    const label = identity.name || identity.tag_number || "Naam/Tag onbekend";
    const identityCell = `<strong>${esc(label)}</strong>${identity.tag_number && identity.name ? `<span>Tag ${esc(identity.tag_number)}</span>` : ""}${pigId ? `<small>Pig-ID ${esc(pigId)}</small>` : ""}`;
    const litter = identity.litter_attribution || {};
    const litterValue = known(litter.display_name) && litter.display_name !== "Unknown" ? litter.display_name : ownerValue(identity.litter_attribution_state);
    const contents = `<td data-label="Tag / Naam">${href ? `<a href="${esc(href)}" aria-label="Open ${esc(label)} se profiel">${identityCell}</a>` : identityCell}</td><td data-label="Huidige status">${esc(offspringState(identity))}</td><td data-label="Doel">${esc(operationalValue(identity, "purpose"))}</td><td data-label="Op plaas">${esc(operationalValue(identity, "on_farm"))}</td><td data-label="Werpsel">${esc(litterValue)}</td>`;
    return `<tr>${contents}</tr>`;
  }).join("")}</tbody></table></div>`;
}

function offspringSummaryHtml(offspring) {
  const summary = offspring.operational_summary || {};
  return metric("Nageslag aangeteken", num(summary.sample_size))
    + metric("Identiteite opgelos", num(summary.resolved_identity_count))
    + metric("Status bekend", num(summary.known_status_count))
    + metric("Doel bekend", num(summary.known_purpose_count))
    + metric("Op-plaas bekend", num(summary.known_on_farm_count))
    + metric("Werpsel gekoppel", num(summary.known_litter_attribution_count))
    + metric("Unknown / conflicting", num(summary.unknown_or_conflicting_operational_count));
}

function matingHtml(summaries, currentName) {
  if (!summaries.length) return '<div class="merit-empty">Geen individuele paringsrekords is beskikbaar nie.</div>';
  return `<div class="merit-related-list">${summaries.map((summary) => {
    const partner = summary.partner_identity || {};
    const litter = summary.litter_identity || {};
    const partnerBase = safeDestination(partner.destination, "animal");
    const partnerHref = partnerBase ? withReturn(partnerBase, `Terug na ${currentName} se profiel`) : "";
    const litterBase = safeDestination(litter.destination, "litter");
    const litterHref = litterBase ? withReturn(litterBase, `Terug na ${currentName} se profiel`) : "";
    const litterLabel = litter.display_name || summary.litter_attribution_state || UNKNOWN;
    return `<article class="merit-mating-row"><div class="merit-mating-heading"><div><strong>${esc(text(summary.mating_date))}</strong><small>Paring-ID ${esc(text(summary.mating_id))}</small></div><span>${esc(text(summary.recorded_status))}</span></div>${partnerHref ? `<a class="merit-inline-identity" href="${esc(partnerHref)}">${identityHtml(partner, { role: partner.role })}</a>` : identityHtml(partner, { role: partner.role })}<div class="merit-mating-litter"><span>Werpsel</span>${litterHref ? `<a href="${esc(litterHref)}">${esc(litterLabel)}</a>` : `<strong>${esc(litterLabel)}</strong>`}</div></article>`;
  }).join("")}</div>`;
}

function ids(title, values) {
  const list = (values || []).filter(Boolean);
  return `<div class="merit-context-card"><h3>${esc(title)}</h3>${list.length
    ? `<div class="merit-id-list">${list.map((value) => `<code>${esc(value)}</code>`).join("")}</div>`
    : `<p>${UNKNOWN}</p>`}</div>`;
}

function lineageHtml(lineage = {}) {
  const litters = lineage.litters || {};
  const events = litters.events || [];
  const superseded = litters.superseded_event_ids || [];
  return `<p>Effective evidence and its append-only correction history are shown separately.</p>
    ${superseded.length
      ? `<div class="merit-id-list">${superseded.map((value) => `<code>${esc(value)} · superseded</code>`).join("")}</div>`
      : '<p class="merit-muted">No superseded litter identity was returned.</p>'}
    <details><summary>View ${events.length} litter lineage record(s)</summary>
      <div class="merit-lineage-records">${events.map((event) => `<p><code>${esc(text(event.litter_id))}</code>${event.is_superseded ? " · superseded" : ""}${event.retained_litter_id ? ` · retained as <code>${esc(event.retained_litter_id)}</code>` : ""}</p>`).join("") || `<p>${UNKNOWN}</p>`}</div>
    </details>`;
}

function updateBack() {
  const params = new URLSearchParams(location.search);
  const href = safeProfileReturn(params.get("return_to"));
  const label = String(params.get("return_label") || "").trim();
  if (!href) return;
  const link = document.getElementById("breeding_detail_back_link");
  link.href = href;
  link.textContent = label || "Terug";
}

function partnerHtml(comparisons, currentName) {
  if (!comparisons.length) {
    return '<div class="merit-empty">Geen toeskryfbare vennootvergelyking is beskikbaar nie.</div>';
  }
  return `<div class="merit-related-list">${comparisons.map((comparison) => {
    const identity = comparison.partner_identity || {};
    const base = safeDestination(comparison.destination || identity.destination, "animal");
    const href = base ? withReturn(base, `Terug na ${currentName} se profiel`) : "";
    const body = `${identityHtml(identity, { role: identity.role })}
      <div class="merit-related-metrics">
        <span><b>${esc(num(comparison.observed_litter_count))}</b> waargenome werpsels</span>
        <span><b>${esc(num(comparison.eligible_litter_count))}</b> geskik</span>
        <span><b>${esc(pct(comparison.survival_rate))}</b> oorlewing</span>
      </div>`;
    return href
      ? `<a class="merit-related-row" href="${esc(href)}" aria-label="Open ${esc(identityName(identity))} se teeldierprofiel">${body}<span class="merit-related-arrow" aria-hidden="true">→</span></a>`
      : `<div class="merit-related-row is-static">${body}</div>`;
  }).join("")}</div>`;
}

function trendHtml(trend, currentName) {
  if (!trend.length) return '<div class="merit-empty">Geen toeskryfbare tydlyn is beskikbaar nie.</div>';
  return `<div class="merit-related-list">${trend.map((entry) => {
    const litter = entry.litter_identity || {};
    const sow = litter.sow_identity || entry.sow_identity || {};
    const base = safeDestination(entry.destination || litter.destination, "litter");
    const href = base ? withReturn(base, `Terug na ${currentName} se profiel`) : "";
    const litterLabel = litter.display_name || entry.litter_id || UNKNOWN;
    const body = `<div><strong>${esc(litterLabel)}</strong>
      <span class="merit-related-meta">${esc(text(entry.period))} · ${esc(pct(entry.survival_rate))} oorlewing</span>
      ${identityHtml(sow, { role: "sow" })}</div>`;
    return href
      ? `<a class="merit-related-row" href="${esc(href)}" aria-label="Open werpsel ${esc(litterLabel)} en keer terug na hierdie profiel">${body}<span class="merit-related-arrow" aria-hidden="true">→</span></a>`
      : `<div class="merit-related-row is-static">${body}</div>`;
  }).join("")}</div>`;
}

async function load() {
  const pigId = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");
  if (!pigId) {
    setState("incomplete", "Pig ID is missing from the page URL.");
    return;
  }
  try {
    const response = await fetch(`/api/pig-weights/breeding-analytics/v1/full-lifecycle/${encodeURIComponent(pigId)}`, {
      headers: { Accept: "application/json" },
    });
    let data;
    try {
      data = await response.json();
    } catch (_) {
      throw new Error("HERDMASTER returned an unreadable response.");
    }
    if (response.status === 401 || response.status === 403) {
      setState("auth", "Owner authentication is required to view this animal profile.");
      return;
    }
    if (response.status === 404 || data.reason === "unknown_pig_id") {
      setState("empty", "No canonical lifetime-merit packet exists for this Pig ID.");
      return;
    }
    if (!response.ok || data.success !== true
      || data.contract_version !== "herdmaster_full_lifecycle_merit_v1"
      || data.identity_contract_version !== IDENTITY_CONTRACT
      || data.writes_performed !== false) {
      throw new Error(data.reason || "Canonical lifetime-merit evidence is unavailable.");
    }
    const row = (data.rows || [])[0];
    if (!row) {
      setState("empty", "No canonical lifetime-merit packet exists for this Pig ID.");
      return;
    }
    renderProfile(data, row);
    setState("ready", "");
  } catch (error) {
    setState("failure", error.message || "Lifetime-merit evidence could not be loaded.");
  }
}

function renderProfile(data, row) {
  const identity = row.identity || {};
  const displayName = identityName(identity);
  const outcomes = row.litter_outcomes || {};
  const opportunities = row.breeding_opportunities || {};
  const offspring = row.offspring || {};
  const growth = row.offspring_growth || {};
  const finance = row.financial_outcomes || {};
  const confidence = row.confidence || {};
  const inputs = confidence.inputs || {};
  const interpretation = row.interpretation || {};
  const family = row.family_relationships || {};
  const context = row.health_observation_context || {};
  const technicalPigId = identity.technical_identity?.pig_id || identity.pig_id;

  document.getElementById("merit_detail_title").textContent = displayName;
  document.getElementById("merit_detail_subtitle").textContent = `${roleLabel(row.breeding_role)} · evidence cutoff ${text(data.evidence_cutoff)}`;
  document.getElementById("merit_detail_boundary").textContent = data.association_boundary || document.getElementById("merit_detail_boundary").textContent;
  document.getElementById("merit_detail_identity").innerHTML = `<div>
    <span class="merit-kicker">Kanonieke dier</span><h2>${esc(displayName)}</h2>
    <p>${identity.tag_number ? `Tag ${esc(identity.tag_number)}` : "Geen tag"}</p>
    ${technicalPigId ? `<small>Pig-ID ${esc(technicalPigId)}</small>` : ""}
  </div><span class="merit-confidence is-${esc(String(confidence.label || UNKNOWN).toLowerCase())}">${esc(text(confidence.label))} confidence</span>`;
  document.getElementById("merit_detail_interpretation").innerHTML = item("Going well", interpretation.going_well)
    + item("Needs attention", interpretation.needs_attention)
    + item("Missing evidence", interpretation.missing_evidence)
    + item("Next review", interpretation.next_review);
  renderMetrics({ outcomes, opportunities, offspring, growth, finance, confidence, inputs });
  const matings = row.individual_mating_summaries || [];
  const partners = row.partner_comparisons || [];
  const trend = row.time_trend || [];
  document.getElementById("merit_mating_count").textContent = `(${num(matings.length)})`;
  document.getElementById("merit_partner_count").textContent = `(${num(row.partner_comparisons_semantics?.aggregate_count)})`;
  document.getElementById("merit_litter_count").textContent = `(${num(outcomes.observed_litter_count)})`;
  document.getElementById("merit_detail_matings").innerHTML = matingHtml(matings, displayName);
  document.getElementById("merit_detail_partners").innerHTML = partnerHtml(partners, displayName);
  document.getElementById("merit_detail_trend").innerHTML = trendHtml(trend, displayName);
  document.getElementById("merit_detail_context").innerHTML = identityGroup("Ouers", [family.dam_identity, family.sire_identity])
    + ids("Effective observations", (context.observations || []).map((value) => value.observation_event_id))
    + ids("Medical events", (context.medical_events || []).map((value) => value.medical_event_id || value.event_id));
  const offspringIdentities = family.offspring_identities || offspring.identities || [];
  document.getElementById("merit_offspring_summary").innerHTML = offspringSummaryHtml(offspring);
  document.getElementById("merit_offspring_scope").textContent = `Hierdie tabel wys die ${num(offspring.sample_size)} nageslagidentiteite en operasionele velde presies soos HERDMASTER dit verskaf. Unknown en conflicting bly sigbaar; assosiasie bewys nie oorsaaklikheid nie.`;
  document.getElementById("merit_offspring_table").innerHTML = offspringHtml(offspringIdentities, displayName);
  document.getElementById("merit_detail_lineage").innerHTML = lineageHtml(data.lineage);
}

function renderMetrics({ outcomes, opportunities, offspring, growth, finance, confidence, inputs }) {
  document.getElementById("merit_detail_metrics").innerHTML = `<section class="merit-context-card">
    <h3>Outcome evidence</h3><div class="merit-card-metrics">
      ${metric("Survival", pct(outcomes.rate), `${num(outcomes.weaned_numerator)} / ${num(outcomes.born_alive_denominator)}`)}
      ${metric("Eligible litters", num(outcomes.eligible_litter_count), `${num(outcomes.observed_litter_count)} observed`)}
      ${metric("Complete opportunities", num(opportunities.eligible_complete_through_count), `${num(opportunities.observed_count)} observed`)}
      ${metric("Offspring sample", num(offspring.sample_size))}
    </div></section>
    <section class="merit-context-card"><h3>Confidence evidence</h3><div class="merit-card-metrics">
      ${metric("Outcome coverage", pct(inputs.outcome_coverage))}
      ${metric("Context coverage", pct(inputs.context_coverage))}
      ${metric("Cohorts", num(inputs.cohort_count))}
      ${metric("Rule", text(confidence.confidence_rule_id))}
    </div></section>
    <section class="merit-context-card merit-unsupported"><h3>Explicitly unsupported</h3>
      <span>Comparable growth: <b>${esc(text(growth.median_weight_kg))}</b></span>
      <small>${esc(growth.limitation || "No supported comparable-growth conclusion.")}</small>
      <span>Exact financial attribution: <b>${esc(text(finance.gross_attributable))}</b></span>
      <small>${esc(finance.limitation || "No supported exact financial attribution.")}</small>
    </section>`;
}

document.addEventListener("DOMContentLoaded", () => {
  updateBack();
  load();
});
