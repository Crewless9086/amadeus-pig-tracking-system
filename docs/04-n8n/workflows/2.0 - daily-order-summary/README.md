# 2.0 - Daily Order Summary

## Role

Scheduled operations workflow that sends the daily order summary to Telegram.

This workflow must read from the backend endpoint only:

```text
GET https://amadeus-pig-tracking-system.onrender.com/api/reports/daily-summary
```

It must not read `ORDER_OVERVIEW`, `ORDER_MASTER`, `ORDER_LINES`, or `ORDER_STATUS_LOG` directly.

## Trigger

Two triggers are included:

1. `Manual Trigger - Test Summary` for safe manual testing.
2. `Schedule - Daily Summary` for the production daily send.

Default schedule in the export:

```text
06:30 Africa/Johannesburg
```

The schedule can be changed in n8n without changing backend code.

## Delivery

Initial delivery channel: Telegram.

Current configured/admin target:

```text
5721652188
```

This matches the approved admin Telegram chat currently used by escalation workflows.

## Backend Contract

Expected backend response:

```json
{
  "success": true,
  "report_date": "2026-05-10",
  "counts": {
    "new_drafts": 1,
    "drafts_missing_payment_method": 16,
    "pending_approval": 0,
    "approved": 2,
    "cancelled_today": 0,
    "completed_today": 0,
    "orders_needing_attention": 17
  },
  "sections": {
    "orders_needing_attention": []
  }
}
```

## Required Behavior

1. Call the backend daily summary endpoint.
2. Verify `success = true`.
3. Format a concise operations message.
4. Include counts for all sections.
5. Include the first few attention orders with reasons.
6. Send the message to Telegram.

## Test Notes

Use the manual trigger first. The manual test will send a Telegram message to the configured admin chat.

Do not activate the schedule until the manual test message has been checked.
