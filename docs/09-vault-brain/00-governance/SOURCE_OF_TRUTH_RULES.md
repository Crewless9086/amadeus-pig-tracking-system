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

Memory records are source-linked aids to recall. They do not outrank owner instructions, runtime truth, or owner-reviewed Vault Brain doctrine.

Mission working memory is scoped to the mission. Long-term typed memories, lessons, sales learning, Beacon performance evidence, and Oom Sakkie learning proposals remain advisory until promoted through owner-reviewed doctrine, tests, code, prompts, or runtime changes.

## Agent Rule

Agents must not invent source-of-truth facts. If data is missing, stale, unavailable, or unverified, say so.

Agents must not treat raw customer transcripts, private media, secrets, stale mission notes, or unsourced learning as memory authority.

## Working Tree Discipline

CHARLIE CORE must not start, package, or send a mission to owner review from a dirty working tree.

Before a mission is picked up, the runner must confirm `git status --porcelain --untracked-files=all` is empty. If it is not empty, mission pickup must stop with a clear recovery packet listing the dirty files.

Every mission must use one clean branch or clean worktree. Mission artifacts must be committed, pushed, or deliberately parked in a named recovery packet before another mission starts.

Unrelated owner files, screenshots, generated test artifacts, or scratchpad changes must never be silently mixed into mission review. They must be restored, committed as explicit source material, ignored as generated output, or quarantined with owner-visible notes.

`planning/CODEX_CHAT.md` is runner scratch state. It must not remain dirty after a mission unless the active mission is still running and the runner owns that state.

If this rule blocks a mission, that is a correct safety stop, not a workflow failure.

Detailed Brain & Memory v2 doctrine: `../06-data/BRAIN_AND_MEMORY_V2.md`.
