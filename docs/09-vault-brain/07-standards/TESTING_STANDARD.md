# Testing Standard

Test evidence must include exact commands and results.

Acceptable examples:

- `node --check ...`
- focused Python unit tests;
- smoke scripts;
- Playwright/screenshots when visual behavior matters.

"Looks good" is not evidence.

## Minimum Bar

Every mission must define the affected surface before testing:

- backend/API;
- frontend/UI;
- n8n/workflow;
- Google Sheets/Supabase/data;
- Telegram/Chatwoot/customer path;
- docs-only;
- agent/prompt behavior.

Test only what matters, but test the thing that can actually break.

## Required Evidence Shape

Record:

- exact command;
- pass/fail result;
- relevant output summary;
- what the test proves;
- what it does not prove;
- any skipped test and reason.

## Final Reviewer Evidence

When a reviewer recommends final release approval, at least one test-evidence
entry must be structured with the executable command and an explicit passing
status. Prose-only claims are insufficient. Any recorded selector, discovery,
or error output (including `AttributeError`) blocks approval even when another
test entry passes.

## Regression Pressure

For live operational paths, include at least one failure/edge case where practical:

- backend guard failure;
- missing required field;
- stale state;
- duplicate submission;
- partial/no-match result;
- service unavailable or not configured;
- user sends vague/short input.

For operational write paths, pressure tests must also prove the submitted,
accepted, processed, succeeded, skipped/duplicate, blocked and failed counts;
every row or item needs attributable status. Partial completion must never be
reported as plain success. Retry tests use one durable operation identity and
must not repeat successful effects.

For data cutovers, test reads and writes separately. A successful schema,
import, comparison or read endpoint does not prove that a write route, fallback
retirement or scheduler is ready. Current production acceptance needs fresh
route/provider evidence, not a dated checklist result.

For lifecycle and order paths, include terminal-state guards, duplicate active
membership, reservation release, incomplete availability, stale/missing
evidence and repeated submission. Formula or projection stores must not be
edited to conceal a source or backend defect.

## Source Reference

- `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`
