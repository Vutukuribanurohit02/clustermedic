---
id: ED-007
title: DRC violations after detailed routing
fault_type: drc_violations
components: [routing]
severity: high
---

## Symptoms
- The detailed router reports a non-zero number of violations (shorts, spacing, min area).
- GDS cannot be signed off until DRC is clean.

## Diagnose
1. Group violations by type and by layer; check whether they cluster in one region.
2. Compare with global-routing congestion reports for the same region.
3. Check pin access problems near standard cells or macros.

## Common causes
- Routing congestion from high utilization or dense logic.
- Too few routing layers allowed.
- Pin access problems or blockages near macros.

## Fix
- Reduce utilization or routing density, allow more routing layers, spread congested cells.
- Re-run detailed routing with more iterations only after removing the congestion cause.

## Verify
- Detailed routing ends with zero violations.
