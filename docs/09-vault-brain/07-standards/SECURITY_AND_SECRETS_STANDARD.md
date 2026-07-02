# Security And Secrets Standard

Never commit `.env`, tokens, secrets, test results, screenshots, external sources, or unrelated owner files unless explicitly approved.

Auth, security, migrations, customer sends, public posts, payments, reservations, and production data changes require extra review.

## Secrets Rules

- Secrets live in `.env`, Render env vars, Supabase/Meta/Chatwoot/n8n credential stores, or owner-controlled password managers.
- Do not paste secrets into docs, Telegram, WhatsApp, Chatwoot, screenshots, or logs.
- Do not expose service-role keys to browser code, frontend JavaScript, public APIs, or n8n unless explicitly approved and safe.
- Do not print credentials in smoke tests.

## Tool And Agent Permission Rules

- Default agent/tool access is read-only.
- Write, send, publish, pay, reserve, migrate, delete, or lifecycle actions require explicit owner-approved gates.
- MCP/tool expansion must use allowlists, per-agent permissions, read/write separation, audit logs, and red-zone approval checks.
- Agents cannot approve their own work or change their own authority.

## Incident Bias

If a secret may have leaked, assume rotation is required until proven otherwise.

If a route could expose customer/farm data, fail closed and require owner/security review.

## Source References

- `docs/06-operations/CHARLIE_BUILD_RELAY_PLAN.md`
- `docs/09-vault-brain/00-governance/REVIEW_AND_APPROVAL_RULES.md`
