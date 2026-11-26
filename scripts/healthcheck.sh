#!/usr/bin/env bash
# Checks every ClusterMedic service. Prints OK/FAIL; exit code = number of failures.
set -u
fail=0

check() {  # usage: check "<label>" <command...>
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf "  %-22s \e[32mOK\e[0m\n" "$name"
  else
    printf "  %-22s \e[31mFAIL\e[0m\n" "$name"; fail=$((fail + 1))
  fi
}

echo "ClusterMedic health:"
check "slurm controller"   docker exec slurmctld scontrol ping
check "slurm nodes healthy" bash -c 's=$(docker exec slurmctld sinfo -h -N -o %t) && [ -n "$s" ] && ! grep -qvE "^(idle|mix|alloc)$" <<<"$s"'
check "redfish"            curl -sf localhost:8000/redfish/v1
check "node-exporter"      curl -sf localhost:9100/metrics
check "gpu-exporter"       bash -c 'curl -sf localhost:9400/metrics | grep -q DCGM_FI_DEV_GPU_TEMP'
check "prometheus"         curl -sf localhost:9090/-/ready
# the clustermedic target is only up while `make serve` runs, so it is not required here
check "prometheus targets" bash -c '[ "$(curl -sf localhost:9090/api/v1/targets | jq "[.data.activeTargets[] | select(.health != \"up\" and .labels.job != \"clustermedic\")] | length")" = "0" ]'
check "alertmanager"       curl -sf localhost:9093/-/ready
check "grafana"            curl -sf localhost:3000/api/health

if curl -sf localhost:9500/healthz >/dev/null 2>&1; then
  printf "  %-22s \e[32mrunning\e[0m\n" "clustermedic service"
else
  printf "  %-22s \e[33mnot running\e[0m (optional: make serve)\n" "clustermedic service"
fi
exit "$fail"
