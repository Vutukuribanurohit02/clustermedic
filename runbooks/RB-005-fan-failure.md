---
id: RB-005
title: Chassis fan failure reported by BMC (Redfish)
fault_type: fan_failure
components: [hardware, redfish]
severity: high
destructive_actions: [drain_node]
---

## Symptoms
- A fan reading in Redfish is 0 RPM, missing, or far below the other fans in the same chassis.
- The fan's `Status.Health` is `Warning` or `Critical`.
- Chassis or CPU temperatures rise on that node (see RB-006).

## Diagnose (read-only)
1. List chassis: `GET /redfish/v1/Chassis`.
2. Read fans: `GET /redfish/v1/Chassis/<id>/Thermal` and inspect `Fans[]` for `Name`, `Reading`, `ReadingUnits`, `Status.Health` and `Status.State`. Newer BMCs may expose this under `ThermalSubsystem/Fans` instead.
3. Compare the suspect fan with its peers. A healthy fan is usually within about 10% of fans of the same type.
4. `Status.State: Absent` means no fan is installed in that slot. That is different from a failed fan, and is normal for empty slots.
5. Read temperatures from the same `Thermal` resource: is the node already heating up?
6. Check the BMC event log (Redfish `LogServices`) for fan or redundancy-lost events and their timestamps.

## Common causes
- Failed fan motor or bearing.
- Fan unplugged or not seated after maintenance.
- Faulty fan sensor (fan spins, reading is wrong).
- Blocked airflow or dust build-up.

## Fix
- Drain the node so no new jobs land on it while cooling is reduced: `scontrol update nodename=<node> state=drain reason="fan failure <fan name>"` (**needs human approval**).
- Open a hardware ticket for fan replacement.
- Do not resume the node until the fan is replaced and readings are normal.

## Verify
- After replacement, the fan reading is in line with its peers and `Status.Health` is `OK`.
- Temperatures return to normal under load.
- Then resume the node per RB-001.

## Escalate if
- Always, for hardware replacement.
- Immediately if temperatures are at or above critical thresholds (see RB-006).
- If more than one fan in the same chassis fails.
