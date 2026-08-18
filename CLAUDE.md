# Repository Guidance Pointer

Lifecycle: `POINTER_ONLY / NON_DOCTRINE`.

Before work, load `docs/09-vault-brain/README.md`, its mandatory mission pack,
and the two registered cross-system exceptions named there. Do not substitute
legacy start-here, planning, handover, static-agent-card, or archive material.

Local backend setup remains `pip install -r requirements.txt`; local startup is
`python app.py`. Secrets belong in the environment and must never be committed.
Current architecture, data authority, business rules, tests, review, release,
and safety boundaries come only from the selected Vault pack and current
technical/runtime evidence.
