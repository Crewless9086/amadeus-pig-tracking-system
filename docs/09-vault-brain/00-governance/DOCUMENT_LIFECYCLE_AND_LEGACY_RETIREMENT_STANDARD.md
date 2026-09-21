# Document Lifecycle and Legacy Retirement Standard

Status: controlling documentation-governance standard.

## Purpose

Amadeus must retain historical evidence without allowing superseded experiments
to steer new implementation. Old technology is a lesson and migration source,
not permanent architecture merely because its files remain in the repository.

## Required classification

The Agentic Operating Mission Standard at
`docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md`
remains authoritative by its tracked identity and owner-directed status. This
standard cannot demote, supersede or reinterpret it.

Every new or materially changed planning, architecture, workflow and operating
document must use one of these lifecycle classifications:

- `authoritative`: current controlling doctrine;
- `active`: current implementation/reference under authoritative doctrine;
- `transitional`: temporarily required with named replacement and exit test;
- `historical`: evidence only; never implementation authority;
- `retired`: replacement proven; may be archived or deleted after retention
  review;
- `quarantined`: contradictory, unsafe or unverified; must not be consumed.

Existing repository vocabulary maps as follows when its designation comes from
the document itself or an authoritative Vault/source map:

| Existing designation | Lifecycle classification |
| --- | --- |
| owner-directed operating standard, controlling standard, controlling programme, authoritative | `authoritative` |
| active, active runtime reference, current implementation/reference | `active` |
| transitional, migration bridge, compatibility/fallback pending named proof | `transitional` |
| historical, archive, evidence only, superseded | `historical` |
| retired, replacement proven | `retired` |
| quarantined, contradictory, unsafe or unverified | `quarantined` |

Until Phase 0 classifies them individually, documents already designated
controlling or active by the authoritative Vault or source maps retain that
established authority. This grandfathering is migration-only: it does not make
an unlisted, stale or merely old document active, and it ends for each document
when Phase 0 records its explicit classification.

An existing document without an established designation is non-authoritative.
Its presence or historical use alone grants no authority. New or materially
changed documents without an explicit lifecycle classification are likewise
non-authoritative until corrected.

## Supersession rule

A superseded document must receive a visible banner naming:

1. its classification;
2. the authoritative replacement;
3. what evidence remains useful;
4. what must no longer be implemented; and
5. the retirement owner or next proof.

Search/source maps must prefer the authoritative replacement. Historical files
must not remain in an `Active Docs` list.

## Build and terminal rule

Before using a legacy n8n, Google Sheets, local relay or architecture document,
a terminal must check the active source map and the Agentic Farm Runtime
Programme. It must challenge any request that would:

- create another channel-specific business path;
- make n8n or Sheets a new source of truth;
- duplicate a durable scheduler or canonical action;
- restore a retired integration without fresh owner approval; or
- preserve technology solely because it already exists.

The challenge must offer the smallest forward-compatible alternative. It must
not obstruct an urgent safe containment action.

## Cleanup procedure

Cleanup is evidence-led and reversible:

1. inventory references, runtime use and unique evidence;
2. classify the document/component;
3. name replacement and owner;
4. prove the replacement with real readback;
5. remove active discovery links;
6. disable runtime use behind a reversible gate;
7. observe the rollback window;
8. archive or delete only after unique evidence is retained elsewhere;
9. update source maps and changelog in the same mission.

Dirty worktrees, unique screenshots, provider evidence and unmerged branches are
not cleanup candidates merely because they are old.

## Approved Local Workspace Layout

The owner-approved Windows layout is:

- `C:\Amadeus\repo`: the single everyday source and durable-document checkout;
- `C:\Amadeus\.runtime`: assigned temporary worktrees, working evidence, tests,
  caches and disposable outputs, outside the project checkout;
- `C:\Amadeus\recovery\20260919`: the single consolidated recovery location for
  preserved old work, manifests and restore material.

Do not create nested repository copies, working reports or caches inside the
everyday checkout, OneDrive, generic `C:\tmp`, AppData or user document folders.
Durable reviewed doctrine, the current-state projection and selected necessary
receipts remain in their governed tracked paths. Working evidence becomes a
durable receipt only by explicit selection, not by copying entire output trees.
These paths are workspace policy, not proof that migration has completed.

Bound runtime growth to explicitly assigned active worktrees and output
directories. Do not create speculative spare checkouts or repeated full copies.
Before adding one, close out or classify its predecessor and record why another
copy is necessary. At closeout, preserve unique commits/evidence in recovery,
verify the manifest and a restore path, then remove only exact approved inactive
temporary directories. Unknown contents or ownership block deletion. Any
separately agreed storage cap must be checked before new bulk output.

The approved consolidation may retire preserved old worktrees and folders only
after verified backup and exact obsolete-path classification. Unmerged commits,
dirty work and failed attempts remain recoverable. Archiving a working copy does
not complete its mission, establish admission, authorize release, prove deployed
operation or clear a hold. The original project root also remains until supported
application project routing is changed and verified. Never edit an application's
internal database to force that transition.

## Periodic audit

CORE must run a documentation/runtime drift audit at each programme phase exit
and at least monthly while migration is active. The audit reports contradictory
authority, stale active links, legacy runtime dependencies and retirement debt.
