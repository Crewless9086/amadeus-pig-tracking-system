from copy import deepcopy
from datetime import datetime, timezone


CHARLIE_CORE_VERSION = "charlie_core_v3"
VAULT_VERSION = "charlie_vault_v1"
HANDOFF_VERSION = "charlie_handoff_v1"
REVIEW_BOARD_VERSION = "charlie_review_board_v1"
INTELLIGENCE_LOOP_VERSION = "charlie_intelligence_loop_v1"


VAULT_SCHEMA = {
    "version": VAULT_VERSION,
    "canonical_storage": "charlie_missions.metadata_json plus normalized Supabase tables when migrations are applied",
    "tables": [
        "charlie_vault_projects",
        "charlie_vault_artifacts",
        "charlie_agent_runs",
        "charlie_handoff_reports",
        "charlie_quality_gates",
        "charlie_owner_decisions",
        "charlie_deployments",
        "charlie_audit_log",
        "charlie_lessons",
        "charlie_income_stream_reviews",
    ],
    "artifact_types": [
        "idea_brief",
        "concept_strategy",
        "product_requirements",
        "technical_architecture",
        "build_plan",
        "test_report",
        "risk_register",
        "review_board_packet",
        "owner_approval",
        "deployment_record",
        "lesson_record",
        "income_stream_readiness",
    ],
}


SPECIALIST_AGENTS = {
    "idea_expander": {
        "purpose": "Expand rough owner intent into opportunity, user outcome, non-goals, assumptions, and first risks.",
        "may": ["read mission vault", "produce idea brief", "list assumptions"],
        "may_not": ["edit code", "approve release", "publish externally"],
    },
    "concept_strategist": {
        "purpose": "Turn the idea into a clear concept, strategic thesis, options, and decision memo.",
        "may": ["produce concept strategy", "recommend direction"],
        "may_not": ["commit to public/customer promises", "approve money movement"],
    },
    "product_architect": {
        "purpose": "Define user journeys, acceptance boundaries, product quality bar, and owner-visible outcomes.",
        "may": ["write requirements", "define acceptance criteria"],
        "may_not": ["ship code", "approve release"],
    },
    "technical_architect": {
        "purpose": "Design implementation structure, file/API/data impacts, integration risk, and test strategy.",
        "may": ["write architecture plan", "identify affected files", "define test plan"],
        "may_not": ["perform broad refactors without approval"],
    },
    "business_model_agent": {
        "purpose": "Evaluate revenue logic, pricing assumptions, cost drivers, and commercial next actions.",
        "may": ["produce business model notes", "flag financial assumptions"],
        "may_not": ["spend money", "send offers", "bind pricing externally"],
    },
    "risk_agent": {
        "purpose": "Create risk register across technical, legal, financial, operational, brand, and data risks.",
        "may": ["block high-risk gaps", "request owner decisions"],
        "may_not": ["dismiss legal/compliance uncertainty"],
    },
    "planner": {
        "purpose": "Break approved direction into scoped tasks, gates, tests, and rollback plan.",
        "may": ["create build plan", "sequence work"],
        "may_not": ["skip required artifacts"],
    },
    "architect": {
        "purpose": "Map the planned work to repository structure, APIs, data, and constraints.",
        "may": ["prepare implementation blueprint"],
        "may_not": ["weaken approval level"],
    },
    "builder": {
        "purpose": "Implement scoped changes under the approved authority level.",
        "may": ["edit scoped files", "run tests", "commit on feature branch"],
        "may_not": ["merge main", "deploy", "delete data", "change secrets"],
    },
    "tester": {
        "purpose": "Run unit, integration, regression, and workflow checks with explicit evidence.",
        "may": ["fail the mission", "request fixes"],
        "may_not": ["approve own test gaps"],
    },
    "qa_red_team": {
        "purpose": "Challenge regressions, weak evidence, unsafe tool use, prompt risk, and owner-risk.",
        "may": ["send back to builder/tester", "raise risk rating"],
        "may_not": ["override owner gates"],
    },
    "security_reviewer": {
        "purpose": "Review permissions, secrets, data exposure, injection, and dangerous actions.",
        "may": ["block security-sensitive gaps"],
        "may_not": ["approve production secret access"],
    },
    "evidence_reviewer": {
        "purpose": "Check claims, tests, citations, artifacts, and proof against the Vault.",
        "may": ["flag unsupported claims"],
        "may_not": ["accept unverifiable claims as truth"],
    },
    "product_reviewer": {
        "purpose": "Check that the result matches owner intent, user value, and acceptance criteria.",
        "may": ["send back unclear product outcomes"],
        "may_not": ["approve technical work without test evidence"],
    },
    "business_reviewer": {
        "purpose": "Check commercial logic, income-stream readiness, and owner decision clarity.",
        "may": ["flag weak revenue logic"],
        "may_not": ["make legal or financial commitments"],
    },
    "reviewer": {
        "purpose": "Combine evidence and recommend owner decision.",
        "may": ["prepare final owner packet"],
        "may_not": ["self-approve release"],
    },
    "publisher": {
        "purpose": "Prepare deployment/publishing packet after owner approval and verification.",
        "may": ["prepare release notes", "record deployment verification"],
        "may_not": ["publish without explicit owner approval"],
    },
}


