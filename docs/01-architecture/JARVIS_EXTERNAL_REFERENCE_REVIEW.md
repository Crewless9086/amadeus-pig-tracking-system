# Usejarvis External Reference Review

> Legacy note: this document predates ADR_0002 CHARLIE CORE. Where this document conflicts with the current architecture, ADR_0002 and the CHARLIE CORE architecture docs win. Current rule: CHARLIE CORE is the top-level owner orchestrator, Oom Sakkie is Farm Commander, Supabase is operational truth, and Markdown/docs are guidance only.

Date: 2026-06-07

Reference source inspected locally:

`external_sources/jarvis-main/jarvis-main`

Public sources:

- Website: `https://www.usejarvis.dev/`
- Repository: `https://github.com/vierisid/jarvis`

## Verdict

Use this project as an architecture reference only. Do not install, run, link,
or copy code from it into Amadeus.

The project appears to be a real, substantial JARVIS-style runtime, but it is
intentionally powerful: daemon, sidecars, desktop/browser/filesystem/clipboard
access, screenshots, workflows, approvals, voice, and autonomous background
services. That is useful to study, but risky to run on the farm laptop.

## Hard No For Now

Do not run:

- `bun install -g @usejarvis/brain`
- `curl ... | bash`
- `install.sh`
- `bun install`
- `bun run ...`
- Docker image or container
- sidecar enrollment
- any setup flow that asks for API keys

Reasons:

- `install.sh` installs dependencies, modifies shell profile PATH, clones into
  `~/.jarvis/daemon`, writes a global `jarvis` command, and posts install
  telemetry to `https://getjarvis.dev/api/install`.
- `package.json` has `postinstall` and `prepare` scripts. Installing packages
  would execute local code and alter Git hook config inside that checkout.
- `config.example.yaml` states that if auth is unset, the dashboard/API/
  WebSocket are open.
- The runtime is designed to expose desktop, browser, terminal, filesystem,
  clipboard, and screenshot capabilities through sidecars.
- Native Windows is not the primary daemon install path; the README points
  Windows users at WSL2 or Docker for the daemon.
- The license is source-available, not a normal permissive license. Do not copy
  implementation code without legal review.

## Things Worth Learning From

### 1. Voice State Model

Their UI uses a small state machine:

- idle
- listening
- thinking
- speaking
- awaiting-approval
- muted

This maps well to Oom Sakkie. We should borrow the state model concept, not the
code. Our kiosk already has some of this; the next UI polish can make these
states more visible and more "Jarvis-like" without adding unsafe autonomy.

### 2. Authority Categories

Their authority model classifies actions into categories like:

- read_data
- write_data
- delete_data
- send_message
- send_email
- execute_command
- install_software
- make_payment
- modify_settings
- spawn_agent
- access_browser
- control_app

This is useful for our future risk model. Oom Sakkie currently has
`RiskLevel.READ_ONLY = 0`; before adding writes, we should expand into a typed
action-category model similar to this.

### 3. Voice Approval Gate

They explicitly prevent destructive actions from being approved by voice and
require a confidence floor for lower-risk voice approvals.

This is directly relevant to our future write/confirmation design. For Oom
Sakkie, destructive or physical actions should never resolve by voice alone.
The confirm path should use an exact payload shown on screen and a deliberate
click/tap.

### 4. Approval Lifecycle

They model approvals as persistent rows:

- pending
- approved
- denied
- expired
- executed

Oom Sakkie should use this pattern when writes eventually arrive. Today we are
read-only, so this stays as planning input.

### 5. Emergency Pause/Kill

They have an emergency controller with:

- normal
- paused
- killed

Before any Oom Sakkie write, Telegram cutover, physical control, or specialist
delegation, we should add a visible pause/kill state that blocks tool execution.

### 6. Sidecar Architecture

The sidecar concept is useful long-term: a central brain plus small local agents
that connect outward. The implementation is too powerful for us right now.

For Amadeus, a safer future version would start with read-only sidecars only:

- kiosk display status
- local mic status
- maybe local logs

No filesystem, terminal, browser, clipboard, screenshots, or desktop control
until an explicit security design exists.

### 7. Personality And Channel Adaptation

Their docs describe a persistent personality model with per-channel adaptation.
That reinforces our existing plan: Oom Sakkie should eventually have stable
voice/personality rules and separate wording for kiosk, Telegram, and reports.

## Things To Avoid

- Always-on desktop awareness.
- Screen OCR/activity tracking before there is a privacy model.
- Browser or desktop control on the farm laptop.
- Terminal/filesystem tools exposed to an agent.
- Long-lived sidecar tokens without expiry/rotation.
- Default-open dashboard/API/WebSocket posture.
- High-authority roles that can install software, execute commands, or modify
  settings.
- Workflow marketplace or arbitrary code-node execution.
- Copying code from the source-available project into this repo.

## Candidate Amadeus Follow-Ups

Safe near-term:

1. Add a clearer Oom Sakkie state strip: idle, listening, thinking, checking,
   speaking, needs-review.
2. Add "why this answer" display: rule route vs LLM route vs composer rewrite.
3. Add a visible emergency pause flag to the Oom Sakkie policy, initially
   read-only/no-op but ready for future writes.
4. Expand our risk enum into action categories while keeping every current tool
   read-only.

Later, after daily use:

1. Confirmation payload table for future writes.
2. Voice approval gate with destructive actions requiring screen click.
3. Read-only specialist delegation.
4. Read-only sidecar concept, only after a separate security design.

Do not use this reference as justification to add autonomy, writes, desktop
control, Telegram cutover, or physical controls early.
