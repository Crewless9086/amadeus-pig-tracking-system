import re
from pathlib import Path

from modules.charlie.core_workflow import AGENT_DOCTRINE_PATHS
from modules.charlie.source_map import implementation_source_packet


REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT_ROOT = REPO_ROOT / "docs" / "09-vault-brain"
VAULT_RETRIEVAL_VERSION = "charlie_vault_retrieval_v1"
OWNER_PREFERENCE_VERSION = "charlie_owner_preferences_v1"

BASE_REQUIRED_DOCS = [
    "docs/09-vault-brain/INDEX.md",
    "docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md",
    "docs/09-vault-brain/00-governance/UPDATE_RULES.md",
    "docs/09-vault-brain/00-governance/BRAIN_GUARD.md",
    "docs/09-vault-brain/01-identity/SYSTEM_HIERARCHY.md",
    "docs/09-vault-brain/01-identity/CHARLIE.md",
    "docs/09-vault-brain/01-identity/CHARLIE_CORE.md",
    "docs/09-vault-brain/02-agents/AGENT_REGISTRY.md",
    "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md",
    "docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md",
    "docs/09-vault-brain/07-standards/TESTING_STANDARD.md",
    "docs/09-vault-brain/09-examples/README.md",
]

TEMPLATE_REQUIRED_DOCS = {
    "software_build": [
        "docs/09-vault-brain/05-playbooks/FEATURE_BUILD.md",
        "docs/09-vault-brain/07-standards/DEPLOYMENT_STANDARD.md",
        "docs/09-vault-brain/07-standards/SECURITY_AND_SECRETS_STANDARD.md",
    ],
    "system_improvement": [
        "docs/09-vault-brain/05-playbooks/AGENT_BUILD.md",
        "docs/09-vault-brain/05-playbooks/LIVE_OPERATIONS_FIX.md",
        "docs/09-vault-brain/07-standards/DEPLOYMENT_STANDARD.md",
    ],
    "business_plan": [
        "docs/09-vault-brain/03-business/README.md",
        "docs/09-vault-brain/05-playbooks/INCOME_STREAM.md",
        "docs/09-vault-brain/08-business-rules/LEGAL_AND_POPIA_REVIEW.md",
    ],
    "content_engine": [
        "docs/09-vault-brain/03-business/BEACON_MARKETING.md",
        "docs/09-vault-brain/05-playbooks/MARKETING_CAMPAIGN.md",
        "docs/09-vault-brain/08-business-rules/MARKETING_RULES.md",
        "docs/09-vault-brain/08-business-rules/MEDIA_PRIVACY_RULES.md",
    ],
    "automation_workflow": [
        "docs/09-vault-brain/04-workflows/N8N_WORKFLOW_SUITE.md",
        "docs/09-vault-brain/05-playbooks/LIVE_OPERATIONS_FIX.md",
        "docs/09-vault-brain/07-standards/SECURITY_AND_SECRETS_STANDARD.md",
    ],
    "income_stream": [
        "docs/09-vault-brain/03-business/MEAT_SALES.md",
        "docs/09-vault-brain/03-business/LIVE_PIG_SALES.md",
        "docs/09-vault-brain/03-business/AMADEUS_PRIVATE_TRANSFERS.md",
        "docs/09-vault-brain/05-playbooks/INCOME_STREAM.md",
        "docs/09-vault-brain/05-playbooks/SAM_MEAT_HUMAN_SALES_PLAYBOOK.md",
        "docs/09-vault-brain/08-business-rules/MEAT_SALES_RULES.md",
        "docs/09-vault-brain/08-business-rules/PAYMENT_RULES.md",
    ],
}

