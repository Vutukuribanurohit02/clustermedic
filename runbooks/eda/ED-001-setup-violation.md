---
id: ED-001
title: Setup timing violation (negative slack on max paths)
fault_type: setup_violation
components: [sta, synthesis, placement]
severity: high
---

## Symptoms
- STA reports `slack (VIOLATED)` on paths with `Path Type: max`; WNS and TNS are negative.
- The design cannot run at the target clock frequency.

## Diagnose
1. Confirm the constraint: is the clock period in the SDC the intended one, and are input/output delays realistic?
2. Look at the worst path: startpoint, endpoint, number of logic levels, fanout of each net, and cell drive strengths.
3. Separate cell delay from wire delay: long wires point to placement distance; long cell chains point to logic depth.
4. Check whether many paths fail by a little (TNS spread across endpoints) or one path fails by a lot.

## Common causes
- Clock period tighter than the logic depth allows.
- Deep combinational logic between registers (many logic levels).
- High-fanout nets driven by small cells.
- Weak (size 1) cells left on the critical path, or restrictive DONT_USE lists.
- Poor placement: launching and capturing flops far apart.

## Fix
- Least invasive first: verify the SDC, then let timing repair upsize cells and buffer fanout.
- Restructure or retime the logic; add a pipeline stage for deep paths (changes latency: needs design review).
- Relax the clock only if the specification allows it.

## Verify
- Re-run STA after the change: WNS >= 0 and TNS = 0 for the max corner.
