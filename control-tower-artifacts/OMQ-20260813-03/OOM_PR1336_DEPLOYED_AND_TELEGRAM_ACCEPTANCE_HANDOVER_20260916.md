# Oom Sakkie PR #1336 deployed and Telegram acceptance handover

Status: current mission handover, 2026-09-16. Continue existing mission
`OMQ-20260813-03` under the Agentic Farm Runtime Programme. This records the
deployed and published state; it creates no new mission or architecture.

## Authoritative location

The current mission lineage is published on branch
`control-tower/herd-operations-20260910`. The current paths are:

- `docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md`
- `docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md`
- `docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md`
- this handover,
  `control-tower-artifacts/OMQ-20260813-03/OOM_PR1336_DEPLOYED_AND_TELEGRAM_ACCEPTANCE_HANDOVER_20260916.md`

The main-branch mission register predates PR #1336. The previous 2026-09-15
handover remains in place as release-waiting history. The preserved Phase 0
dependency register remains the historical baseline; this handover is its
current Oom Sakkie Telegram update.

## Deployed release and model result

PR #1336 merged as `3d321e4932cf205d03e759cc71a26edd411bc9d2`.
The approved application candidate was
`cca25516ec9848afd3c629216c244afdad5850a6`; its independently reviewed
fixture-only successor was `231305595391a982755b1dc916a1e6c2e4e19ca6`,
tree `4162aaea74fc60a52039d0262a1e830bd550336e`.

All five candidate checks passed after fresh hosted execution of all 272 herd
tests, 27 subtests and every later required selector and browser job. All exact
merge checks passed. The first exact-merge audit attempt remains recorded as a
failure because its Playwright server did not start; its required retry passed.
No gate, assertion or test was removed or weakened.

The sole release operator deployed only web service
`srv-d6sijjkhg0os73f7regg` once in the approved fresh-date window. Render deploy
`dep-daks09jl550s73alg2g0` started at `2026-09-15T22:00:48Z`, finished live at
`2026-09-15T22:02:50Z`, and production `/health/revision` returned the exact
merge. Both identity checks were empty, bindings were unchanged and all eight
other services stayed on their prior revisions. Previous web revision
`9edc57d643bae3974f3321478fc59e1631c50623` remains the bounded web rollback
target if the existing release controls require it. No rollback has been
triggered.

The one approved corrected configured-model attempt completed earlier with HTTP
200 and usable reply `OK`; it was not truncated, ended with `stop`, and used
response model `gpt-5.4-mini-2026-03-17` for 15 tokens. It changed no farm record,
provider configuration or billing setting and has not been repeated.

## Current Telegram owner and minimal interim correction

Telegram still registers the n8n host as its sole webhook. Active GateKeeper
workflow `s8QaxmqT69Z5mhvE`, published version
`00c44771-9a6c-4a4e-bcb4-087a0502908e`, owns ingress and delivery. Active relay
`TlKy9kUgJJE0msU4` remains its backend-conversation subworkflow. This is the
current transport owner, not the canonical business owner.

The already approved reply-ID correction was published once at
`2026-09-16T03:32:24Z` through the existing relay owner. It changed only node
`2d0b4a5a-0002-4f41-b7db-2c3c5d1a9d02`, **Code - Normalize GateKeeper
Message**, field `parameters.jsCode`:

- exact before hash:
  `a8bb6a2a492e2f59ef8a6e7a76863a7b8e64acabe4fc87b1215dfb58c2ae2708`;
- exact published hash:
  `cd7e2d56185ee2f33e6bc5a2b1c8411a48e78dc74c5a4493e1eee45224aa38f0`;
- new saved and active version:
  `84decfbb-62a9-4298-b9c6-f927dd4b59e4`.

The relay remained active throughout. Saved and published versions match. All
other nodes, connections, settings, static data, pin data, groups, name and
description remained exact. Telegram reports zero pending updates, accepts
`message` and `callback_query`, and has no current webhook error. A fresh
offline post-publication check proved ordinary English and Afrikaans envelopes,
native reply ID `900`, reply-bound farrowing/health-loss/manager-question
selection and fail-closed invalid reply IDs. It sent no message and performed no
database/model/farm call. Two verifier-only fixture failures and one stale-file
race are retained as invalid attempts; none touched production.

The exact rollback owns this one field. It may restore the recorded before value
only if the then-active field still exactly matches the published after hash.
It must republish and verify the before hash. Any mismatch requires a newly
reviewed inverse so concurrent changes survive.