KEYWORD_DOCS = {
    "bulk": ["docs/09-vault-brain/06-data/FARM_DATA_MODEL.md"],
    "weight": ["docs/09-vault-brain/06-data/FARM_DATA_MODEL.md", "docs/09-vault-brain/08-business-rules/FARM_RULES.md"],
    "pig": ["docs/09-vault-brain/06-data/FARM_DATA_MODEL.md", "docs/09-vault-brain/08-business-rules/PIG_PURPOSE_RULES.md"],
    "order": ["docs/09-vault-brain/06-data/ORDER_DATA_MODEL.md", "docs/09-vault-brain/08-business-rules/PAYMENT_RULES.md"],
    "sam": [
        "docs/09-vault-brain/02-agents/sales/SAM.md",
        "docs/09-vault-brain/02-agents/sales/SAM_MEAT_PERSONALITY.md",
        "docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md",
        "docs/09-vault-brain/05-playbooks/SAM_MEAT_HUMAN_SALES_PLAYBOOK.md",
        "docs/09-vault-brain/09-examples/SAM_MEAT_GOLD_STANDARD_REPLIES.md",
    ],
    "meat": [
        "docs/09-vault-brain/03-business/MEAT_SALES.md",
        "docs/09-vault-brain/02-agents/sales/MEAT_SALES_AGENT.md",
        "docs/09-vault-brain/02-agents/sales/SAM_MEAT_PERSONALITY.md",
        "docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md",
        "docs/09-vault-brain/05-playbooks/SAM_MEAT_HUMAN_SALES_PLAYBOOK.md",
        "docs/09-vault-brain/08-business-rules/MEAT_SALES_RULES.md",
        "docs/09-vault-brain/09-examples/SAM_MEAT_GOLD_STANDARD_REPLIES.md",
    ],
    "beacon": ["docs/09-vault-brain/02-agents/marketing/BEACON.md", "docs/09-vault-brain/03-business/BEACON_MARKETING.md"],
    "fred": ["docs/09-vault-brain/02-agents/transport/FRED.md", "docs/09-vault-brain/03-business/AMADEUS_PRIVATE_TRANSFERS.md"],
    "dashboard": ["docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md", "docs/09-vault-brain/09-examples/GOLD_STANDARD_DASHBOARD.md"],
    "ui": ["docs/09-vault-brain/07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md", "docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md"],
    "frontend": ["docs/09-vault-brain/07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md", "docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md"],
    "screenshot": ["docs/09-vault-brain/07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md", "docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md"],
    "blocked": ["docs/09-vault-brain/09-examples/GOLD_STANDARD_RECOVERY_PACKET.md"],
    "recovery": ["docs/09-vault-brain/09-examples/GOLD_STANDARD_RECOVERY_PACKET.md"],
    "artifact": ["docs/09-vault-brain/09-examples/GOLD_STANDARD_REVIEW_PACKET.md", "docs/09-vault-brain/09-examples/GOLD_STANDARD_RECOVERY_PACKET.md"],
    "supabase": ["docs/09-vault-brain/06-data/SUPABASE_CONTRACTS.md", "docs/09-vault-brain/05-playbooks/DATA_MIGRATION.md"],
    "n8n": ["docs/09-vault-brain/04-workflows/N8N_WORKFLOW_SUITE.md"],
    "telegram": ["docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md"],
}

OWNER_PREFERENCES = [
    "Clean structure beats scattered documents or hidden state.",
    "Buttons and owner actions must be visible, reliable, and not overflow.",
    "CHARLIE CORE must cite and update the Vault Brain when workflow, agent, data, business, or review rules change.",
    "Do not present weak UI, missing screenshots, stale evidence, or vague review packets as ready.",
    "Keep CHARLIE distinct from CHARLIE CORE: CHARLIE is the AI command identity; CHARLIE CORE is the workflow system.",
    "Owner approval is mandatory before merge, deploy, customer sends, public posts, payments, reservations, migrations, or farm lifecycle writes.",
]


