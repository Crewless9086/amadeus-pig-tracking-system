# Marketing Rules

Beacon must not post publicly without owner-approved gates, spend money without approved caps, use unapproved/private media, or create demand the farm cannot fulfil.

Public copy must not overpromise stock, timing, delivery, final booking, or price.

Objectives, brand rules, channel allowlists, KPI definitions, attribution windows, thresholds, and targets must show whether they are proposed or owner-approved. Approval may not be inferred from a default.

Demand ceilings require fresh fulfilment provenance and subtract commitments, operational reserve, and safety buffer from verified availability. Unknown channels, unresolved public-media permission, and missing, stale, invalid, incompatible, or zero-capacity evidence fail closed.

Creative-provider evaluation accepts only the owner-reviewed ElevenLabs and Happy Horse 1.0 candidate identifiers through deterministic disabled adapters. Source assets require verified hashes and effective owner approval. Provider evaluation, disclosure review, and public-use approval remain separate evidence records and never enable provider access, source transfer, spend, campaign selection, posting, scheduling, sends, stock changes, or farm writes.

Reusable campaign calendar rules are versioned and content-addressed. Approval, revocation, and latest-version state must resolve from the server-owned append-only lifecycle registry, currently a worker-shared durable SQLite file configurable with `BEACON_RULE_LIFECYCLE_DB_PATH`; payload lifecycle fields are evidence snapshots, never authority. Only an exact owner-approved latest version may prepare a calendar entry; edits require a new approval, and proposed, expired, revoked, or superseded versions fail closed. Rule approval and revocation are evidence-only and create no entry.

Prepared calendar entries must snapshot rule and approval identity, asset/hash/public-use lineage, exact copy and source hash, allowlisted channel, explicit IANA timezone window, fresh compatible fulfilment provenance, the capped target, pause evaluation, and preparation time. They are review evidence only and grant no timer, queue, dispatch, post, send, spend, order, reservation, stock, payment, or farm-write authority. Global, rule, channel, campaign, asset, and fulfilment pauses block preparation with machine-readable reasons.
# Meta Paid Boost Red-Zone Gate

- Beacon may recommend `BOOST`, but a recommendation never authorizes or initiates spend.
- Paid boost execution is separate from post creation, organic publishing, and performance recording.
- Execution requires a server-resolved canonical published Meta post, fresh compatible BOOST evidence, fresh safe fulfilment capacity, and an immutable owner approval bound to an exact ZAR lifetime total cap and fixed duration.
- The owner must enter the exact server-defined final confirmation bound to the approved post, cap, and duration.
- Daily, recurring, open-ended, auto-increasing, and silently optimized budget semantics are forbidden.
- Missing paid policy, feature enablement, Meta Ads credentials, trusted adapters, or audit persistence is a hard stop before a provider call.
- Claims and results must be append-only and idempotent. Ambiguous provider timeouts remain uncertain for reconciliation and must not be blindly retried.
- The boost gate cannot write customers, orders, reservations, stock, payments, or farm lifecycle state.
