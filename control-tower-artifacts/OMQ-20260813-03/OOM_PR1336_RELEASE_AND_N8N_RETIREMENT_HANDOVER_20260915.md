# Oom Sakkie PR #1336 release and n8n-retirement handover

Status: current mission handover, 2026-09-15. Mission identity remains
`OMQ-20260813-03`; this is dated current-state evidence under the existing
Agentic Farm Runtime Programme, not a new architecture or mission.

## Authoritative location

The retained current mission lineage is branch
`control-tower/herd-operations-20260910`. The authoritative current-state paths
on that branch are:

- `docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md`
- `docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md`
- this handover,
  `control-tower-artifacts/OMQ-20260813-03/OOM_PR1336_RELEASE_AND_N8N_RETIREMENT_HANDOVER_20260915.md`

The main-branch mission register predates PR #1336 and must not be used to infer
this release state. The Phase 0 dependency register at
`docs/99-archive/vault-cutover/docs/06-operations/AGENTIC_FARM_RUNTIME_PHASE0_DEPENDENCY_RETIREMENT_REGISTER.md`
is the preserved 2026-08-13 dependency baseline. This handover refreshes its
Oom Sakkie Telegram rows without rewriting the historical snapshot.

## Release state

PR #1336 is merged. Its approved candidate lineage is:

- approved application candidate `cca25516ec9848afd3c629216c244afdad5850a6`;
- independently reviewed fixture-only successor
  `231305595391a982755b1dc916a1e6c2e4e19ca6`, tree
  `4162aa7557dbfe96913404710edb8a88e412baf8`;
- serialized merge `3d321e4932cf205d03e759cc71a26edd411bc9d2`.

All five required candidate checks passed. Hosted audit execution ran all 272
herd tests and 27 subtests, plus every later required selector; the candidate
browser job passed. The exact merge passed CHARLIE CORE, browser, closed
migration and audit rails. Merge audit attempt 1 is preserved as a failure: its
Playwright server did not start. Required run attempt 2 passed; no gate was
removed or weakened.

Production had not deployed the merge at the last readback. The web service was
still serving `9edc57d643bae3974f3321478fc59e1631c50623`. The one retained release
operator, PID `29224`, is waiting for the approved 2026-09-16 operating-date
window, which opens at `2026-09-15T22:00:00Z` / 00:00 SAST. It has not started a
deployment. The separate passive acceptance observer, PID `36628`, is waiting
for verified production revision readback. No competing operator is permitted.

The one approved corrected configured-model probe completed at
`2026-09-15T17:17:06Z`: HTTP 200, usable reply `OK`, finish reason `stop`, not
truncated, configured model `gpt-5.4-mini`, response model
`gpt-5.4-mini-2026-03-17`, 15 total tokens. It used the application's configured
organization and project, changed no records or configuration, and must not be
repeated.

## Remaining Oom Sakkie n8n dependency

### Current owner

Telegram provider truth still identifies the n8n host as the registered Oom
Sakkie webhook. Active workflow `s8QaxmqT69Z5mhvE`, **2 - The GateKeeper**,
published version `00c44771-9a6c-4a4e-bcb4-087a0502908e`, owns ingress. It calls
active workflow `TlKy9kUgJJE0msU4`, **2.0B - Oom Sakkie Backend Read-Only
Relay**, published version `b90f2f4d-399b-4d1d-beb2-eb28551105bb`, for current
backend conversation delivery. The latest read found zero pending Telegram
updates. These workflows are transitional transport owners; they are not
canonical business owners.

### Implemented backend replacement

The repository implements the backend-owned adapter at
`POST /api/oom-sakkie/channels/telegram/direct-webhook` in
`modules/oom_sakkie/routes.py` and `modules/oom_sakkie/telegram_direct.py`.
It has explicit default-off gates
`OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED` and
`OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED`, requires an allowlisted private user,
Telegram's secret-token header and configured bot token, records the normal Oom
Sakkie audit trace, and routes ordinary messages and protected callbacks through
backend-owned Oom Sakkie/family/specialist action rails. The review-gated
`GET /api/oom-sakkie/channels/telegram/direct-parity` route exposes readiness.
The code is implemented and qualified; it is not provider-active while Telegram
still points at n8n. A first read-only environment-list inference at
`2026-09-15T18:45:49Z` was invalid because Render paginated the list; it is
preserved as `TELEGRAM_DIRECT_RENDER_READINESS_ATTEMPT1_INVALID.json`. Corrected
exact-key reads at `2026-09-15T18:50:29Z` returned HTTP 200 for all five inputs:
both enablement gates are true, bot token is present, webhook secret is present
and at least 32 characters, and three owner IDs are allowlisted. No values or
digests were recorded. The replacement is configured but cannot become the
provider owner before merge deployment, sole-webhook cutover and live acceptance.
The corrected receipt is `TELEGRAM_DIRECT_RENDER_READINESS.json` beside this
handover.

### Minimal interim transport correction