The three native-voice GateKeeper edits remain unchanged, separately held and
unpublished.

## Implemented backend replacement and retirement condition

The backend-owned replacement is implemented at
`POST /api/oom-sakkie/channels/telegram/direct-webhook` in
`modules/oom_sakkie/routes.py` and `modules/oom_sakkie/telegram_direct.py`.
It routes allowlisted private messages and protected callbacks through the
backend-owned conversation, specialist and action rails. It requires the
Telegram secret header, bot token, allowed owner IDs and separate direct/send
gates. Corrected exact-key Render reads found all five required inputs present,
both gates true, a secret of at least 32 characters and three allowlisted IDs.
The earlier pagination-based inference that these keys were absent remains
preserved as invalid.

At `2026-09-16T03:43:55Z`, a local review evaluated the deployed policy with 21
exact current Render inputs. Direct chat/send readiness passed for three
allowlisted owners, the secret boundary and audit trace passed, and writes,
dispatch, physical controls and customer output remained false. No provider,
model or database call ran and no webhook changed. The report also makes the
remaining functional gap explicit: generic Telegram inline callbacks outside
the SAM Live owner-review path and persistent task/reminder/project memory are
not carried over yet. Proactive daily delivery and BEACON media intake are
disabled; the separate voice hold remains unchanged.

The backend adapter is implemented and configured, but it is not yet provider
owner or full callback replacement. The remaining n8n dependency can retire
only after:

1. current-transport acceptance proves genuine ordinary English/Afrikaans text,
   native reply metadata, protected confirmation and protected cancellation;
2. the review-gated direct-adapter parity check runs in its approved local or
   provider context without weakening its local-review access boundary;
3. a separately controlled sole-webhook cutover moves Telegram from the exact
   n8n URL to the backend direct-webhook URL while retaining the exact protected
   rollback URL and secret boundary;
4. live backend ownership proves Linda lookup and contextual follow-up, one
   genuinely needed permitted confirmed update saved exactly once and readable
   afterwards, a cancellation and replay with zero duplicate effect, and
   ordinary English/Afrikaans use;
5. scheduled and event-driven work continues with n8n unavailable, with no
   lost update, duplicate reply or remaining GateKeeper call to relay `2.0B`;
   only then may the two transitional workflows be deactivated, observed and
   archived under CORE retirement control.

No new n8n business logic is permitted. GateKeeper and relay remain the reversible
interim transport until these conditions pass.

## Callback reconciliation and live acceptance state

Historical callback effects remain reconciled before any retry:

- execution `66743` timed out after Charl's Linda farrowing confirmation, but
  claim `OOM-HERD-LITTER-E71867CF692725B072D0D50C` completed exactly once;
- execution `66837` was Anton's unauthorized farrowing attempt and wrote
  nothing;
- execution `66840` timed out after Anton's tag-138 mortality confirmation, but
  claim `OOM-HERDMASTER-3DDE52A15BCF4B0F21E730DE` completed exactly once.

The two completed operations must not be retried. A new current-version genuine
confirmation and cancellation remain open acceptance requirements.

At `2026-09-16T03:32:58Z`, immediately before the requested live Linda message,
the latest GateKeeper/relay executions were `70783`/`70784`. Charl was then given
this exact first message:

`Oom Sakkie, what do our saved records currently say about Linda's latest litter?`

The expected canonical answer is Linda's 2026-08-22 litter: 9 total, 8 born
alive, 0 stillborn, 1 mummified and 8 active on-farm piglets. Genuine execution,
delivered reply and the natural follow-up remain pending at this handover
publication point; they must be appended from actual evidence and may not be
replaced by the offline checks. After the first reply is verified, the intended
natural follow-up is:

`How many of those piglets are still active on the farm?`

## Time-dependent work and holds

The existing passive observer is waiting for the genuine 06:45 SAST scheduled
sample; its earliest read point is 06:43 SAST. Later duplicate suppression and
follow-through remain time-dependent. Ordinary read-only Telegram conversation
does not wait for that scheduler.

Migration, weaning, first-treatment, native voice, permission,
physical-operation, ROOTLINE and CHARLIE holds remain unchanged. HERDMASTER tags
138 and `PIG-2026-3EE5` remain resolved deaths and Linda's litter is resolved as
above. Pig 146, Waki, Teena and Prince still require fresh physical observation;
priority annotations are not completed farm work.
