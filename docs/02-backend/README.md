# Backend Documentation

## Purpose

This folder is the source of truth for the Flask backend layer.

The backend is responsible for safe API behavior between n8n, the web app, and Google Sheets. It should protect order integrity, reservation state, status transitions, and sheet writes.

## Folder Map

| File | Purpose |
| --- | --- |
| `API_STRUCTURE.md` | Current backend endpoints, inputs, outputs, and callers. |
| `ORDER_LOGIC.md` | Business rules for drafts, lines, reservation, release, approval, rejection, cancellation, and completion. |
| `QUOTE_INVOICE_DESIGN.md` | Phase 2 quote/invoice generation design before implementation. |
| `DATA_MODELS.md` | Backend-facing order data models and important fields. |
| `MODULE_STRUCTURE.md` | Current backend module layout and ownership. |
| `REFACTOR_PLAN.md` | Planned backend cleanup and hardening work. |

## Current Backend Principle

n8n orchestrates what should happen. The Flask backend executes the order action safely.

## Current Focus

The order system needs stabilization before new features. Known focus areas:

- reject/cancel should release reserved pigs
- customer cancellation needs a dedicated backend action
- split requested items must sync reliably
- repeated syncs must not create duplicates
- partial matches must not silently look complete
- Sam should get order context through backend/Order Steward, not direct uncontrolled sheet access
