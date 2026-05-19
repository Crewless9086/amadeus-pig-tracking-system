# Database Scaling Plan

## Purpose

Phase 7.2 planning for moving transactional order data away from Google Sheets when volume or reliability requires it.

Status: Phase 7.2 planning accepted. Do not implement a database migration from this document until a future database implementation phase is deliberately opened.

## Current Decision

- Keep Google Sheets as the operational source of truth for now.
- Treat recent Sheets `429` quota errors as a scaling warning, not an immediate production blocker.
- Build toward Postgres, with Supabase Postgres the preferred provider to evaluate first.
- Keep n8n, Sam, and future agents behind backend APIs. They must not write directly to Postgres.
- Preserve Google Sheets operator visibility until the web app has replacement views or Sheets are safely synced as read-only views.

Owner update 2026-05-18:

- Supabase Pro has been created at the USD 25/month tier.
- This does not change the build gate: do not move production data yet.
- Treat the Pro project as available infrastructure for the planned migration phase, after repository boundaries, migrations, import rules, backups, and rollback checks are ready.

When setup starts, collect these details step by step:

- Supabase project URL and project reference.
- Database connection string for backend server use, stored only in Render environment variables.
- Service-role key only if a backend-admin path truly needs it; never expose it to the browser or n8n unless deliberately approved.
- Anon key for future frontend read/write paths only if Row Level Security policies are designed first.
- Region, database password custody, backup/PITR settings, and restore-test plan.
- Separate development/staging decision before production data is imported.
- Approved schema migration tool and where migrations will live in this repo.

## First Migration Boundary

The first migration should focus on sales/order transaction data only:

- `ORDER_MASTER`
- `ORDER_LINES`
- `ORDER_INTAKE_STATE`
- `ORDER_INTAKE_ITEMS`
- `ORDER_DOCUMENTS`
- `ORDER_STATUS_LOG`
- `SALES_PRICING`

Do not include full piggery records in the first migration unless a separate stability problem appears. Pig records, weight logs, mating records, and stock availability can stay in Sheets for the first database phase.

## Adjacent Dependencies

These sheets are not first-migration source tables, but they affect order behavior and must be planned:

| Sheet | Current role | 7.2 planning decision |
| --- | --- | --- |
| `ORDER_OVERVIEW` | Formula/read model for order list/detail summaries. | Replace with backend/Postgres read models later; keep while Sheets is source of truth. |
| `ORDER_STATUS_LOG` | Audit trail and daily summary transitions. | Migrate with the first order tables as `order_status_logs`; this is part of the order audit trail. |
| `SALES_AVAILABILITY` | Formula stock eligibility gate for order-line matching. | Keep in Sheets initially; order matching still reads it until pig/stock data migrates. |
| `SALES_PRICING` | Pricing lookup for line sync and quote totals. | Move to Postgres with an admin page; pricing changes must preserve historical order pricing. |
| `SYSTEM_SETTINGS` | Document generation settings. | Keep in Sheets initially; consider app settings table later. |
| `PIG_MASTER` | Updated when orders are completed. | Do not migrate in first order phase, but completion logic must still update pigs safely. |

## Backend Access Inventory

### Orders

| Module | Functions | Current sheet access |
| --- | --- | --- |
| `modules/orders/order_write.py` | `create_order`, `update_order`, `create_order_line`, `update_order_line`, `delete_order_line`, helpers | Reads/writes `ORDER_MASTER`, `ORDER_LINES`; reads `SALES_AVAILABILITY`; writes `ORDER_STATUS_LOG` through status helper. |
| `modules/orders/order_read.py` | `list_orders`, `get_order_detail`, `get_active_customer_order_context` | Reads `ORDER_OVERVIEW`, `ORDER_MASTER`, `ORDER_LINES`. |
| `modules/orders/order_line_sync.py` | `sync_order_lines_from_request`, helpers | Reads `ORDER_MASTER`, `ORDER_LINES`, `SALES_AVAILABILITY`, `SALES_PRICING`; writes/cancels `ORDER_LINES`; may auto-cancel through order lifecycle. |
| `modules/orders/order_reservation.py` | `reserve_order_lines`, `release_order_lines` | Reads/writes `ORDER_LINES`; updates `ORDER_MASTER.Reserved_Pig_Count`. |
| `modules/orders/order_lifecycle.py` | `send_order_for_approval`, `approve_order`, `reject_order`, `cancel_order`, `complete_order` | Reads/writes `ORDER_MASTER`, `ORDER_LINES`; writes `PIG_MASTER` on completion; writes `ORDER_STATUS_LOG`; sends n8n notifications. |
| `modules/orders/order_status_log.py` | `write_order_status_log` | Appends `ORDER_STATUS_LOG`. |
| `modules/orders/order_service.py` | `create_order_with_lines` facade/orchestration | Delegates to write/sync/lifecycle modules and quote helpers. |

