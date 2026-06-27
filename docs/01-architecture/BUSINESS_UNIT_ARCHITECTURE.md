# Business Unit Architecture

## Purpose

Business units keep CHARLIE CORE practical. Each unit has a commander, specialist agents, source-of-truth records, approval rules, and owner-facing summaries.

## Units

| Business unit | Commander | Status | Primary goal |
| --- | --- | --- | --- |
| Owner Command Layer | CHARLIE | Planned | Owner-level overview, decisions, and cross-business summaries. |
| Farm Business | Oom Sakkie | Existing | Farm command, specialist coordination, and safe owner summaries. |
| SAM Meat Sales | SAM / Ledger / Butcher / Beacon / Gatekeeper | Urgent recovery | Convert meat demand into approved follow-up and money flow. |
| FRED Transport | FRED | Planned | Transport leads, opportunities, quotes, jobs, and compliance gates. |
| Build Team | Release Gatekeeper | Planned | Build requests, patch plans, tests, docs, and release decisions. |
| Brain / Vault | Docs Keeper | Guidance only | Human-readable guidance, decisions, prompts, and history. |
| Personal Command | Personal Admin | Future | Owner personal admin, reminders, documents, and calendar planning. |

## Source Of Truth

Supabase is the live operational source of truth. Business units may read from legacy sources while migrating, but live collaboration and approvals belong in Supabase.

Markdown docs guide work. They must not become live state.

## Gates

Every business unit must declare:

- read-only data surfaces
- draft-only surfaces
- owner/admin mutation routes
- approval-required actions
- forbidden actions
- audit records

## Forbidden Without Approved Rails

- customer messages
- public posts
- deposits or payment claims
- quotes sent to customers
- dispatch commitments
- driver commitments
- farm record writes
- stock allocations
- hardware control
- code deployment
