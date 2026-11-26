---
id: ED-004
title: Undriven net (used but no driver)
fault_type: undriven_net
components: [rtl, synthesis]
severity: high
---

## Symptoms
- Yosys log: `Wire ... is used but has no driver`.
- Simulation shows X on the signal; gate-level logic may be optimized away.

## Diagnose
1. Find where the wire is read and where it should be driven.
2. Check for typos in signal or port names, which create implicit wires.
3. Check instance port connections for missing or misspelled ports.

## Common causes
- Misspelled signal name creating an implicit net.
- Missing assign statement or missing instance output connection.

## Fix
- Connect the intended driver or remove the read.
- Add `` `default_nettype none `` to catch implicit nets at elaboration.

## Verify
- Re-run synthesis and lint: no undriven-wire warnings.