### Intake

| Module | Functions | Current sheet access |
| --- | --- | --- |
| `modules/orders/order_intake_service.py` | `get_intake_context`, `update_intake_state`, `reset_intake`, helpers | Reads/writes `ORDER_INTAKE_STATE` and `ORDER_INTAKE_ITEMS`. |
| `scripts/setup_order_intake_infrastructure.py` | setup utility | Creates/validates intake sheet headers. Keep as historical setup until replaced by migrations. |

### Documents

| Module | Functions | Current sheet access |
| --- | --- | --- |
| `modules/documents/document_service.py` | document lookup, append, mark sent, send document | Reads/writes `ORDER_DOCUMENTS`; reads `SYSTEM_SETTINGS`; triggers n8n document delivery. |
| `modules/documents/quote_service.py` | quote readiness and generation | Reads order detail through order service, reads `ORDER_LINES` fallback, reads/writes `ORDER_DOCUMENTS` via document service, reads `SYSTEM_SETTINGS`, uploads PDF to Drive. |
| `modules/documents/invoice_service.py` | invoice generation | Reads order detail, latest quote/document records, settings; appends invoice records to `ORDER_DOCUMENTS`. |
| `scripts/setup_document_infrastructure.py` | setup utility | Creates/validates `ORDER_DOCUMENTS` and `SYSTEM_SETTINGS`. Keep as historical setup until replaced by migrations/settings admin. |

### Reports

| Module | Functions | Current sheet access |
| --- | --- | --- |
| `modules/reports/report_service.py` | `get_daily_order_summary` | Reads `ORDER_STATUS_LOG` and `list_orders()`. Any database move must preserve daily report inputs. |

## Minimum Postgres Tables

The first schema design should cover these tables:

| Table | Purpose | Key fields |
| --- | --- | --- |
| `orders` | Order header, replacing `ORDER_MASTER`. | `order_id`, customer fields, requested fields, payment method, lifecycle statuses, collection fields, conversation ID, timestamps. |
| `order_lines` | Order line and reservation state, replacing `ORDER_LINES`. | `order_line_id`, `order_id`, `pig_id`, sale category, weight band, sex, unit price, line status, reserved status, request item key, timestamps. |
| `order_intakes` | Conversation-level intake header, replacing `ORDER_INTAKE_STATE`. | `intake_id`, conversation/contact fields, draft order ID, intake status, known fields, next action, missing fields, timestamps. |
| `order_intake_items` | Intake item rows, replacing `ORDER_INTAKE_ITEMS`. | `intake_item_id`, `intake_id`, item key, quantity, category, weight range, sex, intent/status, linked order lines, match status. |
| `order_documents` | Quote/invoice metadata and delivery status, replacing `ORDER_DOCUMENTS`. | `document_id`, `order_id`, type/ref/version/status, totals, payment method, Drive file data, sent metadata. |
| `order_status_logs` | Order audit/history log, replacing `ORDER_STATUS_LOG`. | `status_log_id`, `order_id`, previous/new status fields, action, notes, actor/source, timestamps. |
| `sales_pricing` | Admin-managed pricing reference, replacing `SALES_PRICING`. | `pricing_id`, category, weight band, sex, unit price, effective dates, active flag, timestamps. |

Strong candidate later support table:

- `app_settings` for `SYSTEM_SETTINGS`

## Owner Decisions

Captured after owner review:

