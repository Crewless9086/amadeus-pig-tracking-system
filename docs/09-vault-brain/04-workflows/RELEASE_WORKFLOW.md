# Release Workflow

Final approval records `release_approved`.

Release bridge may merge reviewed PRs only after approval and evidence checks.

Render deploys from `main` unless configured otherwise. Always verify live deployment.

Legacy compatibility paths: `docs/00-start-here/DEPLOYMENT_SOP.md`,
`docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md`. They do not govern release.

## Required Release Journey

1. Reconcile authoritative main and prove the exact bounded diff.
2. Run proportional automated tests plus the affected real workflow journey.
3. Record migration, configuration, provider and production-effect scope.
4. Obtain independent review and owner approval where the authority matrix
   requires it.
5. Merge through the serialized release lane.
6. Verify the exact loaded revision and the changed user/business path.
7. For scheduled or autonomous work, prove the provider-origin cycle, result,
   next trigger and a later terminal-independent cycle.

Documentation, workflow exports and schema/formula contracts are updated only
when their owned behavior changed. A historical checklist, healthy URL, green
merge or successful local test cannot substitute for the applicable live gate.
