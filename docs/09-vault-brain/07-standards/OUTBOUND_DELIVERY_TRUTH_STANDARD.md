# Outbound Delivery Truth Standard

Status: current cross-system authority for customer-message and document
delivery evidence.

Evidence cut: `2026-07-25`, repository revision
[`3954c5bd`](https://github.com/Crewless9086/amadeus-pig-tracking-system/commit/3954c5bd32b30b1beec9a53a5015db5e24e0493e).

This standard governs AUTO_GENERAL, SAM Livestock, SAM Meat, quotes, invoices,
attachments, and every future agent that sends customer-visible output.

## Incident: SAM Outbound Accepted-Unverified

Fault identity: `SAM-OUTBOUND-DELIVERY-TRUTH-20260725`.

The first AUTO_GENERAL canary in Chatwoot conversation `2013` created outgoing
Chatwoot message `759446597`. Its wording passed conversational review, but the
message remained `status=sent` without provider delivered/read confirmation.
Read-only evidence for conversations `2009`, `2008`, `2007`, `875`, `2005`,
and `2006` showed the same accepted-but-unconfirmed outcome.

The affected application path treated HTTP 2xx as
`chatwoot_send_confirmed`. Application-generated source identities of kind
`sam_live_stock:*` were retained where earlier successful manual WhatsApp
messages carried provider identities of kind `wamid.*`. The exact
delivery-claim/outcome evidence was not reliably recoverable through the
conversation.

No automatic retry occurred. The AUTO_GENERAL canary was disabled after the
failure.

The correct state is **`accepted_unverified`**. This evidence does not prove the
listed messages were delivered, not delivered, read, or failed. Only later
authoritative provider evidence may strengthen that state.

No customer content, phone number, provider identity, credential, token, or raw
payload belongs in permanent incident documentation.

## Canonical Delivery States

| State | Exact meaning | May claim customer received it? |
| --- | --- | --- |
| `prepared` | Content/document passed preparation gates; no attempt identity is yet claimed. | No |
| `attempt_claimed` | A stable idempotent attempt identity was durably claimed before external send. | No |
| `chatwoot_accepted` | Chatwoot accepted the request and an exact outgoing Chatwoot message identity is known. HTTP 2xx or Chatwoot `status=sent` stops here without stronger evidence. | No |
| `provider_delivered` | Authoritative provider event binds delivered status to the exact outgoing message/attempt. | Yes, delivered only |
| `provider_read` | Authoritative provider event binds read status to the exact outgoing message/attempt. | Yes, read |
| `failed` | Authoritative terminal failure binds to the exact attempt/message. | No |
| `ambiguous` | Outcome cannot be determined, identities conflict, evidence is unavailable, or dispatch may have happened without a recoverable authoritative result. | No |

`accepted_unverified` is the operational presentation of
`chatwoot_accepted` while neither delivered/read nor terminal failure is known.

States are monotonic append-only evidence, not mutable labels that erase
history. A later provider event may reconcile accepted-unverified to delivered,
read, or failed while retaining the original preparation, claim, and acceptance
events.

## Completion And Autonomy Rules

- HTTP 2xx, n8n success, Chatwoot acceptance, and Chatwoot `status=sent` are
  transport acceptance—not confirmed customer delivery.
- `customer_send_confirmed=true` requires `provider_delivered` or
  `provider_read` for the exact outgoing message.
- `handled_autonomously=true` requires the full applicable customer journey,
  including `provider_delivered` or `provider_read`, no unresolved protected
  action, and no active owner exception/card.
- `safely_completed` requires delivery/read evidence plus the journey's
  domain-specific completion gates. It cannot be inferred from preparation,
  dispatch, HTTP success, or Telegram/card cleanup.
- A mock HTTP success proves adapter behavior only. It is insufficient canary
  or autonomy graduation evidence.
- Canary graduation requires at least one controlled real end-to-end provider
  `delivered` or `read` event bound to the exact attempt and outgoing message.

## Identity And Append-Only Reconciliation

Every attempt must preserve:

- stable attempt/claim identity and idempotency key;
- agent/lane and business-purpose identity;
- conversation identity;
- exact outgoing Chatwoot message identity after acceptance;
- application correlation identity;
- provider source identity, when supplied;
- document/attachment identity where applicable;
- prepared, claimed, accepted, provider-event, and reconciliation timestamps;
- source and evidence version;
- latest truthful state and unresolved reason; and
- retry decision and authority.

Application idempotency/correlation values must not overwrite, replace, or
masquerade as provider source identity. Preserve both in separate fields.

Reconciliation must query or consume authoritative evidence for the exact
outgoing message, append a new event, and retain prior events. Conversation
history alone is not a durable delivery ledger when claim/outcome evidence
cannot be recovered through the exact message.

## Retry And Recovery

- Never automatically retry after `chatwoot_accepted`,
  `accepted_unverified`, or `ambiguous`.
- A timeout or missing response after dispatch is ambiguous unless exact
  evidence proves no acceptance occurred.
- Recovery first reconciles the exact attempt, Chatwoot message, and provider
  state.
- Any later resend requires a separately authorized new attempt identity and
  must expose duplicate-delivery risk.
- Duplicate webhook/provider events append idempotently and must not create a
  second logical delivery.

## Shared-System Contract

This standard applies uniformly:

| Surface | Required application |
| --- | --- |
| AUTO_GENERAL | A correct reply is not autonomous completion until delivered/read evidence exists. |
| SAM Livestock | Owner-approved and automatic replies use the same exact attempt/message/provider ledger. |
| SAM Meat | Prepared review, dispatch, and delivery remain separate; a Meat journey cannot complete at HTTP success. |
| Quotes/invoices | Generated, prepared, accepted, delivered/read, failed, and ambiguous are separate document-delivery states. Legacy `Sent` must not be interpreted as provider-delivered without evidence. |
| Attachments | Chatwoot acceptance of a file upload does not prove provider delivery or customer receipt. Preserve document, attachment, outgoing-message, and provider identities. |
| Future agents | No agent may define a weaker local meaning for confirmed send, autonomous handling, cleanup, or customer completion. |

## Operational Metrics

Owner dashboards and daily reconciliation must report counts and denominators
for:

- inbound;
- prepared;
- claimed;
- accepted;
- delivered;
- read;
- failed;
- ambiguous;
- still awaiting confirmed reply;
- active owner card; and
- safely completed.

`still awaiting confirmed reply` must distinguish at least:

- accepted-unverified outbound awaiting provider truth;
- delivered/read outbound awaiting customer response; and
- inbound requiring a response but not safely completed.

Dashboards must surface accepted-unverified messages as actionable
reconciliation work. They must not hide them inside success totals.

## Telegram And Owner-Card Rule

Telegram notification deletion, exact-card cleanup, HUMAN-to-AUTO transition,
or owner-card resolution is not customer completion. Cleanup may record the
owner-control lifecycle separately, but it must not set
`customer_send_confirmed`, `handled_autonomously`, or `safely_completed` before
delivery truth is known.

## Acceptance Evidence

Before any delivery path or canary graduates:

1. prove stable claim-before-send and exact outgoing-message capture;
2. prove provider identity is retained separately from application identity;
3. prove HTTP 2xx produces accepted-unverified, not delivered;
4. prove real delivered/read provider events reconcile the exact message;
5. prove failed and ambiguous paths;
6. prove no automatic retry after accepted/ambiguous;
7. prove idempotent duplicate-event handling;
8. prove dashboards/daily reconciliation expose accepted-unverified;
9. prove owner-card cleanup cannot manufacture customer completion; and
10. report the complete customer-journey metrics above.

## Correction Evidence Index

The eventual implementation correction must be linked here only when each item
exists:

- correction PR: pending;
- exact merge commit: pending;
- exact-revision deployment: pending;
- controlled real delivered/read proof: pending.

Unmerged candidates, tests, deployment health, mock success, or message
acceptance must remain in their weaker states.

ROOTLINE PR
[#464](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/464)
merged before this candidate finalized. Its newer ROOTLINE source-map entry is
retained, and the shared SAM/customer-delivery map now links this standard
without replacing that entry.

## Source References

- [`SAM_GENERAL_CONVERSATION.md`](../04-workflows/SAM_GENERAL_CONVERSATION.md)
- [`SAM.md`](../02-agents/sales/SAM.md)
- [`SAM_LIVE_STOCK_SALES_WORKFLOW.md`](../04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md)
- [`SAM_MEAT_SALES_WORKFLOW.md`](../04-workflows/SAM_MEAT_SALES_WORKFLOW.md)
- [`EVIDENCE_AND_REVIEW_STANDARD.md`](EVIDENCE_AND_REVIEW_STANDARD.md)
- [`BRAIN_GUARD.md`](../00-governance/BRAIN_GUARD.md)
- [`QUOTE_INVOICE_DESIGN.md`](../../02-backend/QUOTE_INVOICE_DESIGN.md)
- [`Outbound document delivery`](../../04-n8n/workflows/1.5%20-%20outbound-document-delivery/README.md)
- [`OPERATING_STATUS.md`](../../00-start-here/OPERATING_STATUS.md)