def retrieve_vault_sources(mission, limit=14, excerpt_chars=900, agent=""):
    mission = mission if isinstance(mission, dict) else {}
    limit = max(1, min(int(limit or 14), 30))
    agent = str(agent or "").strip().lower()
    query = _mission_query(mission)
    tokens = _tokens(query)
    template = _workflow_template(mission)
    agent_docs = _agent_required_docs(agent)
    required = _unique(BASE_REQUIRED_DOCS + agent_docs + TEMPLATE_REQUIRED_DOCS.get(template, []))
    candidates = {path: {"path": path, "reasons": ["required_base_or_template"], "score": 40} for path in required}

    for token, paths in KEYWORD_DOCS.items():
        if token in tokens or token in query.lower():
            for path in paths:
                item = candidates.setdefault(path, {"path": path, "reasons": [], "score": 0})
                item["score"] += 30
                item["reasons"].append(f"keyword:{token}")

    for path in _vault_markdown_files():
        if path in candidates:
            continue
        text = _read_repo_text(path)
        text_tokens = _tokens(path + " " + text[:5000])
        overlap = len(tokens.intersection(text_tokens))
        if overlap:
            candidates[path] = {"path": path, "reasons": [f"token_overlap:{overlap}"], "score": min(25, overlap * 3)}

    ranked = sorted(candidates.values(), key=lambda item: (-item["score"], item["path"]))[:limit]
    for item in ranked:
        text = _read_repo_text(item["path"])
        item["status"] = "loaded" if text else "missing"
        item["excerpt"] = text[:excerpt_chars].strip() if text else ""
    return {
        "version": VAULT_RETRIEVAL_VERSION,
        "query": query,
        "agent": agent,
        "agent_doctrine_docs": agent_docs,
        "workflow_template": template,
        "selected_count": len(ranked),
        "required_docs": required,
        "sources": ranked,
        "implementation_sources": implementation_source_packet(mission),
        "missing_docs": [item["path"] for item in ranked if item["status"] != "loaded"],
        "selection_rule": "base doctrine + workflow template + keyword mapping + local token overlap",
    }


def _agent_required_docs(agent):
    docs = []
    doctrine = AGENT_DOCTRINE_PATHS.get(str(agent or "").strip().lower(), "")
    if doctrine:
        docs.append(doctrine)
    if agent in {"product_architect", "product_reviewer"}:
        docs.extend([
            "docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md",
            "docs/09-vault-brain/07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md",
            "docs/09-vault-brain/09-examples/GOLD_STANDARD_DASHBOARD.md",
        ])
    if agent in {"risk_agent", "qa_red_team", "security_reviewer", "brain_guard", "council_synthesis"}:
        docs.extend([
            "docs/09-vault-brain/00-governance/BRAIN_GUARD.md",
            "docs/09-vault-brain/07-standards/SECURITY_AND_SECRETS_STANDARD.md",
        ])
    if agent in {"evidence_reviewer", "reviewer"}:
        docs.append("docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md")
    if agent in {"business_model_agent", "business_reviewer"}:
        docs.extend([
            "docs/09-vault-brain/03-business/README.md",
            "docs/09-vault-brain/05-playbooks/INCOME_STREAM.md",
        ])
    return _unique(docs)


def owner_preference_packet():
    return {
        "version": OWNER_PREFERENCE_VERSION,
        "owner": "CHARL",
        "preferences": list(OWNER_PREFERENCES),
        "enforcement": [
            "Brain Guard blocks weak Vault usage.",
            "Reviewer must provide owner-visible evidence and action clarity.",
            "UI missions require visual review evidence before owner review.",
        ],
    }


def evaluate_vault_source_coverage(artifacts, retrieval_packet):
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    retrieval_packet = retrieval_packet if isinstance(retrieval_packet, dict) else {}
    required = set(retrieval_packet.get("required_docs") if isinstance(retrieval_packet.get("required_docs"), list) else [])
    selected = {item.get("path") for item in retrieval_packet.get("sources", []) if isinstance(item, dict)}
    cited = set()
    uncited_agents = []
    for agent, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            continue
        sources = set(_artifact_vault_sources(artifact))
        cited.update(sources)
        if not any(source.startswith("docs/09-vault-brain/") for source in sources):
            uncited_agents.append(agent)
    missing_required = sorted(required - cited)
    selected_not_cited = sorted(selected - cited)
    score = 100
    if uncited_agents:
        score -= min(40, len(uncited_agents) * 10)
    if missing_required:
        score -= min(35, len(missing_required) * 4)
    if selected_not_cited:
        score -= min(20, len(selected_not_cited) * 2)
    score = max(0, score)
    return {
        "version": "charlie_vault_source_coverage_v1",
        "score": score,
        "passed": score >= 45 and not uncited_agents and bool(cited.intersection(selected or required)),
        "cited_sources": sorted(cited),
        "uncited_agents": sorted(uncited_agents),
        "missing_required_docs": missing_required,
        "selected_not_cited": selected_not_cited,
    }


