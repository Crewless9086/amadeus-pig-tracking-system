# CHARLIE Mission Loop Goals

Machine-checkable goals belong here. They are used to keep long-running mission-loop work honest without adding model spend.

Initial goals:

- `scripts/verify_mission.ps1` exists and passes for scoped foundation changes.
- `loop/memory/trust.tsv` exists with the required trust columns.
- `loop/memory/budget.json` exists and disables live model API usage by default.
- `docs/00-start-here/NEXT_STEPS.md` exists.
- No `.env` or secrets are staged.
- No migrations run without owner approval.

Later phases may add small goal files that a script can evaluate directly.

