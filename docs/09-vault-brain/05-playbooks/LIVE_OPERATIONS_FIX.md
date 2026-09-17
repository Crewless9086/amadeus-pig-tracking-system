# Live Operations Fix Playbook

Treat as P0/P1 when live operations are blocked. Verify active process, branch, deployment, data store, and user-visible state before patching.

## Fix Sequence

1. Confirm what the user sees.
2. Confirm local vs Render/live behavior.
3. Confirm active branch/worktree.
4. Inspect logs or stored batch/state where relevant.
5. Reproduce safely if possible.
6. Patch narrowly.
7. Test success path and failure path.
8. Verify live if deployed.
9. Record evidence and update docs/Vault where operating rules changed.

## Common Failure Classes

- local runner off/stale;
- wrong worktree/branch;
- Render not deployed yet;
- server returns HTML/error page where JSON is expected;
- stale browser/local draft data;
- Supabase/Google Sheets state mismatch;
- workflow waiting on owner approval;
- n8n/Chatwoot service-window or credential gate;
- missing migration/table/env var.

## Rule

Do not treat symptoms as solved until the user-visible path is verified or the remaining blocker is clearly named.

For bulk or multi-row owner work, preserve the full owner input before a network
call. Use a durable operation and row ledger, bounded chunks, resumable
processing and idempotent retry. Only complete confirmed success may clear the
recoverable draft. HTML/non-JSON provider failures become a clear resumable
state; backend mechanics, raw exception tokens and contradictory counts do not
belong in the owner-facing message.

One failed source or row must not erase already attributable results or make an
unrelated surface unavailable. Report partial completion explicitly and retain
the exact remaining work.
