# Amadeus

Open **`C:\Amadeus\repo`** for everyday project work. From that checkout run:

```powershell
python -B scripts/check_workspace.py --root C:\Amadeus\repo
```

Follow [AGENTS.md](AGENTS.md), the
[active authority map](docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md)
and the [current register](docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md).
The register names the sole coordinator, current work, holds and next gate.

The [1 October shared status](docs/06-operations/receipts/20261001/HERDMASTER_SHARED_STATUS.md)
records the HERDMASTER work and its acceptance limits. PR1364 is merged at
`9bef22336a98fa92f5ee2a419ab4cbafc781c163`; that web revision was verified live
on 1 October. Six deployed question readers passed the 30 September checks and
one genuine protected mortality journey is proven. Retained follow-up repair
and fresh Telegram acceptance remain open. Full agent autonomy is not proven.
ROOTLINE is the next proposed focus after HERDMASTER readiness.

Local cleanup is verified and all original eighteen commits were integrated by
[PR1341](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/1341).
The protected merge is `3e77d3434b071078a41917a68fa63f2fa7b314ec`.
Temporary work and output belong in `C:\Amadeus\.runtime`; recovery belongs in
`C:\Amadeus\recovery\20260919`. Preserved history is not permission to delete
or restart old runtimes.

The daily checkout retains local coordination history on its documentation
branch. Use fetched `origin/main` or the registered application worktree for
released-source review. Do not publish the accumulated coordination branch
wholesale. Shared status is a dated checkpoint, not a live fleet dashboard.

Use the [workspace lifecycle rules](docs/09-vault-brain/00-governance/DOCUMENT_LIFECYCLE_AND_LEGACY_RETIREMENT_STANDARD.md);
add `--require-clean` to the guard at closeout. Keep secrets out of Git.
