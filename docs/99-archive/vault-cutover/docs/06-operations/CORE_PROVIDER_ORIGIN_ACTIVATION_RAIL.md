# CORE provider-origin activation rail

This rail is the source contract for a serialized, observe-only CORE activation. It does not make source readiness, CI, staging, activation, runtime health, or Business completion interchangeable.

## Authority and sequence

Control Tower issues a short-lived HMAC-sealed authority for one immutable activation ID. The authority binds the runtime and execution revisions, runtime-manifest digest, isolated-validation receipt digest and path, governed-stop digest, exact scheduled-task action digest, `observe_only` mode, and expiry. The key belongs in the protected runtime state directory and is never source, output, or feedback.

The activation terminal first runs `dry-run`, then `prepare`. Preparation acquires `activation.lock` with create-new semantics, durably records rollback evidence, writes a sealed provider packet, atomically archives the exact stop marker, and enables/triggers only the scheduled task whose complete action digest was authorized. It never creates a supervisor or runner process.

The scheduled watchdog consumes the packet. It accepts only a `pythonw.exe` instance whose exact parent chain begins at a Windows scheduled-task provider and contains no Codex, terminal, command-shell, or interactive PowerShell boundary. Inspection queries only the current PID and each exact parent PID; it does not take a host process snapshot. A create-new consumption record makes replay and concurrent starts fail closed. The provider passes the activation ID into the governed runner-control startup, and that ID is carried through supervisor state, signed acknowledgements, and runner heartbeat.

The bounded activation lane may enable the
Microsoft-Windows-TaskScheduler/Operational channel and retain its exact prior
channel state plus rollback command. When the COM running-instance view no
longer contains the short-lived watchdog, exactly one post-preparation Event
200 may authenticate it. That record must bind the exact task path, current
EnginePID, task-instance/activity identity, action, record ID and timestamp to
the sealed activation ID. The current Schedule service identity, configured
single action and working directory, and twice-read current process ancestry
remain mandatory. Disabled, missing, stale, pre-activation, duplicate,
ambiguous, mismatched or substituted event evidence fails closed. Historical
failed activation epochs are never eligible evidence.

`verify` accepts activation only when the immutable revision and observe-only mode agree across the packet, signed supervisor/runner evidence and heartbeat; both live trees revalidate; the heartbeat is fresh; and the activation ID agrees throughout. Before verification succeeds, a failure disables only the exact authorized task and restores the exact governed-stop bytes under the same lane. Incomplete recovery retains contradictory evidence and must be manually assessed; broad cleanup is prohibited.

## Trust boundary and remaining acceptance

The state-directory ACL and HMAC issuer custody are security boundaries. The serialized lane coordinates compliant writers; it is not a hostile local-administrator boundary. Windows scheduler and filesystem changes must be re-read at each mutation boundary. No process name, command substring, ancestry alone, stale PID, or task name grants ownership or termination authority.

Source and tests enable a later separately authorized activation; they do not perform it. Acceptance still requires exact-current staging, provider-origin activation, signed exact owned-tree proof, a fresh heartbeat and independently triggered cycle, next-cycle evidence, and a Control Tower readback after the development/activation terminal closes.