- `ORDER_STATUS_LOG` should migrate with the first order tables.
- `SALES_PRICING` should move to Postgres and receive a web admin page.
- Google Sheets should remain only during migration, not as the long-term operator system.
- Historical test data should not be imported.
- Old intake rows and test orders should be filtered so only useful business data is transferred.
- Pricing must use effective dates. A future price may be entered ahead of time, but it should only become active once its effective date arrives.
- Orders/customer records using the test name `Charl N` are test data and should be excluded from the production import.
- Real cancelled customer orders with documents or payments should be retained as archived history after a suitable period.
- Google Sheets should be retired systematically, table/view by table/view, only after the matching web app views and backend behavior are accepted.

Planning interpretation:

- Treat `order_status_logs` as required in the first order migration because approvals, cancellations, warnings, and daily reports depend on it.
- Move pricing into Postgres as a controlled reference table, but keep copied line prices on each order line so old orders, quotes, and invoices do not change when pricing is updated later.
- Store pricing changes as dated records, not direct overwrites. The app should select the active price by sale category, weight band, sex when needed, and effective date.
- Use Sheets as a temporary transition/read-only visibility layer during migration. Retire each sheet only after the web app has an accepted replacement view.
- Define objective import rules before migration so "useful data" is not decided manually row by row.
- Treat `Charl N` as the first explicit test-data exclusion rule. Add more test markers only when they are verified.
- Keep meaningful cancelled customer history, but it should not clutter active operational views.

## Draft Schema Detail

This is a planning schema, not an implementation migration. Field names can still change during technical design, but the data ownership should stay stable.

### `orders`

Replaces `ORDER_MASTER`.

| Field | Type direction | Notes |
| --- | --- | --- |
| `order_id` | text, unique | Keep existing `ORD-YYYY-######` public ID. |
| `order_date` | date/timestamp | From `Order_Date`; keep original value during import. |
| `customer_name` | text | Latest order customer name. |
| `customer_phone` | text, indexed | Normalize for lookup, but preserve original where needed. |
| `customer_channel` | text | Example: WhatsApp/Chatwoot route. |
| `customer_language` | text | Used by Sam/customer communication. |
| `order_source` | text | Example: Sam, Admin, Web App. |
| `requested_category` | text | Header-level legacy/simple request field. Detailed items live in `order_lines`. |
| `requested_weight_range` | text | Header-level legacy/simple request field. |
| `requested_sex` | text | Header-level legacy/simple request field. |
| `requested_quantity` | integer | Header-level legacy/simple request field. |
| `quoted_total` | numeric | Snapshot from quote/order flow. |
| `final_total` | numeric | Snapshot final total when known. |
| `order_status` | text, indexed | Draft/Pending_Approval/Approved/Rejected/Cancelled/Completed style values. |
| `approval_status` | text | Approval state separate from order lifecycle. |
| `payment_status` | text | Pending/Paid/Cancelled/etc. |
| `payment_method` | text | Cash/EFT; copied into documents. |
| `collection_method` | text | Collection/delivery when applicable. |
| `collection_location` | text | Riversdale/Albertinia/etc. |
| `collection_date` | date/timestamp | Customer collection date if known. |
| `reserved_pig_count` | integer | May become computed later; store initially for compatibility. |
| `conversation_id` | text, indexed | Chatwoot conversation ID. |
| `notes` | text | Admin/system notes. |
| `created_by` | text | System/Admin/Sam/etc. |
| `created_at` | timestamp, indexed | Source creation timestamp. |
| `updated_at` | timestamp | Source update timestamp. |
| `source_sheet_row` | integer | Import traceability. |
| `import_batch_id` | text | Import traceability. |

### `order_lines`

Replaces `ORDER_LINES`.

