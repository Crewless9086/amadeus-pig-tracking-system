# OP-004 live-transfer and treatment-disclosure contract

Status: replacement preview, zero write. The earlier Tags 123/151 purpose-only preview is
`SUPERSEDED_BY_OWNER_RULE_CORRECTION` and must not be confirmed, replayed, or reused.

## Governed distinction

An active medicine withdrawal blocks slaughter and food-chain entry for its governed period.
It does not independently prove or prohibit live transfer. Live transfer is a separate result of
current, attributable transport fitness, quarantine, notifiable/infectious-disease, veterinary
movement-stop, serious health/welfare, treatment-evidence, purpose, active/on-farm, and order
gates. Missing evidence remains `Unknown`; it is never interpreted as clearance or zero risk.
The cited residue guidance supports withdrawal and traceability only and is not independent
authority for live transfer.

## Versioned read packet

HERDMASTER owns `herdmaster_live_transfer_disclosure_v1`. It is a bounded, repeatable-read,
read-only projection over canonical Supabase pig, medical, order, and order-line truth. Every pig
has independent axes with `state`, an exact supported `reason`, and attributable evidence IDs:

- livestock-transfer eligibility;
- food-chain eligibility;
- fit for transport;
- quarantine;
- notifiable/infectious disease;
- veterinary movement stop;
- serious health/welfare hold;
- treatment-evidence completeness and conflicts;
- current purpose and active/on-farm state; and
- current order eligibility.

The packet carries `writes_performed: false`, creates no order line or reservation, generates no
document or acknowledgement, and is bound by a deterministic `packet_digest`.

## Canonical production evidence at 2026-08-16

Order `ORD-2026-A6EC6D` is Draft/Pending, requests two piglets in `5_to_6_Kg`, and has one
existing line.

Tag 123, Pig ID `PIG-2026-A643`, is Active, on farm, purpose Sale, and had a 5.6 kg canonical
weight on 2026-08-11 (`5_to_6_Kg`). It is already present once as draft, unreserved line
`OL-2026-01E24C`. Its 2026-07-06 canonical treatment evidence contains two same-clinical-signature
Ecomectin events (`MED-9123C224`, `MED-F924E93D`) and two same-signature Panacur events
(`MED-9F6BF68A`, `MED-576D5EC7`). The contract preserves all four events, reports possible
duplicate treatment evidence, and blocks live-transfer support until the conflict is governed.
It does not remove or alter the existing order line.

The exact unresolved pairs are:

- Ecomectin 1%, 1.0 ml, treatment date 2026-07-06: `MED-9123C224` recorded
  2026-07-06T19:18:15.251687+00:00 and `MED-F924E93D` recorded
  2026-07-06T19:27:59.439910+00:00, both attributed to `web_app`, with no sheet row or import batch.
- Panacur 4%, 1.25 gram, treatment date 2026-07-06: `MED-9F6BF68A` recorded
  2026-07-06T19:18:16.345424+00:00 and `MED-576D5EC7` recorded
  2026-07-06T19:28:00.498868+00:00, both attributed to `web_app`, with no sheet row or import batch.

The rows have identical clinical signatures within each pair but distinct identities and timestamps.
That cannot establish whether they are duplicated records or separate administrations. An attributable
owner or treating veterinary professional must state the physical fact for each pair. The current
`pig_medical_events` schema contains neither predecessor nor supersession fields. The append-only
`pig_observation_events.supersedes_observation_event_id` rail can preserve factual correction evidence
for the same pig, but cannot govern or rewrite a medical event. Any future medical correction must add
governed append-only medical lineage rather than delete, merge, update, or suppress these rows.

The existing line is reported as `existing_line_blocks_duplicate`. The SAM writer checks existing active
lines, but the database has no unique active `(order_id, pig_id)` constraint. Any later writer work is
blocked on SAM adding transaction-safe canonical uniqueness or locking; this contract creates no second
line, reservation, or allocation.

Tag 151, Pig ID `PIG-2026-B156`, is Active, on farm, and purpose Sale. Its latest canonical
weight is 4.0 kg on 2026-08-11 (`2_to_4_Kg`), which does not match the order's `5_to_6_Kg`
request, and it has no order line. Medical event `MED-6DEF1FD54736F134C2F1D25B` records
Ecomectin 1%, 1.0 ml, on 2026-08-11, withdrawal 28 days through 2026-09-08, recorded at
2026-08-11T16:23:19.682893+00:00 by the attributable owner-admin principal. Its evidence digest
is `d780387645f291403bb2544b86c1bf7a3c3486f837633ff5e3cbe1133a3aff0c`.

