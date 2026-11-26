---
id: RB-003
title: slurmd not responding on compute node
fault_type: slurmd_down
components: [slurm]
severity: high
destructive_actions: [restart_service, scontrol_resume]
---

## Symptoms
- `sinfo` shows the node as `down*` or `idle*`; the `*` means the controller cannot reach slurmd.
- `sinfo -R` shows the reason `Not responding`.
- Jobs on the node fail or are requeued; new jobs avoid the node.

## Diagnose (read-only)
1. `sinfo -R` and `scontrol show node <node>`: State, Reason, and when slurmd last responded.
2. Is the node reachable at all? `ping <node>`; if not, treat it as a node or network outage.
3. On the node: `systemctl status slurmd` or `pgrep -a slurmd` to see whether the daemon is running.
4. Read the slurmd log (`journalctl -u slurmd` or `/var/log/slurm/slurmd.log`) for crash or startup errors.
5. Check for the out-of-memory killer: `dmesg | grep -i -E "killed process|out of memory"`.
6. `slurmd -C` prints the hardware slurmd detects; compare it with the node's line in `slurm.conf`.
7. Rule out authentication problems: see RB-004 (munge).

## Common causes
- slurmd crashed or was killed (often by the OOM killer).
- The node rebooted and slurmd did not start.
- Hardware detected by `slurmd -C` does not match `slurm.conf` (memory, CPUs), so the node registers as invalid.
- Network or munge failure between the node and the controller.

## Fix
- Restarting slurmd (`systemctl restart slurmd`) **needs human approval**.
- If the node stays `down` after slurmd is back, resume it: `scontrol update nodename=<node> state=resume` (**needs human approval**).
- For a config mismatch, fix `slurm.conf` (or the hardware) first; do not resume a node with the wrong resources.

## Verify
- `sinfo -h -n <node> -o %t` returns `idle`, `mix` or `alloc` with no `*`, polled for up to 30 s.
- A short test job runs on the node: `srun -w <node> hostname`.

## Escalate if
- The node is unreachable (no ping) or does not boot.
- slurmd crashes again within 1 hour of a restart.
- The OOM killer is repeatedly killing slurmd.
