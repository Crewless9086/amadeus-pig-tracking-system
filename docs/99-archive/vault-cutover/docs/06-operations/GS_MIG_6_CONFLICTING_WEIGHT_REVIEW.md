# GS-MIG-6 Conflicting Weight Review And Reconciliation

Date: 2026-06-29

## Status

Read-only review/reconciliation complete. No app routes have been cut over.

## Safety

- No Google Sheets writes.
- No Supabase writes.
- No route cutover.
- No customer sends, public posts, payments, reservations, or lifecycle/purpose writes.

## Supabase Reconciliation

| Table | Expected | Imported | Delta | Status |
| --- | ---: | ---: | ---: | --- |
| `app_settings` | 18 | 18 | 0 | match |
| `farm_products` | 3 | 3 | 0 | match |
| `litters` | 17 | 17 | 0 | match |
| `mating_events` | 15 | 15 | 0 | match |
| `pens` | 20 | 20 | 0 | match |
| `pig_location_events` | 179 | 179 | 0 | match |
| `pig_medical_events` | 261 | 261 | 0 | match |
| `pig_weight_events` | 1190 | 1190 | 0 | match |
| `pigs` | 217 | 217 | 0 | match |

## Derived Views

| View | Rows |
| --- | ---: |
| `pig_current_state` | 217 |
| `pig_latest_location_events` | 113 |
| `pig_latest_weight_events` | 155 |

## Conflicting Weight Groups For Review

These rows were excluded from the canonical import. They must not affect current weight, meat readiness, allocation, stock valuation, or dashboards until reviewed.

| Review ID | Pig ID | Date | Candidate weights | Source rows | Status |
| --- | --- | --- | --- | --- | --- |
| CW-001 | PIG-2026-0874 | 2026-02-02 | 12.2, 16.4 | 2 | pending_owner_review |
| CW-002 | PIG-2026-12D8 | 2026-03-23 | 2.3, 2.8 | 2 | pending_owner_review |
| CW-003 | PIG-2026-3E84 | 2026-03-02 | 10.8, 110.8 | 2 | pending_owner_review |
| CW-004 | PIG-2026-42B7 | 2026-05-04 | 130, 132.4 | 2 | pending_owner_review |
| CW-005 | PIG-2026-6D24 | 2026-05-11 | 3.39, 3.4 | 2 | pending_owner_review |
| CW-006 | PIG-2026-8FFC | 2026-02-09 | 27.2, 32.8 | 3 | pending_owner_review |
| CW-007 | PIG-2026-A5EA | 2026-03-17 | 36.6, 37.4 | 2 | pending_owner_review |
| CW-008 | PIG-2026-E926 | 2026-05-11 | 10.8, 9.2 | 2 | pending_owner_review |
| CW-009 | PIG-2026-EFB3 | 2026-05-25 | 54.4, 55.2 | 2 | pending_owner_review |

## Source Row Details

### CW-001 - PIG-2026-0874 on 2026-02-02

| Sheet row | Weight_Log_ID | Pig name | Weight kg | Pen | Notes |
| ---: | --- | --- | ---: | --- | --- |
| 64 | WGT-2960590D |  | 16.4 |  |  |
| 65 | WGT-39E475C0 |  | 12.2 |  |  |

### CW-002 - PIG-2026-12D8 on 2026-03-23

| Sheet row | Weight_Log_ID | Pig name | Weight kg | Pen | Notes |
| ---: | --- | --- | ---: | --- | --- |
| 363 | WGT-3C7DE5E0 |  | 2.3 |  |  |
| 364 | WGT-DA1F669B |  | 2.8 |  |  |

### CW-003 - PIG-2026-3E84 on 2026-03-02

| Sheet row | Weight_Log_ID | Pig name | Weight kg | Pen | Notes |
| ---: | --- | --- | ---: | --- | --- |
| 239 | WGT-FDCE9354 |  | 110.8 |  |  |
| 240 | WGT-2405CDA4 |  | 10.8 |  |  |

### CW-004 - PIG-2026-42B7 on 2026-05-04

| Sheet row | Weight_Log_ID | Pig name | Weight kg | Pen | Notes |
| ---: | --- | --- | ---: | --- | --- |
| 769 | WGT-1B36FA4A |  | 130 |  |  |
| 770 | WGT-EB4B59CD |  | 132.4 |  |  |

### CW-005 - PIG-2026-6D24 on 2026-05-11

| Sheet row | Weight_Log_ID | Pig name | Weight kg | Pen | Notes |
| ---: | --- | --- | ---: | --- | --- |
| 907 | WGT-ECBEF9DB |  | 3.39 |  |  |
| 908 | WGT-D54DFE48 |  | 3.4 |  |  |

### CW-006 - PIG-2026-8FFC on 2026-02-09

| Sheet row | Weight_Log_ID | Pig name | Weight kg | Pen | Notes |
| ---: | --- | --- | ---: | --- | --- |
| 14 | WGT-3D4E83A4 |  | 27.2 |  |  |
| 15 | WGT-220BD750 |  | 27.2 |  |  |
| 16 | WGT-3F68810D |  | 32.8 |  |  |

### CW-007 - PIG-2026-A5EA on 2026-03-17

| Sheet row | Weight_Log_ID | Pig name | Weight kg | Pen | Notes |
| ---: | --- | --- | ---: | --- | --- |
| 165 | WGT-A1B518A3 |  | 37.4 |  |  |
| 166 | WGT-2A222C59 |  | 36.6 |  |  |

### CW-008 - PIG-2026-E926 on 2026-05-11

| Sheet row | Weight_Log_ID | Pig name | Weight kg | Pen | Notes |
| ---: | --- | --- | ---: | --- | --- |
| 881 | WGT-7F17023A |  | 10.8 |  |  |
| 883 | WGT-80866A1D |  | 9.2 |  |  |

### CW-009 - PIG-2026-EFB3 on 2026-05-25

| Sheet row | Weight_Log_ID | Pig name | Weight kg | Pen | Notes |
| ---: | --- | --- | ---: | --- | --- |
| 995 | WGT-E60C4940 |  | 54.4 |  |  |
| 996 | WGT-373ACB80 |  | 55.2 |  |  |

## Conflict Exclusion Check

| Review ID | Pig ID | Date | Imported rows for conflict key | Status |
| --- | --- | --- | ---: | --- |
| CW-001 | PIG-2026-0874 | 2026-02-02 | 0 | excluded |
| CW-002 | PIG-2026-12D8 | 2026-03-23 | 0 | excluded |
| CW-003 | PIG-2026-3E84 | 2026-03-02 | 0 | excluded |
| CW-004 | PIG-2026-42B7 | 2026-05-04 | 0 | excluded |
| CW-005 | PIG-2026-6D24 | 2026-05-11 | 0 | excluded |
| CW-006 | PIG-2026-8FFC | 2026-02-09 | 0 | excluded |
| CW-007 | PIG-2026-A5EA | 2026-03-17 | 0 | excluded |
| CW-008 | PIG-2026-E926 | 2026-05-11 | 0 | excluded |
| CW-009 | PIG-2026-EFB3 | 2026-05-25 | 0 | excluded |

## Recommendation

Do not cut over app routes yet. Next step is owner/admin review of the 9 conflicting-weight groups, followed by route-by-route shadow verification against Supabase canonical reads.
