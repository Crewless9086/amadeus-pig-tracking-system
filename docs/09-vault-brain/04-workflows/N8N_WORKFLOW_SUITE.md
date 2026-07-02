# n8n Workflow Suite

Status: active runtime reference.

n8n is an integration/orchestration layer, not the source of farm truth.

## Suite Map

| Workflow | Role | Authority |
| --- | --- | --- |
| `1.0 - SAM - Sales Agent - Chatwoot` | Customer-facing inbound sales hub. | May reply and call approved steward actions inside gates. |
| `1.1 - SAM - Sales Agent - Escalation Telegram` | Human reply bridge from Telegram to Chatwoot. | Sends human-approved replies only. |
| `1.2 - Amadeus Order Steward` | Backend order action worker. | Calls Flask APIs; must not directly write order sheets. |
| `1.3 - SAM - Sales Agent - Media Tool` | Customer media sender. | Disabled until fixed/tested and approved. |
| `1.4 - Outbound Order Notification` | Backend-triggered approval/rejection customer messages. | Sends exact backend-provided text only. |
| `1.5 - Outbound Document Delivery` | Backend-triggered quote/invoice PDF delivery. | Sends backend-generated documents only. |
| `1.6 - Daily Order Summary` | Scheduled order report. | Read-only reporting; no order mutation. |
| `2 - The GateKeeper` | Oom Sakkie Telegram gateway. | Authorization/routing only. |
| `2.0 - OOM SAKKIE` | Farm assistant/orchestrator. | Read-only/tool-dispatch unless approved tools exist. |
| `2.1/2.1.1` | Weather/forecast tools. | Read current/forecast backend payloads. |
| `2.2` | Sunsynk/power tool. | Should use backend telemetry payloads, not raw sheet scans. |
| `2.3.x` | Irrigation plan/status/control family. | Status read-only unless backend command/audit control is approved. |
| `2.4.x` | Order approval/lookup/document callbacks. | Backend-owned approval/document gates. |

## Decision Modes

- `AUTO`: continue with system logic and order processing when enough facts exist.
- `CLARIFY`: ask one useful follow-up question or answer without backend processing.
- `ESCALATE`: hand to a human and stop automated customer reply where human action is required.

## Field Ownership

Protected fields:

- `decision_mode`;
- `escalation_raw_output`;
- `ai_reply_output`;
- `cleaned_reply`;
- `order_state`;
- `requested_items[]`;
- `conversation_mode`;
- `pending_action`;
- `order_id`;
- `order_status`;
- `payment_method`;
- `sales_lane` and `meat_*` Chatwoot fields.

High-risk field: `output`. Important outputs must be copied into dedicated fields before merge/switch/external call nodes.

## Non-Negotiable Rules

- n8n must not directly write operational order Google Sheets.
- Formula-driven Google Sheets are read-only.
- Customer cancellation requires two-turn confirmation.
- SAM may only say a quote/document was sent after backend/steward delivery confirms it.
- `1.4` must not rewrite backend approval/rejection messages.
- `1.5` must not calculate VAT, totals, document refs, or invoice eligibility.
- Chatwoot custom attribute writes must preserve the full required snapshot.
- Disabled media workflow `1.3` must not be enabled until attribute preservation and media approvals are tested.

## Source References

- `docs/04-n8n/WORKFLOW_MAP.md`
- `docs/04-n8n/WORKFLOW_RULES.md`
- `docs/04-n8n/DATA_FLOW.md`
- `docs/04-n8n/NODE_RESPONSIBILITIES.md`
- `docs/04-n8n/DO_NOT_CHANGE.md`
- `docs/04-n8n/CHATWOOT_ATTRIBUTES.md`
