# Legacy CHARLIE Mission Protocol Pointer

Lifecycle: `POINTER_ONLY / NON_DOCTRINE`.

Current intake, mission contract, orchestration, queue, approval, execution,
review, recovery and operator-command rules are in
`../09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md`. Release authority
is governed separately by `../09-vault-brain/04-workflows/RELEASE_WORKFLOW.md`.

Supabase/runtime records remain live mission truth. This compatibility path
cannot create authority, start a runner, merge, deploy, or perform a protected
business action.
