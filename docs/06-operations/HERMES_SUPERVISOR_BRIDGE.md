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

The installable Hermes surface is the native `plugin.yaml` plus `register(ctx)`
package in that directory. Install it from the immutable reviewed repository
commit and enable only the `charlie-builder` plugin. Slack uses Hermes' built-in
Bolt adapter in Socket Mode; it does not require a public webhook URL.
Socket Mode requires the protected `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN`.
Hermes' gateway-level `SLACK_ALLOWED_USERS` must contain the same exact member
ID as `CHARLIE_SLACK_OWNER_USER_ID`; the plugin fails closed if they diverge.

## Deterministic loop

1. Verify the Slack signature, exact owner user ID, and exact `#charlie`
   channel ID; acknowledge in the originating thread through the bot token.
2. Reconcile the Slack event idempotently through authenticated CHARLIE APIs.
3. Read current mission generation and externally issued Mission Admission.
4. Dispatch one Cursor Cloud Agent using `<mission_id>:<generation>`.
5. Persist Agent/run/thread/branch/PR/head linkage canonically.
6. Discover the open PR from the Cursor branch, then poll Agent/run/PR/check/
   review state without an LLM; report a 30-minute run or CI stall in the
   configured `#core-cloud-build` channel.
7. Route `SEND_BACK` to the same idle Agent, with at most two failed attempts.
8. Put only a green, independently approved exact candidate in
   `#owner-approvals`; never merge or deploy.

## Protected configuration

Hermes Cloud must protect `CURSOR_API_KEY`, `SLACK_SIGNING_SECRET`,
`SLACK_BOT_TOKEN`, `CHARLIE_SLACK_OWNER_USER_ID`, `CHARLIE_CANONICAL_API_URL`,
the three exact channel IDs, and a least-privilege CHARLIE API token. Values
must never enter Git, Slack, mission rows, PR metadata, artifacts, logs, or
Kanban task text.

`CHARLIE_GITHUB_READ_TOKEN` is restricted to repository metadata, pull-request,
check, and review reads. Hermes receives no GitHub write permission. The
canonical CHARLIE service separately holds
`CHARLIE_ADMISSION_ISSUER_GITHUB_TOKEN`, restricted to dispatching the protected
issuer workflow; Hermes can request that bounded action only for the PR/head
already bound in canonical mission authority.

## Remaining operational gates

- exact Cursor Cloud API key authorization;
- Slack app installation and exact channel/user IDs;
- reviewed PR merge;
- exact Hermes protected configuration/deployment approval;
- a terminal-independent Slack-to-Cursor pilot including one `SEND_BACK`.
