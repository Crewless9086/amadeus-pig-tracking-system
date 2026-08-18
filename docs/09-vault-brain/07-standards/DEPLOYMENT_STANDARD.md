# Deployment Standard

Render deploys from `main` unless configured otherwise.

Use clean branch/worktree discipline. Never use `git add .`. Stage exact files only.

Always verify live after `main` changes.

Legacy compatibility path: `docs/00-start-here/DEPLOYMENT_SOP.md`.

## Branch And Commit Discipline

- Confirm branch with `git status` / `git branch`.
- Do not mix unrelated worktrees.
- Do not commit runner scratchpad noise unless the mission explicitly updates it.
- Stage exact files only.
- Commit message must describe the real change.
- Push the correct branch/remote.

Never use `git add .`. Before commit or merge inspect status, the exact
`origin/main...HEAD` file list and diff statistics. Stage only exact approved
paths, then inspect the cached file list/statistics before committing.

Never commit secrets, `.env`, tokens, test results, screenshots,
`external_sources/`, local `.claude` settings, owner scratch files, generated
assets or unapproved migrations. A direct push to `main` requires exact owner
approval and an exact bounded file list; auth, security, backend, migration,
customer-send, payment, reservation, public-post, route-guard and production
data changes use a reviewed PR.

## Release Gate

Before release/merge/deploy:

- tests relevant to changed surface passed;
- docs/Vault updated where behavior, agent roles, workflows, data, or business rules changed;
- migrations/data writes are explicitly identified;
- rollback or recovery path is known;
- owner final approval is recorded where required.

## Configuration Planes And Compatibility

- Local owner configuration supplies local CORE and development/operator tools.
- Hosted backend configuration supplies the application and CHARLIE Executive
  ingress; it must not be assumed to configure local CORE.
- CI contains test-only credentials and flags.
- GitHub stores source and CI metadata, never application secrets.
- Supabase stores durable operational state, not deployment secrets.

Configuration names are not renamed in place. Compatibility code may accept
one canonical key and one explicitly declared legacy alias. When both are set,
their normalized values must agree or startup fails closed. Retirement requires
a staged rollout: add the canonical key, prove parity locally and in the hosted
environment, retain rollback, then remove the alias in a later reviewed change.

Configuration inventory and diagnostics record key names, ownership, plane and
status only—never values. Dynamic key families are discovered from the actual
environment and runtime reader, not an incomplete literal-name scan. A
successful compatibility rollout retains legacy names through the observation
window; retirement remains a separate owner-reviewed change with current
caller and rollback proof.

The release report identifies exact changed files, tracked/untracked state,
tests and outcomes, migration/data-write status, rollback, and confirmation that
unrelated owner files were untouched.

## Live Verification

After `main` changes that should deploy:

- verify Render/live target or explain why no live deploy is expected;
- confirm the exact URL checked;
- confirm key page/API behavior;
- if deploy is slow/pending, state the status rather than assuming success.

After merge, fetch authoritative main, record the exact merge/revision and check
available CI/deployment evidence. A healthy URL alone does not prove the changed
business path. If no deployment is expected, say so explicitly.

## CORE promotion and activation

Source validation, merge, hosted deployment, local staging, activation and
terminal-independent operation are separate gates. The owner checkout is never
the CORE execution runtime. Staging uses a clean detached runtime, exact source
revision, signed isolated-validation receipt, manifest, rollback tuple,
governed-stop readback and a serialized non-stealable release lane. It does not
clear the stop, enable a task or start CORE.

Activation requires a new short-lived authority bound to the exact revision,
manifest, validation receipt, governed-stop digest, scheduled-task action,
mode and expiry. The provider task, not a terminal, starts the worker. Acceptance
requires authenticated provider ancestry, controller-observed supervisor and
runner identities, signed acknowledgement, fresh heartbeat, independent result,
next trigger and a later terminal-independent cycle. Historical or failed
activation identities are immutable and never retried.

Failure disables only the exact authorized task and restores the exact stop and
rollback state. Broad PID/name matching, process snapshots, ancestry alone,
stale PIDs and inferred stale locks grant no mutation or termination authority.

## Dependency retirement and scheduler singularity

Documented, runtime-loaded, provider-verified, OS-observed and physical evidence
are distinct. A committed export or an `active` field does not prove current
provider ownership, application loading, useful execution or physical effect.
Unknown never means disabled.

Before retiring a scheduler, webhook, callback, relay, legacy workflow or data
fallback, record its exact owner, callers, disable impact, canonical replacement,
rollback and provider-backed exit proof. Prove sole trigger/endpoint ownership,
fresh canonical and provider readback, replay silence and at least one reversible
observation window. Disabling a scheduled task does not stop an already-loaded
process. Missing or contradictory proof retains the dependency; dated inventory
must be refreshed rather than reused as current truth.