| Field | Type direction | Notes |
| --- | --- | --- |
| `order_line_id` | text, unique | Keep existing stable line ID. |
| `order_id` | text, foreign key | Links to `orders.order_id`. |
| `pig_id` | text, nullable | Links to current/future pig record when selected. |
| `tag_number` | text, nullable | Snapshot for operator visibility. |
| `sale_category` | text | Category requested/sold. |
| `weight_band` | text | Band requested/sold. |
| `sex` | text | Male/Female/Any/etc. |
| `current_weight_kg` | numeric | Snapshot at line creation/reservation. |
| `unit_price` | numeric | Copied price snapshot; must not change when price table changes. |
| `pricing_id` | text, nullable | Optional reference to `sales_pricing` record used. |
| `line_status` | text, indexed | Active/Cancelled/etc. |
| `reserved_status` | text, indexed | Reserved/Released/Confirmed/Collected/etc. |
| `request_item_key` | text, indexed | Links back to intake item and sync logic. |
| `notes` | text | Admin/system notes. |
| `created_at` | timestamp | Source creation timestamp. |
| `updated_at` | timestamp | Source update timestamp. |
| `source_sheet_row` | integer | Import traceability. |
| `import_batch_id` | text | Import traceability. |

### `order_intakes`

Replaces `ORDER_INTAKE_STATE`.

| Field | Type direction | Notes |
| --- | --- | --- |
| `intake_id` | text, unique | Keep existing stable intake ID. |
| `conversation_id` | text, indexed | Chatwoot conversation ID. |
| `account_id` | text, nullable | Chatwoot account ID. |
| `contact_id` | text, nullable | Chatwoot contact ID. |
| `customer_name` | text | Latest known name. |
| `customer_phone` | text | Normalized where possible. |
| `customer_channel` | text | Source/channel. |
| `customer_language` | text | Latest known language. |
| `draft_order_id` | text, nullable, indexed | Linked order once created. |
| `intake_status` | text, indexed | Open/Ready_For_Draft/Draft_Created/etc. |
| `collection_location` | text | Parsed/preferred location. |
| `collection_time_text` | text | Human text from conversation. |
| `collection_date` | date | Parsed date where known. |
| `collection_time` | time | Parsed time where known. |
| `payment_method` | text | Cash/EFT when known. |
| `quote_requested` | boolean | Customer asked for quote. |
| `order_commitment` | boolean | Customer wants to proceed/order. |
| `missing_fields` | json/text | Backend-computed missing fields. |
| `next_action` | text | Backend-computed next action. |
| `ready_for_draft` | boolean | Backend-computed readiness. |
| `ready_for_quote` | boolean | Backend-computed readiness. |
| `last_customer_message` | text | Last processed message. |
| `last_updated_by` | text | Sam/App/Admin/etc. |
| `created_at` | timestamp | Source creation timestamp. |
| `updated_at` | timestamp | Source update timestamp. |
| `closed_at` | timestamp, nullable | Closed timestamp. |
| `closed_reason` | text, nullable | Completed/cancelled/abandoned/admin_reset/etc. |
| `notes` | text | Admin/system notes. |
| `source_sheet_row` | integer | Import traceability. |
| `import_batch_id` | text | Import traceability. |

### `order_intake_items`

Replaces `ORDER_INTAKE_ITEMS`.

| Field | Type direction | Notes |
| --- | --- | --- |
| `intake_item_id` | text, unique | Keep existing stable intake item ID. |
| `intake_id` | text, foreign key | Links to `order_intakes.intake_id`. |
| `conversation_id` | text, indexed | Duplicated for lookup/debugging. |
| `item_key` | text | Stable key used for sync, e.g. `item_1`. |
| `quantity` | integer | Requested quantity. |
| `category` | text | Piglet/Weaner/Grower/Finisher/Slaughter/etc. |
| `weight_range` | text | Requested weight range. |
| `sex` | text | Male/Female/Any/etc. |
| `intent_type` | text | Add/change/remove style sync intent. |
| `status` | text, indexed | active/removed/replaced. |
| `linked_order_line_ids` | json/text | Line IDs created from this item. |
| `last_match_status` | text | exact_match/partial_match/no_match/etc. |
| `matched_quantity` | integer | Latest matched quantity. |
| `replaced_by_item_key` | text | Replacement tracking. |
| `removal_reason` | text | Customer/system removal reason. |
| `notes` | text | Admin/system notes. |
| `created_at` | timestamp | Source creation timestamp. |
| `updated_at` | timestamp | Source update timestamp. |
| `removed_at` | timestamp, nullable | Set when removed/replaced. |
| `source_sheet_row` | integer | Import traceability. |
| `import_batch_id` | text | Import traceability. |

