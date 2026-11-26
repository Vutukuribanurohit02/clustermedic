---
id: ED-003
title: Latch inferred during synthesis
fault_type: latch_inferred
components: [rtl, synthesis]
severity: medium
---

## Symptoms
- Yosys log: `Latch inferred for signal ...`; latch cells appear in the netlist statistics.
- Unexpected level-sensitive storage makes timing analysis harder and can cause glitches.

## Diagnose
1. Find the always block that drives the signal named in the warning.
2. Check every if/case branch: is the signal assigned on all paths?
3. Check case statements for missing default branches.

## Common causes
- Combinational always block where a signal is not assigned in some branch.
- Incomplete case statement without a default.

## Fix
- Add a default assignment at the top of the always block, or assign the signal on every branch.
- Use `always_comb` in SystemVerilog so tools flag incomplete assignments.
- If a latch is truly intended, document it and constrain it explicitly.

## Verify
- Re-run synthesis: no `Latch inferred` warnings and no latch cells in the statistics.