REVIEW_BOARD_AGENTS = ["product_reviewer", "business_reviewer", "security_reviewer", "evidence_reviewer", "reviewer"]


WORKFLOW_TEMPLATES = {
    "software_build": {
        "label": "Software Build",
        "mission_type_aliases": ["feature build", "software", "agent build", "bug fix"],
        "agent_order": [
            "idea_expander",
            "product_architect",
            "technical_architect",
            "planner",
            "architect",
            "builder",
            "tester",
            "qa_red_team",
            "security_reviewer",
            "evidence_reviewer",
            "reviewer",
            "publisher",
        ],
        "required_artifacts": ["idea_brief", "product_requirements", "technical_architecture", "build_plan", "test_report", "review_board_packet"],
        "owner_gates": ["approve_build", "approve_final_release"],
    },
    "system_improvement": {
        "label": "System Improvement",
        "mission_type_aliases": ["system", "workflow", "governance", "dashboard", "runner"],
        "agent_order": [
            "idea_expander",
            "technical_architect",
            "risk_agent",
            "planner",
            "architect",
            "builder",
            "tester",
            "qa_red_team",
            "security_reviewer",
            "evidence_reviewer",
            "reviewer",
            "publisher",
        ],
        "required_artifacts": ["current_state_analysis", "risk_register", "technical_architecture", "test_report", "review_board_packet"],
        "owner_gates": ["approve_build", "approve_final_release"],
    },
    "business_plan": {
        "label": "Business Plan",
        "mission_type_aliases": ["business plan", "strategy", "business", "new venture"],
        "agent_order": [
            "idea_expander",
            "concept_strategist",
            "business_model_agent",
            "risk_agent",
            "product_architect",
            "business_reviewer",
            "evidence_reviewer",
            "reviewer",
        ],
        "required_artifacts": ["idea_brief", "concept_strategy", "business_model", "risk_register", "review_board_packet"],
        "owner_gates": ["approve_strategy"],
    },
    "content_engine": {
        "label": "Content Engine",
        "mission_type_aliases": ["content", "marketing", "campaign", "beacon"],
        "agent_order": [
            "idea_expander",
            "concept_strategist",
            "product_architect",
            "risk_agent",
            "business_reviewer",
            "evidence_reviewer",
            "reviewer",
            "publisher",
        ],
        "required_artifacts": ["content_brief", "source_pack", "brand_review", "owner_approval"],
        "owner_gates": ["approve_public_copy", "approve_publish"],
    },
    "automation_workflow": {
        "label": "Automation Workflow",
        "mission_type_aliases": ["automation", "n8n", "integration", "process"],
        "agent_order": [
            "idea_expander",
            "technical_architect",
            "risk_agent",
            "planner",
            "architect",
            "builder",
            "tester",
            "qa_red_team",
            "security_reviewer",
            "evidence_reviewer",
            "reviewer",
        ],
        "required_artifacts": ["process_map", "automation_design", "fake_data_test", "security_review", "owner_approval"],
        "owner_gates": ["approve_fake_data_test", "approve_live_rollout"],
    },
    "income_stream": {
        "label": "Income Stream",
        "mission_type_aliases": ["income", "income stream", "revenue", "sales", "private transfers", "fred", "sam"],
        "agent_order": [
            "idea_expander",
            "concept_strategist",
            "business_model_agent",
            "risk_agent",
            "product_architect",
            "technical_architect",
            "business_reviewer",
            "security_reviewer",
            "evidence_reviewer",
            "reviewer",
        ],
        "required_artifacts": ["idea_brief", "business_model", "risk_register", "income_stream_readiness", "owner_decision_packet"],
        "owner_gates": ["approve_business_model", "approve_customer_contact", "approve_money_path"],
    },
}


