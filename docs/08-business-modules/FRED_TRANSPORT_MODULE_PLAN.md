# FRED Transport Module Plan

## Purpose

FRED is the future Transport Commander under CHARLIE CORE and a planned money path.

FRED starts as lead/opportunity capture and a read-only board. It must not begin with dispatch automation.

## MVP Scope

First MVP should cover:

- transport leads
- load/customer opportunities
- pickup and delivery locations
- vehicle and driver availability
- quote status
- job status
- cost and margin
- documents and compliance reminders
- customer follow-ups
- owner approval gates

## Initial Team

| Role | Responsibility |
| --- | --- |
| FRED Transport Commander | Owner-level transport summary and routing. |
| Dispatch Agent | Dispatch planning only until approved. |
| Loads / Sales Agent | Lead and opportunity capture. |
| Fleet Agent | Vehicle readiness and capacity. |
| Driver Comms Agent | Draft-only driver/customer communication support. |
| Finance Agent | Cost, quote, margin, and payment state. |
| Compliance Agent | Documents, permits, reminders, and blocked states. |

## Safety

No dispatch, quote send, deposit request, customer message, or driver commitment may happen without owner approval rails.

## Source Of Truth

Supabase is the target operational source of truth for FRED records.

Markdown docs describe the plan only. No live transport collaboration state belongs in Markdown.

## Reporting Into CHARLIE

FRED reports:

- open opportunities
- blocked quotes
- jobs needing owner approval
- missing documents
- margin risks
- customer follow-up drafts

No implementation is approved by this plan.
