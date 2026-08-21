# Green Print Commissioning Inventory - 2026-08-21

Status: `DORMANT_INSTALLATION_OWNER_OBSERVED / STOPPED / START_ON_BOOT_OFF / NOT_COMMISSIONED`

Mission: existing DOCUMENTS mission `DMQ-20260816-01`, fixed pilot
`farm.weekly_weight_sheet.v1`, A4, exactly one copy, monochrome, one-sided.

Charl has authorized one bounded dormant installation step only: while GitHub main
is verified at `f5d6634b25142d95a943f2c7c10a89fbfd5a4383`, add the private Amadeus
repository and install `Amadeus Green Print Bridge` version `0.2.0`, never press
Start, and immediately prove the app is `Stopped` with `Start on boot` OFF before
leaving the page or rebooting. Charl subsequently observed that exact bounded
installation state: version `0.2.0` installed, `Stopped`, `Start on boot` OFF,
app never started, and no deviation.
If the app starts, cannot remain stopped, cannot disable Start on boot, or the
repository/package identity differs, stop/uninstall it and report the deviation.

This authorization does not include options, credentials, identities, certificates,
device mapping, CUPS/printer configuration or access, job creation, physical output,
commissioning or autonomous activation.

## Confirmed Home Assistant Green baseline

- Device: Home Assistant Green; Home Assistant OS installation; `aarch64`.
- Core `2026.8.2`; Supervisor `2026.07.5`; OS `18.2`; kernel `6.18.39-haos`.
- Apps store, three-dot menu, Repositories option and repository URL field are
  available. Advanced Mode is not separately exposed in this current UI, but the
  app/repository management functions required for commissioning are available.
  No private repository has been added.
- Post-update resources: 28 GB usable, 7.1 GB used (7.0 GB system data), 20.9 GB
  free; storage lifetime indicator 0% used; 4 GB RAM with 0.9 GB/20% used; CPU 1%;
  no storage or hardware warning.
- Full Home Assistant backup completed and downloaded; Emergency Kit stored outside
  Green.

## Source and package lineage

- Repository: `https://github.com/Crewless9086/amadeus-pig-tracking-system`.
- App: `Amadeus Green Print Bridge`; slug `amadeus_green_print_bridge`; package
  version `0.2.0`; stage `experimental`.
- Historical packaging lineage: PR #1150 head
  `35cdb8d7ce245e9192cad9e250be44909db34a38`, merged as
  `e027c403978ca3e5ccb5cc03a008c3075b76f941`.
- Historical PR #1150 is enabling evidence only. The current compatible Green
  migration/API/operational continuation is PR #1152 and must be independently
  approved, merged, migrated, deployed and verified before installation authority.

## Printer and LAN baseline

- Physical printer: HP OfficeJet Pro 8123; discovered IPP identity reports HP
  OfficeJet Pro 8120 series; firmware `6.23.6.41-202605070458`.
- A firmware update is available but was deliberately not installed; the printer
  was not restarted and no diagnostic or test page was printed.
- Wi-Fi/private LAN; current state idle; A4 loaded; black ink low; colour ink empty;
  no printer warnings.
- Existing Home Assistant IPP integration is installed and can read state/ink. It is
  monitoring only and is not the commissioned CUPS print adapter.
- Duplicate IPP discovery remains unconfigured.
- Router: TP-Link TL-WR840N. Green and printer are on the same normal private LAN,
  not Guest Wi-Fi. DHCP reservations exist for both.
- Router exposure inventory: zero Virtual Server rules; UPnP disabled/zero mappings;
  DMZ disabled; zero Port Triggering rules; no identified public tunnel or public
  Home Assistant/CUPS/printer exposure.
- The reserved printer IP exists but is deliberately omitted from this tracked
  non-secret artifact. It must be entered only through the protected secure record.

## Required private printing boundary

- Proposed URI shape: `ipps://<RESERVED-PRINTER-PRIVATE-IP>/ipp/print`.
- Exact IPP/IPPS path, IPPS response and commissioned URI remain unknown.
- Printer certificate subject, SANs, issuer, SHA-256 fingerprint and expiry remain
  unknown. The reserved private IP must be present in the accepted certificate SAN
  under the current contract.
- Intended CA filename/path: `private-ca.crt` at `/config/private-ca.crt`, read-only
  `addon_config` mapping. CA is not provisioned. Never store certificate contents or
  private keys in source, chat, screenshots or logs.
- TLS verification must remain enabled. Do not substitute ordinary IPP, public IPP,
  exposed ports, host networking or a verification bypass.

## Package capabilities requiring exact-current verification