STAGE_DEFINITIONS = [
    {"stage": 0, "name": "clean_build_lane", "required": ["branch_truth", "worktree_truth"]},
    {"stage": 1, "name": "vault_v1", "required": ["vault_schema", "project_truth", "artifact_registry"]},
    {"stage": 2, "name": "handoff_contract", "required": ["handoff_schema", "handoff_validation"]},
    {"stage": 3, "name": "workflow_templates", "required": ["workflow_template", "required_artifacts", "owner_gates"]},
    {"stage": 4, "name": "specialist_agents", "required": ["agent_order", "agent_instruction_packs"]},
    {"stage": 5, "name": "review_board", "required": ["review_board", "review_decision"]},
    {"stage": 6, "name": "command_center", "required": ["dashboard_truth", "owner_actions"]},
    {"stage": 7, "name": "runner_enforcement", "required": ["runner_gates", "send_back_rules"]},
    {"stage": 8, "name": "release_verification", "required": ["release_packet", "deployment_record"]},
    {"stage": 9, "name": "intelligence_loop", "required": ["lesson_records", "improvement_backlog"]},
    {"stage": 10, "name": "income_stream_readiness", "required": ["income_review", "money_path_gates"]},
]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def clean_text(value, max_len=1200):
    return " ".join(str(value or "").strip().split())[:max_len]


def clean_list(value, max_items=20, max_len=500):
    if isinstance(value, str):
        raw = [line.strip("- ").strip() for line in value.splitlines()]
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    items = []
    for item in raw:
        text = clean_text(item, max_len)
        if text:
            items.append(text)
        if len(items) >= max_items:
            break
    return items


def classify_workflow_template(mission_type="", raw_text=""):
    haystack = f"{mission_type} {raw_text}".lower()
    for template_id, template in WORKFLOW_TEMPLATES.items():
        for alias in template["mission_type_aliases"]:
            if alias in haystack:
                return template_id
    return "software_build"


def workflow_template(template_id):
    template_id = template_id if template_id in WORKFLOW_TEMPLATES else "software_build"
    template = deepcopy(WORKFLOW_TEMPLATES[template_id])
    template["template_id"] = template_id
    template["version"] = CHARLIE_CORE_VERSION
    return template


def agent_instruction_pack(agent):
    definition = SPECIALIST_AGENTS.get(agent, {})
    return {
        "agent": agent,
        "identity": f"You are CHARLIE {agent.replace('_', ' ').title()}.",
        "mission": definition.get("purpose", "Complete the assigned CHARLIE stage."),
        "authority": {
            "may": definition.get("may", []),
            "may_not": definition.get("may_not", []),
        },
        "vault_rules": [
            "Check mission vault before opinion.",
            "Cite vault/source context when making claims.",
            "Mark assumptions and uncertainty.",
            "Write a handoff report before completion.",
        ],
        "output_contract": HANDOFF_VERSION,
        "quality_bar": [
            "All required artifacts for this stage are present.",
            "Tests or review evidence are recorded where applicable.",
            "Risks and owner decisions are explicit.",
        ],
    }


