# Green Print Commissioning Inventory - 2026-08-21

Status: `LOCAL_BASELINE_PREPARED / NOT_COMMISSIONED / INSTALLATION_NOT_AUTHORIZED`

Mission: existing DOCUMENTS mission `DMQ-20260816-01`, fixed pilot
`farm.weekly_weight_sheet.v1`, A4, exactly one copy, monochrome, one-sided.

This is a non-secret preparation record. It authorizes no repository installation,
app upload/start, migration, credential or certificate registration, CUPS activation,
printer configuration, print job or physical output.

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

- Private repository not added; app not uploaded/installed/built locally/started.
- CUPS app/service not installed or started; no fixed queue or printer configuration.
- Private CA and adapter credential not installed.
- Green/printer registry pair not registered from Green.
- No canonical, synthetic or farm print job; no document submission; no physical
  page produced.

## First remaining gates

1. Complete PR #1152 operational-gap repair and exact-head independent review,
   including HAOS 18.2/aarch64 packaging, CUPS, AppArmor, `/data`, tmpfs, private CA,
   strict private IPPS and rollback packet.
2. Obtain one exact serialized merge/migration/application release decision.
3. Verify exact loaded application revision, migration ledger/schema/functions,
   least-privilege grants and zero-effect route checks while Green remains disabled.
4. Through protected commissioning, determine the exact IPPS endpoint and
   certificate metadata; validate SAN/trust without printing; register the exact
   private identities, queue and least-privilege credential.
5. Only after explicit `GREEN INSTALLATION AUTHORIZED`, install and perform synthetic
   non-farm commissioning, followed by separately authorized physical acceptance.
6. Let deployed Oom Sakkie receive a genuine natural request, prove one correct page,
   canonical/provider/physical agreement, safe cleanup/follow-up and a later
   terminal-independent cycle.

Owner outcome achieved: `NONE`.

Usable now: `NO` - IPPS identity/trust, canonical release, protected identities,
installation, commissioning and physical acceptance remain incomplete.
