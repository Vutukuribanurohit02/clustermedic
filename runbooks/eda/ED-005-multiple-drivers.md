---
id: ED-005
title: Multiple conflicting drivers on a net
fault_type: multiple_drivers
components: [rtl, synthesis]
severity: high
---

## Symptoms
- Yosys log: `multiple conflicting drivers for ...` or `Driver-driver conflict`.
- Simulation shows X or contention; hardware behaviour is undefined.

## Diagnose
1. Find every assign statement and always block that drives the signal.
2. Check for the same signal assigned in two always blocks.

## Common causes
- Two `assign` statements or two always blocks writing the same signal.
- Copy-paste of logic without renaming the target.

## Fix
- Keep exactly one driver; merge the logic into one always block or select with a mux.

## Verify
- Re-run synthesis: no conflicting-driver warnings.
