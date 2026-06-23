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
| Prisma/Beacon | Public/social demand-generation drafts for meat launch campaigns. Full future scope includes media library, opportunity scanning, scheduling, paid promotion, performance monitoring, and campaign optimization. Phase 11N has a draft-only packet for the first pork freezer preorder pilot. Phase 11P adds private media-library metadata/API foundation. Phase 11Q adds the Farm App media review UI. Phase 11R pairs approved media with draft copy. Phase 11S prepares exact owner-review publish packets. | Draft/catalog/selection/packet-only until owner approves public posting and channel rules. Existing system docs call this role `Beacon`; owner may refer to it as `Prisma`. |
| Atlas / Analyst | Reviews sales conversations, objections, missing facts, conversion/loss reasons, and improvement opportunities. Phase 11O records append-only sales conversation learning evidence for later summary. | Learning evidence and recommendations only. No automatic prompt/rule/tool changes. |
| Oom Sakkie | Summarizes state, next gates, risks, and learning for the owner. | Internal command center. Does not replace Sam in customer conversations. |

## Sam v3 Direction

Sam Meat is moving from rule-first replies to an LLM-first shared-context runtime. The plan and implementation log are in `docs/05-ai/agents/sam/SAM_V3_LLM_FIRST_SHARED_CONTEXT_PLAN.md`.

The operating target is:

- Beacon creates campaign/post/media context.
- Sam reads that shared context plus Chatwoot, lead, conversation, and farm knowledge before replying.
- The LLM writes normal customer-facing wording.
- Backend code validates, saves facts, and blocks unsafe actions instead of being the main conversation script.

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
6. Beacon Media Review UI.
7. Beacon Approved-Media Campaign Draft Selection.
8. Beacon Campaign Publish Packet Review.
9. Beacon Manual Public Post Evidence.
10. Beacon Performance Tracking And Boost Recommendation Packet.
11. Beacon Owner-Approved Facebook Page Post Gate.
12. Beacon Approved-Image Facebook Page Post Gate.

Phase 11N note: Beacon's meat launch packet lives in `docs/08-business-modules/MEAT_LAUNCH_CAMPAIGN_PACKET.md` and is backed by `modules/sales/beacon_campaign.py`. Full Beacon scope is logged in `docs/05-ai/agents/beacon/BEACON_SCOPE.md`. Beacon cannot post, send customer messages, create quotes/invoices/orders, reserve stock, or confirm payment until later approved authority levels exist.

Phase 11P note: Beacon's private media-library foundation lives in `modules/beacon/media_library.py`, `supabase/migrations/202606180002_create_beacon_media_library.sql`, and `docs/05-ai/agents/beacon/MEDIA_STORAGE_DECISION.md`. It catalogs assets and records review events only; it cannot publicly serve, post, schedule, spend, or automatically use media.

Phase 11Q note: Farm App page `/sales/beacon-media` lets the owner upload small review assets, filter review status, and record append-only note/approve/reject/archive events. It still cannot publicly post, schedule, spend, send customer messages, or automatically use media.

Phase 11R note: Beacon can recommend approved media assets for draft campaign copy through `GET /api/beacon/campaign-draft-selection` and the `/sales/beacon-media` Campaign Draft Selection panel. This is selection evidence only; it still cannot publicly post, schedule, spend, send customer messages, create signed public URLs, or automatically use media.

Phase 11S note: Beacon can prepare an exact owner-review publish packet through `POST /api/beacon/campaign-publish-packet` and the `/sales/beacon-media` Publish Packet panel. The packet does not post, schedule, spend, call Meta, create signed URLs, send customer messages, or persist public approval.

Phase 11T note: Beacon can record owner-performed manual public post evidence through `GET/POST /api/beacon/manual-post-evidence` and the `/sales/beacon-media` Manual Post Evidence panel. This lets Beacon learn from manually posted campaigns, but it still cannot post, schedule, boost, spend, call Meta, send customer messages, or change orders/stock.

Phase 11U note: Beacon can record append-only campaign performance evidence and prepare owner-review boost recommendation packets through `GET/POST /api/beacon/campaign-performance` and the `/sales/beacon-media` Performance + Boost Recommendation panel. Recommendations are capped at R500 and optimize for Sam messages and qualified buyer leads. Beacon still cannot call Meta, boost, spend, schedule, send customer messages, or change orders/stock.

Phase 11V note: Beacon can post exact owner-confirmed text to a configured Facebook Page through `GET /api/beacon/facebook-posting-policy` and `GET/POST /api/beacon/facebook-post-executions`. This is env-gated, requires exact owner confirmation, records append-only execution evidence, and is text-only. Beacon still cannot boost, spend, schedule, DM customers, create orders, change stock, or auto-use private media.

Phase 11W note: Beacon can post an owner-confirmed approved image to the configured Facebook Page through the same `GET/POST /api/beacon/facebook-post-executions` gate when the publish packet carries a Beacon media `asset_id`. The backend resolves the asset from approved image media, creates a short-lived Supabase signed URL, posts to the Facebook Page photos endpoint, and records selected media evidence. Beacon still cannot boost, spend, schedule, DM customers, create orders, change stock, post videos/documents, or use unapproved/private media.

Other sales options remain planned, but the first agent pattern is proven through Meat Sales before repeating it for live pig sales, slaughter/abattoir sales, assisted slaughter, or custom cuts.