### `order_documents`

Replaces `ORDER_DOCUMENTS`.

| Field | Type direction | Notes |
| --- | --- | --- |
| `document_id` | text, unique | Keep `DOC-YYYY-######`. |
| `order_id` | text, foreign key, indexed | Links to `orders.order_id`. |
| `document_type` | text | Quote/Invoice. |
| `document_ref` | text, indexed | Public reference, e.g. `Q-2026-XXXXXX`. |
| `payment_ref` | text | Short EFT reference. |
| `version` | integer | Quote/invoice version number. |
| `document_status` | text, indexed | Generated/Sent/Voided/Superseded. |
| `payment_method` | text | Snapshot at document generation. |
| `vat_rate` | numeric | Locked VAT rate snapshot. |
| `subtotal_ex_vat` | numeric | Snapshot. |
| `vat_amount` | numeric | Snapshot. |
| `total` | numeric | Snapshot. |
| `valid_until` | date | Quote validity date. |
| `google_drive_file_id` | text | Stored file ID. |
| `google_drive_url` | text | Stored internal lookup URL. |
| `file_name` | text | Generated PDF filename. |
| `created_at` | timestamp | Generated timestamp. |
| `created_by` | text | Admin/system actor. |
| `sent_at` | timestamp, nullable | Sent timestamp. |
| `sent_by` | text, nullable | Workflow/admin actor that sent it. |
| `notes` | text | Admin/system notes. |
| `source_sheet_row` | integer | Import traceability. |
| `import_batch_id` | text | Import traceability. |

### `order_status_logs`

Replaces `ORDER_STATUS_LOG`.

| Field | Type direction | Notes |
| --- | --- | --- |
| `status_log_id` | text, unique | Generate if legacy row has no stable ID. |
| `order_id` | text, indexed | Links to `orders.order_id` where available. |
| `previous_order_status` | text | Previous order status. |
| `new_order_status` | text | New order status. |
| `previous_approval_status` | text | Previous approval status where applicable. |
| `new_approval_status` | text | New approval status where applicable. |
| `previous_payment_status` | text | Previous payment status where applicable. |
| `new_payment_status` | text | New payment status where applicable. |
| `action` | text, indexed | approve/reject/cancel/complete/warning/etc. |
| `actor` | text | System/Admin/Sam/n8n/etc. |
| `source` | text | Backend route/workflow/tool. |
| `notes` | text | Human/system reason. |
| `created_at` | timestamp, indexed | Event timestamp. |
| `source_sheet_row` | integer | Import traceability. |
| `import_batch_id` | text | Import traceability. |

### `sales_pricing`

Replaces `SALES_PRICING` and adds effective-dated pricing.

| Field | Type direction | Notes |
| --- | --- | --- |
| `pricing_id` | text, unique | Stable pricing row ID. |
| `sale_category` | text, indexed | Category. |
| `weight_band` | text, indexed | Weight band. |
| `sex` | text, nullable | Optional future support; `Any`/blank applies generally. |
| `unit_price` | numeric | Current/future price value. |
| `currency` | text | Default `ZAR` unless changed later. |
| `effective_from` | date/timestamp, indexed | Price can only be selected from this date/time onward. |
| `effective_to` | date/timestamp, nullable | Optional close date when superseded. |
| `active` | boolean, indexed | Admin visibility flag; app must still respect effective dates. |
| `change_reason` | text | Why price changed. |
| `created_by` | text | Admin/system actor. |
| `created_at` | timestamp | Creation timestamp. |
| `updated_at` | timestamp | Last update timestamp. |
| `source_sheet_row` | integer | Import traceability. |
| `import_batch_id` | text | Import traceability. |

Pricing selection rule:

1. Match `sale_category`, `weight_band`, and `sex` where applicable.
2. Only consider rows with `active = true`.
3. Only consider rows where `effective_from <= order/quote date`.
4. Ignore rows where `effective_to` is set and `effective_to < order/quote date`.
5. Select the newest valid `effective_from`.
6. Copy the selected `unit_price` and `pricing_id` to the order line so future pricing edits do not alter old quotes, invoices, or orders.

