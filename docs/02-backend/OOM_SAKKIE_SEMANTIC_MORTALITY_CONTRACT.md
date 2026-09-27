# Oom Sakkie mortality conversation handoff

Status: implementation reference; non-doctrine. Source qualification is separate
from deployment, real model evaluation and owner-visible operational acceptance.

The controlling semantic-first rule remains in the Vault Mission Standard. This
reference describes its bounded implementation for the existing single-animal
health/loss journey; it does not replace agent doctrine or grant farm authority.

## Meaning and responsibility

Oom Sakkie's existing semantic front door interprets a natural report once.
HERDMASTER receives structured facts, not a paraphrase that must match another
list of date or death expressions. The existing specialist resolves canonical
identity and chronology, prepares the protected preview, and uses the existing
confirmation and recording services. No additional model call, scheduler,
conversation store, action framework or database migration is introduced.

The model receives the original provider timestamp, South African timezone and
bounded active-case question/facts. Relative dates use that original timestamp,
not the later recovery cycle's date. The model must keep burial dates separate
from death/discovery dates and must not invent missing dates, causes or times.

## Contract

`SemanticInterpretation.mortality_observation` is an optional object with only:

| Field | Meaning |
| --- | --- |
| `animal` | Exact tag, name or Pig ID appearing in the quoted owner words |
| `death` | `dead`, `alive`, or `unknown` |
| `date` | ISO death/discovery date, or `null` for explicitly uncertain/conflicting dates |
| `disposal` | `removed`, `buried`, `removed_and_buried`, `cremated`, `disposed`, or `unknown` |

Each supplied field has exactly `value` and `quote`. Quotes must be verbatim
substrings of the current owner message. Unmentioned fields are omitted. A
short date answer supplies only a date; the earlier report remains retained.
Questions and hypothetical future reports are not observations.

The authenticated caller binds each fact to its actual provider message ID and
timestamp. The model cannot supply those identities. Validation rejects malformed
values, absent quotations, missing source records, future source timestamps and
conflicting animal references. Calendar, canonical chronology and exact animal
resolution remain deterministic. The existing protected preview displays the
proposed normalized date and original owner reports so the owner can correct an
interpretation before any farm effect.

## Continuity and recovery

The existing health/loss mission and report parts retain field-level source
bindings. Manager-question partial replies retain the same facts and original
IDs before passing them to that specialist. No manager observation is promoted
to farm truth merely because a receipt exists.

A semantic continuation may attach to one unambiguous open case without matching
a phrase list. Multiple cases remain ambiguous unless the message identifies
one. A reply to one animal's card cannot move another animal's facts into it.
An explicit correction replaces the affected fact and invalidates the old
preview. Unknown replaces previous certainty. A correction that the animal is
alive cancels the death preview without asking the answered question again;
it does not automatically close unrelated welfare work.

The existing retained recovery adapter carries the typed facts into a fresh
canonical preview. Repeated delivery and confirmation retain the existing
single-use claim and idempotent recording rails. Scheduled recovery does not
re-run the language model. Historical reports without typed facts retain the
legacy compatibility evaluator; their migration is not declared complete.
Compound farrowing/litter outcomes and other domains retain their own contracts.

## Qualification and acceptance

- `tests/test_oom_sakkie_mortality_semantic_journey.py`: real semantic parser,
  manager partial-answer adapter, specialist evaluator, case retention, preview
  buttons, uncertainty, cancellation, corrections, identity and replay guards.
  Model responses and I/O are isolated fixtures, not a live model evaluation.
- `tests/test_oom_sakkie_retained_report_recovery_postgres.py`: the existing real
  disposable-database manager delivery/callback/readback/replay journey also
  accepts typed source facts with wording the legacy parser cannot resolve.
  Provider sends and human confirmations are simulated, never production.
- The hosted audit includes the general-manager worker suite as well as the new
  semantic journey suite, closing the earlier worker coverage gap.

Release acceptance still requires the exact deployed revision, a genuine
owner-visible protected preview, the owner's confirmation, canonical readback,
provider delivery evidence and a later independent manager cycle. Passing these
source tests alone proves neither a farm outcome nor full agent autonomy.
