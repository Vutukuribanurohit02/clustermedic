#!/usr/bin/env bash
# Scripted demo for recording: fault -> alert -> diagnosis + GitHub issue -> approval -> verified fix.
# Needs `make up` and `make serve` (in another terminal) running. Takes about 2 minutes.
set -euo pipefail
cd "$(dirname "$0")/.."
FAULT="${1:-node_drain}"

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
nodes() { docker exec slurmctld sinfo -N -o "%N|%T|%E" | column -t -s "|"; }

say "Healthy cluster"
nodes
python -m clustermedic.faults status

say "Injecting fault: $FAULT"
python -m clustermedic.faults inject "$FAULT"
nodes

say "Waiting for Prometheus alert -> ClusterMedic diagnosis"
start=$(date +%s)
while :; do
  out=$(python -m clustermedic.agent pending 2>/dev/null || true)
  [[ -n "$out" && "$out" != no\ incidents* ]] && break
  printf '\r  %ss elapsed' "$(( $(date +%s) - start ))"
  (( $(date +%s) - start > 300 )) && { echo; echo "no incident after 5 min (cooldown? service running?)"; exit 1; }
  sleep 3
done
printf '\r  incident ready after %ss\n' "$(( $(date +%s) - start ))"
echo "$out"

id=$(echo "$out" | head -1 | awk '{print $1}')
issue=$(echo "$out" | grep -o 'issues/[0-9]*' | head -1 | cut -d/ -f2 || true)

while read -r -t 0.1 _; do :; done; read -rp $'\nHuman review: approve this action? [press Enter] '
say "Approving $id"
python -m clustermedic.agent approve "$id"

say "Result"
nodes
if [[ -n "$issue" ]]; then
  gh issue view "$issue" --json number,title,state,url \
    --template '#{{.number}} {{.title}} -> {{.state}}{{"\n"}}{{.url}}{{"\n"}}'
fi
python -m clustermedic.faults clear --all >/dev/null 2>&1 || true
say "Done"
