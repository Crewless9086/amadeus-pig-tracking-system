# Feature Build Playbook

## Purpose

Feature builds turn owner intent into scoped, tested, reviewable system changes.

## Required Stages

- Planner: define user outcome and acceptance criteria.
- Architect: identify files, routes, data contracts, risks, and rollback path.
- Builder: implement only scoped changes.
- Tester: run focused tests and pressure tests.
- QA Red Team: look for broken flows, hidden buttons, stale state, source-of-truth mistakes, and owner-risk gaps.
- Reviewer: inspect diff, evidence, and owner review packet.

## Must Include

- changed files;
- screenshots or UI proof if visual;
- test commands and results;
- known risks;
- source-of-truth/data-write statement;
- rollback or release plan;
- owner decision needed.

## Hard Rules

- Do not call work complete because code was written.
- Do not hide missing tests.
- Do not refactor unrelated areas unless required for the owner outcome.
- Do not skip Vault Brain updates when agent behavior, rules, data contracts, dashboards, or review gates changed.
