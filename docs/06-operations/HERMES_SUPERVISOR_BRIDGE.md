# Hermes CHARLIE Supervisor Bridge

Status: source-stage commissioning; not deployed and not operationally proven.

Canonical mission: `CMQ-20260813-05-SLACK-GATEWAY`, under root `CMQ-20260813-05`.

## Boundary

Hermes is the always-on supervisor and Slack edge. Cursor Cloud is the admitted
repository writer. Supabase `charlie_missions` and `operational_events` remain
canonical. Slack and Hermes Kanban are mirrors, never queues or sources of truth.

Hermes receives only bounded tools declared in
`integrations/hermes/charlie_builder/plugin.json`. It receives no GitHub write
credential, raw database credential, signing authority, arbitrary shell, merge,
deployment, customer, farm, payment, printer, irrigation, or hardware authority.

## Deterministic loop

1. Verify the Slack signature and exact owner user ID.
2. Reconcile the Slack event idempotently through authenticated CHARLIE APIs.
3. Read current mission generation and externally issued Mission Admission.
4. Dispatch one Cursor Cloud Agent using `<mission_id>:<generation>`.
5. Persist Agent/run/thread/branch/PR/head linkage canonically.
6. Poll Agent/run/PR/check/review state without an LLM.
7. Route `SEND_BACK` to the same idle Agent, with at most two failed attempts.
8. Put only a green, independently approved exact candidate in
   `#owner-approvals`; never merge or deploy.

## Protected configuration

Hermes Cloud must protect `CURSOR_API_KEY`, `SLACK_SIGNING_SECRET`,
`SLACK_BOT_TOKEN`, `CHARLIE_SLACK_OWNER_USER_ID`, `CHARLIE_CANONICAL_API_URL`,
and a least-privilege CHARLIE API token. Values must never enter Git, Slack,
mission rows, PR metadata, artifacts, logs, or Kanban task text.

## Remaining operational gates

- exact Cursor Cloud API key authorization;
- Slack app installation and exact channel/user IDs;
- reviewed PR merge;
- exact Hermes protected configuration/deployment approval;
- a terminal-independent Slack-to-Cursor pilot including one `SEND_BACK`.
