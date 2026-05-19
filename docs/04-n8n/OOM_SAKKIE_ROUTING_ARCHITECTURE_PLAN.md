# Oom Sakkie Routing Architecture Plan

Date: 2026-05-19

Status: Path A implemented and first live Telegram message test passed on 2026-05-19.

## Decision

Use the slimmer plan:

- Keep `2 - The GateKeeper` as the single Telegram Trigger workflow.
- Keep deterministic update-type and callback-prefix routing in GateKeeper.
- Do not move callback routing into `2.0`.
- Do not build Router V2.
- Add authorization coverage to the GateKeeper callback branch. - Done.
- Retire/archive `2.4.2` after concrete gates pass.

Why:

- GateKeeper already has the correct structural shape for `message` and `callback_query` routing.
- Moving callback routing into `2.0` would edit the live LLM workflow and add no safety benefit.
- Callback routing is deterministic transport routing, not an AI/tool decision.
- Button callbacks must be authorized at the Telegram trigger boundary.

## Root Cause

The Oom Sakkie workflow suite became fragile because more than one workflow contained a Telegram Trigger for the same bot.

Telegram supports one active webhook URL per bot token. In n8n, every active Telegram Trigger can register, overwrite, or delete that bot webhook. A workflow that appears unrelated can make Oom Sakkie go silent if it owns the same Telegram bot credential.

## Target Flow

```text
Telegram
  -> 2 - The GateKeeper
       - one Telegram Trigger
       - message/callback update-type routing
       - authorization for both messages and callbacks
       - callback-prefix routing
  -> normal message branch: 2.0 - OOM SAKKIE
  -> approval callback branch: 2.4 - Amadeus Orders Sub Agent
  -> quote callback branch: 2.4.5 - Document Send Callback Handler
```

`2.0` receives normal authorized messages only. It remains the AI assistant and tool dispatcher for weather, Sunsynk, order lookup, and other operator questions.

Button callbacks are never sent to the AI agent. They are routed deterministically. Unknown callback prefixes return an invalid-callback Telegram response.

## Current Live State

As of 2026-05-19:

- `2 - The GateKeeper` is active in n8n as workflow `s8QaxmqT69Z5mhvE`.
- The live GateKeeper Telegram Trigger receives `message` and `callback_query`.
- The live GateKeeper export has been downloaded into `docs/04-n8n/workflows/2 - The GateKeeper/workflow.json`.
- Owner tested Telegram `Hi`; GateKeeper routed the message to `2.0`, and Oom Sakkie replied.
- `2.4.2` remains retired from the live path and must not be reactivated.

## Workflow Responsibilities

### `2 - The GateKeeper` - Gateway

Role:

- Own the only active Telegram Trigger for the Oom Sakkie bot.
- Receive both `message` and `callback_query` updates.
- Normalize Telegram identity fields for both update types.
- Authorize both messages and callbacks against `ASSISTANT_USERS`.
- Reject unauthorized users.
- Route normal messages to `2.0`.
- Route approval callbacks to `2.4`.
- Route quote-send/cancel callbacks to `2.4.5`.

Allowed logic:

- Telegram update-type routing.
- Telegram identity extraction.
- Authorization lookup.
- Callback prefix routing.
- Minimal payload shaping for worker workflows.

Not allowed:

- Weather logic.
- Sunsynk logic.
- Order lookup logic.
- Approval business decisions.
- Quote-send business decisions.
- LLM/agent prompts.

Trigger rule:

- This must be the only active Oom Sakkie Telegram Trigger.

Operational rule:

- Edit GateKeeper through the n8n UI only.
- Before any GateKeeper edit, export/download the current workflow JSON from n8n and save it as a dated backup, for example `workflow.pre-cleanup-YYYYMMDD.json`.
- Do not use n8n API updates for GateKeeper unless there is a separately reviewed reason.

### `2.0 - OOM SAKKIE - Amadeus Assistant Agent` - Orchestrator

Role:

- Main AI assistant and tool dispatcher for normal operator messages.
- Receive only authorized normal `message` updates from GateKeeper.
- Call weather, Sunsynk, order lookup, and other tools as needed.
- Send final Telegram replies for normal assistant conversations.

Not allowed:

