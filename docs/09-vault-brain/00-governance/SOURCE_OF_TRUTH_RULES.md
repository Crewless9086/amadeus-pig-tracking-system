# Source Of Truth Rules

## Conflict Order

1. Latest direct owner instruction.
2. Supabase/runtime records for live state.
3. Vault Brain after owner review.
4. Active `docs/00-start-here/`.
5. Module-specific active docs.
6. Planning scratchpads and archived docs.

## Operating Truth

Supabase is operational truth for live state, approvals, ledgers, events, and runtime records where migration has been completed.

Markdown docs are operating guidance, rules, and context. They are not live collaboration state.

## Agent Rule

Agents must not invent source-of-truth facts. If data is missing, stale, unavailable, or unverified, say so.
