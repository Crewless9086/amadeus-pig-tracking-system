# SAM inbox reconciliation pre-claim timeout handover

Status: source correction under review

## Production evidence

PR #728 remains deployed at merge `587cf6b9e689ebb7a49c07cd87127c74de8f7572` through Render deployment `dep-d9pq1bbbc2fs73apkd8g`. Its exact Chatwoot inbox provider-identity correction is preserved.

The 2026-08-05 bounded reconciliation for conversation 2101/inbound 777634477 returned HTTP 503 after approximately 32 seconds. Immediate authoritative reconciliation proved that the exact inbound remained latest and unanswered and that no durable claim, provider call, customer send, delivery attempt, quarantine, or Chatwoot mutation existed.

## Reusable diagnosis

The request-critical inbox operator loaded the complete Chatwoot inbox before selecting one candidate. Each inventory page used a hard 30-second network timeout. A single transient page read therefore converted an otherwise isolated provider-read failure into a global 503 before the durable claim boundary.

A later zero-write production trace loaded the current 1,790-conversation inventory across 72 pages in approximately 10 seconds. All pages completed in 1.4-2.5 seconds and the three current candidate histories completed in 0.7-0.9 seconds. This excludes claim persistence, stock/pricing composition, LLM drafting, provider dispatch, Chatwoot mutation, database contention, connection-pool exhaustion, and deployment health as participants in the contained execution. The failure class is a transient Chatwoot inventory-page read reaching the old 30-second timeout.

## Correction contract

- Bound Chatwoot inventory and chronology reads to a five-second default, clamped to 1-10 seconds.
- Isolate a failed non-first inventory page as partial provider coverage and continue only with conversations whose exact rows and complete chronology were loaded.
- Isolate one unavailable candidate history to that exact conversation.
- Preserve global fail-closed behavior for first-page loss, duplicate identities, account/inbox conflicts, changed identity/chronology and other systemic binding failures.
- Revalidate exact chronology and claim state inside the existing processor before claim.
- Classify processing exceptions using a fresh claim-ledger read: `not_crossed`, `crossed`, or `indeterminate`. Only a proven pre-claim failure is eligible for a later fresh execution; crossed or indeterminate boundaries never authorize retry.
- Preserve provider-confirmed delivery, no-retry quarantine, usefulness, inventory, pricing, policy and protected-authority gates.

Conversation 2101 is evidence only. It must be freshly revalidated after reviewed deployment and must never be processed merely to replay the contained execution.

## Current customer and manager state

At the last cutoff, conversation 2101/inbound 777634477 remained awaiting SAM with zero claim and zero delivery attempt. The earlier compact manager artifact that reported `whatsapp_provider_identity_unavailable` is superseded by PR #728's provider-bound evidence. A refreshed summary must be built from the newest exact chronology/reconciliation result only; it must report a current provider-read coverage exception only while that dependency is currently unavailable.

## Authority

SAM Livestock Level 1 remains narrow. Meat, cohorts, broad dispatch, automatic retry, protected commercial authority, farm mutation and unsupported customer commitments remain disabled.