- Own a Telegram Trigger.
- Receive raw Telegram callbacks.
- Route button callback prefixes.
- Make deterministic approval/send decisions that belong to backend or worker workflows.

### `2.1 - Amadeus Weather Sub-Agent` - Weather Tool

Role:

- Weather questions only.
- Called by `2.0`.
- No Telegram Trigger.

### `2.1.1 - Amadeus Forecast Tool` - Forecast Worker

Role:

- Focused forecast utility.
- Called by the weather workflow.
- No Telegram Trigger.

### `2.2 - Amadeus Sunsynk Sub-Agent` - Solar Tool

Role:

- Solar/power questions only.
- Called by `2.0`.
- No Telegram Trigger.

### `2.3.1 - Build Daily Irrigation Plan` - Irrigation Planning Worker

Role:

- Scheduled/worker irrigation planning.
- No Oom Sakkie Telegram Trigger.

### `2.3.2 - Run Irrigation Controller` - Irrigation Controller Worker

Role:

- Worker/controller for irrigation actions.
- Must remain carefully credentialed and environment-driven.
- No Oom Sakkie Telegram Trigger.

### `2.4 - Amadeus Orders Sub Agent` - Approval Worker

Role:

- Internal order approval worker.
- Receives approval request actions and approval callback decisions from GateKeeper.
- Sends Telegram approval request/confirmation messages where required.
- Calls backend approve/reject endpoints.
- Keeps stale approval replay protection.

Allowed actions:

- `request_order_approval`
- `process_order_approval_reply`

Not allowed:

- Own a Telegram Trigger.
- Parse normal free-text Telegram messages directly.
- Intercept `Hi`, weather, power, or order lookup questions.

### `2.4.2 - Orders Approval Callback Handler` - Retired Historical Handler

Status:

- Retire/archive in n8n after retirement gates pass.
- Keep local README/documentation only as history.

Reason:

- Its old job was `Telegram callback -> 2.4`.
- The live path should be `Telegram callback -> GateKeeper auth -> GateKeeper callback routing -> 2.4`.
- Keeping it live or easy to reactivate creates the same webhook conflict risk again.

Retirement gates:

- GateKeeper webhook is confirmed with `getWebhookInfo`.
- All live test cases in this plan pass.
- GateKeeper still points to the correct webhook after one off/on cycle.
- At least 24 hours of normal Oom Sakkie usage passes with no callback regressions.

### `2.4.3 - Order Approval Request Webhook` - Approval Request Webhook

Role:

- Backend-facing webhook entry for order approval requests.
- Receives approval-request events from backend/order flows.
- Starts the approval request path without using a Telegram Trigger.

Allowed:

- Receive backend webhook requests.
- Call or route to `2.4` approval request behavior if that is how the live workflow is wired.

Not allowed:

- Own an Oom Sakkie Telegram Trigger.
- Handle Telegram callback decisions.
- Replace GateKeeper authorization.

### `2.4.4 - Order Lookup Tool` - Order Lookup Tool

Role:

- Order lookup and guarded quote-send preparation tool.
- Called by `2.0`.
- No Telegram Trigger.

Allowed actions:

- `find_order`
- `get_order_summary`
- `get_order_documents`
- `prepare_latest_quote_send`

Important:

- It may send an operator-only Telegram button message for quote-send confirmation.
- It must not send customer documents directly.

### `2.4.5 - Document Send Callback Handler` - Quote-Send Worker

Role:

- Worker for quote-send/cancel button callbacks.
- Called by GateKeeper after callback auth and prefix routing.
- No Telegram Trigger.

Allowed actions:

- `quote_cancel`
- `quote_send` through the backend confirmed-send endpoint.

Important:

- It must call backend safety checks before sending.
- It must not call Chatwoot or `1.5` directly.
- If it remains a single quote-send branch long term, consider folding it into `2.4` in a future dedicated cleanup pass. Do not combine now.

## Proposed Final Workflow Map

