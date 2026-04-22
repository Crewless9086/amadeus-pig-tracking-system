# Workflow Rules

## Decision Modes
- AUTO → proceed with system logic
- CLARIFY → ask ONE question only, no backend processing
- ESCALATE → send to human

## Critical Rule: CLARIFY
When decision_mode = CLARIFY:
- DO NOT modify AI Sales Agent response
- DO NOT pass through Final Replay Composer
- DO NOT create or update orders
- MUST use AI Sales Agent reply directly

## AUTO Flow
When decision_mode = AUTO:
- Continue to order processing
- Build or update draft if applicable
- Use Final Replay Composer ONLY for:
  - confirmations
  - summaries
  - structured replies

## Output Priority
Reply must follow this hierarchy:
1. AI Sales Agent output (if CLARIFY)
2. Final Replay Composer output (if AUTO)
3. Fallback → aligned_reply_seed

## No Rewriting Rule
If AI Sales Agent already answered:
→ DO NOT ask the same question again

## One Question Rule
Never ask more than one follow-up question.

## Data Integrity
- Do not overwrite fields unnecessarily
- Preserve `output` correctly through flow
- Do not mix classifier output with reply output