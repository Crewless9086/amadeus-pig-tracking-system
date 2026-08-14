"""Thin Oom Sakkie presentation adapter for HERDMASTER daily evidence."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from modules.oom_sakkie.farm_manager_loop import (
    Authority, Provenance, SpecialistAvailability, SpecialistResult,
    SpecialistWorkItem, WorkState,
)
from modules.pig_weights.herdmaster_daily_manager_evidence import PACKET_TYPE


def consume_daily_manager_evidence(packet, *, observed_at: datetime,
                                   active_lifecycles=(), language="en"):
    if not _valid(packet):
        provenance = Provenance("herdmaster", "herdmaster-daily-evidence-unavailable",
            ("canonical_daily_manager_evidence_unavailable",), observed_at, 1.0)
        item = SpecialistWorkItem(item_id=provenance.result_id,
            dedupe_key="herdmaster:weekly-weight-evidence", domain="herd",
            title="Weekly weighing evidence unavailable",
            why="HERDMASTER could not establish the governed cohort within the bounded evidence window.",
            next_action="Wait for canonical evidence; do not weigh every active pig.",
            assignee="charl", state=WorkState.WAITING_EVIDENCE,
            authority=Authority.READ_ONLY, provenance=provenance, business_value=105)
        return SpecialistResult("herdmaster", provenance.result_id,
            observed_at, SpecialistAvailability.AVAILABLE, work_items=(item,))
    weight = packet["weight"]
    snapshot = weight["current_snapshot"]
    provenance = Provenance("herdmaster", packet["material_digest"],
        (PACKET_TYPE, packet["material_digest"]), observed_at, 1.0)
    items = []
    missing = weight["missing_eligible_tagged"]
    findings = weight["material_weight_findings"]
    conflicts = weight["conflicting_weight_evidence"]
    is_af = str(language).casefold().startswith("af")
    if conflicts:
        items.append(SpecialistWorkItem(item_id=packet["material_digest"]+":weight-conflict",
            dedupe_key="herdmaster:weekly-weight-evidence", domain="herd",
            title="Weekly weighing evidence conflicts",
            why=f"{len(conflicts)} eligible tagged pig(s) have conflicting same-day values; completion is Unknown.",
            next_action="Resolve the canonical evidence conflict; do not select a biological interpretation.",
            assignee="charl", state=WorkState.WAITING_EVIDENCE, authority=Authority.READ_ONLY,
            provenance=provenance, business_value=120))
    elif missing:
        tags = ", ".join(str(row["tag"]) for row in missing)
        items.append(SpecialistWorkItem(item_id=packet["material_digest"]+":weight-missing",
            dedupe_key="herdmaster:weekly-weight-evidence", domain="herd",
            title=f"Weekly weighing: {len(missing)} eligible tagged pig(s) missing",
            why=(f"Current-snapshot coverage is {snapshot['covered']}/{snapshot['eligible_tagged']}. "
                 "Breeding, untagged, inactive/off-farm and Unknown eligibility remain separate."),
            next_action=f"Weigh only these missing eligible tags: {tags}.", assignee="charl",
            state=WorkState.DUE_TODAY, authority=Authority.ADVISORY,
            provenance=provenance, business_value=110))
    elif snapshot["status"] == "complete":
        finding_text = _findings(findings)
        items.append(SpecialistWorkItem(item_id=packet["material_digest"]+":weight-covered",
            dedupe_key="herdmaster:weekly-weight-evidence", domain="herd",
            title=f"Weekly weighing covered: {snapshot['covered']}/{snapshot['eligible_tagged']} eligible tagged pigs",
            why=("This is current-snapshot coverage; historical 11–12 August eligibility remains Unknown. "
                 + finding_text),
            next_action="No further cohort weighing instruction. Review only the descriptive changes shown.",
            assignee="charl", state=WorkState.PLANNED, authority=Authority.ADVISORY,
            provenance=provenance, business_value=70))
    else:
        items.append(SpecialistWorkItem(item_id=packet["material_digest"]+":weight-unknown",
            dedupe_key="herdmaster:weekly-weight-evidence", domain="herd",
            title="Weekly weighing evidence unavailable",
            why="The eligible tagged denominator cannot be established from current canonical evidence.",
            next_action="Wait for HERDMASTER canonical evidence; do not weigh every active pig.",
            assignee="charl", state=WorkState.WAITING_EVIDENCE, authority=Authority.READ_ONLY,
            provenance=provenance, business_value=105))

    mortality = packet["mortality"]
    if mortality.get("digest_changed"):
        open_ids = {str(row.get("pig_id") or "") for row in active_lifecycles
                    if str(row.get("state") or "") not in {"completed", "closed", "handled"}}
        candidates = [row for row in mortality.get("candidate_deaths") or ()
                      if str(row.get("pig_id") or "") in open_ids]
        if candidates:
            row = sorted(candidates, key=lambda value: (str(value.get("effective_date") or ""),
                                                        str(value.get("event_id") or "")))[-1]
            tag = str(row.get("tag") or row.get("pig_id") or "the pig")
            items.append(SpecialistWorkItem(item_id=packet["material_digest"]+":mortality:"+str(row.get("event_id") or tag),
                dedupe_key="herdmaster:mortality:"+str(row.get("event_id") or row.get("pig_id")),
                domain="herd", title=f"Mortality follow-up — {tag}",
                why="One changed canonical death has an unresolved attributable individual lifecycle.",
                next_action="Continue that existing individual follow-up; patterns remain associations, not diagnoses.",
                assignee="charl", state=WorkState.WAITING_EVIDENCE, authority=Authority.ADVISORY,
                provenance=provenance, business_value=125))
    result_id = "HERD-DAILY-EVIDENCE-" + packet["material_digest"][:24]
    rebound = tuple(replace(item, provenance=replace(provenance, result_id=result_id)) for item in items)
    return SpecialistResult("herdmaster", result_id, observed_at,
        SpecialistAvailability.AVAILABLE, work_items=rebound)


def _findings(rows):
    if not rows:
        return "No material descriptive weight change crossed the review threshold."
    return "Descriptive changes for review: " + "; ".join(
        f"{row.get('tag') or row['pig_id']} {row['change_kg']:+g} kg ({row['change_pct']:+g}%)"
        for row in rows[:4]) + ". No cause or diagnosis is inferred."


def _valid(packet):
    if not isinstance(packet, dict) or packet.get("packet_type") != PACKET_TYPE:
        return False
    authority = packet.get("authority") or {}
    if authority.get("read_only") is not True or authority.get("writes_farm_data") is not False \
            or authority.get("hardware_commands") != 0 or authority.get("sends_messages") is not False:
        return False
    weight = packet.get("weight") or {}; snapshot = weight.get("current_snapshot") or {}
    required_lists = ("missing_eligible_tagged", "breeding_excluded", "untagged_excluded",
                      "inactive_off_farm", "unknown_eligibility", "conflicting_weight_evidence",
                      "material_weight_findings")
    return bool(packet.get("material_digest") and weight.get("historical_completion_percentage") is None
        and all(isinstance(weight.get(key), list) for key in required_lists)
        and snapshot.get("status") in {"complete", "partial", "unknown", "conflicting"})
