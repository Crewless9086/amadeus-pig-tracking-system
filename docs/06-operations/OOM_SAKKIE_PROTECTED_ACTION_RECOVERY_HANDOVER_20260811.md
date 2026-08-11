# Oom Sakkie protected mortality and grouped-weight recovery

## Stage

Deployed and historical reconciliation complete. PR #820 merged at
`ede07ab78a4a2617e420a172b0baf9bfdf752cfb`; SQL follow-up PR #821 merged at
`1e6f77e69bfe91b1c15cfbeaaecc675473073b39`. Live descendant revision
`011f466b140b651794ff4abb6ba98d15bb77c265` contains both changes. Broad
production runtime is released. Business completion remains automatically
waiting for one future genuine mortality or grouped-weight journey.

## Authoritative reconciliation

Provider chronology proves mortality messages `3515`, `3517`, and confirmation
`3518`; the explicit owner date was 2026-08-06. The former 2026-08-11 current
projection has been corrected append-only to 2026-08-06. Grouped-weight messages `3519`, `3521`, and `3523`
prove the original four-row report, the defective one-row Bonnie preview, and
the unrelated manager response. Canonical readback independently proves one
11 August batch containing Bonnie 64.4 kg, Waki 70.0 kg, Zigay 71.4 kg, and
Teena 69.2 kg, with all four currently in D3. Those correct rows must not be
replayed or rewritten.

## Reusable contract

`protected_action_claims.py` owns an opaque, expiring, owner/private-chat and
provider-card-bound claim. The claim binds the exact preview digest, evidence
generation, identities, row count, weights, date, and movements. Callback and
natural confirmation precede generic manager routing. Grouped execution locks
every pig, revalidates current eligibility, and commits the batch, every weight,
every movement, and claim completion in one transaction. Completion edits the
same provider card once and removes its keyboard. Stale, unauthorized,
ambiguous, expired, concurrent, mismatched, or replayed claims perform no farm
or provider effect.

The grouped parser accepts newline, comma, semicolon, and sentence separation,
including hyphen/colon facts, one shared ISO date, and one shared pen movement.
Pen identity comes from canonical Supabase evidence rather than the legacy
sheet path.

Mortality previews use the same buttons (`Bevestig`, `Verander`, `Kanselleer`)
and revalidate their stored preview SHA and animal identity against the active
HERDMASTER lifecycle before the existing governed mortality writer runs.

## Pig 130 correction

`mortality_date_correction.py` and
`scripts/correct_pig130_mortality_date.py` define the separately governed,
append-only operation `HERD-MORTALITY-CORR-PIG130-20260811`. It preserves the
original exit event, appends a superseding lifecycle correction, and updates
only the current effective date from 2026-08-11 to 2026-08-06. Removal/burial,
no visible signs in other pigs, and pen cleaning remain owner-attributed;
exact time, cause, diagnosis, and treatment remain Unknown. The writer requires
sealed owner authority plus the exact canonical correction digest, and exact
replay is a zero-write result.

Production created correction `MORT-CORR-7A9DEE33DADE2035FA3923D1` and
superseding event `LIFE-CORR-7A9DEE33DADE2035FA3923D1`. Original event
`LIFE-HL-7B7FFE5D6715F1B2A2FD628D` remains unchanged. Readback proves current
Dead/off-farm date 2026-08-06; replay changed zero rows. The four existing
11 August weights remain one batch and all four canonical pens remain D3.

## Acceptance and resumption

Independent farm-operations/CX and backend/security/authority reviews approved;
exact-head and exact-merge core, audit-rail, and browser gates passed. The
deployed lifecycle now waits automatically for a
genuine owner-created mortality or grouped-weight report. Do not manufacture or
request a test fact. Business completion requires one complete preview, working
button, exact matching transaction/readback, one completion edit, and zero-
effect replay.

Durable release: `C:/tmp/oom-sakkie-protected-actions-production-release-20260811.md`,
SHA-256 `48B75B63980C5964BBC85500652A142FB16F3C64BBB5356EEE964C0486F93B5D`.
