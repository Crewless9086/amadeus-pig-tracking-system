# Molly first-treatment Telegram parity handover

Status: `DURABLY LOGGED - NOT YET AN OWNER OUTCOME` after reviewable commit.

This is a bounded repair in the existing HERDMASTER continuous-husbandry
operating loop. It adds a distinct first-treatment semantic contract, resolves
one canonical active litter, retains explicit 4/4/8 facts, asks one question for
missing medical facts, creates one protected preview, and executes through the
existing litter-health operation with Supabase required. Farrowing and treatment
remain mutually exclusive. No heat evidence is introduced.

The source was recovered from the stale uncommitted worktree into a clean
current-main worktree at `6b51eb1984bb55bd63635354ad9f8e6bf4b9ad6a`.
The stale worktree and Molly's farm records were not changed. Focused semantic,
preview, protected-action and gateway tests pass. Review, exact-current CI,
merge, deployment, read-only production preflight, one fresh genuine report,
protected confirmation, canonical medical/tally readback and later follow-up are
still required. Do not resend Molly's prior message yet.

OWNER ACTION: NONE.
