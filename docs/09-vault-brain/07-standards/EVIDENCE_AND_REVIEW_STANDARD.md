# Evidence And Review Standard

Nothing is done because code was written. Review-ready means the owner can see what changed, why it works, what remains risky, and what decision is needed.

## Minimum Review Packet

Every build review must include:

- mission id and title;
- original owner request;
- desired outcome;
- scope completed;
- files changed;
- branch and commit SHA;
- PR/diff link when applicable;
- tests run;
- pass/fail result;
- known bugs and risks;
- screenshots or visual evidence for UI work;
- migration/data-write statement;
- unsafe-action proof;
- owner decision needed;
- next action.

## UI Evidence

For dashboards and owner review surfaces:

- show actual screen or local/live preview;
- verify critical buttons are visible;
- verify cards do not hide owner decisions;
- verify no overflow/overspill breaks layout;
- verify text wraps;
- verify empty/loading/error states;
- verify actions give feedback.

Generated fallback screenshots must be labelled as generated packets, not live screenshots.

## Test Evidence

Test evidence must include exact commands and results.

For PR-backed missions it must also include the expected PR head SHA and the exact tested SHA. Tests from a base branch, stale branch, or different PR are not evidence for the current mission.

"Looks good" is not evidence.

## Release Evidence

Release/merge/deploy review must include:

- clean branch status;
- staged file list;
- tests;
- merge/PR status;
- deploy target;
- live verification URL;
- post-deploy check result.

Render deploy assumptions must be verified. Local runner status must not be confused with Render state.

## Send-Back Evidence

When owner sends a mission back:

- preserve owner comments;
- preserve previous review packet;
- record target return stage;
- keep mission audit trail;
- show what changed on the next review attempt.

## Review Quality Rule

A review packet is weak if the owner cannot answer these quickly:

- What changed?
- Why was it needed?
- What proof exists?
- What is still risky?
- What decision is being requested?
- What happens if I approve it?

If those answers are missing, Brain Guard should block review-ready status.

Brain Guard blocking means internal evidence repair unless the packet identifies an explicit owner decision or red-zone approval. Environment failures, branch conflicts, stale revisions, missing evidence, and unrelated findings must not be presented as owner decisions.
