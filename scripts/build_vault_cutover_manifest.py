"""Build and validate the owner-review Vault physical-cutover manifest.

This script is intentionally non-destructive. It inventories tracked Markdown
and MDX files and writes review artifacts; it never moves or deletes sources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = REPO_ROOT / "docs/09-vault-brain/10-source-map/VAULT_MIGRATION_INVENTORY.md"
JSON_PATH = REPO_ROOT / "docs/09-vault-brain/10-source-map/VAULT_PHYSICAL_CUTOVER_MANIFEST.json"
MARKDOWN_PATH = REPO_ROOT / "docs/09-vault-brain/10-source-map/VAULT_PHYSICAL_CUTOVER_MANIFEST.md"
GENERATED_REPORT_PATH = "docs/09-vault-brain/10-source-map/VAULT_PHYSICAL_CUTOVER_MANIFEST.md"
GENERATED_JSON_PATH = "docs/09-vault-brain/10-source-map/VAULT_PHYSICAL_CUTOVER_MANIFEST.json"
REFERENCE_INDEX_EXCLUSIONS = {
    "docs/09-vault-brain/10-source-map/VAULT_MIGRATION_INVENTORY.md",
    GENERATED_REPORT_PATH,
    GENERATED_JSON_PATH,
}

MANIFEST_VERSION = "vault_physical_cutover_manifest_v23"
BASELINE = "a79085afdfeded06c329caa1ea079013d1bb10f3"

BATCH9_COMPATIBILITY_POINTERS = {
    "docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md",
    "docs/00-start-here/GLOSSARY.md",
    "docs/00-start-here/HOW_WE_WORK.md",
    "docs/00-start-here/PROJECT_OVERVIEW.md",
    "docs/00-start-here/README.md",
    "docs/00-start-here/WORKFLOW.md",
    "docs/07-decisions/README.md",
}

BATCH10_COMPATIBILITY_POINTERS = {
    "CLAUDE.md",
    "docs/00-start-here/AGENT_ASSET_REGISTER.md",
    "docs/00-start-here/AGENT_PORTFOLIO_STATUS.md",
    "docs/00-start-here/OPERATING_STATUS.md",
    "docs/00-start-here/OWNER_INBOX_GUIDE.md",
}

BATCH11_COMPATIBILITY_POINTERS = {
    "docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md",
    "docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md",
    "docs/00-start-here/DEPLOYMENT_SOP.md",
}

BATCH12_COMPATIBILITY_POINTERS = {
    "docs/00-start-here/CURRENT_STATE.md",
    "docs/00-start-here/NEXT_STEPS.md",
}

BATCH13_COMPATIBILITY_POINTERS = {
    "docs/00-start-here/PRODUCT_VISION.md",
}

BATCH15_GENERATED_PROJECTIONS = {
    f"static/assets/agents/{agent}/agent.md"
    for agent in (
        "beacon", "butcher", "gatekeeper", "herdmaster", "ledger",
        "oom-sakkie", "quartermaster", "rootline", "sam",
    )
}

BATCH26_TECHNICAL_SCRATCHPADS = {
    "planning/CODEX_CHAT.md",
    "planning/ToDoList.md",
}

REMAINING_PHYSICAL_DISPOSITIONS = {
    "EXTRACT_THEN_ARCHIVE",
    "SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY",
    "RECONCILE_GENERATED_PROJECTION",
}


def _planned_batch(path: str, disposition: str) -> tuple[int | None, str | None]:
    """Assign every remaining physical item to one collision-bounded batch."""
    if disposition not in REMAINING_PHYSICAL_DISPOSITIONS:
        return None, None
    if path.startswith("static/assets/agents/"):
        return 15, "generated_agent_projections"
    if path.startswith("planning/storyworks/"):
        return 27, "storyworks"
    if path.startswith("planning/"):
        return 26, "planning_and_inbox"
    if path.startswith("docs/08-business-modules/"):
        return 25, "business_modules"
    if path.startswith("docs/07-decisions/") or path == "docs/MIGRATION_INDEX.md":
        return 16, "decisions_and_migration_index"
    if re.search(r"/(GS_MIG_|GOOGLE_SHEETS_)", path):
        return 17, "sheets_migration"
    if "/HERDMASTER_" in path:
        return 21, "herdmaster"
    if "/OOM_SAKKIE_" in path:
        return 22, "oom_sakkie"
    if "/ROOTLINE_" in path:
        return 23, "rootline"
    if "/SAM_" in path:
        return 24, "sam_revenue"
    if "/CMQ_" in path:
        return 18, "core_missions"
    if re.search(r"/(CHARLIE_|CORE_PROVIDER_|MISSION_LOOP_|AGENTIC_|BUILD_RELAY)", path):
        return 19, "core_operating_spine"
    return 20, "general_operations"

CURRENT_EXTERNAL_TECHNICAL_REFERENCES = {
    "external_sources/AMADEUS_HALF_CARCASS_CUTTING_STANDARD_v1.0.md",
    "external_sources/README.md",
    "external_sources/telemetry/forecast/amadeus-forecast-logger/README.md",
    "external_sources/telemetry/sunsynk/amadeus-sunsynk-logger/README.md",
}

CONTROLLING_EXCEPTIONS = {
    "docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md",
    "docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md",
}

CURRENT_STATE_FILES = {
    "docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md",
    "docs/06-operations/GENERAL_TERMINAL_INTAKE_CONTRACT.md",
}

ALLOWED_DISPOSITIONS = {
    "KEEP_VAULT",
    "KEEP_CONTROLLING_EXCEPTION",
    "KEEP_CURRENT_STATE",
    "KEEP_TECHNICAL",
    "KEEP_POINTER",
    "KEEP_GENERATED_PROJECTION",
    "KEEP_TRANSITIONAL",
    "KEEP_ARCHIVE",
    "RECONCILE_GENERATED_PROJECTION",
    "POINTER_AFTER_RECONCILIATION",
    "EXTRACT_THEN_ARCHIVE",
    "SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY",
    "ARCHIVE_CANDIDATE",
    "DELETE_CANDIDATE",
    "OWNER_REVIEW_REQUIRED",
}

LEDGER_RE = re.compile(
    r"^\| `(?P<path>[^`]+)` \| (?P<lines>\d+) \| `(?P<sha>[^`]+)` \| "
    r"`(?P<signal>[^`]*)` \| `(?P<lifecycle>[^`]*)` \| `(?P<action>[^`]*)` \| "
    r"(?P<refs>\d+) \| (?P<duplicate>[^|]+) \| (?P<rationale>.+) \|$"
)


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", *args],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def _tracked_docs() -> list[str]:
    output = _git("ls-files", "*.md", "*.mdx")
    return sorted(
        path
        for line in output.splitlines()
        if line.strip()
        for path in [line.replace("\\", "/")]
        if path != GENERATED_REPORT_PATH
    )


def _inventory_rows() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    generated = False
    for line in INVENTORY_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip() == "<!-- BATCH1_GENERATED_START -->":
            generated = True
            continue
        if not generated:
            continue
        match = LEDGER_RE.match(line)
        if not match:
            continue
        row = match.groupdict()
        row["lines"] = int(row["lines"])
        row["refs"] = int(row["refs"])
        rows[row["path"]] = row
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _physical_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _tracked_text_corpus() -> dict[str, str]:
    corpus = {}
    for relative in _git("ls-files").splitlines():
        relative = relative.replace("\\", "/")
        if not relative or relative in REFERENCE_INDEX_EXCLUSIONS:
            continue
        source = REPO_ROOT / relative
        try:
            corpus[relative] = source.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    return corpus


def _exact_references(path: str, documents: dict[str, str]) -> list[str]:
    needle = path.replace("\\", "/")
    return sorted(
        candidate
        for candidate, text in documents.items()
        if candidate != path and needle in text.replace("\\", "/")
    )


def _vault_target(path: str) -> str:
    lower = path.lower()
    name = Path(path).name
    if path.startswith("docs/00-start-here/"):
        if "DEPLOY" in name:
            return "docs/09-vault-brain/07-standards/DEPLOYMENT_STANDARD.md"
        if "MISSION" in name or "CORE" in name:
            return "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md"
        return "docs/09-vault-brain/README.md"
    if path.startswith("docs/05-ai/agents/beacon/"):
        return "docs/09-vault-brain/02-agents/marketing/BEACON.md"
    if path.startswith("docs/05-ai/agents/sam/"):
        return "docs/09-vault-brain/02-agents/sales/SAM.md"
    if path.startswith("docs/05-ai/"):
        return "docs/09-vault-brain/02-agents/AGENT_REGISTRY.md"
    if path.startswith("docs/08-business-modules/"):
        return (
            "docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md"
            if any(term in lower for term in ("meat", "pork"))
            else "docs/09-vault-brain/03-business/AMADEUS_FARM.md"
        )
    if path.startswith("static/assets/agents/"):
        agent = path.split("/")[3]
        mapping = {
            "beacon": "docs/09-vault-brain/02-agents/marketing/BEACON.md",
            "butcher": "docs/09-vault-brain/02-agents/sales/BUTCHER.md",
            "gatekeeper": "docs/09-vault-brain/02-agents/farm/GATEKEEPER.md",
            "herdmaster": "docs/09-vault-brain/02-agents/farm/HERDMASTER.md",
            "ledger": "docs/09-vault-brain/02-agents/sales/LEDGER.md",
            "oom-sakkie": "docs/09-vault-brain/02-agents/farm/OOM_SAKKIE.md",
            "quartermaster": "docs/09-vault-brain/02-agents/farm/QUARTERMASTER.md",
            "rootline": "docs/09-vault-brain/02-agents/farm/ROOTLINE.md",
            "sam": "docs/09-vault-brain/02-agents/sales/SAM.md",
        }
        return mapping.get(agent, "docs/09-vault-brain/02-agents/AGENT_REGISTRY.md")
    if path.startswith("planning/"):
        return "docs/09-vault-brain/00-governance/OPEN_QUESTIONS.md"
    if path.startswith("docs/06-operations/"):
        return "docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md"
    if path.startswith("docs/01-architecture/"):
        return "docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md"
    return "docs/09-vault-brain/README.md"


def _archive_target(path: str) -> str:
    return f"docs/99-archive/vault-cutover/{path}"


def _disposition(path: str, row: dict | None, exact_refs: list[str], lines: int) -> tuple[str, str, str, list[str]]:
    if path.startswith("docs/09-vault-brain/"):
        return "KEEP_VAULT", path, "canonical Vault doctrine/reference", []
    if path in CONTROLLING_EXCEPTIONS:
        return "KEEP_CONTROLLING_EXCEPTION", path, "registered cross-system controlling exception", []
    if path in CURRENT_STATE_FILES:
        return "KEEP_CURRENT_STATE", path, "durable current-state record; history split is later work", []
    if path in BATCH9_COMPATIBILITY_POINTERS | BATCH10_COMPATIBILITY_POINTERS | BATCH11_COMPATIBILITY_POINTERS | BATCH12_COMPATIBILITY_POINTERS | BATCH13_COMPATIBILITY_POINTERS:
        return "KEEP_POINTER", _vault_target(path), "minimal compatibility pointer; cannot govern agents", []
    if path in BATCH15_GENERATED_PROJECTIONS:
        return "KEEP_GENERATED_PROJECTION", _vault_target(path), "deterministic digest-bound runtime/UI projection from Vault doctrine and asset metadata", []
    if path in BATCH26_TECHNICAL_SCRATCHPADS:
        return "KEEP_TECHNICAL", path, "minimal non-doctrine, non-durable technical scratchpad retained for current tooling", []
    if path == "CLAUDE.md":
        return "POINTER_AFTER_RECONCILIATION", "docs/09-vault-brain/README.md", "obsolete root guidance must become a short Vault pointer after unique developer commands are retained", ["unique_fact_reconciliation_required"]
    if path in {
        "docs/07-decisions/ADR_0001_DOCUMENTATION_SOURCE_OF_TRUTH.md",
        "docs/07-decisions/ADR_0002_CHARLIE_CORE_TERMINOLOGY_AND_CONFIGURATION.md",
        "docs/MIGRATION_INDEX.md",
    }:
        return "EXTRACT_THEN_ARCHIVE", _archive_target(path), "dated migration/decision evidence; extract accepted facts and archive", ["unique_fact_extraction_required"]
    if path == "docs/07-decisions/README.md":
        return "POINTER_AFTER_RECONCILIATION", "docs/09-vault-brain/00-governance/OWNER_DECISIONS.md", "legacy ADR index becomes a pointer to canonical owner decisions", ["unique_fact_reconciliation_required"]
    if path.startswith("docs/99-archive/"):
        return "KEEP_ARCHIVE", path, "already physically archived", []
    if path in CURRENT_EXTERNAL_TECHNICAL_REFERENCES:
        return "KEEP_TECHNICAL", path, "current external implementation/source evidence; Vault doctrine remains authoritative", []

    action = (row or {}).get("action", "classify_manually")
    lifecycle = (row or {}).get("lifecycle", "review_queue")
    signal = (row or {}).get("signal", "unspecified")
    blockers: list[str] = []

    if action in {"keep_review", "keep_technical_review", "split_doctrine_from_technical"}:
        return "KEEP_TECHNICAL", path, "retain beside implementation; cannot govern agents", []
    if action == "keep_until_exit_test":
        return "KEEP_TRANSITIONAL", path, "runtime dependency requires named retirement exit test", ["exit_test_unproven"]
    if action == "keep_archive":
        return "KEEP_ARCHIVE", path, "historical evidence already belongs in archive", []
    if action == "generate_or_reconcile":
        return "RECONCILE_GENERATED_PROJECTION", _vault_target(path), "replace manual projection from Vault authority", ["projection_generation_unproven"]
    if action == "consolidate_then_pointer_or_delete":
        return "POINTER_AFTER_RECONCILIATION", _vault_target(path), "retain a short pointer only after unique facts reconcile", ["unique_fact_reconciliation_required"]
    if action in {"extract_then_archive_or_delete", "consolidate_then_archive_or_delete"}:
        target = _vault_target(path)
        # Deletion is deliberately rare: only a tiny retired/superseded wrapper,
        # zero exact references, and an exact replacement may qualify.
        if lifecycle in {"retired", "superseded"} and not exact_refs and lines <= 30 and target:
            return "DELETE_CANDIDATE", target, "tiny retired/superseded wrapper with zero exact references", ["owner_approval_required"]
        return "EXTRACT_THEN_ARCHIVE", _archive_target(path), "extract unique durable facts, then preserve dated evidence", ["unique_fact_extraction_required"]
    if action == "split_active_runbook_from_history":
        return "SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY", _archive_target(path), "retain current procedure and archive dated evidence separately", ["runbook_history_split_required"]
    if action == "archive_or_delete_review":
        if lifecycle in {"retired", "superseded"} and not exact_refs and lines <= 30:
            return "DELETE_CANDIDATE", _vault_target(path), "retired/superseded, tiny, unreferenced, exact replacement named", ["owner_approval_required"]
        return "ARCHIVE_CANDIDATE", _archive_target(path), "historical evidence; archive is safer than deletion", ["owner_approval_required"]
    if path.startswith("static/assets/agents/"):
        return "RECONCILE_GENERATED_PROJECTION", _vault_target(path), "manual runtime projection must be derived from Vault", ["projection_generation_unproven"]
    return "OWNER_REVIEW_REQUIRED", _vault_target(path), f"no safe deterministic conclusion ({signal}/{lifecycle})", ["owner_classification_required"]


def build_manifest() -> dict:
    tracked = _tracked_docs()
    inventory = _inventory_rows()
    documents = _tracked_text_corpus()
    entries = []
    for path in tracked:
        source = REPO_ROOT / path
        row = inventory.get(path)
        refs = _exact_references(path, documents)
        lines = _physical_lines(source)
        disposition, destination, reason, blockers = _disposition(path, row, refs, lines)
        planned_batch, reconciliation_family = _planned_batch(path, disposition)
        entries.append(
            {
                "path": path,
                "sha256": _sha256(source),
                "physical_lines": lines,
                "batch1_lifecycle": (row or {}).get("lifecycle", "post_batch1_unclassified"),
                "batch1_action": (row or {}).get("action", "post_batch1_unclassified"),
                "disposition": disposition,
                "destination_or_replacement": destination,
                "exact_reference_count": len(refs),
                "exact_references": refs,
                "reason": reason,
                "blockers": blockers,
                "physical_change_authorized": False,
                "planned_batch": planned_batch,
                "reconciliation_family": reconciliation_family,
            }
        )
    counts = Counter(entry["disposition"] for entry in entries)
    return {
        "version": MANIFEST_VERSION,
        "baseline": BASELINE,
        "generated_from_head": BASELINE,
        "owner_boundary": "Batch 26 archives eight historical planning/inbox sources intact, retains only minimal non-doctrine CODEX_CHAT and ToDoList compatibility scratchpads, and routes durable mission, CORE and SAM authority to focused Vault/register sources; it authorizes no mission execution, runtime, customer, provider, farm, database or hardware change",
        "entry_count": len(entries),
        "counts": dict(sorted(counts.items())),
        "entries": entries,
    }


def validate_manifest(manifest: dict) -> list[str]:
    findings = []
    tracked = _tracked_docs()
    entries = manifest.get("entries", [])
    paths = [entry.get("path") for entry in entries]
    if paths != sorted(set(paths)):
        findings.append("manifest paths are duplicated or not sorted")
    if paths != tracked:
        findings.append("manifest does not cover every tracked Markdown/MDX file exactly once")
    if manifest.get("entry_count") != len(tracked):
        findings.append("entry_count does not match tracked document count")
    for entry in entries:
        path = entry["path"]
        source = REPO_ROOT / path
        if not source.is_file():
            findings.append(f"source missing during manifest-only batch: {path}")
            continue
        if entry.get("sha256") != _sha256(source):
            findings.append(f"stale source digest: {path}")
        if entry.get("disposition") not in ALLOWED_DISPOSITIONS:
            findings.append(f"unknown disposition: {path}")
        if entry.get("physical_change_authorized") is not False:
            findings.append(f"physical change accidentally authorized: {path}")
        if entry.get("disposition") == "DELETE_CANDIDATE":
            if entry.get("exact_reference_count") != 0:
                findings.append(f"delete candidate still has exact references: {path}")
            if not entry.get("destination_or_replacement"):
                findings.append(f"delete candidate lacks exact replacement: {path}")
            if "owner_approval_required" not in entry.get("blockers", []):
                findings.append(f"delete candidate lacks owner gate: {path}")
        if entry.get("disposition") == "KEEP_TRANSITIONAL" and "exit_test_unproven" not in entry.get("blockers", []):
            findings.append(f"transitional file lacks exit-test blocker: {path}")
        if entry.get("disposition") in REMAINING_PHYSICAL_DISPOSITIONS:
            if not isinstance(entry.get("planned_batch"), int) or not entry.get("reconciliation_family"):
                findings.append(f"remaining physical item lacks a planned batch: {path}")
        elif entry.get("planned_batch") is not None or entry.get("reconciliation_family") is not None:
            findings.append(f"non-physical item received a physical batch: {path}")
    return findings


def _markdown(manifest: dict, findings: list[str]) -> str:
    lines = [
        "# Vault Physical Cutover Manifest",
        "",
        "Status: Batch 26 planning/inbox reconciliation complete; no further physical change authorized.",
        "",
        f"Version: `{manifest['version']}`",
        f"Baseline: `{manifest['baseline']}`",
        f"Generated from HEAD: `{manifest['generated_from_head']}`",
        f"Tracked Markdown/MDX files covered: **{manifest['entry_count']}**",
        f"Validation: **{'PASS' if not findings else 'BLOCKED'}**",
        "",
        "This manifest records completed Batches 5 through 24 and schedules later",
        "dispositions only. It does not authorize another move, archive, deletion, pointer",
        "rewrite, deployment, runtime action or production change. Every remaining entry",
        "keeps `physical_change_authorized: false`.",
        "",
        "## Disposition totals",
        "",
        "| Disposition | Count |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{key}` | {value} |" for key, value in manifest["counts"].items())
    schedule_counts = Counter(
        (entry["planned_batch"], entry["reconciliation_family"])
        for entry in manifest["entries"]
        if entry["planned_batch"] is not None
    )
    lines.extend([
        "",
        "## Remaining execution schedule",
        "",
        "The remaining 52 physical-reconciliation entries are assigned",
        "to exactly one of Batches 25 through 27. Batch 28 owns the 72 transitional",
        "exit-test decisions; Batch 29 owns deployed Brain Guard acceptance.",
        "This schedule is an ordering contract, not physical-change authority.",
        "",
        "| Batch | Family | Entries |",
        "| ---: | --- | ---: |",
        "| 15 | `generated_agent_projections` | COMPLETE (9) |",
        "| 16 | `decisions_and_migration_index` | COMPLETE (3) |",
        "| 17 | `sheets_migration` | COMPLETE (12) |",
        "| 18 | `core_missions` | COMPLETE (10) |",
        "| 19 | `core_operating_spine` | COMPLETE (18) |",
        "| 20 | `general_operations` | COMPLETE (16) |",
        "| 21 | `herdmaster` | COMPLETE (22) |",
        "| 22 | `oom_sakkie` | COMPLETE (30) |",
        "| 23 | `rootline` | COMPLETE (13) |",
        "| 24 | `sam_revenue` | COMPLETE (5) |",
    ])
    lines.extend(
        f"| {batch} | `{family}` | {count} |"
        for (batch, family), count in sorted(schedule_counts.items())
    )
    lines.extend([
        "| 28 | `transitional_exit_tests` | 72 |",
        "| 29 | `deployed_brain_guard_acceptance` | operational proof |",
    ])
    lines.extend([
        "",
        "## Safety gates",
        "",
        "- Transitional n8n and Google Sheets references remain until their named exit tests pass.",
        "- Historical evidence defaults to archive, not deletion.",
        "- A delete candidate requires zero exact path references, an exact replacement, a tiny retired/superseded source, and later owner approval.",
        "- Pointer conversion requires unique-fact reconciliation first.",
        "- Static agent cards require a proven generated projection before replacement.",
        "- All nine reconciled `docs/05-ai` files are now preserved intact in the archive.",
        "- The two superseded external UI briefs are preserved intact in the archive.",
        "- The four remaining external candidates are retained as current technical/source evidence; the archive-candidate queue is empty.",
        "- Seven legacy navigation/process paths are minimal non-doctrine compatibility pointers to the Vault.",
        "- Five root/status/navigation paths are minimal non-doctrine compatibility pointers with required technical facts retained.",
        "- Three legacy runner/mission/deployment paths are compatibility pointers after current procedures were consolidated into focused Vault files.",
        "- Two stale current-state/roadmap projections are compatibility pointers to the durable register and Vault mission workflow.",
        "- The final legacy product-vision projection is a compatibility pointer after durable Oom Sakkie experience rules moved into focused Vault files.",
        "- Two dated ADR wrappers and the completed legacy migration index are archived after their durable facts were reconciled into focused Vault governance, CORE identity and deployment standards.",
        "- Twelve Google Sheets migration plans/reports are archived intact after current migration, conflict-quarantine, Supabase-first fallback and fallback-retirement rules moved into focused Vault files.",
        "- Sixteen general-operations plans, evidence/checklist ledgers, configuration migrations and placeholder runbooks are archived intact after current rules moved into focused Vault files.",
        "- No later physical change is authorized by this regenerated manifest.",
        "",
        "## Exact non-keep review queue",
        "",
        "The machine-readable JSON contains every tracked source document (the generated",
        "Markdown report excludes itself). This table lists every",
        "entry whose physical disposition needs later work or owner review.",
        "",
        "| Source | Disposition | Planned batch | Destination / replacement | Exact refs | Blockers |",
        "| --- | --- | ---: | --- | ---: | --- |",
    ])
    for entry in manifest["entries"]:
        if entry["disposition"].startswith("KEEP_"):
            continue
        blockers = ", ".join(entry["blockers"]) or "none"
        lines.append(
            f"| `{entry['path']}` | `{entry['disposition']}` | {entry['planned_batch'] or '-'} | "
            f"`{entry['destination_or_replacement']}` | {entry['exact_reference_count']} | {blockers} |"
        )
    lines.extend(["", "## Validation findings", ""])
    if findings:
        lines.extend(f"- {finding}" for finding in findings)
    else:
        lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate committed artifacts without rewriting")
    args = parser.parse_args()
    manifest = build_manifest()
    findings = validate_manifest(manifest)
    rendered_json = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    rendered_markdown = _markdown(manifest, findings)
    if args.check:
        if not JSON_PATH.is_file() or JSON_PATH.read_text(encoding="utf-8") != rendered_json:
            findings.append("JSON manifest is missing or stale")
        if not MARKDOWN_PATH.is_file() or MARKDOWN_PATH.read_text(encoding="utf-8") != rendered_markdown:
            findings.append("Markdown manifest is missing or stale")
    else:
        JSON_PATH.write_text(rendered_json, encoding="utf-8", newline="\n")
        MARKDOWN_PATH.write_text(rendered_markdown, encoding="utf-8", newline="\n")
    print(json.dumps({"passed": not findings, "entry_count": manifest["entry_count"], "counts": manifest["counts"], "findings": findings}, indent=2))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