| Workflow | Alias | Final role | Live status | Telegram Trigger |
| --- | --- | --- | --- | --- |
| `2 - The GateKeeper` | Gateway | Telegram entry, auth, update-type routing, callback routing | Live-tested | Yes, only one |
| `2.0 - OOM SAKKIE` | Orchestrator | AI assistant and tool dispatcher for normal messages | Live | No |
| `2.1` | Weather Tool | Weather sub-agent | Live | No |
| `2.1.1` | Forecast Worker | Forecast utility | Live | No |
| `2.2` | Solar Tool | Sunsynk/power sub-agent | Live | No |
| `2.3.1` | Irrigation Planning Worker | Irrigation planning | Live | No |
| `2.3.2` | Irrigation Controller Worker | Irrigation control | Live on-demand / inactive | No |
| `2.4` | Approval Worker | Approval request and approval decision worker | Live | No |
| `2.4.2` | Retired Callback Handler | Historical callback handler only | Retired / do not reactivate | No |
| `2.4.3` | Approval Request Webhook | Backend webhook for approval requests | Live | No Telegram |
| `2.4.4` | Order Lookup Tool | Read-only order lookup and quote-send preparation | Live | No |
| `2.4.5` | Quote-Send Worker | Confirmed quote-send/cancel callbacks | Live | No |

## Manual Build Plan After Approval

Do not apply this until the owner approves.

1. Backup before edit
   - In n8n UI, export/download current `2 - The GateKeeper`.
   - Save it in the repo as a dated backup before any UI edits.

2. GateKeeper narrow edit only
   - Keep current message/callback routing in GateKeeper.
   - Add authorization coverage to the callback branch so unauthorized users cannot click approval or quote-send buttons.
   - Keep normal message branch routed to `2.0`.
   - Keep approval callback branch routed to `2.4`.
   - Keep quote callback branch routed to `2.4.5`.

3. Do not edit `2.0` shape
   - `2.0` continues to receive normal messages only.
   - No callback routing is added to the LLM workflow.

4. Keep `2.4`
   - Worker only.
   - No Telegram Trigger.
   - Preserve stale approval replay guard.

5. Keep `2.4.4`
   - Worker/tool only.
   - No Telegram Trigger.

6. Keep `2.4.5`
   - Worker only.
   - No Telegram Trigger.

7. Webhook diagnostic and reset
   - Run Telegram `getWebhookInfo` first.
   - If the URL is empty or stale, deactivate GateKeeper in n8n UI, wait 5-10 seconds, reactivate GateKeeper, then re-run `getWebhookInfo`.
   - If Telegram already points to GateKeeper and messages still do not arrive, do not toggle blindly; inspect n8n service/execution logs and credential health.

8. Retire/archive `2.4.2`
   - Only after retirement gates pass.
   - Keep documentation in repo.

9. Update canonical docs
   - Update `docs/04-n8n/WORKFLOW_MAP.md`.
   - Update affected workflow READMEs.

## Rollback Ladder

If GateKeeper reactivation does not restore traffic:

1. Manually call Telegram `setWebhook` from the operator machine pointing to GateKeeper's exact n8n webhook URL.
2. If that fails, call Telegram `deleteWebhook`, then toggle GateKeeper off/on in n8n UI to force a clean re-register.
3. If still nothing arrives, check n8n service health and execution logs; a 500 from n8n's webhook endpoint can look like no traffic from outside.
4. Verify the bot token in the `Telegram - Oom Sakkie` credential against BotFather.

## Test Plan

Test in this order:

1. `getWebhookInfo` baseline before any toggle.
2. `getWebhookInfo` shows GateKeeper as the Telegram webhook after any required reset.
3. `Hi` creates fresh GateKeeper and `2.0` executions.
4. Weather question reaches `2.1`.
5. Sunsynk question reaches `2.2`.
6. Exact order lookup reaches `2.4.4`.
7. Approval request still sends approval buttons through `2.4`.
8. Approval button click reaches GateKeeper -> `2.4`.
9. Stale approval callback replay is refused by `2.4`.
10. Unauthorized callback click is rejected at GateKeeper and does not reach `2.4` or `2.4.5`.
11. Quote-send preparation reaches `2.4.4` and shows operator buttons.
12. `Cancel` button reaches GateKeeper -> `2.4.5`.
13. Real `Send quote to customer` only after explicit approval and destination confirmation.

## Open Decision

No build starts until:

- Owner accepts Path A.
- We agree on the exact manual GateKeeper edit.
- We have a GateKeeper backup export from n8n UI.