## Migration Data Selection Rules

Draft import rules:

- Import active, pending, approved, completed, and other real customer orders.
- Import real cancelled orders only when they have customer history, documents, payments, delivery notes, or audit value.
- Archive real cancelled customer orders after the active operational period when they have documents, payments, or other business value.
- Exclude obvious test orders, test intake conversations, setup rows, duplicate dry-run rows, and cancelled orders that were only created for testing.
- Exclude rows where `Customer_Name` is `Charl N`; this is an explicit owner-confirmed test data marker.
- Preserve source sheet row IDs, original order IDs, and an import batch ID for traceability.
- Run a dry-run report before import showing included rows, excluded rows, and exclusion reasons.

## Google Sheets Retirement Rules

Retire Sheets systematically. Do not remove a sheet from operational use just because the data has been imported.

Per sheet/view retirement checklist:

- A matching web app view exists for the same operator job.
- The web app view has been checked against real data and accepted.
- Backend APIs return the same or better information than the Sheet view.
- Sam/n8n workflows no longer depend on the Sheet directly.
- Reports and daily summaries no longer depend on the Sheet formula output.
- Operators have a clear place to inspect, search, and correct the same business data.
- The Sheet is first made read-only/synced before it is fully retired.

Minimum replacement views before retiring order sheets:

| Sheet/View | Replacement needed before retirement |
| --- | --- |
| `ORDER_MASTER` | Web order list, order detail, create/update order controls, status/actions visibility. |
| `ORDER_LINES` | Order detail line table, reservation state, line cancellation/release visibility. |
| `ORDER_OVERVIEW` | Web/API order summary view with active/history tabs and filters. |
| `ORDER_INTAKE_STATE` | Intake/conversation context view or admin diagnostics for active intake state. |
| `ORDER_INTAKE_ITEMS` | Intake requested-items view tied to the order/customer conversation. |
| `ORDER_DOCUMENTS` | Document register in the web app with quote/invoice status, refs, totals, and send state. |
| `ORDER_STATUS_LOG` | Order history/audit timeline on the order detail page and report inputs. |
| `SALES_PRICING` | Admin pricing page with effective-date management. |

## Formula Replacement Strategy

Postgres will not work like Google Sheets cell formulas. The same logic should move into system-owned calculations:

| Current formula/data area | Future replacement |
| --- | --- |
| `ORDER_OVERVIEW` order summaries | SQL view, API read model, or backend summary builder over `orders`, `order_lines`, `order_documents`, and `order_status_logs`. |
| Order totals and line totals | Backend order-line calculation with stored snapshot values on `order_lines` and documents. |
| `SALES_PRICING` lookups | Postgres `sales_pricing` table with admin-managed effective prices; copied into order lines at the time of quote/order creation. |
| `SALES_AVAILABILITY` matching formulas | Keep in Sheets until pig/stock data migrates; later replace with SQL views over pig, weight, health, location, reservation, and order-line data. |
| Stock and sales summaries | SQL views/materialized views or backend report endpoints, depending on performance and freshness needs. |
| Document readiness checks | Backend service rules, because quote/invoice readiness depends on order status, line status, customer details, and payment fields. |
| Daily reporting formulas | Backend report service reading `order_status_logs` and order state from Postgres. |

Rule of thumb:

- Use backend services for business decisions and validation.
- Use SQL views for read-only summaries and list screens.
- Use stored snapshot fields when historical documents must not change.
- Avoid hiding critical business logic inside database triggers unless there is a strong reason.

## Required Indexes

At minimum:

- `orders.order_id` unique
- `orders.order_status`
- `orders.conversation_id`
- `orders.customer_phone`
- `orders.created_at`
- `order_lines.order_line_id` unique
- `order_lines.order_id`
- `order_lines.pig_id`
- `order_lines.request_item_key`
- `order_intakes.intake_id` unique
- `order_intakes.conversation_id`
- `order_intakes.draft_order_id`
- `order_intake_items.intake_id`
- `order_documents.document_id` unique
- `order_documents.order_id`
- `order_documents.document_ref`
- `order_documents.document_status`
- `order_status_logs.order_id`
- `order_status_logs.created_at`
- `sales_pricing.active`
- `sales_pricing.effective_from`