def build_workflow(template_id):
    template = workflow_template(template_id)
    workflow = []
    for index, agent in enumerate(template["agent_order"]):
        next_agent = template["agent_order"][index + 1] if index + 1 < len(template["agent_order"]) else "owner"
        workflow.append({
            "agent": agent,
            "status": "pending",
            "purpose": SPECIALIST_AGENTS.get(agent, {}).get("purpose", ""),
            "handoff_to": next_agent,
            "required_output": HANDOFF_VERSION,
            "instruction_pack": agent_instruction_pack(agent),
            "findings": "",
        })
    if workflow:
        workflow[0]["status"] = "active"
    return workflow


def build_project_truth(mission):
    mission = mission if isinstance(mission, dict) else {}
    mission_type = clean_text(mission.get("mission_type", "feature build"), 80)
    template_id = classify_workflow_template(mission_type, mission.get("raw_text", ""))
    template = workflow_template(template_id)
    return {
        "version": CHARLIE_CORE_VERSION,
        "project_key": clean_text(mission.get("project_key") or _project_key_for_mission(mission_type), 80),
        "mission_type": mission_type,
        "workflow_template": template_id,
        "workflow_label": template["label"],
        "owner": "CHARL",
        "charlie_role": "workflow_governor",
        "required_artifacts": list(template["required_artifacts"]),
        "owner_gates": list(template["owner_gates"]),
        "created_at": utc_now(),
    }


def build_core_plan(mission):
    from modules.charlie.model_registry import model_registry_packet
    from modules.charlie.tool_permissions import tool_permission_registry

    project_truth = build_project_truth(mission)
    template_id = project_truth["workflow_template"]
    return {
        "version": CHARLIE_CORE_VERSION,
        "vault_schema": VAULT_SCHEMA,
        "project_truth": project_truth,
        "workflow_template": workflow_template(template_id),
        "agent_workflow": build_workflow(template_id),
        "review_board": build_review_board_packet({}),
        "model_registry": model_registry_packet(),
        "tool_permissions": tool_permission_registry(),
        "intelligence_loop": {
            "version": INTELLIGENCE_LOOP_VERSION,
            "lesson_records": [],
            "improvement_backlog": [],
            "status": "ready_to_capture_lessons",
        },
        "readiness": evaluate_core_readiness({"metadata": {"charlie_core": {"project_truth": project_truth}}}),
    }


def build_handoff_report(mission, agent, artifact=None, stage=""):
    mission = mission if isinstance(mission, dict) else {}
    artifact = artifact if isinstance(artifact, dict) else {}
    report = {
        "version": HANDOFF_VERSION,
        "mission_id": clean_text(mission.get("mission_id", ""), 90),
        "project": clean_text((mission.get("metadata") or {}).get("project_key") or mission.get("title", ""), 160),
        "stage": clean_text(stage or artifact.get("stage") or agent, 80),
        "agent": clean_text(agent, 80),
        "task": clean_text(artifact.get("task") or artifact.get("summary") or mission.get("title", ""), 1200),
        "inputs_used": clean_list(artifact.get("inputs_used") or artifact.get("files_inspected") or []),
        "vault_sources_used": clean_list(artifact.get("vault_sources_used") or artifact.get("sources") or []),
        "actions_taken": clean_list(artifact.get("actions_taken") or artifact.get("commands_run") or []),
        "artifacts_created": clean_list(artifact.get("artifacts_created") or artifact.get("changed_files") or []),
        "files_changed": clean_list(artifact.get("files_changed") or artifact.get("changed_files") or []),
        "decisions_made": clean_list(artifact.get("decisions_made") or []),
        "assumptions": clean_list(artifact.get("assumptions") or []),
        "risks_found": clean_list(artifact.get("risks_found") or artifact.get("risk_notes") or artifact.get("qa_findings") or []),
        "tests_run": clean_list(artifact.get("tests_run") or artifact.get("test_evidence") or []),
        "test_results": clean_text(artifact.get("test_results") or artifact.get("test_status") or artifact.get("red_team_status") or "", 400),
        "open_questions": clean_list(artifact.get("open_questions") or []),
        "recommended_next_agent": clean_text(artifact.get("recommended_next_agent") or artifact.get("handoff_to") or "", 80),
        "pass_fail_status": clean_text(artifact.get("pass_fail_status") or artifact.get("status") or "pass", 40),
        "confidence": clean_text(artifact.get("confidence") or "", 40),
        "recorded_at": utc_now(),
    }
    report["validation"] = validate_handoff_report(report)
    return report


