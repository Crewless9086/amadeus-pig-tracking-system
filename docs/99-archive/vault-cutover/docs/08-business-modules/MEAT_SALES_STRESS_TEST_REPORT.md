# Sam Meat Sales Stress-Test Run

- Scenarios: 44
- Passed: 44
- Failed: 0
- Known improvement opportunities: 0

## Category Coverage

- `assisted_slaughter`: 1
- `authority_pressure`: 1
- `budget`: 1
- `butcher_match`: 2
- `change_mind`: 1
- `channel`: 3
- `custom_cut`: 1
- `cut_set_question`: 3
- `delivery`: 2
- `document_request`: 1
- `followup`: 1
- `frustration`: 1
- `full_carcass`: 1
- `happy_path`: 2
- `ignore`: 2
- `language`: 1
- `location_pin`: 2
- `missing_fact`: 4
- `payment`: 3
- `price_objection`: 1
- `test_cleanup`: 1
- `typos`: 1
- `vague_interest`: 1
- `whatsapp_window`: 1
- `wrong_product`: 2

## Recommendations

- No known gaps recorded.

## Failures

- No launch-blocking stress assertions failed.

## Sam v3 Replay Addendum - 2026-06-23

Sam v3 LLM-first shared-context replay tests were added beside the deterministic meat-sales stress pack.

Covered:

- Beacon/Facebook meat-post context handed into Sam's context packet.
- Warm social reply such as `Yummy` uses LLM wording instead of the old menu script.
- Existing delivery context prevents repeated address prompts.
- No-intent fade-out can produce `no_reply`.
- Unsafe LLM claims about money, payment, booking, slaughter, butcher, or delivery are blocked before customer send.
- Quote/document requests are overridden by the backend document gate.
- POP/payment-proof messages are overridden by the POP-vs-bank payment gate.
- The v3 policy only reports usable when both `SAM_MEAT_BACKEND_AGENT_V3_ENABLED=1` and `SAM_MEAT_BACKEND_LLM_ENABLED=1` are set with model/API key configured.

Verification:

- `python -m unittest tests.test_sam_v3_shared_context tests.test_sam_v3_replay_stress tests.test_sam_meat_runtime tests.test_sam_meat_stress` passed.
- `python -m unittest tests.test_sam_meat_stress` passed.
- `python scripts/sam_meat_stress_test.py` passed 44/44.
- `python -m unittest tests.test_sales_transaction_routes tests.test_chatwoot_hygiene tests.test_sales_conversation_learning tests.test_sam_farm_knowledge` passed.
