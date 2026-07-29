# SAM Livestock continuous follow-up contract

## Current diagnosis

The Level 1 control is an authority decision evaluated inside the backend
handler. It is not an event consumer. On 2026-07-29 account `147387` had no
configured Chatwoot account webhooks, and the legacy
`1.0 - SAM - Sales Agent - Chatwoot` n8n workflow was inactive. The bounded
cohort reached the backend only because the terminal posted each exact inbound
to the protected backend route.

Consequently, post-cohort inbounds `766408519`, `766412831` and `766413218`
did not independently traverse Chatwoot to SAM. Later
`sam_live_stock_direct_inbound` review events were created by diagnostic
terminal posts, not by a continuous consumer. No delivery claim exists for
those three inbounds. Conversation `2111` had no newer customer inbound after
outgoing `766404536`, so it correctly required no action.

GateKeeper consumes Telegram updates. It is not a Chatwoot message consumer
and did not receive these customer messages.

## Composed source path

`SAM Livestock - Continuous Chatwoot Inbound` is a narrow, inert-until-reviewed
n8n workflow source:

1. Chatwoot `message_created` webhook;
2. dedicated 32+ character webhook URL token plus exact account, inbox,
   WhatsApp, public-incoming and identity gate;
3. authenticated relay to
   `/api/sales/channels/chatwoot/sam-live-stock/inbound`;
4. authoritative chronology and contextual AUTO_SPECIALIST routing;
5. fresh `(account, inbox, conversation, contact, inbound message)` operation;
6. durable claim-before-send and provider delivery reconciliation.

Prior idempotency suppresses only the same inbound identity. Historical
ambiguous attempts remain quarantined and are never replayed.

Production activation requires the serialized runtime owner to:

- import and activate only the narrow workflow;
- register one Chatwoot account webhook for `message_created` to its production
  webhook URL with the dedicated token query parameter;
- preserve the existing single Telegram trigger and all unrelated workflows;
- verify a genuine new customer inbound, without replay or terminal POST.

## Follow-up behavior

- Known 7–19 kg male/female interest asks only quantity.
- A fully specified weaner request can ask location and timing while price and
  availability remain separately unconfirmed.
- A delivery request with a supplied location creates one deduplicated owner
  exception and never promises delivery.
- Customer silence creates no operation.

## Chatwoot inbox state

The supported Application API route is:

`POST /api/v1/accounts/{account_id}/conversations/{conversation_id}/update_last_seen`

Chatwoot stores `agent_last_seen_at` on the conversation and
`assignee_last_seen_at` for the assigned current user. It also clears unread
notifications for the authenticated user. Read state is therefore not an
exact per-message receipt and is not purely user-independent: the conversation
timestamps are shared fields while notification clearing and assignee behavior
depend on the authenticated user.

SAM may automate this only after:

- exact conversation/inbound binding;
- provider `delivered` or `read`, or an explicit reviewed disposition;
- a fresh chronology check proving that no newer inbound exists;
- a scoped Chatwoot agent principal whose read effect is intended.

Accepted-unverified and ambiguous delivery never mark the conversation seen.
SAM state labels are replaced only after reading and preserving every non-SAM
label:

- `awaiting_customer`
- `qualification_in_progress`
- `owner_decision_required`
- `delivery_quarantined_do_not_retry`

A genuinely new inbound removes prior SAM workflow-state labels and returns
the exact conversation to active work. Assignment, status, ownership and
unrelated labels are preserved. No bulk historical cleanup is allowed.
