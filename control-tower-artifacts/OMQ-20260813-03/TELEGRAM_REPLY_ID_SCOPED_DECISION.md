# Telegram reply-ID transport correction — scoped publication decision

## Current published before-state

Fresh read-only inspection at `2026-09-15T16:04:46.872713Z` found:

- Workflow `TlKy9kUgJJE0msU4`, **2.0B - Oom Sakkie Backend Read-Only Relay**
- Active published version `b90f2f4d-399b-4d1d-beb2-eb28551105bb`
- Node `2d0b4a5a-0002-4f41-b7db-2c3c5d1a9d02`, **Code - Normalize GateKeeper Message**
- Field `parameters.jsCode`
- Exact current/published before SHA-256 `a8bb6a2a492e2f59ef8a6e7a76863a7b8e64acabe4fc87b1215dfb58c2ae2708`
- Exact proposed after SHA-256 `cd7e2d56185ee2f33e6bc5a2b1c8411a48e78dc74c5a4493e1eee45224aa38f0`

The active version and exact field still match the retained before-value. Nothing
has been published by this preparation.

## Proposed one-field change

Add this validation immediately after `const errors = [];`:

```javascript
const reply = rawMessage && rawMessage.reply_to_message;
const hasReply = rawMessage && Object.prototype.hasOwnProperty.call(rawMessage, "reply_to_message");
const replyId = reply && typeof reply === "object" && !Array.isArray(reply) ? reply.message_id : null;
if (hasReply && (!Number.isSafeInteger(replyId) || replyId <= 0)) {
  errors.push("provider reply message_id is invalid");
}
```

Add this property to `gateway_payload.message` immediately after `date`:

```javascript
...(hasReply ? { reply_to_message: { message_id: replyId } } : {}),
```

No other field, node, connection, credential, variable, callback, route,
activation, webhook, selector, application file, database record, or farm outcome
is in this scoped change. The exact full before and proposed after field values are
recorded in `TELEGRAM_REPLY_ID_SCOPED_CHANGE.json`.

## Verification already completed

Fresh offline execution used the current published JavaScript body and the exact
proposed field body:

- An ordinary typed English message retained provider message, sender, private
  chat, and timestamp identity and produced a request-ready envelope.
- The same result held for an Afrikaans typed message.
- Current published behavior omitted the native reply ID; the proposed field
  preserved replied-to message ID `900`.
- With an older manager card replied to, current published behavior selected the
  newest current question; the proposal selected the actual replied-to card.
- Invalid, absent, group-chat, and empty inputs remained fail-closed.
- No backend/provider request, message send, database access, or farm write was
  performed by this verification.

After an approved publication, verification must reread the exact active version
and field hash, then use a genuine Telegram reply to an older current manager card
to show the delivered backend receipt binds to that card. It must also recheck
ordinary typed messages and protected confirm/cancel callbacks. No farm operation
may be confirmed as part of the reply-ID verification.

## Exact rollback

Rollback owns this one field only. It may run only when the then-current
`parameters.jsCode` exactly matches after SHA-256
`cd7e2d56185ee2f33e6bc5a2b1c8411a48e78dc74c5a4493e1eee45224aa38f0`.
Restore the exact before field recorded in
`TELEGRAM_REPLY_ID_SCOPED_CHANGE.json`, publish through the existing transport
owner, and verify SHA-256
`a8bb6a2a492e2f59ef8a6e7a76863a7b8e64acabe4fc87b1215dfb58c2ae2708`.
Any hash mismatch requires a newly reviewed inverse so concurrent edits are
preserved. This rollback changes transport normalization only and does not undo a
farm event.

## Separate native-voice changes still held

The retained voice proposal contains three distinct GateKeeper edits. They are
outside this reply-ID decision and remain unpublished:

| Workflow/node field | Published before SHA-256 | Voice proposal SHA-256 |
|---|---|---|
| `s8QaxmqT69Z5mhvE` / `Code - Gate BEACON Single Photo` / `parameters.jsCode` | `4d762cdeb14244152fff137178f04ded42f798d3625f9ae7025e7902e4eeea24` | `b21e40dfe0c9a7e53e36eadd6714cdb6adc438cba7d57ea6e10683f527590bff` |
| `s8QaxmqT69Z5mhvE` / `Switch - BEACON Media Intake` / `parameters.rules.values` | `6d09bb05c23a2c53b0a250dbc740b7ce8de2147549ec1c92b1af696fea1a2e1e` | `becb6ac891ffc7c24627448a33350f9661fecc8ddd3d3ec01f282847ad267986` |
| `s8QaxmqT69Z5mhvE` / `Switch - BEACON Media Intake` / `connections.main` | `84a2b5358047f2bb53f042747c7895e8efc93948bd94a60b4085ef3c859ea7c1` | `a0089aee84f69eb4ec16dedfcecfd09a593b8d1ceb6dfd2a3ff3ca69f769c783` |

The reply-ID correction and the three voice edits require separate outcome
reporting even if the existing owner later schedules them together.
