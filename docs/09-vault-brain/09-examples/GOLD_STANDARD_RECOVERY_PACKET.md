# Gold Standard Recovery Packet

Status: active seed example.

Use this when an agent blocks, times out, fails to produce a final artifact, or sends work back.

## Required Shape

```json
{
  "status": "recoverable|blocked",
  "blocked_agent": "builder",
  "blocked_reason": "Final artifact missing after partial implementation.",
  "partial_work": {
    "changed_files": ["path/to/file.py"],
    "pr_links": [],
    "commit_refs": [],
    "stdout_tail": "short relevant tail",
    "stderr_tail": "short relevant tail"
  },
  "what_worked": [
    "Specific useful work that can be preserved."
  ],
  "what_failed": [
    "Specific missing artifact, missing evidence, or failing test."
  ],
  "rerun_from_stage": "builder",
  "next_actions": [
    "Read the partial diff.",
    "Create the required final JSON artifact.",
    "Run the named focused tests.",
    "Send to tester only after the artifact contract passes."
  ],
  "owner_visibility": "Plain-language explanation of what happened and what CHARLIE will do next."
}
```

## Quality Bar

- Name the exact blocked agent.
- Preserve useful changed files; do not discard partial work blindly.
- Identify missing final artifact fields.
- Include stdout/stderr tails only when they explain the recovery.
- Prefer rerunning from the smallest responsible stage.
- Do not call a mission ready for owner review while unresolved blockers remain.
