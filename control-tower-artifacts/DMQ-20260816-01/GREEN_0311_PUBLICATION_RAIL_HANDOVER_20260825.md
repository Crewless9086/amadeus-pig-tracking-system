# DMQ-20260816-01 - GREEN 0.3.11 publication rail handover

Status: `DURABLY LOGGED - NOT YET AN OUTCOME` after reviewable commit.

Publication preflight at merged worker revision
`69775e4856de5fff697c276789afd7151e7fadf4` found the governed workflow still
pinned `VERSION: 0.3.10` even though the add-on manifest is 0.3.11. No workflow
was dispatched, avoiding collision with the existing immutable 0.3.10 tag.

This bounded existing-mission repair updates only the normal publish/recover
version, package binding, SBOM and release packet to 0.3.11. The historical
0.3.10 partial-publication recovery lane and its exact evidence names remain
unchanged. Tests bind both contracts separately.

Merge is not publication. Acceptance requires one exact-commit governed
publication, immutable tag/digest, native signature, build provenance, SBOM
attestation and add-on repository visibility before Home Assistant installation.
Installation and the existing job's later natural processing remain separate.

OWNER ACTION: NONE.
