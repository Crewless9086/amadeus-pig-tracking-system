# Slack Architecture Assessment

Date: 2026-06-05

## Executive Summary

Slack should not become core infrastructure for the Amadeus Farm Operations Platform.

Recommended position: **Keep for future phase, as an optional human visibility layer only.**

Slack can be useful later if the farm has enough staff, managers, sales operators, and operational traffic to justify a structured internal team workspace. It should not be used as the place where agents store state, share truth, make decisions, or coordinate backend actions.

The safer long-term architecture remains:

```text
Web App / PWA
Backend API
Database / Event Log
Read Models
AI Agents / Automation Workers
Notification Delivery Layers
```

Slack, if ever used, should sit at the edge:

```text
Backend event or alert
Notification policy
Slack message for human visibility
```

It should not sit in the middle:

```text
Agent A writes Slack
Agent B reads Slack
Slack becomes shared memory
```

## Recommendation

**Do not implement Slack now.**

Keep it as a future option once at least one of these becomes true:

- There are multiple staff members who need structured internal channels.
- Telegram/WhatsApp/email become too noisy for internal operations.
- The web app has a notification center and the farm still needs a team chat layer.
- A dedicated operations team needs searchable discussions, handovers, and incident threads.

Until then, the current direction is better:

- Backend owns truth.
- Database/event tables own durable state.
- n8n stays a thin integration/delivery layer where useful.
- Telegram/WhatsApp remain practical farm communication channels.
- Web app/PWA becomes the main operating surface.

## Problems Slack Could Solve

Slack can help with human collaboration if the farm team grows.

Useful use cases:

- Internal team channels, for example `#farm-ops`, `#sales`, `#irrigation`, `#alerts`.
- Manager handover notes.
- Incident discussion threads.
- Human-visible alert summaries.
- Daily/weekly operating digests.
- Sales/operator coordination once meat, delivery, and inventory processes become more active.

Slack is stronger than Telegram for structured team channels and searchable internal discussion. It is weaker than the farm app for operational source of truth, recordkeeping, and workflow enforcement.

## Problems Slack Would Create

Slack would add another operational surface:

- Another app users must check.
- Another permission model.
- Another notification/noise source.
- Another vendor dependency.
- Another place where people may accidentally paste sensitive customer, financial, or farm data.
- Another integration path to maintain.

The biggest risk is architectural drift: Slack can become an informal database if agents or users start relying on chat history as truth.

That should be avoided.

## Slack As Human Communication Layer

Slack may be useful later for internal staff collaboration, but it does not replace:

- The web app for decisions and records.
- WhatsApp/Chatwoot for customer-facing sales conversations.
- Telegram for current operator alerts and farm assistant flows.
- Email for documents, formal notices, and external records.

Current recommendation:

| Channel | Best role |
| --- | --- |
| Web app / PWA | Primary operating system and source of operational actions. |
| Backend/API | Rules, truth, safety checks, and durable decisions. |
| Database/event tables | Source of truth and audit trail. |
| Telegram | Fast operator alerts, Oom Sakkie, and farm attention summaries. |
| WhatsApp/Chatwoot | Customer conversations and sales intake. |
| Email | Formal documents and external communication. |
| Slack | Optional future internal team visibility/discussion layer. |

## Slack As AI Agent Workspace

Slack should not be the agent workspace.

Agents should communicate through backend-owned structures:

- database tables
- event logs
- queues
- backend read models
- explicit API calls
- deterministic workflow contracts

Slack can receive a summary of what agents did, but it should not be where agents decide what happened.

Good pattern:

```text
Weather worker detects heavy rain risk
Backend writes alert/event
Irrigation worker reads backend event or read model
Farm dashboard updates
Telegram or Slack receives human summary
```

Bad pattern:

```text
Weather agent posts in Slack
Irrigation agent reads Slack message
Sales agent reads Slack message
Agents depend on chat history for truth
```

## Slack Vs Internal Event Bus

Slack is not an event bus.

| Requirement | Slack | Backend event bus / database |
| --- | --- | --- |
| Durable system state | Weak | Strong |
| Agent-to-agent contracts | Weak | Strong |
| Auditability | Limited by plan/config | Strong if designed in app/database |
| Permissions by operational object | Weak | Strong |
| Human discussion | Strong | Weak |
| High-volume automation events | Poor fit | Good fit |
| Vendor independence | Weak | Strong |

Slack should be treated as notification/output, not infrastructure.

## Scalability Assessment

Slack can become noisy as event volume grows.

If the farm expands to hundreds of pigs, multiple farms, more sales channels, and many automated events, Slack should only receive filtered summaries:

- high-severity alerts
- daily/weekly digests
- human-action-required items
- incident threads

It should not receive every pig weight, every telemetry reading, every allocation signal, every order state change, or every automation event.

The web app and backend read models should handle volume. Slack should only show curated human-facing messages.

## Security Assessment

Slack introduces data exposure risk because people and agents can paste operational/customer information into chat.

Sensitive information should remain inside the app/database:

- customer personal details
- payment details
- financial totals where not needed in chat
- exact farm security/asset details
- credentials, webhook URLs, database URLs, tokens
- full medical/treatment records where not needed

If Slack is ever used:

- post summaries, not full sensitive records
- link back to authenticated app pages
- keep backend audit logs as the source of truth
- restrict channels and members deliberately
- define what may and may not be posted
- review current Slack plan security/retention features before adoption

Slack's stronger audit/security controls are plan-dependent, so pricing and plan features must be rechecked before implementation.

## Cost Assessment

Slack has a free tier and paid tiers, but cost grows per active user and plan features matter.

Use the official Slack pricing page before any decision because pricing and plan names can change:

- https://slack.com/pricing

Cost guidance:

- Free may be acceptable for a small trial, but retention and admin controls are limited.
- Paid plans become meaningful once several staff use it daily.
- Enterprise-level audit/security capabilities may require higher tiers.
- If only Charl and a few farm users need alerts, Telegram and the web app remain cheaper and simpler.

Slack should not be introduced unless it solves a real collaboration problem worth the extra per-user cost.

## Alternative Approaches

| Option | Recommendation |
| --- | --- |
| Telegram | Keep for fast operator alerts and Oom Sakkie workflows. |
| WhatsApp/Chatwoot | Keep for customer-facing sales conversations. |
| Email | Keep for formal documents and external messages. |
| Web app/PWA notification center | Build as the primary internal notification/history layer. |
| Dedicated agent dashboard | Prefer for agent state, event history, and debugging. |
| Microsoft Teams | Only consider if the farm standardizes on Microsoft 365. |
| Discord | Not recommended for farm operations. |
| Slack | Future optional human visibility layer only. |

## Architecture Diagrams

Preferred architecture:

```text
Users
  |
  v
Web App / PWA
  |
  v
Backend API
  |
  v
Database + Event Log
  |
  +--> AI/Automation Workers
  |
  +--> Read Models / Dashboards
  |
  +--> Notification Policy
          |
          +--> Telegram
          +--> WhatsApp/Chatwoot
          +--> Email
          +--> Optional Slack
```

Slack visibility layer:

```text
Backend alert/event
  |
  v
Notification policy checks severity, audience, cooldown, and privacy
  |
  v
Slack channel message with link back to farm app
```

Anti-pattern:

```text
Agent writes Slack
  |
  v
Another agent reads Slack
  |
  v
Slack becomes source of truth
```

## When Slack Should Not Be Used

Do not use Slack for:

- source-of-truth records
- agent memory
- agent-to-agent contracts
- financial truth
- customer order state
- pig lifecycle state
- medical/treatment records
- permissions or approvals that should be backend-owned
- high-volume telemetry/pig events
- replacing the farm app dashboard

## When Slack Could Be Used Later

Consider Slack later for:

- staff handover channels
- incident discussion
- weekly farm summaries
- sales team coordination
- human-visible copies of selected alerts
- management digest channels

Only adopt it if the team actually wants to work in Slack daily.

## Final Decision

**Keep for future phase. Do not implement now.**

Slack is not needed for the current build because the farm already has:

- web app/PWA direction
- backend API
- database/Supabase direction
- n8n for thin delivery workflows
- Telegram for operator alerts
- WhatsApp/Chatwoot for customer sales
- email/document flows

The next better investment is a backend-owned notification/event model plus a web app notification center. Slack can be added later as another delivery target if there is a real team-collaboration need.

## Suggested Future Phase

Fit this after:

1. Supabase-backed operational event/audit model is stable.
2. Web app/PWA notification center exists.
3. Telegram alert preferences and multi-recipient routing are deliberate.
4. Multiple staff members need shared internal channels.

Possible future slice:

**Phase 10.4+ / Platform Notifications: Optional Slack Delivery Adapter**

Scope:

- no agent memory in Slack
- no Slack-owned truth
- backend event -> notification policy -> Slack message
- links back to authenticated app pages
- channel/audience rules
- privacy and data redaction rules
- cost/security review before enabling

## Sources To Recheck Before Implementation

- Slack pricing: https://slack.com/pricing
- Slack audit logs: https://slack.com/hc/en-us/articles/360000394286-Audit-logs-on-Enterprise-Grid