def _artifact_vault_sources(artifact):
    sources = []
    for key in ("vault_sources_used", "inputs_used", "files_inspected"):
        value = artifact.get(key)
        if isinstance(value, str):
            sources.append(value)
        elif isinstance(value, list):
            sources.extend(value)
    canonical = artifact.get("canonical") if isinstance(artifact.get("canonical"), dict) else {}
    for key in ("vault_sources_used", "inputs_used", "files_inspected"):
        value = canonical.get(key)
        if isinstance(value, str):
            sources.append(value)
        elif isinstance(value, list):
            sources.extend(value)
    return [str(source or "").strip().replace("\\", "/") for source in sources if str(source or "").strip()]


def autonomy_readiness_packet(command_center=None):
    command_center = command_center if isinstance(command_center, dict) else {}
    checks = {
        "vault_retrieval": True,
        "brain_guard_runtime_gate": True,
        "owner_preferences": True,
        "tool_permissions": True,
        "model_registry": True,
        "learning_loop": bool(command_center.get("improvements")),
        "dashboard_visibility": True,
        "normalized_vault_tables": bool(((command_center.get("vault") or {}).get("health") or {}).get("success")),
        "autonomous_release": False,
        "self_approval": False,
    }
    passed = sum(1 for value in checks.values() if value)
    percent = round((passed / len(checks)) * 100)
    return {
        "version": "charlie_autonomy_readiness_v1",
        "percent": percent,
        "safe_mode": "supervised_missions_only",
        "checks": checks,
        "conclusion": "CHARLIE CORE is stronger for supervised missions, but owner approval remains mandatory for release, money, customers, public output, migrations, and lifecycle writes.",
    }


def _mission_query(mission):
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    pieces = [
        mission.get("mission_type", ""),
        mission.get("title", ""),
        mission.get("raw_text", ""),
        vault.get("problem_statement", ""),
        vault.get("desired_outcome", ""),
        str(metadata.get("owner_comments", "")),
    ]
    return " ".join(str(piece or "") for piece in pieces).strip()


def _workflow_template(mission):
    for source in [
        (mission.get("metadata") or {}).get("charlie_core") if isinstance(mission.get("metadata"), dict) else {},
        mission.get("vault") if isinstance(mission.get("vault"), dict) else {},
    ]:
        project_truth = source.get("project_truth") if isinstance(source, dict) and isinstance(source.get("project_truth"), dict) else {}
        template = str(project_truth.get("workflow_template") or "").strip()
        if template:
            return template
    text = _mission_query(mission).lower()
    if "income" in text or "sales" in text or "fred" in text or "sam" in text:
        return "income_stream"
    if "n8n" in text or "automation" in text:
        return "automation_workflow"
    if "marketing" in text or "beacon" in text or "content" in text:
        return "content_engine"
    if "business" in text or "strategy" in text:
        return "business_plan"
    if "workflow" in text or "runner" in text or "dashboard" in text:
        return "system_improvement"
    return "software_build"


def _vault_markdown_files():
    if not VAULT_ROOT.exists():
        return []
    paths = []
    for path in VAULT_ROOT.rglob("*.md"):
        try:
            relative = path.resolve().relative_to(REPO_ROOT)
        except ValueError:
            continue
        paths.append(str(relative).replace("\\", "/"))
    return sorted(paths)


def _read_repo_text(relative_path):
    path = (REPO_ROOT / str(relative_path or "").replace("\\", "/")).resolve()
    try:
        path.relative_to(REPO_ROOT)
    except ValueError:
        return ""
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _tokens(value):
    return {token for token in re.findall(r"[a-z0-9_]{3,}", str(value or "").lower()) if token not in {"the", "and", "for", "with", "that", "this"}}


def _unique(items):
    result = []
    seen = set()
    for item in items:
        text = str(item or "").replace("\\", "/").strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result
