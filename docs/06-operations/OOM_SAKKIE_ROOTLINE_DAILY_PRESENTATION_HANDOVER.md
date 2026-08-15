# Oom Sakkie ROOTLINE daily presentation handover

Date: 2026-08-09  
Stage: prepared for reviewed integration

## Reused production capabilities

- ROOTLINE live base at reconciliation: `aa4cd71184d3ce5a6d844fddbfa34958d36275f8`.
- Existing scheduler `jIRPu33UOFCbk2Gx` remains the only automatic reassessment owner and continues its 15-minute cadence.
- Existing authenticated `/api/oom-sakkie/management/rootline/reassess` endpoint, automatic reassessment claim store, ROOTLINE canonical specialist reader, family delivery rail, and execution coordinator are reused.
- No second scheduler, planner, queue, Telegram path, command path, or database table is introduced.

## Daily presentation contract

On the first existing scheduler tick at or after 07:00 SAST, Oom Sakkie loads a fresh canonical ROOTLINE specialist result. Evidence older than 30 minutes, unavailable evidence, or refresh still in progress produces no message and no daily claim; the next existing scheduler tick retries. This also provides the bounded catch-up behavior when deployment occurs after 07:00.

One deterministic identity, `OOM-ROOTLINE-DAILY-<owner>-<YYYYMMDD>`, owns that date's plan. Provider-confirmed delivery is persisted on the existing reassessment audit rail. Replay is silent. Provider ambiguity is preserved without retry.

The presentation contains only B Camp, C Camp, Run/Hold/Needs Data, supported windows, one short reason, at most one owner fact, and the next automatic reassessment. When no owner fact is required it says `Nothing` and `No action required from you.` Battery SOC, solar, load, grid and reserve are neither displayed nor used by the presentation to block or rank gravity-fed B/C.

The daily and material-change paths share one stable material digest. Evidence cutoffs, generated timestamps, whitespace, and formatting do not create a change. Decisions, reasons, preferred windows, the stable reassessment contract, or the genuine owner question do.

## Notification lifecycle

- Daily plan: one new provider-confirmed message per SAST date.
- Unchanged 15-minute reassessment: zero sends and zero edits.
- Material decision/owner-action change: one concise new notification.
- Governed execution Started, verified Completed, and Intervention each use a distinct state-bound notification identity, producing a visible alert rather than an unnoticed edit.
- Ambiguous delivery is never blindly retried.

ROOTLINE alone retains command authority. The presentation grants no hardware or farm-write authority and cannot create a second segment. Borehole, fertilizer, channels 3/4, simultaneous B/C and automatic segment two remain outside authority.

## Family access

Charl remains the sole configured Telegram identity (`5721652188`). Mum and Dad remain absent. The reviewed family-access contract is reconciled onto the current base. Unknown identities and configured non-owner identities cannot enter owner handlers; owner authority is issued only to Charl. A future real Mum/Dad onboarding requires Charl's separately governed exact identity and permission authorization and must use the documented family lifecycle integration boundary—never inferred names or language.

## Required production proof

1. Exact reviewed merge, all exact-merge gates and exact Render lineage.
2. Healthy service and preservation of both ROOTLINE activation flags and scheduler identity.
3. One naturally scheduled or date-catch-up current daily plan delivered to Charl with provider message identity.
4. Repeat of the exact due invocation: zero sends, edits, commands, work items or farm rows.
5. One later unchanged natural scheduler tick: zero owner effects.
6. Material-change notification remains waiting for real changed canonical evidence if none occurs; do not manufacture it.
7. Verify no family identity was added and Charl's ordinary owner route remains healthy.

Release the serialized lane immediately after proof or exact containment.