## Migration Approach

1. Add backend repository interfaces around order/intake/document persistence while still backed by Google Sheets.
2. Add tests at the repository boundary so business services do not care whether storage is Sheets or Postgres.
3. Design Postgres schema and migrations.
4. Build one-time import scripts from Sheets to Postgres with dry-run validation.
5. Run shadow comparison: Sheets remains live, Postgres is populated and compared but not served to users.
6. Move selected reads to Postgres behind a feature flag.
7. Move writes only after transactions, backups, rollback, and operator views are ready.
8. Keep Sheets read-only/synced for operator visibility until replacement web views are accepted.

## Migration Checklist And Rollback Gates

### Planning Gate

- Confirm final first-migration table list.
- Confirm schema field names and required indexes.
- Confirm import inclusion/exclusion rules for test data, cancelled orders, and old intake rows.
- Confirm the per-sheet web app replacement checklist before each sheet is retired.
- Confirm Supabase/Postgres provider, monthly cost expectation, backup settings, and restore process.
- Run a Claude Code review of the final implementation plan before coding begins.

### Build Gate

- Add repository interfaces while still using Google Sheets underneath.
- Add repository-level tests for create, update, list, detail, lifecycle, document, intake, and pricing paths.
- Add Postgres migrations only after repository tests pass against the current Sheets-backed behavior.
- Add import scripts with dry-run mode first.
- Add validation reports that compare source row counts, imported row counts, excluded row counts, totals, statuses, and document references.

### Dry-Run Gate

- Export/copy source Google Sheets data for a dry run.
- Run import dry run and review included/excluded rows.
- Confirm every excluded row has a reason.
- Confirm active orders, order lines, documents, intake links, and status logs reconcile against Sheets.
- Confirm pricing effective-date lookup returns the same current prices as `SALES_PRICING`.
- Confirm order list/detail API output matches current behavior for selected real orders.

### Shadow Mode Gate

- Populate Postgres without serving it to users.
- Keep Sheets as live source of truth.
- Compare selected backend read models from Sheets and Postgres.
- Monitor differences for order totals, active line counts, reserved counts, document lists, active customer context, and daily report inputs.
- Do not move writes while shadow comparisons are failing.

### Read Cutover Gate

- Move selected reads behind a feature flag.
- Start with low-risk read-only endpoints.
- Keep fallback to Sheets available.
- Confirm web app order list/detail, Sam active context, and reports still match accepted behavior.
- Record every mismatch as a migration blocker until resolved.

### Write Cutover Gate

- Freeze relevant Sheets or make them read-only/synced before Postgres becomes writable source of truth.
- Confirm database backups are enabled and a restore path has been tested.
- Confirm rollback plan is written and accepted.
- Move writes only after read cutover is stable.
- Keep n8n and Sam writing only through backend APIs.

### Rollback Rules

- Before write cutover, rollback means disabling Postgres reads and returning all reads to Sheets.
- After write cutover, rollback requires a written decision because Sheets may no longer contain every new write.
- Do not run dual writable systems without an explicit reconciliation plan.
- Keep import batch IDs and source row IDs so imported data can be identified or removed if a dry run or shadow load is wrong.
- If totals, document refs, order statuses, or active customer context do not reconcile, stop the migration and keep Sheets as source of truth.

## Implementation Gates

Do not start implementation until:

- 7.2A inventory is reviewed.
- Schema draft is accepted.
- Backup and rollback rules are written.
- A Claude Code review is run because this change crosses backend, web app, n8n, data contracts, and operations.
- Supabase/Postgres cost and backup settings are confirmed.

## Remaining Open Questions

- What retention period should apply before real cancelled customer orders move from normal history to archived history?
- Which additional names, phone numbers, conversation IDs, or order notes should be treated as verified test-data markers besides `Charl N`?
- Which exact web app replacement views should be built first when implementation eventually starts?
