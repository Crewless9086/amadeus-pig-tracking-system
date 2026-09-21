# Amadeus

Open **`C:\Amadeus\repo`** for everyday project work. From that checkout run:

```powershell
python -B scripts/check_workspace.py --root C:\Amadeus\repo
```

Follow [AGENTS.md](AGENTS.md), the
[active authority map](docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md)
and the [current register](docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md).
The register names the sole coordinator, current work, holds and next gate.

The final old checkout has been moved to recovery and its full preservation
audit passed. **Local cleanup is verified; admission repair PR1342 is merged and live.**
The [current integration receipt](docs/06-operations/receipts/20260921/CONSOLIDATION_ADMISSION_REPAIR.md)
records the verified repair release and the remaining paused mission transition
required before integrating consolidation PR1341.
Docker/n8n were unavailable at the September 20 post-restart check; historical
health results must not be treated as current service health.
Temporary work and output belong in `C:\Amadeus\.runtime`; recovery belongs in
`C:\Amadeus\recovery\20260919`.

Keep `codex/workspace-consolidation-20260919` current until governed review and
integration. These local changes are unreleased; new worktrees from
`origin/main` do not yet contain them. The saved project and current cleanup
task both use this checkout. No operational continuation or release follows
from local cleanup.

Use the [workspace lifecycle rules](docs/09-vault-brain/00-governance/DOCUMENT_LIFECYCLE_AND_LEGACY_RETIREMENT_STANDARD.md);
add `--require-clean` to the guard at closeout. Keep secrets out of Git.
