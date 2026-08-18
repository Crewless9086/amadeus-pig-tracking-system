# Vault Cutover Batch 5 Reconciliation

Status: first bounded physical cleanup slice completed; no deletion authorized or performed.

Date: 2026-08-18

## Scope

Only the five top-level legacy governance files under `docs/05-ai/` were
reconciled and moved intact to
`docs/99-archive/vault-cutover/docs/05-ai/`. The agent-specific BEACON and SAM
subfolders remain in place for later bounded slices.

## Unique-fact disposition

| Archived source | Reconciliation result | Active authority |
| --- | --- | --- |
| `AGENT_PORTFOLIO_REVIEW.md` | Dated 2026-06-18 planning, readiness claims, build order, risks and owner answers are preserved as history. None is promoted as current state or doctrine. | Current mission state and priority remain in the Control Tower Mission Register; agent doctrine remains in focused Vault packs. |
| `AGENT_ROLES.md` | Role boundaries, staged authority, learning-as-evidence and specialist separation are already represented more precisely in the Agent Registry, focused agent files, workflows, rules and standards. Dated phase notes remain archive evidence. | `02-agents/AGENT_REGISTRY.md` plus the relevant focused agent pack. |
| `PROMPT_RULES.md` | Contains only a migration note stating that the predecessor was empty. No live prompt rule exists to extract. | Common governance and mission-specific Vault packs. |
| `README.md` | Contains only a legacy folder ownership/index statement. No unique rule exists. | `docs/09-vault-brain/README.md` and `ACTIVE_DOCS_SOURCE_MAP.md`. |
| `RESPONSE_RULES.md` | Its four short safety rules are retained and expanded in the Customer Response Standard and focused SAM rules. | `07-standards/CUSTOMER_RESPONSE_STANDARD.md` and the relevant SAM pack. |

## Safety result

- All five source files remain tracked with byte content preserved through Git
  renames.
- Every active exact-path reference was reconciled to a canonical Vault target
  or an explicit archive-evidence path.
- Archive files are excluded from ordinary doctrine retrieval.
- No runtime, provider, production-data, authority or agent behavior changed.
- No deletion candidate was created or approved.

## Next boundary

The next physical slice requires a fresh owner approval after this merge. It
must select one coherent family from the regenerated manifest and close that
family's exact extraction or reference blockers before moving anything.
