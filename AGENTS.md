# Repository Agent Guidance

Lifecycle: `POINTER_ONLY / NON_DOCTRINE`.

Before work, fetch the exact current `origin/main`, record its SHA, and read
`docs/09-vault-brain/README.md`. Follow the common and mission-specific pack
selected by
`docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md`, including its two
registered cross-system exceptions. Development workers must also read
`.agents/skills/amadeus-implement/SKILL.md`.

Do not substitute legacy start-here files, planning notes, handovers, static
agent cards, or archive material for current Vault authority.

## Safe Cloud development commands

The repository Cloud environment installs dependencies with:

```bash
python3 -m pip install -r requirements.txt
npm ci
npx playwright install chromium
```

Start the local backend without production credentials or writes:

```bash
python3 app.py
```

Run representative repository-only checks:

```bash
python3 -m unittest tests.test_frontend_route_contracts -q
python3 -m unittest tests.test_vault_alignment -q
node tests/oom_sakkie_browser_behavior_smoke.js
```

The exact Oom Sakkie real-browser gate and its test-only environment are defined
in `.github/workflows/oom-sakkie-browser-behavior.yml`. Never place secrets in
Git. Architecture, data authority, review, release, and safety boundaries come
only from the selected Vault pack and current technical/runtime evidence.