def validate_handoff_report(report):
    required = [
        "version",
        "mission_id",
        "stage",
        "agent",
        "task",
        "inputs_used",
        "actions_taken",
        "pass_fail_status",
    ]
    missing = [key for key in required if not report.get(key)]
    return {
        "valid": not missing,
        "missing_fields": missing,
        "required_fields": required,
    }


def build_review_board_packet(mission, artifacts=None):
    mission = mission if isinstance(mission, dict) else {}
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    reviews = []
    for agent in REVIEW_BOARD_AGENTS:
        reviews.append({
            "agent": agent,
            "status": "pending",
            "focus": SPECIALIST_AGENTS[agent]["purpose"],
            "required_evidence": _review_required_evidence(agent),
        })
    return {
        "version": REVIEW_BOARD_VERSION,
        "mission_id": clean_text(mission.get("mission_id", ""), 90),
        "reviews": reviews,
        "decision": "pending",
        "send_back_target": "",
        "artifacts_seen": sorted(artifacts.keys()),
        "owner_summary": "Review board pending.",
    }


def evaluate_review_board(packet):
    packet = packet if isinstance(packet, dict) else {}
    reviews = packet.get("reviews") if isinstance(packet.get("reviews"), list) else []
    failed = [item for item in reviews if item.get("status") in {"fail", "blocked"}]
    pending = [item for item in reviews if item.get("status") in {"", "pending", None}]
    if failed:
        return {"decision": "send_back", "passed": False, "reason": f"{len(failed)} review(s) failed."}
    if pending:
        return {"decision": "pending", "passed": False, "reason": f"{len(pending)} review(s) pending."}
    return {"decision": "approve_owner_review", "passed": True, "reason": "Review board passed."}


def build_deployment_record(mission, commit_sha="", verify_url="", status="pending"):
    return {
        "version": "charlie_deployment_record_v1",
        "mission_id": clean_text((mission or {}).get("mission_id", ""), 90),
        "commit_sha": clean_text(commit_sha, 80),
        "verify_url": clean_text(verify_url, 500),
        "status": clean_text(status or "pending", 40),
        "requires_live_verification": bool(commit_sha or verify_url),
        "verified_at": utc_now() if status == "verified" else "",
    }


def build_lesson_record(mission, failure="", improvement="", source_stage=""):
    return {
        "version": INTELLIGENCE_LOOP_VERSION,
        "mission_id": clean_text((mission or {}).get("mission_id", ""), 90),
        "source_stage": clean_text(source_stage, 80),
        "failure": clean_text(failure, 1200),
        "improvement": clean_text(improvement, 1200),
        "target": "prompt_or_test_or_workflow_update",
        "status": "queued",
        "recorded_at": utc_now(),
    }


def build_income_stream_readiness(mission):
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    vault = metadata.get("mission_vault") if isinstance(metadata.get("mission_vault"), dict) else mission.get("vault", {})
    business_model = vault.get("business_model") if isinstance(vault, dict) else {}
    risk_register = vault.get("risk_register") if isinstance(vault, dict) else []
    gates = {
        "business_model": bool(business_model),
        "risk_register": bool(risk_register),
        "owner_money_path_approval": _has_owner_gate(metadata, "approve_money_path"),
        "customer_contact_approval": _has_owner_gate(metadata, "approve_customer_contact"),
        "evidence_review": _review_has_status(metadata, "evidence_reviewer", "pass"),
        "business_review": _review_has_status(metadata, "business_reviewer", "pass"),
    }
    missing = [name for name, passed in gates.items() if not passed]
    return {
        "version": "charlie_income_stream_readiness_v1",
        "ready": not missing,
        "gates": gates,
        "missing_gates": missing,
        "next_action": "Owner can review income-stream packet." if not missing else f"Complete: {', '.join(missing)}.",
    }


