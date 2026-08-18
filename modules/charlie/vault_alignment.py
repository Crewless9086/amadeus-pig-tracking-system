"""Deterministic Vault/agent alignment checks used by Brain Guard and CI."""

from __future__ import annotations

import re
from pathlib import Path

from modules.charlie.vault_retrieval import COMMON_MANDATORY_DOCS, MANDATORY_MISSION_PACKS
from modules.charlie.agent_card_projection import projection_findings


REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_CURRENT_DOCS = (
    "docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md",
    "docs/09-vault-brain/00-governance/CONTROL_TOWER_ASSESSMENT_AND_DISPATCH_PROTOCOL.md",
    "docs/09-vault-brain/00-governance/DOCUMENT_LIFECYCLE_AND_LEGACY_RETIREMENT_STANDARD.md",
    "docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md",
    "docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md",
    "docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md",
    "docs/06-operations/GENERAL_TERMINAL_INTAKE_CONTRACT.md",
    "docs/00-start-here/CURRENT_STATE.md",
    "docs/00-start-here/NEXT_STEPS.md",
)

PRINCIPAL_AGENT_DOCS = {
    "charlie": "docs/09-vault-brain/02-agents/owner-command/CHARLIE.md",
    "oom_sakkie": "docs/09-vault-brain/02-agents/farm/OOM_SAKKIE.md",
    "rootline": "docs/09-vault-brain/02-agents/farm/ROOTLINE.md",
    "herdmaster": "docs/09-vault-brain/02-agents/farm/HERDMASTER.md",
    "sam": "docs/09-vault-brain/02-agents/sales/SAM.md",
    "beacon": "docs/09-vault-brain/02-agents/marketing/BEACON.md",
}

REQUIRED_MARKERS = {
    "docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md": (
        "## Continuous Operations Acceptance Gate",
        "A daily brief is a summary projection",
        "INCOMPLETE_HANDOFF",
    ),
    "docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md": (
        "## 2026-08-17 Continuous Agent Operations Reset",
        "CORE operating spine",
        "Continuous farm management spine",
        "Revenue operating spine",
    ),
    "docs/00-start-here/CURRENT_STATE.md": (
        "POINTER_ONLY / NON_DOCTRINE",
        "CONTROL_TOWER_MISSION_REGISTER.md",
    ),
    "docs/00-start-here/NEXT_STEPS.md": (
        "POINTER_ONLY / NON_DOCTRINE",
        "P0 compatibility fallback",
    ),
    "docs/09-vault-brain/02-agents/AGENT_REGISTRY.md": (
        "Continuous Operations Acceptance Gate",
        "continuous manager loop not proven",
        "customer dispatch authority disabled",
    ),
}

AUTHORITY_ROUTING_MARKERS = {
    "docs/09-vault-brain/README.md": (
        "## Single-Authority Rule",
        "## Mandatory Mission Packs",
    ),
    "docs/09-vault-brain/00-governance/BRAIN_GUARD.md": (
        "## Batch 2 Authority-Routing Gate",
        "AMADEUS_FARM_UI_FACELIFT_STANDARD.md",
        "BEACON_LIVE_STOCK_AWARENESS_WORKFLOW.md",
    ),
    "docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md": (
        "## Common Mandatory Governance Pack",
        "## Deterministic Agent Packs",
        "## Authority Classes And Cutover Disposition",
    ),
}


def evaluate_vault_alignment(repo_root: Path | str | None = None) -> dict:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    findings: list[str] = []
    checked: list[str] = []

    for relative in REQUIRED_CURRENT_DOCS:
        path = root / relative
        checked.append(relative)
        if not path.is_file():
            findings.append(f"required current document missing: {relative}")

    for agent, relative in PRINCIPAL_AGENT_DOCS.items():
        path = root / relative
        checked.append(relative)
        text = _read(path)
        expected = "## Continuous Manager Contract" if agent == "oom_sakkie" else "## Continuous Operating Contract"
        if expected not in text:
            findings.append(f"principal agent lacks continuous contract: {agent} -> {relative}")
        for marker in ("Current honest state", "continuous"):
            if marker.lower() not in text.lower():
                findings.append(f"principal agent lacks {marker!r}: {agent} -> {relative}")

    for relative, markers in REQUIRED_MARKERS.items():
        path = root / relative
        checked.append(relative)
        text = _read(path)
        for marker in markers:
            if marker not in text:
                findings.append(f"required alignment marker missing from {relative}: {marker}")

    for relative, markers in AUTHORITY_ROUTING_MARKERS.items():
        path = root / relative
        checked.append(relative)
        text = _read(path)
        for marker in markers:
            if marker not in text:
                findings.append(f"authority-routing marker missing from {relative}: {marker}")

    active_map_path = root / "docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md"
    checked.append("docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md")
    active_map = _read(active_map_path)
    mandatory_docs = sorted(set(
        COMMON_MANDATORY_DOCS
        + [path for paths in MANDATORY_MISSION_PACKS.values() for path in paths]
    ))
    for relative in mandatory_docs:
        checked.append(relative)
        if not (root / relative).is_file():
            findings.append(f"mandatory mission-pack document missing: {relative}")
        vault_relative = relative.removeprefix("docs/09-vault-brain/")
        if relative not in active_map and f"`{vault_relative}`" not in active_map:
            findings.append(f"mandatory mission-pack document absent from authority map: {relative}")
        if not relative.startswith("docs/09-vault-brain/") and relative not in {
            "docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md",
            "docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md",
        }:
            findings.append(f"unregistered doctrine outside Vault: {relative}")
    for relative in REQUIRED_CURRENT_DOCS:
        if relative not in active_map:
            findings.append(f"current document absent from active source map: {relative}")

    # Some proportional mission tests intentionally construct a minimal Vault
    # fixture without runtime/UI assets. Enforce card integrity whenever the
    # asset surface is present; the full repository audit always contains it.
    if (root / "static/assets/agents").exists():
        projection_issues, projection_files = projection_findings(root)
        findings.extend(projection_issues)
        checked.extend(projection_files)

    current_map = active_map.split("## Archived After Migration", 1)[0]
    for relative in re.findall(r"`((?:docs|modules|scripts|static|templates|tests|config)/[^`]+)`", current_map):
        checked.append(relative)
        exists = any(root.glob(relative)) if any(token in relative for token in "*?[") else (root / relative).exists()
        if not exists:
            findings.append(f"active source map target missing: {relative}")
        if relative.startswith("docs/99-archive/"):
            findings.append(f"archived document exposed as current authority: {relative}")

    return {
        "version": "charlie_vault_alignment_v1",
        "passed": not findings,
        "findings": findings,
        "checked_files": sorted(set(checked)),
    }


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""
