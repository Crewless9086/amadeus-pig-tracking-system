# CMQ-20260813-05 Current Portfolio Baseline Plan

Status: owner-approved plan; no legacy mission mutation authorized

Portfolio epoch: `CORE-CURRENT-2026-08-14`

## Purpose

Phase A Shadow Control Tower must reason from Charl's current owner-outcome
portfolio, not from the unfiltered legacy CHARLIE queue. Legacy records remain
searchable evidence. They are not deleted, rewritten, scheduled, recovered or
released merely to make the old queue internally consistent.

This plan is an internal programme of existing mission `CMQ-20260813-05`, not a
new mission.

## Required portfolio boundary

Execution status and portfolio eligibility are separate truths. Preserve the
original mission status and add an independently reviewable classification:

- `current`
- `waiting`
- `historical`
- `superseded`
- `duplicate`
- `recovery_fragment`
- `test_evidence`

Only missions explicitly admitted to epoch `CORE-CURRENT-2026-08-14` may be
considered by current-work boards, priority selection, runner pickup, stale or
blocked recovery, release processing, PR reconciliation or automated
notification. Historical records fail closed against those paths.

## Admission test

Every proposed current mission must answer:

1. Is the owner-visible outcome still required?
2. Is it already complete in production?
3. Is another mission already responsible for the same outcome?
4. Is its evidence current?
5. Which deployed specialist owns the result?
6. Which visible development terminal owns active work, if any?
7. Which exact worktree/branch lease contains active work?
8. What is the one next bounded action?
9. What fresh real-world evidence proves completion?

A mission waiting for a genuine deployed-runtime event may have no active
development terminal. Its terminal is released and the durable deployed agent
owns the next event.

## Findings and mission creation

A finding is not a mission. Findings, incidents, adjacent UI/backend work and
recovery notes enter the parent mission's findings inbox or internal task list.
CORE may propose promotion but may not create a child mission. Control Tower may
promote one only when it has an independent owner-visible outcome, separate
acceptance criteria, separate authority or terminal ownership, and can complete
independently.

## No-write baseline manifest

Before any bulk classification or normal Shadow scoring, CORE must produce a
reviewable no-write manifest containing:

- a summary reconciliation of all terminal-status legacy records;
- every unresolved legacy record, including original identity/status/source;
- proposed portfolio classification and reason;
- machine-generated versus owner/non-machine provenance;
- unique evidence, decisions, PRs, commits, deployments and artifacts to retain;
- proposed current successor, if any;
- individual review of every owner/non-machine unresolved record;
- individual review of every `pr_ready` and `blocked` record;
- proposed current Control Tower missions and their admission-test answers;
- duplicates, recovery fragments and conflicts requiring owner judgment.

No status, mission, event, process, scheduled task, worktree, branch, PR or
production state may change while producing the manifest. Charl approves the
manifest before classifications or admissions are written.

## Canonical views

One canonical Supabase mission/event contract must derive:

- Current Mission Board;
- Terminal Board; and
- Historical Library.

The source-controlled Control Tower register remains reviewed planning and
audit evidence until normalized. It must not become a second runtime truth.
Terminal heartbeat and worktree lease state must be evidence-backed; CORE may
not infer that a Cursor terminal is alive or working.

## Revised sequence and gates

1. Repair authenticated opaque mission-ID creation.
2. Create exactly one canonical `CMQ-20260813-05`, admitted to
   `CORE-CURRENT-2026-08-14`, with human Control Tower as sole authority.
3. Produce the no-write Portfolio Baseline Manifest.
4. Obtain Charl's explicit manifest approval.
5. Implement and review portfolio classification/admission enforcement across
   every scheduling, recovery and release path.
6. Normalize and admit approved current Control Tower missions; preserve legacy
   evidence without reviving old lifecycles.
7. Establish the evidence-backed terminal/worktree lease registry.
8. Run ten genuine Shadow comparisons. A proposal must precede the human
   decision; no comparison may be fabricated or retroactively counted.
9. After owner approval of performance, allow one supervised read-only dispatch.
10. Expand gradually. Release and production authority remain separately gated.

## Hard stops

- No automatic mission creation from findings.
- No recovery or incident-repair mission chains.
- No scheduling outside the current portfolio epoch.
- No automatic reopening or merging of historical/old `pr_ready` records.
- No global branch switching in a shared workspace.
- No completion based on code, CI, deployment, replay or handover alone.
- No more than one current mission per owner-visible outcome.
- No n8n or Google Sheets business authority.
- No CORE dispatch, release or production authority during Phase A.

