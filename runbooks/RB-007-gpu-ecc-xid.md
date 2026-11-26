---
id: RB-007
title: GPU ECC memory errors and Xid errors
fault_type: gpu_ecc_xid
components: [gpu, prometheus]
severity: critical
destructive_actions: [drain_node, gpu_reset, cancel_job]
---

## Symptoms
- `DCGM_FI_DEV_ECC_DBE_VOL_TOTAL` (double-bit, uncorrectable) increases.
- `DCGM_FI_DEV_XID_ERRORS` reports a non-zero Xid code.
- Jobs on the GPU crash with CUDA errors or produce wrong results.
- Kernel log on the node contains `NVRM: Xid` lines.

## Diagnose (read-only)
1. New uncorrectable errors: PromQL `increase(DCGM_FI_DEV_ECC_DBE_VOL_TOTAL[15m]) > 0`.
2. Last Xid per GPU: PromQL `DCGM_FI_DEV_XID_ERRORS != 0`.
3. Correctable error rate: `increase(DCGM_FI_DEV_ECC_SBE_VOL_TOTAL[1h])`. A steadily rising rate can come before uncorrectable errors.
4. On a real node: `dmesg | grep -i xid`, `nvidia-smi -q -d ECC`, and on A100/H100-class GPUs `nvidia-smi -q -d ROW_REMAPPER` (look for pending remaps or remap failure).
5. `squeue -w <node>` to find jobs affected by the error.
6. Interpret common Xid codes:
   - 48: double-bit ECC error (hardware).
   - 63 / 64: memory row remapping recorded / failed.
   - 79: GPU has fallen off the bus (hardware or power).
   - 92: high single-bit ECC error rate.
   - 94 / 95: contained / uncontained ECC error.
   - 13, 31, 43: usually application faults (bad memory access in user code). Check whether only one user's jobs trigger them before suspecting hardware.

## Common causes
- Failing GPU memory.
- GPU or board power and seating problems (especially Xid 79).
- User code bugs (Xid 13/31/43), which are not hardware faults.

## Fix
- Drain the node (**needs human approval**) so no new jobs use the GPU.
- Let running jobs finish where possible; cancelling them **needs human approval**.
- Once the GPU is idle, a GPU reset (`nvidia-smi -r -i <gpu>`) or node reboot clears pending row remaps (**needs human approval**).
- Open a hardware (RMA) ticket for repeated double-bit errors, row-remap failure, or Xid 79.

## Verify
- No new double-bit errors or hardware Xids over the following 24 hours.
- A GPU diagnostic (`dcgmi diag -r 3` on real hardware) passes.
- Then resume the node per RB-001.

## Escalate if
- Xid 79, 64 or 95 appears.
- Double-bit errors recur after a reset.
- Several GPUs on the same node report errors (board or power problem).
