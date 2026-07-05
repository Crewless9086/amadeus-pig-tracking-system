# Gold Standard Example: Litter Detail State-Aware View

Status: active reference example.

Source mission: `CHARLIE-MISSION-03819D23083FB5CF` / PR `#90`.

Source branch: `litter-detail-state-aware`.

Source commit: `d1530920824952066a1fe866d784a05befe476dd`.

Example type: state-aware farm UI improvement with successful Brain Guard recovery.

## Why This Is A Good Example

This mission is a gold standard because CHARLIE CORE did not simply push through a weak review packet. Brain Guard caught that the workflow missed `product_reviewer`, blocked owner review, and forced a targeted recovery.

The successful recovery preserved upstream implementation work, inserted the missing product review stage, reran the downstream Product/Security/Evidence/Reviewer/Publisher path, and only then returned the mission to owner review with PR evidence, passing checks, a working local preview URL, and visual review context.

## Files And Evidence Pattern

Agents should treat this as the pattern when a mission is blocked late by review-board or Vault discipline:

- preserve completed upstream artifacts;
- identify the smallest responsible rerun stage;
- do not restart the whole mission unless the preserved work is invalid;
- add the missing reviewer or evidence stage explicitly;
- rerun downstream reviewers after the correction;
- verify the review packet persisted as `ready_for_owner_review`;
- include a local preview URL and durable review media when the mission is UI-facing;
- include PR URL, head commit, GitHub checks, and focused local test evidence.

## Recovery Lessons

- A blocked mission is not automatically a failed mission. It can be a healthy gate doing its job.
- Brain Guard blocks must produce a recovery packet that says exactly which stage to rerun and why.
- Review packets with stale statuses must never be accepted as owner-ready.
- Agents must not guess test commands. Use repo test command memory and prefer focused `unittest` commands unless repo dependencies prove otherwise.
- UI owner review must remain inspectable until the owner approves or rejects. Local preview links and screenshots must be clickable during review.

## Quality Bar

Future missions may cite this example only when they:

- recover from a real blocker without losing useful prior work;
- maintain agent memory across the retry;
- preserve a clear backflow/replay trail;
- rerun the correct downstream specialists;
- attach mission-quality score, recovery packet, test evidence, and review-board result;
- leave the owner with an obvious approve/send-back decision.

## Anti-Pattern To Avoid

Do not hide a blocked stage by marking the mission complete.

Do not produce a new review packet that still contains `send_back`, stale, or blocked status while the mission is marked review-ready.

Do not tell the owner there is evidence if screenshots, PR links, local preview links, or test output cannot be opened or verified.
