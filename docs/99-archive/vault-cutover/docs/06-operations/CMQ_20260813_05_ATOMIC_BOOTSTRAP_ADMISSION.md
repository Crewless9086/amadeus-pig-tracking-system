# CMQ-20260813-05 Atomic Bootstrap Admission

Status: reviewed source contract; no admission performed by this document

## Authorized identity

This contract is restricted to existing owner-approved mission
`CMQ-20260813-05`. It is not a general portfolio-admission API.

The sealed authenticated private action must receive exactly:

- portfolio epoch: `CORE-CURRENT-2026-08-14`;
- classification: `current`;
- universal lifecycle: `WORKING`;
- admission version: `portfolio_admission_v1`;
- admission evidence: `owner_approved_cmq_20260813_05_bootstrap`;
- decision authority: `human_control_tower`;
- dispatch authority: `human_control_tower`;
- runnable: `false`.

Any missing, additional, altered, aliased or cross-mission value fails before a
mission-store write.

## Atomic canonical effect

`modules/charlie/private_tools.py` passes the structured admission with the
unchanged opaque ID into `record_mission(..., exact_identity=True)`.
`modules/charlie/mission_store.py` uses the existing Supabase mission/event
transaction to persist one canonical mission row with execution status
`paused`, the structured admission in canonical `metadata_json`, one ordinary
`created` event and one `portfolio_admitted` event.

The `paused` execution status and `runnable:false` admission are deliberately
separate from the owner-outcome lifecycle `WORKING`. They keep the bootstrap
row outside approved runner pickup, automated recovery, dispatch and release.
Normal portfolio enforcement and all other admissions remain later reviewed
stages of the controlling Portfolio Baseline Plan.

## Replay and conflict

The mission store serializes the normalized title and exact opaque ID. An exact
replay must match ID, title, raw text, execution status and the entire
structured admission. It returns the existing canonical mission without a
second event. A different admission, identity, title or raw text returns a
conflict without creating or altering another mission.

## Authority boundary

This contract creates no route, schema, queue, scheduler, process, agent or
ledger. It does not enable Shadow scoring, prompt delivery, terminal control,
mission dispatch, release, provider messaging, farm writes, n8n authority or
Google Sheets authority. Human Control Tower remains the sole decision and
dispatch authority.
