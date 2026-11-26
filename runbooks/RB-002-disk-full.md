---
id: RB-002
title: Filesystem full on compute node or shared storage
fault_type: disk_full
components: [storage, slurm]
severity: high
destructive_actions: [delete_files, cancel_job]
---

## Symptoms
- Jobs fail with `No space left on device`, or output files are empty or truncated.
- Jobs fail within seconds of starting on one node but run fine on others.
- slurmd cannot write to its spool directory; the node may drain with a job-completion or prolog error.
- `df -h` shows a filesystem at or near 100% use.

## Diagnose (read-only)
1. `df -h` on the affected node: which filesystem is full (`/`, `/tmp`, `/var`, scratch, home)?
2. `df -i`: a filesystem can be "full" on inodes (millions of tiny files) while still showing free space.
3. `du -xh --max-depth=1 <mount> 2>/dev/null | sort -h | tail` to find the largest directories.
4. `find <mount> -xdev -type f -size +1G -mmin -60` to find large files written in the last hour.
5. `lsof +L1` to find deleted files still held open by a process; that space is not freed until the process exits.
6. `squeue -w <node>` and `scontrol show job <id>` to match the growing path to a running job and its owner.

## Common causes
- A runaway job writing huge stdout/stderr or checkpoint files.
- Core dumps from crashing jobs.
- `/tmp` or local scratch not cleaned after jobs finish.
- Log growth (`/var/log/slurm`, system logs) without rotation.
- A deleted log file still held open by a long-running process.
- Shared filesystem quota exhausted for a user or group.

## Fix
- Notify the job owner first; the data belongs to them.
- Cancelling the job that is filling the disk (`scancel <jobid>`) **needs human approval**.
- Deleting or moving any files **needs human approval**. Never delete user data automatically.
- Safe once approved: remove core dumps after recording their job IDs, rotate or compress old logs, clear stale `/tmp` files from finished jobs.
- If space is held by a deleted-but-open file, restarting the holding process frees it (**needs human approval**).

## Verify
- `df -h` and `df -i` show use below 85% on the affected filesystem.
- A short test job on the node writes output successfully.
- If the node was drained, follow RB-001 to resume it.

## Escalate if
- The full filesystem is shared storage (NFS, Lustre, GPFS) or a project quota.
- The disk fills again within 24 hours of cleanup.
- The root filesystem (`/`) is full.
