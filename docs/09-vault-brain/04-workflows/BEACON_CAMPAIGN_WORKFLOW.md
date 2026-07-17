# Beacon Campaign Workflow

1. Beacon detects opportunity from the owner-read-only Supabase-first scanner; a scanner card is advisory and cannot trigger a campaign or public action.
2. Beacon reads the owner-review operating contract and verifies fresh fulfilment evidence; missing, stale, invalid, or zero capacity stops campaign targeting.
3. Drafts campaign plan/copy/media selection within the channel allowlist and demand ceiling.
4. Owner reviews proposed operating rules and the exact packet separately.
5. Operating-contract approval records a decision only and never posts, schedules, spends, sends, reserves, or writes operational state.
6. Public post/send/spend remains blocked unless its separate exact gate is approved.
7. Manual or controlled execution evidence is recorded.
8. Performance evidence informs future recommendations.
9. Compatible recurring weaknesses may produce deterministic follow-up suggestions for owner review. Single-campaign, stale, malformed, duplicated, superseded, missing, or incompatible evidence cannot establish recurrence.
10. Previewing a suggestion writes nothing. Only a separate authenticated owner-admin action may create the stable suggestion as a deduplicated CORE mission with status `new`, no owner decision, and no approval or execution state.

## Campaign Outcome Evidence

The authenticated owner may retrieve only provider-supported, allowlisted post metrics. Each metric retains its source, source reference, retrieval time, and evidence status. A numeric zero is verified only when the source explicitly returns zero; absent, unsupported, malformed, or provider-error values remain unavailable and cannot support recommendations or cost calculations.

Provider snapshots use deterministic content identity so unchanged retries are idempotent and changed source values append a new snapshot. Missing-evidence review is owner-visible. Corrections append a new event with explicit supersession lineage and never mutate original evidence. Retrieval and correction grant no posting, sending, boosting, spending, sales creation, stock, reservation, or farm lifecycle authority.

## Owner-Gated Live-Stock Sales Lane

`live_stock_sales` is separate from `live_stock_awareness`. It may prepare sales copy only when the current Supabase-first opportunity card is fresh, unblocked, sale-eligible, and carries a positive fulfilment cap, and when the effective price comes from `public.sales_pricing` with its inherited `SALES_PRICING` lineage.

Beacon may pair that copy only with an owner-approved public-use asset whose content hash is present. Facebook and WhatsApp suggestions remain distinct: WhatsApp is copy-only with no send action. The exact Facebook packet content-addresses the copy, asset/hash, opportunity revision, fulfilment cap, effective price record, and Beacon-to-SAM Live Stock attribution identity. Facebook execution must rebuild that packet from current server-side evidence and reject missing, altered, stale, or superseded evidence before applying the existing exact owner phrase `POST EXACT BEACON PACKET`.

For the bounded `meat_launch` Facebook pilot, preparation and execution remain fail-closed unless the server-side `SAM_MEAT_PUBLIC_OFFER_ENABLED` owner flag is enabled, the owner supplies an explicit positive whole-number fulfilment/pilot cap, and a currently approved public-use image is selected. The immutable packet identity includes the canonical exact Facebook text, exact asset identity, Facebook channel, cap, and owner-enable truth. Execution rebuilds this packet server-side and rejects any missing, altered, stale, or client-asserted readiness before the deterministic claim or Meta call. SAM Meat remains `interest_capture_only`; this pilot grants no quote, order, reservation, payment, stock, fulfilment, delivery, customer-send, or paid-spend authority.

The lane never authorizes an automatic post, customer send, negotiation, reservation, order, stock change, spend, or farm lifecycle write. Before calling Meta, a gated Facebook execution must acquire one deterministic, append-only claim for the exact publish packet; a retry or concurrent duplicate that cannot create that claim must stop without calling Meta. A successful gated execution records the returned Facebook post ID through a separate append-only result event. Buyer responses carrying the campaign identity route as `live_stock_sales` attribution to SAM.

## Beacon-To-SAM Attribution Read Model

Attribution requires stable, non-conflicting campaign, lead, and sale identities. Identical retries are idempotent; missing or conflicting identities fail closed as malformed evidence. Recognized revenue requires explicit `sale_status=Completed`, `payment_status=Paid`, and valid `net_total` evidence, with currencies kept separate.

Beacon attribution is a deterministic, read-only projection over canonical append-only campaign, SAM lead, order, sales-transaction, fulfilment, and loss evidence. Exact campaign identifiers attribute every matching SAM lead independently and outrank campaign-source/time-window matching; ambiguous source/time matches, expired, unmatched, duplicate, superseded, and malformed evidence must remain visible or fail closed rather than creating a conversion silently.

Qualification comes from explicit SAM lead status, orders require a resolvable `linked_order_id`, and revenue comes only from explicit completed sales-transaction `net_total` values kept separate by currency. Fulfilment uses the latest deterministic lead-linked event. Lost-reason aggregation accepts controlled reason codes only. The projection cannot post, send, call Meta/Chatwoot/n8n, optimize campaigns, spend, create orders, reserve or change stock, or write farm lifecycle data. Persistent attribution ingestion remains blocked until a separately approved append-only data migration exists.
## Owner-Rule Campaign Calendar

1. Beacon may propose a reusable campaign rule version containing an explicit campaign lane, channel allowlist, IANA timezone window, and demand unit.
2. Only the authenticated owner may approve the exact content-addressed version. Approval records evidence only; it creates no calendar entry and performs no external action.
3. An edit creates a new proposed version requiring fresh owner approval. The server-owned append-only lifecycle registry uses a worker-shared durable SQLite file (configurable with `BEACON_RULE_LIFECYCLE_DB_PATH`) to resolve approval evidence and the latest version across process restarts; caller-supplied approval fields are never authoritative. Owner revocation is a separate append-only event. Proposed, expired, revoked, and superseded versions cannot prepare entries.
4. Calendar preparation requires an effectively approved, public-use-approved, hash-verified, privacy-safe, lane-compatible asset; exact source-bound copy; an allowed channel; an unambiguous in-window instant; fresh compatible fulfilment evidence; positive residual capacity; and no active global, rule, channel, campaign, asset, or fulfilment pause.
5. A prepared entry is an immutable owner-review evidence snapshot. It is not a timer, runnable job, queue item, webhook, post, send, boost, reservation, order, stock action, or farm write.
6. Revocation and pauses block current use without rewriting historical preparation evidence.

Source reference: `docs/05-ai/agents/beacon/BEACON_SCOPE.md`.

## Creative Studio Evaluation Lane

1. An authenticated owner admin submits an exact prompt, parameters, cost-estimate provenance, and source asset IDs plus SHA-256 hashes.
2. The service verifies source existence, hash integrity, and the latest effective owner public-use approval; missing, hashless, tampered, rejected, or archived sources fail closed.
3. Only the ElevenLabs and Happy Horse 1.0 identifiers are accepted, and their adapters return deterministic provider-disabled mock manifests without network, credential, source-transfer, or spend authority.
4. Job, source lineage, attempt, cost, mock variant, and review evidence are appended as structured records. Mock variants remain private in `beacon-raw-intake`, `needs_review`, and not campaign-selectable.
5. Brand, privacy, safety, animal/product fidelity, provider disclosure, evaluation, and owner public-use decisions are recorded separately by the server-bound authenticated owner identity.
6. Evaluation or public-use approval records evidence only. It cannot enable a provider, spend, post, schedule, send, campaign action, order, stock change, or farm lifecycle write.
