# Marketing Rules

Beacon must not post publicly without owner-approved gates, spend money without approved caps, use unapproved/private media, or create demand the farm cannot fulfil.

Public copy must not overpromise stock, timing, delivery, final booking, or price.

Live-stock awareness is not a demand or sales lane. Its public copy must contain
no availability, sale, stock, price, booking, reservation, urgency, contact,
message or buying invitation, even when current sale-readiness triggered Beacon's
internal observation. A litter story uses the sow's canonical human name and
never exposes the internal litter identity. Organic inbound is routed to SAM
only after the person independently contacts the farm.

A distinct `live_stock_enquiry_capture` lane may state the stable, supported
business purpose that Amadeus Farm handles live-pig enquiries and may invite a
person to message the farm with animal type, quantity, intended use and area.
It must be text-only unless separately governed current media exists; it must
name SAM's qualification handoff and explicitly say that no stock, price,
availability, delivery or reservation is promised. It may not name current
animals, imply an offer or fulfilment outcome, optimize commercial livestock
copy from engagement, boost or spend. The exact owner-approved organic packet
and provider readback remain mandatory.

Objectives, brand rules, channel allowlists, KPI definitions, attribution windows, thresholds, and targets must show whether they are proposed or owner-approved. Approval may not be inferred from a default.

Demand ceilings require fresh fulfilment provenance and subtract commitments, operational reserve, and safety buffer from verified availability. Unknown channels, unresolved public-media permission, and missing, stale, invalid, incompatible, or zero-capacity evidence fail closed.

Creative-provider evaluation accepts only the owner-reviewed ElevenLabs and Happy Horse 1.0 candidate identifiers through deterministic disabled adapters. Source assets require verified hashes and effective owner approval. Provider evaluation, disclosure review, and public-use approval remain separate evidence records and never enable provider access, source transfer, spend, campaign selection, posting, scheduling, sends, stock changes, or farm writes.

Reusable campaign calendar rules are versioned and content-addressed. Approval, revocation, and latest-version state must resolve from the server-owned append-only lifecycle registry, currently a worker-shared durable SQLite file configurable with `BEACON_RULE_LIFECYCLE_DB_PATH`; payload lifecycle fields are evidence snapshots, never authority. Only an exact owner-approved latest version may prepare a calendar entry; edits require a new approval, and proposed, expired, revoked, or superseded versions fail closed. Rule approval and revocation are evidence-only and create no entry.

Prepared calendar entries must snapshot rule and approval identity, asset/hash/public-use lineage, exact copy and source hash, allowlisted channel, explicit IANA timezone window, fresh compatible fulfilment provenance, the capped target, pause evaluation, and preparation time. They are review evidence only and grant no timer, queue, dispatch, post, send, spend, order, reservation, stock, payment, or farm-write authority. Global, rule, channel, campaign, asset, and fulfilment pauses block preparation with machine-readable reasons.

Recurring-weakness analysis requires at least two distinct campaigns with fresh, latest non-superseded, compatible evidence. Weakness category, recurrence, lineage, expected-value state, safety level, readiness, and authority are server-owned. Equivalent evidence has one stable suggestion identity. Preview never writes; a separate authenticated owner-admin action may create one deduplicated CORE mission in `new` only. Beacon cannot approve, advance, execute, post, boost, send, spend, call Meta/Chatwoot/n8n, create orders, reserve or change stock, take payment, or write farm lifecycle state through this workflow.
