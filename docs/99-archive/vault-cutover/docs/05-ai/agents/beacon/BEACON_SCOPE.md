# Beacon Scope

## Status

Logged on 2026-06-17. Operational status corrected on 2026-07-12.

Beacon is the Amadeus Marketing Department Leader. The live foundation includes a private Supabase media library, owner review, campaign and publish packets, manual performance evidence, boost recommendations, and exact owner-confirmed Facebook text/image posting. Scheduling, paid-spend execution, automatic performance ingestion, creative-provider execution, and controlled campaign automation remain gated future phases.

## One-Line Definition

Beacon watches farm sale readiness, prepares public demand campaigns, uses approved media assets, schedules and manages approved posts/ads, monitors performance, and learns which campaigns produce qualified sales.

## Business Purpose

Beacon exists to help the farm make money without Charl manually thinking through every post, photo, channel, advert, timing decision, and follow-up.

Beacon should connect:

- pigs becoming ready,
- meat preorder opportunities,
- live pig sale opportunities,
- slaughter/abattoir fallback opportunities,
- customer demand patterns from Sam,
- campaign performance,
- approved media assets,
- and owner-approved posting/spend rules.

## Sales Streams Beacon Must Understand

Beacon should eventually support all pork sales routes, not only meat:

- Meat preorder sales: half carcass, full carcass, cut sets, delivery/collection routes.
- Live pig sales: pigs ready for direct livestock sale.
- Slaughter/abattoir fallback sales: pigs that should move through slaughter if meat/live demand does not convert in time.
- Assisted slaughter: later customer-facing offer after standard flows are stable.
- Butcher/custom-cut sales: later, once standard carcass sales are stable.

Beacon must not push demand that the backend cannot safely fulfil.

## Core Responsibilities

Beacon should eventually:

- Scan upcoming sale readiness from backend truth.
- Suggest what should be promoted and why.
- Recommend the best sale stream for the available animals.
- Draft campaign angles, captions, statuses, posts, stories, and ads.
- Recommend channels such as WhatsApp status/channel, Facebook, Instagram, direct known buyers, and later paid ads.
- Recommend timing based on campaign history and audience behavior.
- Recommend a spend cap where paid promotion is useful.
- Select suitable approved photos/videos/assets.
- Ask for owner approval when required by authority rules.
- Schedule posts only inside approved rules.
- Monitor campaign performance.
- Recommend pause, change, boost, repost, or removal.
- Log campaign outcomes and lessons for future use.

## Media Library Scope

Beacon needs an asset library before serious automation.

Storage decision:

- Binary files live in Supabase Storage.
- Searchable asset metadata and approval/review history live in Postgres.
- Full decision source: `docs/05-ai/agents/beacon/MEDIA_STORAGE_DECISION.md`.
- Phase 11P uses private buckets only: `beacon-raw-intake` and `beacon-approved-media`.
- Public serving, signed URL delivery, campaign scheduling, paid spend, and automatic public use remain disabled.

Asset input sources may include:

- Telegram upload.
- Farm App upload.
- Watched local/OneDrive folder.
- WhatsApp/media inbox later if safe.
- Google Drive/OneDrive sync later if useful.

Each asset should be logged with structured metadata:

- asset id,
- file path or storage key,
- source,
- upload date,
- owner/uploader,
- animal/product/farm subject,
- sale-stream relevance,
- location/context,
- quality score,
- public-use approval state,
- privacy/safety risks,
- visible people or private information,
- best channel fit,
- campaign usage history.

Beacon may suggest assets. Beacon must not use unapproved assets publicly.

## Suggested Beacon Sub-Agents

These can start as backend modules under one Beacon agent. They do not need separate personalities until the system earns that complexity.

| Sub-agent/module | Job |
| --- | --- |
| Beacon Strategy | Reads farm readiness and decides what should be promoted, where, when, and why. |
| Beacon Creative | Writes post, status, story, ad, and customer-education variants. |
| Beacon Media Librarian | Receives photos/videos, tags them, checks safety, scores quality, and queues owner approval. |
| Beacon Scheduler | Schedules approved posts within approved channel and spend rules. |
| Beacon Performance Analyst | Reads campaign results and recommends stop/change/boost/reuse actions. |

These modules form Beacon's team. Beacon owns the target and final recommendation; specialist modules do not become independent public-posting agents.

## Creative Studio Providers

Beacon may eventually use controlled external creative providers, but generated output must return to the private Beacon media library before public use.

- **ElevenLabs:** preferred first provider to evaluate for voiceovers, narration, sound design and its broader image/video creative tooling. The provider is already represented in the agent registry, but no Beacon production voice or creative execution authority is configured. Product reference: `https://elevenlabs.io/docs/overview/capabilities/image-video`.
- **Happy Horse 1.0:** experimental provider candidate for text-to-video, image-to-video, reference-guided video, prompt-based editing and joint audio/video generation. Provider identity, commercial terms, privacy, API stability and output quality must be verified before integration.

Creative provider flow:

1. Beacon Creative prepares a campaign-specific brief from approved brand and sale facts.
2. Only approved source assets are supplied to the provider.
3. Generated variants return to `beacon-raw-intake` with provider, prompt, cost and source-asset lineage.
4. Beacon Media Librarian checks animal/product fidelity, privacy, safety, brand quality and disclosure needs.
5. Owner approves public use.
6. Beacon may attach the approved variant only to an approved campaign packet.

No provider may post, schedule, spend, read customer conversations, receive secrets, or bypass media approval.

## Authority Model

Beacon should move from strict draft-only to controlled automation in stages.

### Current Authority

Beacon can:

- create draft campaign packets,
- create owner-review copy,
- recommend channel/angle/timing/spend in draft form,
- describe required approvals.

