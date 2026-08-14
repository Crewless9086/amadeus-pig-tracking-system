# CMQ-20260813-05 Phase A private observation input

Status: source-prepared; disabled by default; not deployed or enabled

Owner and sole dispatch authority: human Control Tower

## Boundary

This slice adds one internal typed action, `observe_shadow_control_tower`, to
the existing private CORE tool registry. It adds no route, endpoint, process,
scheduler, terminal, agent, mission queue, database schema or ledger. The
handler reuses the Phase A Shadow module and the existing owner-private
`operational_events` fabric.

The caller must arrive through the existing private CORE authentication
boundary. `handle_authenticated_private_action` reuses
`authenticate_private_update` and converts its successful result into a sealed,
immutable internal context. The handler rejects caller-constructed mappings and
accepts only that context proving the authenticated owner principal, private
channel and `core_private_owner` scope;
credential values are never accepted in the action payload. The configured
owner identity is compared exactly. The referenced mission must already exist
in canonical Supabase mission truth and must equal the runtime-bound mission.
Cross-mission records fail closed.

Proposal and human-decision inputs preserve the exact feedback transaction,
proposal, mission and human-decision identities. The existing Shadow module
owns durable idempotency, exact replay, conflicting replay rejection and
distinct-feedback-transaction comparison counting. One stable proposal record
identity is used per feedback transaction; a concurrent or later changed
proposal fails closed. A recorded proposal is returned to the
authenticated internal caller so a later human decision can refer to the same
complete durable content.

## Disabled state and authority

`CHARLIE_SHADOW_CONTROL_TOWER_ENABLED` remains absent/false by default.
`shadow_input_runtime_state` exposes only whether the feature is enabled, the
kill-switch name and zero-effect counters; it exposes no secret value. While
disabled, input fails before mission lookup or event persistence.

Even when a later reviewed observation window enables the switch, the handler
can append only the two owner-private observe-tier Shadow event types. It
cannot send prompts, start terminals or processes, create missions, merge,
deploy, contact providers, write farm data or grant release authority. It is
not connected to natural-language parsing, Telegram delivery or any public
route in this source slice. No comparison was fabricated during development.