The already approved reply-ID correction is one field only:
workflow `TlKy9kUgJJE0msU4`, node
`2d0b4a5a-0002-4f41-b7db-2c3c5d1a9d02` (**Code - Normalize GateKeeper
Message**), field `parameters.jsCode`. Fresh readback at
`2026-09-15T17:37:52Z` still matched published before SHA-256
`a8bb6a2a492e2f59ef8a6e7a76863a7b8e64acabe4fc87b1215dfb58c2ae2708`.
The proposed after SHA-256 is
`cd7e2d56185ee2f33e6bc5a2b1c8411a48e78dc74c5a4493e1eee45224aa38f0`.
It validates and preserves Telegram `reply_to_message.message_id`; it adds no
business logic. Publication remains sequenced after verified web deployment.

The exact before value, exact proposed field and inverse are retained beside
this handover in `TELEGRAM_REPLY_ID_SCOPED_CHANGE.json`; the readable decision is
`TELEGRAM_REPLY_ID_SCOPED_DECISION.md`. The packet's embedded prepublication
status predates the owner's later approval. The approved rollback may restore
the exact before value only when the active field still exactly matches the
after hash, then must publish and verify the before hash. A mismatch requires a
new inverse so concurrent edits survive.

The three native-voice GateKeeper fields remain separate and unpublished. This
reply-ID publication does not authorize them.

### Callback failure reconciliation

Three historical n8n executions were reconciled against canonical records before
any retry:

- execution `66743` timed out after Charl's Linda farrowing callback, but claim
  `OOM-HERD-LITTER-E71867CF692725B072D0D50C` completed once. Canonical litter
  `LIT-OOM-D7F1943733BEDCE0` records Linda's 2026-08-22 farrowing as 9 total,
  8 born alive, 0 stillborn and 1 mummified, with 8 active on-farm piglets.
- execution `66837` was Anton's unauthorized farrowing attempt. It returned 403
  and produced no canonical write.
- execution `66840` timed out after Anton's mortality callback, but claim
  `OOM-HERDMASTER-3DDE52A15BCF4B0F21E730DE` completed once. Lifecycle event
  `LIFE-HL-14C031928489C6B8ED1C71A2` records pig `PIG-2026-6BB3`, tag 138, as
  dead and off farm; exact death time is Unknown and the body was removed and
  buried.

Neither completed operation may be retried. A genuine current-version protected
cancel and a new permitted confirmed update remain unproved.

### Missing work and retirement condition

The remaining n8n Oom Sakkie dependency can retire only after this ordered,
reversible path completes:

1. deploy merge `3d321e4932cf205d03e759cc71a26edd411bc9d2` to the one web service and verify
   the revision actually serving production;
2. publish and hash-verify only the approved relay reply-ID field, then prove an
   ordinary typed message, a genuine reply to an earlier Oom Sakkie message and
   protected confirmation/cancellation metadata through the current transport;
3. reverify the currently configured direct-adapter inputs and review-gated parity
   report without recording values; then, under a separately controlled transport
   decision, execute the sole-webhook cutover from the exact n8n URL to the backend
   direct-webhook URL while preserving the exact provider rollback URL and secret
   boundary;
4. prove English and Afrikaans ordinary conversation, canonical Linda lookup and
   natural follow-up context, one genuine permitted confirmed farm update saved
   exactly once with application/backend readback, one protected cancellation
   with zero effect, and safe replay without duplicate effect;
5. observe scheduled and event-driven follow-through with n8n unavailable, no
   lost updates, no duplicate consumer/reply and no remaining GateKeeper calls to
   relay `2.0B`; then deactivate, observe and archive those two workflows under
   CORE retirement control.

Until all five steps pass, GateKeeper and relay `2.0B` remain the rollback-capable
transport owner. No new n8n business logic is allowed. Other n8n workflows and
SAM/ROOTLINE/CHARLIE provider dependencies are outside this retirement slice.

## Next usable farm outcome

The next usable outcome is a real read-only Telegram conversation in which Charl
asks:

`Oom Sakkie, what do our saved records currently say about Linda's latest litter?`

The delivered answer must agree with the canonical Linda litter above. A natural
follow-up such as `How many of those piglets are still active on the farm?` must
retain Linda's context and answer from current saved records. The release
operator and reply-ID publication must complete first; no morning schedule is
needed for this read-only conversation.

The next safe farm-write acceptance must use a genuinely needed current fact,
the confirming person's existing permission and a new operation identity. It
must preview missing facts, confirm once, read back the exact saved effect and
later follow through. No historical report may be replayed as a new event.

Migration, weaning, first-treatment, native voice, permission, physical-operation,
ROOTLINE and CHARLIE holds remain unchanged. For the ten prioritized HERDMASTER
welfare/outcome cases, tags 138 and `PIG-2026-3EE5` are resolved deaths; Linda's
canonical litter is resolved as above; pig 146, Waki, Teena and Prince still need
fresh physical observations before their unresolved outcomes can close. Priority
annotations do not complete farm work.