Beacon cannot:

- post publicly,
- send customer messages,
- call Meta/Facebook/Instagram APIs,
- call Chatwoot/n8n to send,
- create quotes,
- create invoices,
- create orders,
- reserve stock or carcasses,
- book slaughter or butchery,
- confirm payment,
- spend money.

### Future Authority Levels

| Level | Meaning |
| --- | --- |
| 0 - Draft only | Beacon drafts and recommends. Owner manually uses or ignores the copy. |
| 1 - Approved packet | Owner approves exact post/ad/status text and asset. Beacon may prepare final scheduling data only. |
| 2 - Approved campaign rule | Owner approves a campaign type, asset pool, audience, spend cap, channel list, and pause rules. Beacon may schedule inside that boundary. |
| 3 - Exception review | Routine approved campaigns run automatically; unusual spend, wording, risky assets, or weak fulfilment signals return to owner review. |
| 4 - Full controlled automation | Beacon manages campaign lifecycle with strict budget, stock, channel, fulfilment, and brand limits. Owner reviews exceptions and performance summaries. |

## Approval Rules

Owner approval should be required for:

- first use of a new campaign type,
- any new asset before public use,
- paid ad spend above the approved cap,
- campaign copy that mentions price, date, guaranteed availability, delivery promise, or final booking wording,
- public use of people, children, customers, license plates, private locations, or sensitive farm content,
- any campaign that may create more demand than the backend can fulfil.

Owner approval should not become a maze. Once a template, asset pool, channel, and spend cap are trusted, Beacon should run normal campaigns inside that lane and escalate only exceptions.

## Campaign Lifecycle

Target lifecycle:

1. Beacon detects opportunity from backend readiness.
2. Beacon drafts campaign plan: sale stream, channel, timing, asset, copy, spend suggestion, expected lead target, and risks.
3. Owner approves campaign or approves a reusable campaign rule.
4. Beacon schedules or prepares the post depending on authority level.
5. Public response routes into Sam/Chatwoot.
6. Sam captures buyer facts and campaign/source attribution.
7. Backend records leads, orders, deposits, reservations, fulfilment, and outcomes.
8. Beacon monitors channel metrics and Sam lead quality.
9. Beacon recommends keep/change/pause/boost/repost.
10. Analyst/Atlas and Oom Sakkie summarize learning for owner-reviewed improvements.

## Performance Metrics

Beacon should eventually track:

- channel,
- date/time posted,
- campaign angle,
- media asset used,
- copy variant,
- spend,
- reach,
- impressions,
- clicks/messages,
- cost per message,
- qualified leads,
- conversion to booking review,
- conversion to deposit requested,
- conversion to bank-confirmed deposit,
- conversion to completed order,
- lost reasons,
- objections,
- customer questions,
- fulfilment risk created by the campaign.

The useful money metric is not likes. It is qualified sales that the farm can fulfil profitably.

## Integration Points

Beacon will need controlled access to:

- backend sale readiness,
- meat planning and Butcher matching,
- live pig availability,
- slaughter/abattoir fallback planning,
- Sam lead source and conversation summaries,
- Chatwoot labels/custom attributes,
- approved media library,
- campaign records,
- Meta/Facebook/Instagram APIs later,
- WhatsApp status/channel process later if technically available,
- Oom Sakkie owner review and summaries.

## Risks To Control

Beacon must avoid:

- overpromising stock,
- overpromising timing,
- public pricing that is not currently approved,
- demand that exceeds fulfilment capacity,
- unapproved photos/videos,
- poor-quality or brand-damaging images,
- sensitive/private information in media,
- spending money without cap and approval,
- posting while payment, slaughter, butcher, or delivery gates are not ready,
- creating confusion between meat, live pig, assisted slaughter, and custom cuts.

## Build Roadmap

### Beacon 1 - Scope And Draft Packet

Status: complete foundation.

- Log full Beacon scope.
- Keep Phase 11N meat launch packet as draft-only.
- No posting or spend automation.

### Beacon 2 - Media Library Foundation

Status: live supervised foundation.

- Add asset records.
- Support owner-approved upload/drop source.
- Classify and tag photos/videos.
- Add approval state and usage history.
- Keep public use blocked until approved.

### Beacon 3 - Opportunity Scanner

Status: partial packet support; continuous scanner not built.

- Read upcoming pigs/meat readiness.
- Identify sale-stream opportunities.
- Produce campaign opportunities with risks and demand caps.

### Beacon 4 - Campaign Planner

Status: partial owner-review packet support; target/calendar loop not built.

- Combine opportunity, channel, copy, asset suggestion, timing, and spend cap.
- Produce owner-review campaign plans.

### Beacon 5 - Manual Posting Phase

Status: built; production evidence sample remains too small.

- Owner still posts manually or approves exact packet.
- Beacon records what was used and links inbound leads to campaign source.

### Beacon 6 - Scheduled Posting Phase

Status: not built.

- Add channel integrations only after rules are explicit.
- Beacon schedules approved posts inside approved limits.

### Beacon 7 - Paid Promotion And Optimization

Status: recommendation packet only; Meta insights ingestion and spend execution disabled.

- Add Meta/ads metrics and spend caps.
- Recommend stop/change/boost/reuse based on qualified lead and conversion data.

### Beacon 8 - Controlled Automation

Status: not built.

- Trusted campaign types run automatically inside approved rules.
- Exceptions return to owner review.

## Current Next Step

Build the production evidence loop next: opportunity scanner, campaign targets/calendar, approved scheduling, Meta/performance ingestion, Sam lead attribution, Ledger revenue/spend attribution, and weekly owner recommendations. Keep spend and reusable campaign authority owner-gated until production evidence supports graduation.
