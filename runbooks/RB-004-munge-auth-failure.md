---
id: RB-004
title: Munge authentication failure between Slurm daemons
fault_type: munge_auth_failure
components: [slurm, munge]
severity: high
destructive_actions: [restart_service, replace_munge_key]
---

## Symptoms
- Slurm commands or daemon logs show `Invalid credential`, `Munge decode failed`, or `Expired credential`.
- One or more nodes go `down*` with reason `Not responding` while the network is fine.
- `srun` or `sbatch` fail from a specific node with authentication errors.

## Diagnose (read-only)
1. Local test on the suspect node: `munge -n | unmunge`. It should report `STATUS: Success (0)`.
2. Cross-node test from the controller: `munge -n | ssh <node> unmunge`. Failure here but not locally points to a key or clock mismatch.
3. Is the daemon running? `systemctl status munge` or `pgrep -a munged`.
4. Compare the key **checksum** on each host: `sha256sum /etc/munge/munge.key`. Never print or copy the key itself.
5. Check clocks: `date` on each host, and `chronyc tracking` or `timedatectl`. Credentials expire after a few minutes by default, so clock skew breaks authentication.
6. Check key permissions: owned by the `munge` user, mode `0400`.

## Common causes
- Different `munge.key` on one node (re-imaged node, manual edit).
- Clock skew between nodes (NTP/chrony stopped).
- munged not running after a reboot.
- Wrong ownership or permissions on the key file, so munged refuses to start.

## Fix
- Restart munged (`systemctl restart munge`) **needs human approval**.
- Fix time sync (restart chrony/NTP) **needs human approval**.
- Replacing a node's key with the cluster key is a security-sensitive change: **needs human approval** and must be done by an administrator. The agent must never read, print or transmit key contents.
- After munge works, follow RB-003 / RB-001 to bring the node back.

## Verify
- `munge -n | ssh <node> unmunge` returns `STATUS: Success (0)` from the controller.
- The node returns to `idle` in `sinfo` without `*`.

## Escalate if
- The key may have been exposed or copied somewhere it should not be (rotate the key cluster-wide).
- Clock skew returns after time sync is fixed.