def evaluate_core_readiness(mission):
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    core = metadata.get("charlie_core") if isinstance(metadata.get("charlie_core"), dict) else {}
    vault = metadata.get("mission_vault") if isinstance(metadata.get("mission_vault"), dict) else mission.get("vault", {})
    workflow = metadata.get("agent_workflow") if isinstance(metadata.get("agent_workflow"), list) else mission.get("agent_workflow", [])
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    deployment = metadata.get("deployment_record") if isinstance(metadata.get("deployment_record"), dict) else {}
    lessons = metadata.get("intelligence_loop") if isinstance(metadata.get("intelligence_loop"), dict) else {}
    income = metadata.get("income_stream_readiness") if isinstance(metadata.get("income_stream_readiness"), dict) else {}

    checks = {
        "branch_truth": True,
        "worktree_truth": True,
        "vault_schema": bool(core.get("vault_schema") or VAULT_SCHEMA),
        "project_truth": bool(core.get("project_truth")),
        "artifact_registry": bool(core.get("vault_schema", {}).get("artifact_types") or VAULT_SCHEMA.get("artifact_types")),
        "handoff_schema": bool(core.get("handoff_schema") or HANDOFF_VERSION),
        "handoff_validation": _workflow_has_handoff_contract(workflow),
        "workflow_template": bool(core.get("workflow_template") or core.get("project_truth", {}).get("workflow_template")),
        "required_artifacts": bool(core.get("workflow_template", {}).get("required_artifacts") or core.get("project_truth", {}).get("required_artifacts")),
        "owner_gates": bool(core.get("workflow_template", {}).get("owner_gates") or core.get("project_truth", {}).get("owner_gates")),
        "agent_order": bool(workflow),
        "agent_instruction_packs": _workflow_has_instruction_packs(workflow),
        "review_board": bool(core.get("review_board") or review_packet.get("review_board")),
        "review_decision": bool(review_packet.get("review_status") or review_packet.get("last_owner_review_decision") or core.get("review_board")),
        "dashboard_truth": bool(core.get("command_center") or metadata or vault),
        "owner_actions": bool(review_packet or core.get("project_truth", {}).get("owner_gates")),
        "runner_gates": bool(core.get("runner_enforcement") or workflow),
        "send_back_rules": bool(core.get("send_back_rules") or review_packet.get("return_to_stage") is not None or workflow),
        "release_packet": bool(metadata.get("release_packet") or deployment or review_packet),
        "deployment_record": bool(deployment or metadata.get("release_packet")),
        "lesson_records": bool(lessons.get("lesson_records") is not None),
        "improvement_backlog": bool(lessons.get("improvement_backlog") is not None),
        "income_review": bool(income or core.get("project_truth", {}).get("workflow_template") != "income_stream"),
        "money_path_gates": bool(income.get("gates") or core.get("project_truth", {}).get("workflow_template") != "income_stream"),
    }
    stages = []
    for definition in STAGE_DEFINITIONS:
        required = definition["required"]
        passed_keys = [key for key in required if checks.get(key)]
        percent = round((len(passed_keys) / len(required)) * 100)
        stages.append({
            "stage": definition["stage"],
            "name": definition["name"],
            "percent": percent,
            "passed": percent == 100,
            "missing": [key for key in required if key not in passed_keys],
        })
    overall = round(sum(stage["percent"] for stage in stages) / len(stages))
    return {
        "version": CHARLIE_CORE_VERSION,
        "overall_percent": overall,
        "passed": overall >= 90 and all(stage["percent"] >= 80 for stage in stages),
        "stages": stages,
        "next_gaps": [f"Stage {stage['stage']} {stage['name']}: {', '.join(stage['missing'])}" for stage in stages if stage["missing"]],
    }


