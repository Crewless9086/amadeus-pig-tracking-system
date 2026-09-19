# Amadeus

Open **`C:\Amadeus\repo`** for everyday project work. From that checkout run:

```powershell
python -B scripts/check_workspace.py --root C:\Amadeus\repo
```

Follow [AGENTS.md](AGENTS.md), the
[active authority map](docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md)
and the [current register](docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md).
The register names the sole coordinator, current work, holds and next gate.

The source workspace and task routing are ready. Approved maintenance cleared
five more folders; **the original OneDrive checkout remains held**.
The [latest cleanup receipt](docs/06-operations/receipts/20260919/MAINTENANCE_CLEANUP_STATUS.md)
records verified recovery, completed removals and exact remaining blockers.
Temporary work and output belong in `C:\Amadeus\.runtime`; recovery belongs in
`C:\Amadeus\recovery\20260919`.

Keep `codex/workspace-consolidation-20260919` current until governed review and
integration. These local changes are unreleased; new worktrees from
`origin/main` do not yet contain them. The saved project and current cleanup
task both use this checkout. No operational continuation or release follows
from local cleanup.

Use the [workspace lifecycle rules](docs/09-vault-brain/00-governance/DOCUMENT_LIFECYCLE_AND_LEGACY_RETIREMENT_STANDARD.md);
add `--require-clean` to the guard at closeout. Keep secrets out of Git.
