# Oom Sakkie P0 operational intake recovery

Status: source correction prepared; no recovery send, farm write or hardware
action has occurred.

## Authoritative preserved chronology

- Pig 125: exact Telegram text `Pig 125 is found dead in pen. No conclusion on
  what it might be.`, message 3179, provider epoch 1785682329
  (2026-08-02 16:52:09 SAST), content SHA-256
  `9703d8133edb27aa155160d6af5580d7f75a0ab93f73408aa49e0d264e6e4779`,
  GateKeeper execution 61909 and relay execution 61910. The deployed backend
  incorrectly reused Pig 11 mission `OOM-HERDMASTER-CE45B85C51356B77E087B099`
  and edited its existing card; it wrote zero farm facts.
- ROOTLINE presence: Telegram 3181, provider epoch 1785684198
  (2026-08-02 17:23:18 SAST), content SHA-256
  `b1dedc233a4d5064ef03ea3a90e94d0ee81296ab3c117533641e23cff76dbe8e`,
  GateKeeper 61915 and relay 61916. The generic word `can` incorrectly matched
  the open Pig 11 health follow-up and returned a replay no-op. This presence
  evidence is now historical and cannot authorize hardware.

Canonical read-only herd evidence uniquely resolves tag 125 to
`PIG-2026-BCEB`, Active, on farm, pen `PEN-012`, availability Unknown, evidence
generation `21ce271022589fd71cf8dd6aace751f6f2451c54a7598446051964579ccfb127`.
These values are identity/context evidence only; death remains owner-reported
and unrecorded.

## Generic correction

- A new explicit report never inherits a different open animal lifecycle.
- Generic `can` language no longer claims unrelated messages as health replies.
- Authenticated ROOTLINE physical presence enters a typed five-minute,
  command-inert specialist boundary before health classification.
- This PR adds the bounded ROOTLINE continuation adapter. It accepts fresh
  presence only when exactly one governed commissioning authorization exists,
  and advances only to supervised read-only configuration discovery. It grants
  zero configuration-write, hardware-command or Telegram authority.
- Existing family-message persistence and Telegram delivery remain the only
  delivery mechanism.
- The relay validator recognizes confirmed backend-owned delivery rather than
  representing it as caller-send failure. It adds no trigger or send node.
- PR #684's consumer now has an existing-store runtime coordinator, canonical
  operating-loop loader, owner-bound provenance loader, active-lifecycle
  suppression and durable audit replay readback. Missing Mona/Mysikind/Baby
  provenance stays Unknown.

## Bounded production recovery

After exact review/merge/deployment, acquire one recovery guard for Telegram
3179 and invoke the deployed generic gateway with its preserved authenticated
envelope exactly once. Require one new visible Pig 125 lifecycle card, zero
farm rows, and an exact preview question for last-seen-alive and body-discovery
evidence. An identical recovery must create zero sends, edits, packets or rows.

The recovery guard binds owner, private chat, Telegram 3179, provider timestamp,
content digest, GateKeeper 61909, relay 61910, exact deployment and recovery
purpose. Before invoking, read the existing family-lifecycle attempt/delivery
events and authoritative Telegram/n8n chronology. If a delivered message ID,
chat, bot identity and exact text digest are proven, use
`bind_existing_card` and send nothing. If an attempt exists without conclusive
provider delivery or conclusive absence, stop as
`family_message_delivery_ambiguous`: zero retry, zero edit and zero farm write.
Telegram offers no general bot-message history lookup, so this ambiguous state
cannot truthfully guarantee a visible card. The production success criterion
is therefore at-most-one send with provider-confirmed identity plus durable
readback; otherwise exact quarantine, never an unsafe retry.

Recover Telegram 3181 only as stale historical evidence. Deliver at most one
contained acknowledgement; do not dispatch or actuate. After the reviewed
adapter is deployed and re-proves the unique commissioning authorization, Oom
Sakkie may send one readiness request. A fresh response can be accepted only
for supervised read-only configuration discovery. No ON/OFF/configuration
write is authorized by this mission.
