# BEACON BMQ-20260813-02 handover

Mission lifecycle state: WORKING

Owner-visible outcome: Oom Sakkie's deployed event-driven BEACON intake stores
one genuine four-photo private album once, retains owner context and order,
presents its contact sheet, and gives one provider-confirmed completion receipt.

Cross-reference: BMQ-20260813-04 is BUSINESS_COMPLETE and remains awareness
proposal evidence. This mission reuses the same shared Oom Sakkie gateway and
does not create another bot, worktree, n8n authority or storage ledger.

## 15 August incident evidence

GateKeeper workflow `s8QaxmqT69Z5mhvE` routed all four inputs as
`owner_request_album` under provider media-group `14294284317288716`:

| n8n | update | message | Telegram unique file | bytes | SHA-256 | result |
|---|---:|---:|---|---:|---|---|
| 64570 | 549158282 | 3617 | AQADJg9rG7LkCFB- | 386588 | 207985cecbca936c58ed02d6b8c8a217689f533c3724581055598c5ada7c90d1 | relay 400 |
| 64571 | 549158283 | 3618 | AQADJw9rG7LkCFB- | 358445 | 2cee506dfc481cb384cbe0faaa0a94aa645aa121c3c11da6fbf608a39ea618a8 | relay 400 |
| 64572 | 549158284 | 3619 | AQADKA9rG7LkCFB- | 385630 | ecb2afb8320f786690c59143b8d7323746046a774fbb72fe29a00022fe867625 | relay 400 |
| 64573 | 549158285 | 3620 | AQADKQ9rG7LkCFB- | 423256 | 496a65a901571397a13c83b31a0214c9d672a18b72e83f329b8d9607a32271b2 | generic clarification |

All four `getFile` calls and bounded in-memory downloads succeeded on 15 August;
download sizes matched Telegram and no diagnostic object was stored. Message
3620 carried `Molly new litter born 2026-08-11`. Charl's current direct owner
instruction adds `litter size eight`; recovery must retain that as separately
provenanced owner-directed context, never as visual inference.

Production was live at `3670e277aa81d8af77619322aa30bca788323b75` but Render
had no `BEACON_TELEGRAM_MEDIA_INTAKE_ENABLED`, allowed-chat,
request-not-before or retired-hash registry. The schema/bucket already existed;
the private bucket had 19 objects and the canonical intake rail had two prior
groups/items, none from this four-photo incident.

## Correction boundary

`modules/oom_sakkie/telegram_gateway.py` and the retained direct path now admit
typed media and `/beacon-complete` before generic context. `media_intake.py`
projects captions from append-only evidence regardless of concurrent arrival,
supports one temporary token-bound exact-group recovery context supplement,
and returns a group-stable receipt identity. The existing family-message
lifecycle owns provider-confirmed delivery, concurrency and replay.

No library acceptance, public-use approval, campaign approval, publication,
customer contact, spend, sales availability, farm write or new n8n/Sheets
authority is introduced.

## Remaining acceptance

Reviewed PRs #949, #950, #953 and #954 are merged. Render revision
`509171e476ae3488b638403975c08f6f3f81cba6` loaded the complete fail-closed
policy. The temporary exact-group recovery token was removed and the same
revision restarted after recovery; normal event intake remains enabled.

The deployed authenticated gateway recovered all four historical provider
updates into group `BEACON-INTAKE-GROUP-1FCFA32ABAC219E62E5CD415`. Canonical
readback proves positions 1-4, the four incident SHA-256 values above, four
private `beacon-raw-intake` objects, four thumbnails, one album-completed event
and owner context including Molly, litter size eight and 11 August 2026. The
family lifecycle delivered one receipt as Telegram message 3626. A replay
exposed and then the reviewed lifecycle repair corrected a completed-card
regression; one bounded restoration edit returned message 3626 to completion.
Subsequent direct and concurrent replay produced zero sends, edits, media,
records or protected effects. No Library Accept, public-use, campaign,
publication, customer, spend, farm, n8n or Sheets effect occurred.

This is sealed historical terminal-invoked recovery evidence, not a fresh
autonomous acceptance epoch. It must not be replayed and Charl must not be asked
to manufacture another album for testing. BMQ-20260813-02 remains WORKING until
Charl naturally supplies an album he actually wants retained. The normal
GateKeeper event trigger must independently create one immutable group, preserve
order/context, store the private objects and thumbnails, present the contact
sheet, expose a digest-bound Finish Album button, complete once, and make stale,
sequential, concurrent and repeated callbacks silent without terminal invocation.

Standing authority ID: `BMQ-20260813-02-OWNER-DIRECTION-20260815`. Scope:
private original-owner photo intake, hashing, private storage, one receipt and
owner review presentation. The completion code remains internal; the visible
card displays canonical stored count and one owner/chat/card/album/digest-bound
Finish Album button. The weaker typed completion route is disabled.
Library Accept, Public Use, Campaign Review and publication remain separate.
Limits: no Library Accept, public-use, campaign, publication, customer contact,
spend or farm write. The runtime now waits for naturally desired media; no fresh
test album is an acceptable owner burden.
