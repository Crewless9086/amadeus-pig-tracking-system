# Green Print 0.3.1 non-actuating commissioning preflight

Status: decision packet only. Owner outcome achieved: `NONE`. Usable now: `NO`.

## Bound release and dormant state

- Deployed authoritative main: `02816350d8eebecf93a6353ae90bc4f0e78787f9`.
- Valid immutable 0.3.1 image digest:
  `sha256:b660fffbc7985f7b5d8f2550f2dbbf779966e5167d51e063051fb1890a10bdd5`.
- Owner-observed Home Assistant state: app 0.3.1 installed, `Stopped`, Start on
  boot OFF, Watchdog OFF, Auto update OFF, and never auto-started.
- Invalid 0.3.0 remains quarantined. Never install, use, attest further,
  overwrite, delete or reuse it.

This packet does not authorize app Start/configuration, option entry, secrets,
private identifiers, network or printer access, CUPS queue creation, a job, a
test page, a farm document, migration or physical printing.

## Safe local preparation completed

Current source fixes the pilot to `farm.weekly_weight_sheet.v1`, A4, one copy,
monochrome and one-sided. It requires verified private HTTPS to the canonical
service, private IP-literal IPPS with matching certificate identity, one fixed
registered queue, least-privilege claims, AppArmor, no published ports, tmpfs
spool and `/data` recovery state. These are reviewed contracts, not commissioned
facts.

Prepare a private commissioning worksheet outside chat/source/logs with empty
fields for farm, Green, printer, queue, registry version, canonical origin,
pinned private endpoint, IPPS URI, CA fingerprint and credential reference.
Values must come from governed provider/registry evidence; never invent them.

## Supervisor resolved-image proof deferred to technical preflight

Charl already supplied the available facts: version 0.3.1, Stopped, Start on
boot/Watchdog/Auto update OFF, never auto-started and aarch64. The Supervisor
digest and additional containment metadata were `NOT EXPOSED` and remain Unknown.
Do not ask Charl to repeat the page or recover technical metadata.

In a later separately authorised technical read-only zero-job window, the
maintainer must obtain the Supervisor-resolved digest and containment metadata
through the governed technical interface while the app remains stopped and no
configuration changes. The digest must equal the valid digest above. Mismatch,
unexpected start, privilege/port/mapping deviation or unavailable governed proof
is a stop condition.

## Private canonical route and TLS preflight

The technical maintainer prepares, without connecting from Green:

- one private HTTPS origin and one pinned private endpoint from its approved
  private DNS answer set;
- hostname/SAN, issuer, expiry and SHA-256 certificate fingerprint metadata;
- proof of private routing with no public fallback, port forward or tunnel;
- fixed read-only `/config/private-ca.crt` mapping plan;
- an exact zero-job validation procedure for a later protected window.

Do not place private IPs, certificate/CA contents or credentials in chat/source.
TLS verification may not be disabled.

## Printer IPPS and certificate inspection plan

In a separately authorised zero-submission window, the maintainer may perform
only a TLS/IPP capability handshake to the reserved private printer IP. Prove the
exact IPPS resource, protocol response, model, certificate subject/SAN/issuer/
fingerprint/expiry and that the private IP is in SAN. Send no document,
Create-Job, Print-Job or test-page operation. Ordinary IPP monitoring is not proof.

If IPPS is absent, the path differs, the certificate lacks the IP SAN, or trust
is Unknown, stop. Never fall back to ordinary/public IPP or weaken TLS.

## Protected identities, credential and fixed queue

The existing canonical registry—not app options—must resolve one exact farm,
Green, printer, registry version and fixed CUPS queue identity. Queue name is
configuration, never request input. The issuer prepares one revocable
least-privilege credential limited to atomic claim, digest-bound retrieval,
fenced transition and protected-command receipts for that pair. Record only
references/fingerprints in evidence. Nothing is created or entered by this packet.

## Proposed protected zero-job commissioning authority

After review of all observations, request one exact authority to verify the
Supervisor digest; register the device pair/queue; provision CA/credential through
protected channels; enter reviewed options once; start with boot/watchdog OFF;
prove AppArmor/no ports/private HTTPS/IPPS, `event_waiting`, heartbeat, empty queue
and zero eligible jobs; then stop and prove zero canonical/provider/physical effect.
This authority must prohibit print submission. Physical acceptance is separate.

## Rollback and stop conditions

On digest, privilege, TLS, identity or queue mismatch; leaked value; unexpected
start/job; or submission-like printer response: stop the app, keep boot/watchdog
OFF, revoke any new credential, preserve content-free evidence and reconcile.
Do not delete `/data`, alter firmware, weaken TLS or improvise another queue.

## Smallest owner actions and completion truth

Owner action now: `NONE`. Control Tower and the technical maintainer own all safe
preparation without repeat owner observations. After technical preparation, one
exact zero-job commissioning approval may be required. Physical acceptance remains
a later separate protected decision and genuine natural request.

Target owner outcome: one genuine natural request produces exactly one correct
physical weekly weighing sheet with canonical/CUPS/physical agreement, safe
cleanup, automatic follow-up and a later terminal-independent cycle.

Owner outcome achieved: `NONE`. Usable now: `NO`; resolved-image readback,
route/TLS, IPPS identity, protected identities/credential/queue, zero-job
commissioning, genuine print and later continuity remain unproven.
