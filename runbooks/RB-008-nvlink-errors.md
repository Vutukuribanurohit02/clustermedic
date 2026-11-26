---
id: RB-008
title: NVLink errors between GPUs
fault_type: nvlink_errors
components: [gpu, prometheus]
severity: high
destructive_actions: [drain_node, gpu_reset]
---

## Symptoms
- `DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL` keeps increasing on one or more GPUs.
- Multi-GPU jobs on the node run slowly, hang, or fail with NCCL timeouts.
- Xid 74 (NVLink error) in the kernel log.

## Diagnose (read-only)
1. Rate of new errors: PromQL `rate(DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL[5m]) > 0`, by `Hostname` and `gpu`.
2. Pattern: errors on one GPU pair point to a specific link; errors on every GPU point to the baseboard or NVSwitch.
3. On a real node: `nvidia-smi nvlink -s` (link status and speed), `nvidia-smi nvlink -e` (per-link error counters), `nvidia-smi topo -m` (how GPUs are connected).
4. Check whether single-GPU jobs on the same node are unaffected; that supports a link problem rather than a GPU problem.
5. `squeue -w <node>` to see which multi-GPU jobs are affected.

## Common causes
- Degraded NVLink connection or bridge.
- NVSwitch or baseboard fault.
- Firmware or driver mismatch after an update.

## Fix
- Drain the node (**needs human approval**).
- After running jobs finish, a GPU reset or node reboot can retrain the links (**needs human approval**).
- Open a hardware ticket if errors continue after a reset.

## Verify
- The error counter stops increasing (rate is 0) for at least 1 hour under multi-GPU load.
- A multi-GPU test job (for example an NCCL all-reduce test) completes at expected bandwidth.

## Escalate if
- Errors resume after a reset or reboot.
- Links show as down or at reduced speed in `nvidia-smi nvlink -s`.