- aarch64 image support; persistent `/data`; SQLite recovery ledger at
  `/data/green-print-ledger.sqlite3`; health at `/data/health.json`; tmpfs PDF spool;
  cold backup behavior; AppArmor; automatic boot/restart; local CUPS; no published
  ports, host networking, privileged access, Docker socket or USB/device mappings.
- All are package/design claims only until an exact-current aarch64 build and later
  authorized Home Assistant installation/commissioning prove them.

## Protected identities and connectivity still unknown

- Fixed CUPS queue name; Green ID; printer ID; farm/tenant ID; registry version;
  commissioned device-pair reference; canonical API origin and private endpoint IP;
  least-privilege bearer credential.
- Green-to-canonical private DNS/routing/HTTPS/certificate validation; additional
  outbound firewall restrictions.
- None may be invented or committed. Provision only after exact release authority
  through the protected registry/credential process.

## Explicit zero-activation state

- Private repository added and app version `0.2.0` installed; owner-observed status
  `Stopped`; `Start on boot` OFF; app never started; deviation none.
- Installation/version alone does not prove the exact installed image/source commit.
  `Dockerfile` defaults `SOURCE_COMMIT=unknown`, and no installed-image provenance
  inspection has occurred. Do not infer exact head `411da4b` or source `f5d6634b`
  from the displayed package version.
- CUPS app/service not started; no fixed queue or printer configuration.
- Private CA and adapter credential not installed.
- Green/printer registry pair not registered from Green.
- No canonical, synthetic or farm print job; no document submission; no physical
  page produced.

## Dormant installation authorization

- Approval state: exercised within scope and owner-observed complete; installation is
  enabling-stage progress only.
- Exact permitted effect: add the private repository and install package version
  `0.2.0` only while authoritative main is exact `f5d6634b25142d95a943f2c7c10a89fbfd5a4383`.
- Required final state: app `Stopped`; `Start on boot` OFF; no configured options;
  no printer/CUPS contact; no canonical job.
- Observed final state: version `0.2.0`; `Stopped`; `Start on boot` OFF; never
  started; deviation none.
- Wake condition: a separately prepared protected commissioning decision after all
  safe provenance/private-endpoint/IPPS/identity preparation is complete.
- Prohibited: Start, reboot before Start-on-boot is proven OFF, credentials,
  registry/device/queue values, private CA, IPPS URI, CUPS/printer access,
  commissioning, jobs and printing.
- Rollback on deviation: stop/uninstall the dormant package and report; do not
  improvise configuration or weaken TLS.

## First remaining gates

1. Charl performs one observation-only Home Assistant
   `Settings > Apps > Amadeus Green Print Bridge > Info` readback and returns the
   nine fields below. This readback is pending and must not be marked complete
   before Charl supplies it.
2. Establish exact installed-image/source provenance without starting the app.
3. Through separately protected commissioning, determine the exact IPPS endpoint and
   certificate metadata; validate SAN/trust without printing; register the exact
   private identities, queue and least-privilege credential.
4. Prove installed-image provenance and perform separately authorized zero-job,
   non-farm commissioning without weakening TLS or exposing ports.
5. Let deployed Oom Sakkie receive a genuine natural request only in a separately
   authorized physical acceptance window; prove one correct page,
   canonical/provider/physical agreement, safe cleanup/follow-up and a later
   terminal-independent cycle.

## Pending nine-field observation-only Info readback

Do not click Start, change a toggle, edit options, upload a CA, use Terminal/SSH,
access the printer or test a URL. Record unavailable fields as `NOT EXPOSED`.

1. Exact displayed app name and version — pending.
2. State remains `Stopped` — pending fresh readback.
3. `Start on boot` remains OFF — pending fresh readback.
4. Repository/source label, if displayed — pending / otherwise `NOT EXPOSED`.
5. Architecture/platform, if displayed — pending / otherwise `NOT EXPOSED`.
6. Protection mode/AppArmor status, if displayed — pending / otherwise `NOT EXPOSED`.
7. Image/build identifier or digest, if displayed — pending / otherwise `NOT EXPOSED`.
8. Network/port section shows no published port, if displayed — pending / otherwise
   `NOT EXPOSED`.
9. Mappings show only app/addon configuration and no Home Assistant config, device,
   USB or Docker mapping, if displayed — pending / otherwise `NOT EXPOSED`.

Leave the page with the app still `Stopped` and `Start on boot` OFF. Version or
repository name alone never proves installed provenance.

Owner outcome achieved: `NONE`.

Usable now: `NO` - dormant installation is complete, but installed provenance,
private route/IPPS trust, protected identities/credential/queue, commissioning and
physical acceptance remain incomplete.
