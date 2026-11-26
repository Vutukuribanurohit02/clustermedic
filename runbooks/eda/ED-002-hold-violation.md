---
id: ED-002
title: Hold timing violation (negative slack on min paths)
fault_type: hold_violation
components: [sta, cts]
severity: high
---

## Symptoms
- STA reports `slack (VIOLATED)` on paths with `Path Type: min`.
- Hold failures cannot be fixed by slowing the clock; they fail at any frequency.

## Diagnose
1. Check the clock skew between launch and capture flops on the failing path.
2. Check whether the failure appears only after CTS (real clock tree) or already in ideal-clock analysis.
3. Look for very short data paths, such as flop-to-flop with no logic.

## Common causes
- Clock skew larger than the data path delay.
- Short paths (shift registers, direct flop-to-flop connections).
- Hold repair not run, or run before CTS.

## Fix
- Run hold repair after CTS so delay buffers are inserted on the short paths.
- Reduce skew by improving clock tree balancing.

## Verify
- Min-corner STA after CTS and routing: no hold violations.
