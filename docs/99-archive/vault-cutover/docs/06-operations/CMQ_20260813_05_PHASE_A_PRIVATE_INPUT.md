# CMQ-20260813-05 Phase A private observation input

Status: authenticated producer bridge and durable-worker subscription prepared for review

Owner and sole dispatch authority: human Control Tower

## Boundary

This slice adds one internal typed action, `observe_shadow_control_tower`, to
the existing private CORE tool registry. It adds no route, endpoint, process,
scheduler, terminal, agent, mission queue, database schema or ledger. The
handler reuses the Phase A Shadow module and the existing owner-private
`operational_events` fabric.

The subsequent systemic-ingress repair adds the internal typed action
`reconcile_control_tower_feedback`. It is the sole canonical producer for this
Phase A slice. It accepts an exact genuine owner-pasted terminal-feedback
identity and later the canonical human Control Tower decision. Conversation
memory, a terminal-generated sample and historical register prose are rejected
as source identities. Both records remain owner-private `observe` events in the
same operational-event fabric.

The strict owner-admin application bridge `POST
/api/charlie/control-tower/feedback` is the platform-facing entry to that same
sealed action. It is not public: an authenticated owner-admin session is
required, then the server constructs the existing private-owner authentication
envelope and seal. Feedback supplies its exact UTF-8 SHA-256; changed bytes
under the same identity fail closed. `GET` on the same path provides
identity-only lifecycle readback without returning the pasted feedback body.
The independently supervised observe-only worker remains the sole proposal and
comparison actor.

The retained supervised CORE runner consumes these events in its existing
`observe_only` mode. That mode runs only the Shadow subscription: it cannot call
mission pickup, recovery, release, Codex execution, delivery or dispatch. The
exact paused `CMQ-20260813-05` bootstrap is observation-eligible only when its
complete non-runnable admission is intact. Every other admitted, candidate or
legacy mission remains ineligible.

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
not connected to natural-language parsing or Telegram delivery. The strict
owner-admin route has observation-only authority and cannot invoke the worker
directly. No comparison was fabricated during development.
