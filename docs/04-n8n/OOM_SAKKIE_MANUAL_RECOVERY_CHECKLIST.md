# Oom Sakkie Manual Recovery Checklist

Date: 2026-05-18

Current status: recovery completed for normal Telegram messages on 2026-05-19. Keep this file as the operating recovery checklist if Oom Sakkie goes silent again.

## Goal

Restore Oom Sakkie with one clean Telegram entry point and no duplicate Telegram triggers.

## Upload / Import These

Import or update these workflows manually through the n8n UI only when recovery or a reviewed workflow change requires it. Export a backup of the current live GateKeeper workflow before replacing it.

1. `2 - The GateKeeper`
   - File: `docs/04-n8n/workflows/2 - The GateKeeper/workflow.json`
   - Must be active.
   - Must be the only workflow with an active Telegram Trigger using the Oom Sakkie bot.
   - Trigger updates must be `message` and `callback_query`.
   - Normal messages and button callbacks both pass through authorization before routing.
   - Normal messages route to `2.0`.
   - Approval callbacks route to `2.4`.
   - Quote-send/cancel callbacks route to `2.4.5`.

2. `2.0 - OOM SAKKIE - Amadeus Assistant Agent`
   - File: `docs/04-n8n/workflows/2.0 - OOM SAKKIE - Amadeus Assistant Agent/workflow.json`
   - Must be active.
   - Must not have a Telegram Trigger.
   - Must be called by GateKeeper.
   - Upload only if your live `2.0` does not already include the current Telegram context/tool updates.

3. `2.4 - Amadeus Orders Sub Agent`
   - File: `docs/04-n8n/workflows/2.4 - Amadeus Orders Sub Agent/workflow.json`
   - Must be active.
   - Must not have a Telegram Trigger.
   - Must only start from `When Executed by Another Workflow`.

4. `2.4.4 - Order Lookup Tool`
   - File: `docs/04-n8n/workflows/2.4.4 - Order Lookup Tool/workflow.json`
   - Must be active.
   - Must not have a Telegram Trigger.
   - Must only start from `When Executed by Another Workflow`.

5. `2.4.5 - Document Send Callback Handler`
   - File: `docs/04-n8n/workflows/2.4.5 - Document Send Callback Handler/workflow.json`
   - Must be active.
   - Must not have a Telegram Trigger.
   - Must only start from `When Executed by Another Workflow`.

## Do Not Upload / Reactivate

Do not upload or reactivate:

- `2.4.2 - Orders Approval Callback Handler`

This workflow is retired from the live path. If it exists in n8n, keep it inactive or archived.

Reason:

- It has historically owned a Telegram `callback_query` trigger.
- Reactivating it can overwrite or delete the Oom Sakkie bot webhook.
- GateKeeper now owns approval and quote callback routing.

Retirement gates before archive/delete:

- `getWebhookInfo` points to GateKeeper.
- The full smoke test list below passes.
- GateKeeper still points to the correct webhook after one off/on cycle.
- At least 24 hours of normal Oom Sakkie use passes with no callback regressions.

## Delete These If You See Them In n8n

In `2.4 - Amadeus Orders Sub Agent`, delete these old nodes if they still exist:

- `Telegram Trigger - Approval Chat`
- `Code - Normalize Telegram Approval Update`
- `IF - Looks Like Order Command`
- `Code - Parse Approval Command`
- `IF - Valid Approval Command`
- `Telegram - Invalid Command Reply`

The cleaned export has already removed them.

## Required Final Trigger State

For the Oom Sakkie bot, the only active Telegram Trigger should be:

- Workflow: `2 - The GateKeeper`
- Node: `Telegram Trigger`
- Updates: `message,callback_query`

There must be no active Telegram Trigger in:

- `2.0`
- `2.4`
- `2.4.2`
- `2.4.4`
- `2.4.5`

## Webhook Registration Reset

Before imports:

1. Run Telegram `getWebhookInfo` and record whether the URL is empty, stale, or already pointing to GateKeeper.

After imports, only if the webhook URL is empty or stale:

1. In n8n UI, deactivate `2 - The GateKeeper`.
2. Wait 5-10 seconds.
3. Reactivate `2 - The GateKeeper`.
4. Check Telegram `getWebhookInfo`.
5. The webhook should point to GateKeeper's webhook, not the old `2.4.2` webhook.

If `getWebhookInfo` already points to GateKeeper but no Telegram executions arrive, do not keep toggling. Check n8n execution logs, n8n service health, and the `Telegram - Oom Sakkie` credential.

Current live GateKeeper trigger webhook ID from the 2026-05-19 n8n export:

```text
b419b4e9-adf4-40a3-b582-a3e4ca1f3488
```

Earlier GateKeeper webhook IDs seen during recovery:

```text
41252191-96ae-4913-b545-af19e8ade5dc
```

Old retired `2.4.2` webhook ID:

```text
55af666c-ba87-4416-b8bf-3e6a9f53f980
```

## Test Order

Test in this exact order:

1. `getWebhookInfo` baseline before any toggle.
2. `Hi`
3. Weather question.
4. Sunsynk/power question.
5. `Show me order ORD-2026-3E46B8`
6. Approval request still sends approval buttons through `2.4`.
7. Approval button click reaches GateKeeper -> `2.4`.
8. Stale approval callback replay is refused.
9. Unauthorized callback click is rejected by GateKeeper.
10. `Prepare quote send for order ORD-2026-3E46B8`
11. Press `Cancel`
12. Only test `Send quote to customer` after explicit approval and destination confirmation.
