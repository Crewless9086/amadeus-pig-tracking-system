# DMQ-20260816-01 - GREEN 0.3.11 release-order addendum

Status: `DURABLY LOGGED - NOT YET AN OWNER OUTCOME` after reviewable commit.

## Finding

Home Assistant exposed add-on version 0.3.11 from the merged repository
manifest while governed immutable publication run `32900638205` was still in
arm64 startup verification. The owner selected the visible update and Home
Assistant reported an unknown install error. This is provider-visible evidence
that the release sequence exposed a version before its image was available.

No retry was requested. Once the exact publication completed, the pending Home
Assistant installation naturally advanced and read back as installed 0.3.11,
latest 0.3.11 and up-to-date.

## Exact publication evidence

- Source: `3b3a3365e27dd13a602a006b6e5ab3020b69a533`
- Workflow: `32900638205` / success
- Release packet artifact: `green-print-0.3.11-verified-release-packet`
- Index/tag digest:
  `sha256:63e4e5aadcd4af92fee4d0f50a856bd784f201562f02d66664f9515c96016a45`
- Sole platform: `linux/arm64`
- Signature, provenance and SBOM attestation: verified by the governed workflow
- Public repository manifest and GHCR tag: version 0.3.11 visible with the same
  source revision and digest

## Classification and containment

Classification: existing-mission release-order defect/addendum under
`DMQ-20260816-01`. No reprioritization. No new job, replay, recovery request or
print was created. The existing job identity remains authoritative.

Required later bounded repair: publish and verify the immutable image before
merging or otherwise exposing the repository manifest version. The repair must
retain immutable tags and exact source/digest evidence; it must not introduce a
mutable latest tag or a second publication route.

GREEN 0.3.11 was subsequently installed and started by the owner. Its natural
same-job claim exposed the separately registered timestamp-contract defect and
remained pre-attempt. The next automatic action is reviewed API repair, normal
deployment and natural same-job recovery. Printing and physical paper remain
unproven.

OWNER ACTION: NONE.
