# Component Ownership

## Purpose

This file defines ownership boundaries so agents, humans, and build tools do not guess.

## Ownership Model

| Component | Owns | Does not own |
| --- | --- | --- |
| CHARLIE CORE | Owner-level orchestration, summaries, decisions, and cross-business command. | Live data storage, unsafe autonomous action, or bypassing approvals. |
| Oom Sakkie | Farm command, farm specialist coordination, owner farm summaries. | Top-level business orchestration outside CHARLIE or customer sends. |
| SAM Meat Sales | Customer fact gathering, draft replies, meat lead recovery planning. | Sending customer messages without approved rails. |
| FRED Transport | Planned transport lead/opportunity command. | Dispatch, quote send, deposit request, or driver commitment without rails. |
| Gatekeeper | Approval boundaries, blocked states, owner decision enforcement. | Bypassing owner approval. |
| Supabase | Live operational source of truth. | Human guidance documents. |
| Flask backend | Business rules, validation, route contracts, safe reads/writes. | Replacing owner approval. |
| Chatwoot / WhatsApp | Communication transport. | Core brain or source of truth. |
| n8n | Workflow runner/integration helper. | Core brain or authority owner. |
| Google Sheets | Legacy input/operator views where still used. | Final operational truth for new collaboration state. |
| Markdown / Brain / Vault | Human-readable guidance and decisions. | Live operational state. |
| Cursor / Codex | Build workshop and patch execution after approval. | Production runtime brain. |

## Rule

Supabase is truth. Markdown is guidance.

Operational writes must go through backend validation and approved rails.

No route, agent, workflow, or assistant may bypass Gatekeeper.
