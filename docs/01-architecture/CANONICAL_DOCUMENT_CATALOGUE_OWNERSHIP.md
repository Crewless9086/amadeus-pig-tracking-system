# Canonical document catalogue ownership map

Status: Mission 1 source foundation. This is descriptive metadata, not a document ledger or business authority.

`modules/documents/catalogue.py` is the single backend-owned, channel-neutral catalogue contract. Supabase remains intended canonical truth; rows below explicitly disclose where current generators still use transitional Google Sheets or operator-entered evidence. The catalogue has no route, generator callable, send adapter, persistence, scheduler, or print adapter.

| Identity | Existing owner/generator | Current contract truth |
| --- | --- | --- |
| `farm.weekly_weight_sheet.v1` | HERDMASTER; `/print-sheets`, `templates/print-sheets.html`, `static/js/printSheets.js` | HTML preview supported from transitional Supabase-first livestock/pen reads with bounded Sheets fallback; PDF and Telegram unsupported; physical/direct-print eligibility Unknown |
| `farm.weight_report.v1` | HERDMASTER; `/weight-report`, `templates/weight-report.html`, `static/js/weightReport.js` | HTML preview supported from transitional Supabase-first weight/pig reads with bounded Sheets fallback; PDF and Telegram unsupported; physical/direct-print eligibility Unknown |
| `farm.mating_litter_record.v1` | HERDMASTER; `/paring-werpselrekord`, template and JS of the same name | Afrikaans HTML preview supported from transitional Supabase-first mating/litter reads with bounded Sheets fallback; PDF and Telegram unsupported; physical/direct-print eligibility Unknown |
| `sales.loading_sheet.v1` | SAM; `loading_sheet_service.generate_loading_sheet_for_order` | PDF and existing owner-Telegram delivery supported from transitional Supabase reads with Sheets fallback; preview and direct print Unknown |
| `sales.removal_transport.v1` | SAM; `movement_documents_service.generate_removal_certificate_for_order` | PDF and existing owner-Telegram delivery supported from transitional Supabase reads with Sheets fallback plus operator/default movement facts whose authority may be Unknown; preview and direct print Unknown |
| `sales.health_declaration.v1` | SAM; `movement_documents_service.generate_health_declaration_for_order` | PDF and existing owner-Telegram delivery supported; medical evidence authority, preview and direct print Unknown; current generator accepts operator health notes |
| `sales.quote.v1` | SAM; `quote_service.generate_quote_for_order` | PDF supported from transitional mixed Supabase plus Sheets fallback/overlay; catalogue Telegram delivery unsupported; preview/direct print Unknown |

An order confirmation is not catalogued because no distinct generator was proven. Existing invoice and SAM Meat PDF generators remain owned by their current sales domains and are not silently reclassified as order confirmations.

## Evidence boundaries

- **Documented capability:** the rows above and architecture/operations documents describe intent and ownership.
- **Runtime-loaded capability:** application routes load the three HTML print views; ReportLab generators load quote, invoice, loading, movement, health and SAM Meat documents. This mission does not activate or alter them.
- **Provider-verified delivery:** none was performed in this mission. Source contains direct Telegram `sendDocument`, Chatwoot attachment, Google Drive and transitional n8n paths; source presence is not a fresh provider receipt.
- **Physical printer facts:** Unknown. No printer, driver, queue, paper, duplex, availability, or successful physical output was requested or inferred.

OOM SAKKIE identity, protected-callback, unified semantic input, Anton `farm_manager`, and Afrikaans contracts remain in their existing modules. The catalogue separates authenticated human roles from requesting application/agent identities. Adapters must authenticate first, enforce both sets, bind Telegram delivery to the authenticated recipient/chat, preserve the canonical `generator_id`, record the declared audit/idempotency fields without sensitive payloads, and fail closed for unsupported or Unknown delivery.

## Mission 2 bounded integration recommendation

Integration owner: OOM SAKKIE, with HERDMASTER retaining document/data authority.

Exact source scope: `modules/documents/catalogue.py`; a new HERDMASTER weekly-weight PDF adapter under `modules/pig_weights/`; a new OOM SAKKIE document-request adapter under `modules/oom_sakkie/`; and focused corresponding tests. Existing `/print-sheets`, templates, JavaScript, generator layouts, protected callback runtime, unified semantic front door, family identity policy, and Telegram transport should be reused and changed only if a separately evidenced defect requires it. Mission 2 must bind `farm.weekly_weight_sheet.v1` to `web.print_sheets.v1`, accept Anton only through the existing `farm_manager` principal, reply in Afrikaans, preserve Unknown facts, and obtain a real provider receipt only during its authorized acceptance phase.