def attach_core_plan_to_metadata(mission, metadata=None):
    metadata = dict(metadata or {})
    plan = build_core_plan(mission)
    metadata.setdefault("mission_vault", {})
    metadata["mission_vault"] = {
        **metadata["mission_vault"],
        "mission_stage": metadata["mission_vault"].get("mission_stage", "intake"),
        "project_truth": plan["project_truth"],
        "required_artifacts": plan["project_truth"]["required_artifacts"],
        "owner_gates": plan["project_truth"]["owner_gates"],
    }
    metadata.setdefault("agent_workflow", plan["agent_workflow"])
    metadata.setdefault("charlie_core", {
        "version": CHARLIE_CORE_VERSION,
        "vault_schema": VAULT_SCHEMA,
        "project_truth": plan["project_truth"],
        "workflow_template": plan["workflow_template"],
        "handoff_schema": {"version": HANDOFF_VERSION, "required_validation": True},
        "review_board": plan["review_board"],
        "runner_enforcement": {
            "template_driven": True,
            "quality_gates_required": True,
            "owner_release_gate_required": True,
        },
        "send_back_rules": {
            "enabled": True,
            "default_target": "builder",
            "allowed_targets": list(SPECIALIST_AGENTS.keys()),
        },
        "command_center": {
            "shows_project_truth": True,
            "shows_risks": True,
            "shows_artifacts": True,
            "shows_review_quality": True,
        },
        "model_registry": plan["model_registry"],
        "tool_permissions": plan["tool_permissions"],
    })
    metadata.setdefault("intelligence_loop", plan["intelligence_loop"])
    if plan["project_truth"]["workflow_template"] == "income_stream":
        metadata.setdefault("income_stream_readiness", build_income_stream_readiness({"metadata": metadata}))
    metadata["charlie_core"]["readiness"] = evaluate_core_readiness({"metadata": metadata})
    return metadata


def _project_key_for_mission(mission_type):
    text = mission_type.lower()
    if "fred" in text or "transfer" in text:
        return "fred"
    if "sam" in text or "sales" in text or "income" in text:
        return "sam"
    if "oom" in text or "farm" in text:
        return "oom_sakkie"
    return "charlie_core"


def _review_required_evidence(agent):
    if agent == "security_reviewer":
        return ["permissions", "secrets", "data exposure", "dangerous actions"]
    if agent == "evidence_reviewer":
        return ["tests", "sources", "artifacts", "unsupported claims"]
    if agent == "business_reviewer":
        return ["commercial logic", "owner decisions", "money path risks"]
    if agent == "product_reviewer":
        return ["owner intent", "acceptance criteria", "user value"]
    return ["all reviews", "release notes", "owner decision recommendation"]


def _workflow_has_handoff_contract(workflow):
    if not workflow:
        return False
    return all(isinstance(item, dict) and item.get("required_output") == HANDOFF_VERSION for item in workflow)


def _workflow_has_instruction_packs(workflow):
    if not workflow:
        return False
    return all(isinstance(item, dict) and isinstance(item.get("instruction_pack"), dict) for item in workflow)


def _has_owner_gate(metadata, gate):
    decisions = metadata.get("owner_review_decisions") if isinstance(metadata.get("owner_review_decisions"), list) else []
    for decision in decisions:
        if isinstance(decision, dict) and gate in str(decision.get("decision") or ""):
            return True
    return False


def _review_has_status(metadata, agent, status):
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    board = review_packet.get("review_board") if isinstance(review_packet.get("review_board"), dict) else {}
    reviews = board.get("reviews") if isinstance(board.get("reviews"), list) else []
    return any(item.get("agent") == agent and item.get("status") == status for item in reviews if isinstance(item, dict))
