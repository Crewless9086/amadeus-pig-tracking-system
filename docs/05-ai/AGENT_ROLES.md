# Agent Roles

## Purpose

This file captures the practical AI role boundaries used by the Amadeus farm system.

Detailed future roster planning lives in `docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md`. This file is the short operating version for current builds.

## Core Model

Oom Sakkie is the owner-facing farm brain. Specialist agents do narrow work and feed Oom Sakkie structured outputs.

Specialists must not become uncontrolled separate brains. They start read-only or gated, and any write/customer/public action needs the approved backend gate for that lane.

## Current Sales Roles

| Agent | Current job | Current authority |
| --- | --- | --- |
| Sam | Customer conversation and intake through Chatwoot/WhatsApp. Collects missing sales facts and writes append-only lead/fact events. | May reply only inside configured backend gates. Must not invent price, timing, stock, bank confirmation, or final booking. |
| Butcher | Meat pipeline and pig/carcass matching. Prioritizes open half-carcass reservations and protects against overbooking. | Recommendation and gated reservation support only. No autonomous slaughter booking or stock mutation. |
| Ledger | Business, pricing, margin, pipeline, and follow-up priority advisor. | Advisory only. No customer sends, quote/invoice creation, or price changes without owner/backend approval. |
| Prisma/Beacon | Public/social demand-generation drafts for meat launch campaigns. Full future scope includes media library, opportunity scanning, scheduling, paid promotion, performance monitoring, and campaign optimization. Phase 11N has a draft-only packet for the first pork freezer preorder pilot. Phase 11P adds private media-library metadata/API foundation. | Draft/catalog-only until owner approves public posting and channel rules. Existing system docs call this role `Beacon`; owner may refer to it as `Prisma`. |
| Atlas / Analyst | Reviews sales conversations, objections, missing facts, conversion/loss reasons, and improvement opportunities. Phase 11O records append-only sales conversation learning evidence for later summary. | Learning evidence and recommendations only. No automatic prompt/rule/tool changes. |
| Oom Sakkie | Summarizes state, next gates, risks, and learning for the owner. | Internal command center. Does not replace Sam in customer conversations. |

## Learning Structure

Each module can have narrow learning evidence:

- Sam: conversation outcomes, missed facts, customer confusion, objections, conversion/loss reason.
- Butcher: match quality, reservation conflicts, pig/carcass availability issues.
- Ledger: price objections, margin signals, demand timing, follow-up priority.
- Prisma/Beacon: campaign angle, response quality, public post performance once posting exists.
- Driver/fulfilment: delivery issues, address quality, customer timing friction.

Atlas/Analyst and Oom Sakkie then summarize those signals into owner-reviewed improvement proposals.

Rules:

- Learning records are evidence, not automatic behavior changes.
- Human approval is required before changing prompts, pricing rules, agent logic, workflow gates, labels, or public/customer wording.
- Strong repeated patterns can become build briefs, but they still go through the normal roadmap and test process.

## Current Money-First Focus

Reference: `docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md`.

Order:

1. Chatwoot Sales Hygiene.
2. Sales Stress-Test Pack.
3. Prisma/Beacon Meat Launch Campaign.
4. Sales Conversation Learning Loop.
5. Beacon Media Library Foundation.

Phase 11N note: Beacon's meat launch packet lives in `docs/08-business-modules/MEAT_LAUNCH_CAMPAIGN_PACKET.md` and is backed by `modules/sales/beacon_campaign.py`. Full Beacon scope is logged in `docs/05-ai/agents/beacon/BEACON_SCOPE.md`. Beacon cannot post, send customer messages, create quotes/invoices/orders, reserve stock, or confirm payment until later approved authority levels exist.

Phase 11P note: Beacon's private media-library foundation lives in `modules/beacon/media_library.py`, `supabase/migrations/202606180002_create_beacon_media_library.sql`, and `docs/05-ai/agents/beacon/MEDIA_STORAGE_DECISION.md`. It catalogs assets and records review events only; it cannot publicly serve, post, schedule, spend, or automatically use media.

Other sales options remain planned, but the first agent pattern is proven through Meat Sales before repeating it for live pig sales, slaughter/abattoir sales, assisted slaughter, or custom cuts.
