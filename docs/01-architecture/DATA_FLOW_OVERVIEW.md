# Data Flow Overview

> Legacy note: this document predates ADR_0002 CHARLIE CORE. Where this document conflicts with the current architecture, ADR_0002 and the CHARLIE CORE architecture docs win. Current rule: CHARLIE CORE is the top-level owner orchestrator, Oom Sakkie is Farm Commander, Supabase is operational truth, and Markdown/docs are guidance only.

## Purpose

Shows how information moves through Chatwoot, n8n, AI agents, Flask, and Google Sheets.

## Rule

This page explains cross-layer flow only. Detailed workflow field ownership belongs in `docs/04-n8n/DATA_FLOW.md`. Detailed sheet ownership belongs in `docs/03-google-sheets/WRITE_OWNERSHIP.md`.
