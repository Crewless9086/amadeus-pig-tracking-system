# Bugfix Playbook

## Required Stages

- reproduce or explain the failure;
- identify current live, branch, runner, and deploy state;
- patch narrowly;
- add regression coverage where practical;
- verify with targeted test;
- record remaining risk.

## Must Not

- refactor unrelated code;
- hide technical failure from the owner;
- leave stale local process/deploy mismatch unresolved;
- claim Render or live state changed without verifying it.
