---
id: RB-001
title: Slurm node drained or down
fault_type: node_drained
components: [slurm]
severity: medium
destructive_actions: [scontrol_resume]
---

## Symptoms
- Users report cancelled jobs will not die: processes keep running after scancel, then the node drops out of the pool.
- `sinfo` shows a node as `drain`, `drng` (draining) or `down`; jobs stay PENDING with reason `Resources`.
- Health check: "slurm nodes healthy" FAIL.

## Diagnose (read-only)
1. `sinfo -R` — reason, who set it, and when.
2. `scontrol show node <node>` — State, Reason, RealMemory vs configured memory.
3. `squeue -w <node>` — jobs still on the node (draining vs drained).
4. Check slurmd on the node: `journalctl -u slurmd` or slurmd.log for "Not responding", "Kill task failed", "Low RealMemory".

## Common causes
- Admin drain for maintenance (reason set by a person).
- "Kill task failed": a job process did not exit; often a hung filesystem.
- "Not responding": slurmd stopped or network/munge problem (see RB-003, RB-004).
- Hardware fault flagged by a health check (see RB-005..RB-008).

## Fix
- Only after the cause is cleared: `scontrol update nodename=<node> state=resume`. **Needs human approval.**
- Never resume a node drained for a hardware fault without checking Redfish/GPU telemetry first.

## Verify
- Poll `sinfo -h -n <node> -o %t` until `idle`/`mix`/`alloc` (timeout 30 s).

## Escalate if
- Drain reason mentions hardware, or the node re-drains within 1 hour.
