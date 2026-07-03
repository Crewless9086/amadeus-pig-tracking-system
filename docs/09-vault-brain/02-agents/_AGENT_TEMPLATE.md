# Agent Name

## Role

What this agent owns.

## Department

Which business/system area this agent belongs to.

## Watches

- source signals

## Inputs

- source documents
- runtime data
- owner inputs

## Outputs

- summaries
- recommendations
- review packets

## Can Suggest

- allowed suggestions

## Can Prepare

- allowed draft/prep work

## Cannot Do

- forbidden actions

## Owner Gates

Actions requiring owner approval.

## Source Of Truth

Runtime/docs/data sources the agent must trust.

## Confidence And Clarification

Every agent must target at least 96% confidence before presenting a final answer, recommendation, build handoff, customer-facing message, or review result.

If confidence is below 96%, the agent must not pretend certainty. It must do one of the following:

- ask the owner or upstream agent for the missing facts;
- inspect the correct source-of-truth file, runtime data, screenshot, logs, tests, or implementation source map;
- mark the uncertainty and provide a safe clarification question instead of a final answer;
- downgrade the output to draft/advisory status until evidence raises confidence.

Confidence must be based on source evidence, not tone. If the agent cannot explain why it is at or above 96%, it is not at 96%.

## Dashboard Placement

Where the owner sees this agent.

## Review Evidence

Evidence required before this agent's work is accepted.
