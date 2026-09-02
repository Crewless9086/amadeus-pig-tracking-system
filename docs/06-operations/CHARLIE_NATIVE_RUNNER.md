# CHARLIE Standalone Native Runner

## Boundary

The native runner is an independent, boot-supervised process. It polls the
existing canonical CHARLIE resumable-execution API and does not depend on a
Hermes plugin, gateway hook, dashboard session, cron entry, Kanban item, or
interactive shell. It has no merge, deployment, migration, or protected-branch
operation.

The runner reuses the existing canonical mission/event plane, native execution
authorization, deterministic worktree implementation, candidate admission,
review roles, GitHub draft-PR packager, and Slack notification contracts. It
does not create another queue or ledger.

## Implementation source map

- `modules/charlie/native_runner/`: plugin-independent structured patch,
  canonical client, model adapter, packaging, notification, locking, and
  canonical recovery service.
- `scripts/charlie_native_runner.py`: bounded once/watch/status/dry-run entry
  point; deliberately has no merge, release, or deployment mode.
- `deploy/charlie-native-runner/charlie-native-runner.service`: boot and
  crash-supervised systemd service with one dedicated process identity.
- This runbook records deployment, independence, acceptance, rollback, and
  credential-containment requirements.

## AMADEUS-CLOUD assessment

The Hermes v0.20.6 System surface exposes gateway status and a gateway restart
control. It does not expose an independently boot-supervised second service,
container lifecycle, one-instance process manager, durable second-service logs,
or a whole-instance boot registration contract. Its other available execution
surfaces (cron, plugin threads, API sessions, and interactive terminal jobs) are
explicitly outside this runner boundary. AMADEUS-CLOUD therefore cannot host
the production runner until its platform provides a documented independent
service primitive satisfying those requirements.

## Dedicated host contract

Provision Ubuntu 24.04 LTS with 4 vCPU, 8 GB RAM, and an 80 GB persistent disk.
Create a dedicated `charlie-runner` account, install the repository at
`/srv/charlie/repository`, use `/srv/charlie/worktrees` for isolated worktrees,
and install a virtual environment at `/srv/charlie/venv`. Store only the
allowlisted runner configuration in `/etc/charlie-native-runner.env` with owner
`charlie-runner:charlie-runner` and mode `0600`; the explicit Hermes profile home remains
`/opt/data` and its profile configuration must be mode `0600`.

Install `deploy/charlie-native-runner/charlie-native-runner.service` under
`/etc/systemd/system`, then daemon-reload, enable, and start it. Journald is the
only service log. Configure SSH keys, Tailscale, and a firewall denying
unsolicited inbound application traffic. No inbound application port is
required.

## Acceptance and recovery

Before admitting production execution, prove all of the following:

1. A read-only structured JSON canary succeeds through the installed Hermes
   auxiliary inference API with an empty tool list.
2. Killing the exact runner PID results in exactly one replacement process.
3. Restarting the Hermes gateway does not change the runner PID.
4. Disabling the directory plugin does not change the runner PID.
5. Rebooting the host starts exactly one runner and resumes the same canonical
   mission and worktree.
6. A second local process is rejected by the process lock, and a second writer
   is rejected by canonical CHARLIE state.

Rollback stops and disables only the systemd unit. It does not delete the
worktree, branch, canonical events, Cursor history, or draft PR. Re-enabling the
same unit resumes the same deterministic identity.

## Security invariants

The model receives text context and a JSON schema only. It receives no tools,
credentials, repository object, process environment, or network client. The
parent validates and applies patches, runs the admitted checks, and packages a
single draft PR. Broad GitHub credentials abort startup. The packager credential
is never passed to the model, argv, verification child environments, logs,
artifacts, Slack, or canonical records.
