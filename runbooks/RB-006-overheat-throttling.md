---
id: RB-006
title: GPU or CPU overheating and thermal throttling
fault_type: overheat
components: [hardware, gpu, redfish, prometheus]
severity: high
destructive_actions: [drain_node]
---

## Symptoms
- `DCGM_FI_DEV_GPU_TEMP` above the site warning threshold (this lab uses 85 °C warning and 90 °C critical; real limits depend on the GPU model).
- Jobs on one node run noticeably slower than the same job on other nodes.
- Redfish CPU or chassis temperature sensors read higher than usual.

## Diagnose (read-only)
1. Which GPUs are hot? PromQL: `DCGM_FI_DEV_GPU_TEMP > 85`, grouped by `Hostname` and `gpu`.
2. Scope the problem:
   - One GPU hot, its neighbours normal: likely that GPU or its local airflow.
   - All GPUs on one node hot: likely node cooling, so check fans (RB-005).
   - Many nodes hot: likely the room, so check the inlet temperature.
3. Redfish: `GET /redfish/v1/Chassis/<id>/Thermal` for CPU, inlet/intake and fan readings.
4. On a real GPU node: `nvidia-smi -q -d TEMPERATURE` shows the current temperature and the model's slowdown and shutdown limits; `nvidia-smi -q -d PERFORMANCE` shows whether clocks are being reduced for thermal reasons.
5. Check load: `DCGM_FI_DEV_GPU_UTIL` and `DCGM_FI_DEV_POWER_USAGE`. High temperature at low load is more worrying than at full load.

## Common causes
- Fan failure (RB-005).
- High inlet (room) temperature or blocked airflow.
- Degraded thermal paste or heatsink contact on one device.
- Sustained full load in a poorly cooled slot.

## Fix
- Drain the node to stop new work landing on it (**needs human approval**).
- If a fan has failed, follow RB-005.
- For room-wide heat, notify facilities; do not try to fix it from the cluster.
- Do not cancel running jobs unless temperatures reach critical (**needs human approval**).

## Verify
- Temperatures stay below the warning threshold for at least 10 minutes under normal load.
- Job runtime on the node matches other nodes.

## Escalate if
- Any reading at or above the critical threshold.
- More than one node is affected (facility issue).
- A single GPU stays hot after airflow is confirmed normal (possible hardware fault).
