# SAM Sales Autonomy Level 1

Level 1 grants SAM Meat and SAM Livestock standing authority for low-risk,
evidence-supported conversational replies. Agentic interpretation may propose
the content; the shared deterministic contract decides whether customer
dispatch is allowed.

The contract requires exact account, conversation, contact, inbox and inbound
message identity; current chronology; an open channel window; persisted review
evidence; a safe response review; and a Tier 1 next action. It reuses the
existing durable delivery-attempt and provider-delivery rail. Chatwoot
acceptance remains unverified, and no retry is automatic.

Supported Tier 1 work includes approved product/process information, fresh
availability or truthful shortage evidence, useful qualification questions and
an explicit explanation that availability is not reserved. Missing or stale
availability must omit counts, answer supported parts, say availability is
being confirmed and ask one useful question.

Evidence is claim-scoped, not response-global. Missing price, availability,
delivery or exact-animal evidence blocks only the corresponding unsupported
claim. It does not block a claim-free clarification or supported product
guidance.

Customers are never expected to know the farm's internal livestock taxonomy.
When category or size is unclear, SAM must translate the choices into ordinary
buyer language with approximate weight ranges:

- small piglets: approximately 2 to 6 kg;
- weaned piglets: approximately 7 to 19 kg;
- growing pigs: approximately 20 to 49 kg;
- larger pigs: approximately 50 to 79 kg;
- slaughter-size pigs: approximately 80 kg and above.

SAM then asks only the smallest genuinely missing qualification fact, normally
which size suits the buyer. It never repeats quantity, sex or another fact
already known. It must not ask only for an unexplained category or `size/type`.
These ranges explain the offer; they do not assert current availability,
reserve animals, or replace the authoritative price list.

Binding quotes, discounts, delivery promises, orders, money, refunds,
reservations, allocations, carcass commitment, slaughter booking, farm writes,
complaints and exceptional terms remain owner exceptions. The contract
prepares one owner card with the recommended decision, commercial consequence
and next executable action.

Code defaults are disabled. The first production cohort is separately enabled
for no more than five exact conversation and inbound-event identity pairs. Every attempt is claimed
before dispatch, every accepted message awaits provider delivered/read truth,
and the cohort stops on the first incorrect interpretation, unsupported claim
or authority breach. A provider failure or ambiguous result quarantines only
that exact claimed conversation/send, prohibits retry, and does not prevent
the next unrelated exact binding from being evaluated. The full cohort stops
only for a systemic provider outage, corrupted claim rail, cross-binding
identity/chronology collision, or authority breach. Provider delivered/read
evidence remains mandatory before counting a customer as delivered. Broad
dispatch remains a separate explicit gate.

After supervised acceptance, Livestock may use the isolated append-only
`sam_live_stock_level1_control_events` contract instead of rewriting shared
Render environment keys for each cohort. The latest event is the kill switch:
`enabled` permits only Livestock ordinary Level 1, while `disabled`, `killed`,
missing, malformed, stale, or unavailable control evidence permits no
dispatch. Activation applies only to authoritative inbound observations at or
after its UTC cutoff plus explicitly listed current follow-up bindings; it
never replays the historical inbox. The control is owner-admin authenticated
with a server-derived principal, contains no customer content, and grants no
Meat or protected authority. GateKeeper remains the sole inbound owner.

Display names are untrusted presentation text. Safe Unicode, spacing,
punctuation, and emoji may be normalized for a greeting, but account, inbox,
conversation, contact, inbound, attempt, chronology, and provider identities
alone bind authority. Control characters, markup, unreasonable length, or
commercial claims disguised as a name are removed or rejected and are never
placed in credentials, headers, commands, or provider identity fields.

The reviewed runtime controls are default disabled:

- `SAM_SALES_AUTONOMY_LEVEL=1` selects this contract;
- `SAM_SALES_LEVEL1_MEAT_ENABLED` and
  `SAM_SALES_LEVEL1_LIVE_STOCK_ENABLED` are independent lane switches;
- `SAM_SALES_LEVEL1_COHORT_ENABLED` enables only the exact first cohort;
- `SAM_SALES_LEVEL1_COHORT_BINDINGS` contains no more than five exact
  `conversation_id:inbound_message_id` pairs; independent identity lists and
  cross-pair membership are prohibited;
- `SAM_SALES_LEVEL1_COHORT_STOPPED` immediately withholds cohort dispatch;
- `SAM_SALES_LEVEL1_BROAD_DISPATCH_ENABLED` remains false until the supervised
  cohort passes and a separate production decision enables the current inbox.

Configured identities grant authority but never supply identity evidence.
Authoritative Chatwoot chronology must independently prove the exact latest
public inbound and an open provider reply window. Source-backed claim checks
and the response review run before the existing append-only delivery claim.
Only a newly created claim may precede a send. Failed, ambiguous, replayed, or
concurrent outcomes never retry automatically.
