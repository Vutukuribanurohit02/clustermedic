---
id: ED-008
title: Flow stopped with a tool error
fault_type: flow_error
components: [flow]
severity: medium
---

## Symptoms
- A log contains an `[ERROR XXX-nnnn]` line and the stage stops.

## Diagnose
1. Find the first error in the earliest failing stage; later errors are often consequences.
2. Search the tool documentation for the error code.
3. Check the inputs of that stage: configuration variables, files, and the previous stage's output.

## Common causes
- Bad configuration value or missing file.
- A previous stage produced an unusable result.

## Fix
- Fix the cause of the first error and re-run from that stage.

## Verify
- The stage completes without errors.
