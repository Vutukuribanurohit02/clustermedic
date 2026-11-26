---
id: ED-006
title: Placement failure from utilization or density
fault_type: placement_density
components: [floorplan, placement]
severity: high
---

## Symptoms
- Global placement stops with an `[ERROR GPL-...]` message about density or utilization.
- The flow never reaches CTS or routing.

## Diagnose
1. Compare the design area with the core area: what utilization was requested?
2. Check the target placement density against the actual utilization.
3. Check for macros or blockages that remove placement rows.

## Common causes
- CORE_UTILIZATION set too high for the cell area.
- PLACE_DENSITY lower than the actual utilization.
- Die or core area too small.

## Fix
- Lower CORE_UTILIZATION or enlarge the core area; keep density above utilization.

## Verify
- Global placement completes and later stages run.
