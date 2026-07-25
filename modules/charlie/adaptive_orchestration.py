"""Deterministic, evidence-based mission orchestration for new CORE missions."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re


VERSION = "charlie_adaptive_orchestration_v1"
DIMENSIONS = (
    "scope_size", "component_count", "architectural_complexity", "uncertainty",
    "reversibility", "blast_radius", "external_side_effects", "customer_impact",
    "data_sensitivity", "authentication_security", "financial_impact",
    "schema_migration", "hardware_physical", "publication_reputation",
    "production_configuration", "evidence_availability", "owner_dependency",
)
PROTECTED = {
    "authentication_security", "financial_impact", "schema_migration",
    "hardware_physical", "publication_reputation", "customer_impact",
    "production_configuration",
}
ALL_AGENTS = (
    "source_mapper", "product_architect", "technical_architect", "planner",
    "architect", "creative_ui_designer", "frontend_design_implementer",
    "builder", "tester", "qa_red_team", "visual_qa_reviewer",
    "product_reviewer", "business_reviewer", "security_reviewer",
    "evidence_reviewer", "reviewer", "publisher",
)


def _text(mission):
    mission = mission if isinstance(mission, dict) else {}
    return " ".join(str(mission.get(key) or "") for key in (
        "mission_type", "title", "raw_text", "description", "acceptance_criteria",
    )).lower()


def _hit(text, words):
    return any(re.search(pattern, text) for pattern in words)


def _dimension(score, evidence, reason, *, confidence=0.9, unknown=False):
    return {
        "score": int(score), "evidence": list(evidence), "confidence": confidence,
        "unknown": bool(unknown), "reason": reason,
    }


def score_mission(mission):
    text = _text(mission)
    file_hints = sorted(set(re.findall(r"[\w./\\-]+\.(?:py|js|html|css|sql|md|json|ps1)", text)))
    mutation = _hit(text, (r"\b(build|fix|change|edit|implement|create|delete|write|deploy)\b",))
    docs = _hit(text, (r"\b(typo|documentation|docs?|readme|wording)\b",))
    read_only = _hit(text, (r"\b(read[- ]only|inspect|audit|report|explain|status)\b",)) and not mutation
    triggers = {
        "ui": (
            _hit(text, (r"\b(ui|frontend|screenshot|browser|page|css|template)\b",))
            and not _hit(text, (r"\b(no|without|non[- ]?)\s*(ui|frontend|visual)\b",))
        ),
        "security": _hit(text, (r"\b(auth|security|credential|secret|permission|privacy)\b",)),
        "database": _hit(text, (r"\b(schema|migration|database|postgres|sql|table)\b",)),
        "customer_delivery": _hit(text, (r"\b(customer|telegram|chatwoot|message|send|delivery)\b",)),
        "financial": _hit(text, (r"\b(payment|money|financial|revenue|price|invoice)\b",)),
        "hardware": _hit(text, (r"\b(hardware|irrigation|valve|pump|rootline|physical)\b",)),
        "publication": _hit(text, (r"\b(publish|publication|campaign|spend|beacon|storyworks)\b",)),
        "farm": _hit(text, (r"\b(herdmaster|pig|farm|livestock|litter|observation)\b",)),
        "sales": _hit(text, (r"\b(sam|sales|order|customer|meat)\b",)),
        "deployment": _hit(text, (r"\b(deploy|production|configuration|environment|render)\b",)),
    }
    explicit_small = _hit(text, (r"\b(simple|small|tiny|focused|bounded|bug|regression)\b",))
    unknown_scope = mutation and not file_hints and not docs and not explicit_small
    component_score = 0 if read_only else 1 if len(file_hints) <= 1 else 2 if len(file_hints) <= 4 else 3
    values = {
        "scope_size": _dimension(0 if read_only else 1 if docs or len(file_hints) <= 2 else 2, file_hints, "Bounded by explicit files and mutation intent.", unknown=unknown_scope),
        "component_count": _dimension(component_score, file_hints, f"{len(file_hints)} explicit component/file hints."),
        "architectural_complexity": _dimension(2 if _hit(text, (r"\b(architecture|cross-module|workflow|orchestration)\b",)) else 0 if read_only or docs else 1, [], "Architecture signal from mission language."),
        "uncertainty": _dimension(2 if _hit(text, (r"\b(unknown|uncertain|investigate|discover)\b",)) or unknown_scope else 0, [], "Explicit uncertainty or missing scope.", unknown=unknown_scope),
        "reversibility": _dimension(3 if _hit(text, (r"\b(irreversible|delete production|destructive)\b",)) else 0 if read_only else 1, [], "Mutation reversibility."),
        "blast_radius": _dimension(3 if triggers["deployment"] or triggers["hardware"] else 0 if read_only else 1, [], "Operational reach."),
        "external_side_effects": _dimension(3 if any(triggers[k] for k in ("customer_delivery", "hardware", "publication")) else 0, [], "External action triggers."),
        "customer_impact": _dimension(3 if triggers["customer_delivery"] else 0, [], "Customer communication impact."),
        "data_sensitivity": _dimension(2 if _hit(text, (r"\b(personal|private|privacy|customer data)\b",)) else 0, [], "Sensitive-data trigger."),
        "authentication_security": _dimension(3 if triggers["security"] else 0, [], "Security trigger."),
        "financial_impact": _dimension(3 if triggers["financial"] else 0, [], "Money/revenue trigger."),
        "schema_migration": _dimension(3 if triggers["database"] and _hit(text, (r"\b(schema|migration|table)\b",)) else 1 if triggers["database"] else 0, [], "Database/schema trigger."),
        "hardware_physical": _dimension(3 if triggers["hardware"] else 0, [], "Physical-control trigger."),
        "publication_reputation": _dimension(3 if triggers["publication"] else 0, [], "Publication/reputation trigger."),
        "production_configuration": _dimension(3 if triggers["deployment"] else 0, [], "Production/configuration trigger."),
        "evidence_availability": _dimension(2 if unknown_scope else 0 if file_hints or read_only else 1, file_hints, "Known acceptance/source evidence.", unknown=unknown_scope),
        "owner_dependency": _dimension(3 if _hit(text, (r"\b(owner approval|owner decision|protected)\b",)) else 0, [], "Explicit owner dependency."),
    }
    protected = [name for name in PROTECTED if values[name]["score"] >= 3]
    maximum = max(item["score"] for item in values.values())
    total = sum(item["score"] for item in values.values())
    if _hit(text, (r"\b(charlie core|workflow system|orchestration engine)\b",)) and mutation:
        tier = "T3"
    elif read_only:
        tier = "T0"
    elif protected:
        tier = "T4"
    elif maximum >= 3 or total >= 15:
        tier = "T3"
    elif total >= 7 or values["architectural_complexity"]["score"] >= 2:
        tier = "T2"
    else:
        tier = "T1"
    return {"version": VERSION, "tier": tier, "total_score": total,
            "dimensions": values, "triggers": triggers, "protected_triggers": protected}


def build_orchestration_packet(mission):
    score = score_mission(mission)
    tier, triggers = score["tier"], score["triggers"]
    text = _text(mission)
    factory_build = _hit(text, (r"\b(agent build|system improvement|charlie core|workflow system|orchestration engine)\b",))
    if factory_build:
        selected = [
            "idea_expander", "source_mapper", "product_architect",
            "technical_architect", "risk_agent", "council_synthesis", "planner",
            "architect", "builder", "tester", "qa_red_team",
            "product_reviewer", "security_reviewer", "evidence_reviewer",
            "reviewer", "publisher",
        ]
    elif tier == "T0":
        selected = ["source_mapper"]
    elif tier == "T1":
        selected = ["builder", "tester", "reviewer"]
    elif tier == "T2":
        selected = ["source_mapper", "architect", "builder", "tester", "reviewer"]
    else:
        selected = ["source_mapper", "technical_architect", "builder", "tester", "qa_red_team", "reviewer", "publisher"]
    mandatory = {}
    def add(agent, reason):
        if agent not in selected:
            insert_at = selected.index("reviewer") if "reviewer" in selected else len(selected)
            selected.insert(insert_at, agent)
        mandatory[agent] = reason
    if triggers["ui"]:
        for agent in ("visual_reference_interpreter", "creative_ui_designer",
                      "ux_interaction_designer", "frontend_design_implementer",
                      "visual_qa_reviewer"):
            add(agent, "UI/reference work requires specialist design and visual proof.")
    if triggers["security"]: add("security_reviewer", "Security/auth/credential impact.")
    if triggers["database"]: add("evidence_reviewer", "Database/schema evidence and audit required.")
    if triggers["customer_delivery"]: add("business_reviewer", "Customer safety and delivery truth required.")
    if triggers["financial"]: add("business_reviewer", "Financial/protected review required.")
    if triggers["hardware"]: add("evidence_reviewer", "ROOTLINE hardware-safety evidence required.")
    if triggers["publication"]: add("business_reviewer", "Publication/rights/owner governance required.")
    if triggers["farm"]: add("product_reviewer", "HERDMASTER domain ownership required.")
    if triggers["sales"]: add("business_reviewer", "SAM sales-domain truth required.")
    if score["protected_triggers"] and "publisher" not in selected:
        add("publisher", "Protected release packet required.")
    selected = list(dict.fromkeys(selected))
    limits = {
        "T0": (20, 1, 1, 8000), "T1": (120, 2, 2, 30000),
        "T2": (480, 2, 3, 70000), "T3": (960, 3, 4, 140000),
        "T4": (1440, 3, 4, 200000),
    }[tier]
    agents = []
    for index, agent in enumerate(selected):
        agents.append({
            "agent": agent, "mandatory": agent in mandatory,
            "selection_reason": mandatory.get(agent, f"Minimum sufficient {tier} workflow role."),
            "evidence_trigger": mandatory.get(agent, tier),
            "required_output": "charlie_handoff_v1",
            "authority": "read_only" if tier == "T0" else "scoped_repository",
            "tools": ["repo_read"] if tier == "T0" else ["repo_read", "scoped_edit", "tests"],
            "allowed_mutations": [] if tier == "T0" else ["explicitly scoped repository files"],
            "prohibited_actions": ["production mutation", "owner-gated action", "unscoped write"],
            "budget": {"minutes": max(5, limits[0] // len(selected)), "attempts": limits[1],
                       "tokens": max(2000, limits[3] // len(selected))},
            "handoff_recipient": selected[index + 1] if index + 1 < len(selected) else "owner",
        })
    skipped = [{"agent": agent, "reason": f"Not required by {tier} score or active specialist trigger."}
               for agent in ALL_AGENTS if agent not in selected]
    material = {"score": score, "selected": selected}
    generation = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()[:24]
    return {
        "version": VERSION, "generation_identity": generation, "created_at": datetime.now(timezone.utc).isoformat(),
        "score": score, "tier": tier, "selected_agents": agents, "skipped_agents": skipped,
        "authority_contract": {"permitted_reads": ["mission evidence", "scoped repository"],
                               "permitted_writes": [] if tier == "T0" else ["claimed files"],
                               "protected_actions": score["protected_triggers"]},
        "validation_contract": {"candidate_binding_required": tier != "T0",
                                "durable_lineage_required": tier != "T0",
                                "required_tests": [] if tier == "T0" else ["focused", "affected regression"],
                                "deployment_required": score["triggers"]["deployment"],
                                "operational_proof_required": tier in {"T3", "T4"}},
        "budgets": {"maximum_elapsed_minutes": limits[0], "maximum_attempts_per_stage": limits[1],
                    "maximum_recovery_cycles": limits[2], "maximum_tokens": limits[3]},
        "concurrency": {"read_only_parallel_allowed": True, "repository_writers_serialized": True},
        "expansion_history": [], "backflow_count": 0, "agent_execution_count": 0,
        "elapsed_seconds": 0, "final_outcome": "pending",
        "stop_conditions": ["protected trigger without mandatory reviewer", "unbound evidence",
                            "budget exhausted", "scope or candidate changed"],
    }


def expand_orchestration(packet, mission, evidence):
    """Return a new generation only when material evidence changes the score/team."""
    prior = deepcopy(packet if isinstance(packet, dict) else {})
    enriched = dict(mission if isinstance(mission, dict) else {})
    enriched["raw_text"] = f"{enriched.get('raw_text', '')} {json.dumps(evidence, sort_keys=True)}"
    updated = build_orchestration_packet(enriched)
    if updated["generation_identity"] == prior.get("generation_identity"):
        return prior
    mandatory_before = {x["agent"] for x in prior.get("selected_agents", []) if x.get("mandatory")}
    selected_after = {x["agent"] for x in updated["selected_agents"]}
    if not mandatory_before.issubset(selected_after):
        raise ValueError("mandatory_agent_contraction_forbidden")
    updated["expansion_history"] = [*prior.get("expansion_history", []), {
        "from_generation": prior.get("generation_identity"), "to_generation": updated["generation_identity"],
        "reason": "material_evidence_changed_score_or_trigger", "evidence": evidence,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }]
    return updated


def throughput_snapshot(packets):
    result = {}
    for packet in packets or []:
        if not isinstance(packet, dict):
            continue
        tier = packet.get("tier", "unknown")
        row = result.setdefault(tier, {"missions": 0, "owner_ready": 0, "elapsed_seconds": 0,
                                      "agent_executions": 0, "backflows": 0})
        row["missions"] += 1
        row["owner_ready"] += int(packet.get("final_outcome") == "owner_ready")
        row["elapsed_seconds"] += int(packet.get("elapsed_seconds") or 0)
        row["agent_executions"] += int(packet.get("agent_execution_count") or 0)
        row["backflows"] += int(packet.get("backflow_count") or 0)
    for row in result.values():
        row["average_elapsed_seconds"] = row["elapsed_seconds"] / row["missions"]
        row["completion_without_manual_repair_pct"] = 100 * row["owner_ready"] / row["missions"]
    return result
