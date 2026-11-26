---
id: RB-010
title: Jobs stuck in PENDING state
fault_type: jobs_pending
components: [slurm]
severity: low
destructive_actions: [scontrol_release, scontrol_resume, change_priority]
---

## Symptoms
- Jobs stay `PD` (pending) in `squeue` much longer than usual.
- Users report jobs "not starting" while the cluster looks partly idle.

## Diagnose (read-only)
1. List pending jobs with their reasons: `squeue -t PD -o "%.10i %.9P %.8u %.20r"` (`%r` is the reason).
2. Details for one job: `scontrol show job <id>`: Reason, requested resources (ReqTRES), TimeLimit, Partition.
3. Are nodes actually available? `sinfo` and `sinfo -R` (drained or down nodes reduce capacity; see RB-001).
4. Read the reason:
   - `Resources`: waiting for enough free nodes, CPUs, memory or GPUs. Check the request is possible at all on this partition.
   - `Priority`: other jobs are ahead in the queue. Use `sprio -j <id>` to see its priority factors.
   - `Dependency`: waiting for another job to finish.
   - `ReqNodeNotAvail`: the requested nodes are drained, down or reserved.
   - `QOSMaxJobsPerUserLimit`, `AssocGrp...` reasons: a usage limit is reached.
   - `PartitionTimeLimit`: the requested time is longer than the partition allows; it will never start as is.
   - `JobHeldUser` / `JobHeldAdmin`: the job is on hold.
   - `BeginTime`: the job is set to start later.
5. `scontrol show partition <name>` for partition limits and state.

## Common causes
- Requests larger than any node can provide (more memory or GPUs than a node has).
- Nodes drained or down, reducing capacity.
- Normal queue contention or fair-share priority.
- Per-user or per-account limits reached.
- Jobs held or waiting on a failed dependency.

## Fix
- Most fixes are on the user side: reduce the request, fix the time limit, or fix the dependency. Report the specific reason and the change needed.
- If capacity is low because nodes are drained, follow RB-001.
- Releasing a held job: `scontrol release <id>` (**needs human approval**).
- Never change job priority, QOS or account limits without human approval.

## Verify
- The job's state changes from `PD` to `R`, or its reason changes to a normal wait (`Priority`) that clears over time.

## Escalate if
- Many users are blocked by the same limit (policy question for administrators).
- Jobs stay pending with `Resources` while matching nodes are idle (possible scheduler or configuration problem).
