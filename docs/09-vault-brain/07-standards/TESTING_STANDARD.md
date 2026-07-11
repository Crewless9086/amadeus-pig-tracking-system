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

## Regression Pressure

For live operational paths, include at least one failure/edge case where practical:

- backend guard failure;
- missing required field;
- stale state;
- duplicate submission;
- partial/no-match result;
- service unavailable or not configured;
- user sends vague/short input.

## Timeout Handling

Timeouts are evidence, not automatic pass or automatic fail. A broad CHARLIE runner or full-suite timeout may be treated as advisory only when focused tests for the changed safety surface pass and the timeout has no direct owner/customer/order/stock risk.

Real safety failures still block even if they appear beside timeout noise. Customer sends, Chatwoot writes, order/quote execution, stock reservation, production data writes, migrations, payments, public posts, farm lifecycle changes, auth failures, and source-of-truth failures must not be downgraded to advisory because another command timed out.

## Source References

- `docs/06-operations/TESTING_CHECKLIST.md`
- `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`
