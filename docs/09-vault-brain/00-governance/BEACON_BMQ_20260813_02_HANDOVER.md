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

Complete review/CI/PR, verify the serialized release lane, deploy exact merge,
set the complete fail-closed Render policy, recover the four immutable provider
updates only through the deployed gateway, remove the temporary recovery token,
complete the album through the deployed boundary, and prove four ordered private
objects/thumbnails, one group/contact sheet, one provider receipt and silent
direct/concurrent replay. Then obtain one fresh genuine album through the normal
event trigger before BUSINESS_COMPLETE.