Tag 151 is prohibited from food-chain entry through 2026-09-08. Live-transfer support is
`Unknown`, not approved or prohibited by that withdrawal alone, because the available canonical
snapshot contains no current attributable clearance for transport fitness, quarantine,
notifiable/infectious disease, veterinary movement stop, or serious health/welfare state.

Canonical source ownership for those missing gates is: current health/welfare facts from effective
non-superseded `pig_observation_events`; location chronology from `pig_location_events`; and quarantine,
disease, veterinary movement-stop, and transport-fitness facts from attributable veterinary or
competent-authority evidence projected through that canonical health boundary. No current typed clearance
event exists for either pig. Tag 151 movement event `MOV-C0F1D295929E5AC3461755BE` proves the
2026-08-11 weaning move only; it does not prove fitness or movement clearance.

The active Supabase price book contains `PRICE-YOUNG_PIGLETS_2_TO_4_KG_ANY`, ZAR 350, effective
2026-05-21, for Tag 151's current band. The order header requests `5_to_6_Kg`, whose corresponding
active rule is ZAR 400. The order model supports line-level band and unit price, so a separately priced
`2_to_4_Kg` line is technically representable, but it is a commercial departure from the requested
order band. It must be presented later as one protected SAM preview with the exact ZAR 350 consequence;
this contract does not change the order, price, weight, line, reservation, or allocation.

Safe buyer wording (`livestock_treatment_disclosure_en_v1`):

> Tag 151 received Ecomectin 1% on 2026-08-11. Food-chain withdrawal applies through
> 2026-09-08; do not slaughter or enter the animal into the food chain during that period. This
> treatment disclosure does not certify fitness for transport or veterinary, welfare, disease,
> quarantine, or movement clearance.

## Document projections — design only

- Loading Sheet: show exact pig identity, snapshot identity, every live-transfer gate, and the
  separate food-chain restriction.
- Removal Certificate: show medical-event identity, product/date, withdrawal end, wording and
  document versions, and evidence/disclosure digests.
- Health Declaration: disclose treatment evidence and every Unknown/blocking veterinary,
  disease, quarantine, welfare, movement, and transport axis without asserting clearance.
- Quote / Order Confirmation: disclose treatment and food-chain restriction before acceptance,
  state exact order-line presence, and bind any later acknowledgement to that version.

Each later document projection must bind order, order line, pig, medical event, medical digest,
wording version, document identity, and document version. No production document is generated by
this contract.

## Buyer acknowledgement — design only

A future append-only `livestock_disclosure_snapshot_v1` binds order, order line, pig, medical
event, medical-evidence digest, wording version, document type/ID/version, buyer identity, and
acknowledgement time. Acknowledgement proves receipt only; it establishes no clearance. Changed
canonical medical evidence changes the digest, marks prior disclosure/document versions outdated,
and requires a new snapshot and acknowledgement without mutating the medical event or history.
No snapshot or acknowledgement is created in this stage.

## Source ownership and handover boundary

- HERDMASTER owns canonical livestock calculations, evidence/provenance, conflicts, Unknowns,
  food-chain versus live-transfer separation, wording identity, and the zero-write packet.
- SAM/orders and document-generation own any later authorized order-line action, immutable
  snapshot persistence, document versions/projections, buyer acknowledgement, and safe document
  delivery. They must consume HERDMASTER states without recalculating livestock safety.
- CODEX UI may render the packet and one bound confirmation journey. It may not infer clearance,
  suppress Unknowns, recalculate eligibility, accept arbitrary destinations, or activate records.

No Google Sheets or n8n business authority is introduced. No competing medical record, writable
table, production configuration, pig/order change, document, or buyer acknowledgement is created.

## Zero-write production proof

The exact live packet digest at the 2026-08-16 cutoff is
`d153d3e95aeb65466c560c586e2b529855110a578db43c8ba13f0b697e00ec35`.
Before and after the bounded read, canonical row counts were identical: pigs 301,
pig medical events 479, orders 31, order lines 135, order documents 35, and operational events 12.
The read therefore created no purpose event, order membership, reservation, price, document,
acknowledgement, or unrelated farm mutation.
