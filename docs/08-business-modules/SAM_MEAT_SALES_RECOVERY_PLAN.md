# SAM Meat Sales Recovery Plan

## Purpose

SAM Meat Sales is the urgent money-flow recovery path under CHARLIE CORE.

The goal is to make meat leads operationally clear without unsafe automation. The owner should see one next action per lead, with all customer sends and money claims behind approval rails.

## Current Direction

SAM may use existing meat-sales rails first. SAM does not need to wait for the full Agent Collaboration Ledger migration.

When the ledger exists, SAM publishes result packets and handoffs into neutral ledger tables.

## Command Flow

```text
Lead/customer inquiry
  -> Sam identifies missing facts
  -> Ledger checks price/deposit/follow-up state
  -> Butcher checks availability and demand pressure
  -> Beacon drafts demand copy when appropriate
  -> Gatekeeper blocks or approves the next action
  -> Owner decides
  -> Supabase logs the decision and state
  -> Oom Sakkie / CHARLIE summarizes
```

## Required No-Send Rules

No customer message may be sent without approved rails.

SAM must not invent:

- price
- payment confirmation
- stock availability
- slaughter date
- butcher date
- delivery promise
- deposit request
- final booking

## First Recovery Target

`/sales/meat-leads` should become a SAM Meat Sales Command Room in a later approved implementation phase.

It should show:

- one next action per lead
- missing facts
- draft reply state
- Ledger money gate
- Butcher availability gate
- Beacon draft gate
- Gatekeeper approve/block state
- owner decision history

## Source Of Truth

Supabase remains the operational truth for leads, approvals, decisions, and audit records.

Markdown is guidance only.

## Out Of Scope Until Approved

- customer send automation
- Chatwoot/n8n send calls
- quote/deposit/order mutation
- stock allocation
- ledger migration implementation
- UI rebuild
