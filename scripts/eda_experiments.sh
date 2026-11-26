#!/usr/bin/env bash
# Generate labelled EDA runs with real tools (OpenROAD-flow-scripts + Yosys in Docker).
# Each run is a deliberate change with a known cause; labels live in eda/labels.json.
#   usage: scripts/eda_experiments.sh [run-name ...]     (default: all)
set -uo pipefail
IMAGE=${ORFS_IMAGE:-openroad/orfs:latest}
cd "$(dirname "$0")/.."
OUT=$PWD/eda/runs
mkdir -p "$OUT"
cp eda/labels.json "$OUT/labels.json"
UIDGID="$(id -u):$(id -g)"

orfs() {  # name, extra make args...
  local name=$1; shift
  echo "=== ORFS gcd/sky130hd: $name ($*)"
  rm -rf "${OUT:?}/$name"; mkdir -p "$OUT/$name"
  docker run --rm -v "$PWD/eda:/eda" "$IMAGE" bash -c "
    source /OpenROAD-flow-scripts/env.sh >/dev/null 2>&1
    cd /OpenROAD-flow-scripts/flow
    timeout 1800 make DESIGN_CONFIG=./designs/sky130hd/gcd/config.mk FLOW_VARIANT=$name $* > /eda/runs/$name/make.log 2>&1
    echo \"make exit code: \$?\" >> /eda/runs/$name/make.log
    cp -r logs/sky130hd/gcd/$name /eda/runs/$name/logs 2>/dev/null
    cp -r reports/sky130hd/gcd/$name /eda/runs/$name/reports 2>/dev/null
    chown -R $UIDGID /eda/runs/$name"
  tail -1 "$OUT/$name/make.log"
}

yosys_run() {  # name, rtl file
  local name=$1 rtl=$2
  echo "=== Yosys: $name ($rtl)"
  rm -rf "${OUT:?}/$name"; mkdir -p "$OUT/$name"
  docker run --rm -v "$PWD/eda:/eda" "$IMAGE" bash -c "
    source /OpenROAD-flow-scripts/env.sh >/dev/null 2>&1
    yosys -l /eda/runs/$name/yosys.log -p 'read_verilog /eda/rtl/$rtl; synth -top top; stat' > /dev/null 2>&1
    echo \"yosys exit code: \$?\" >> /eda/runs/$name/yosys.log
    chown -R $UIDGID /eda/runs/$name"
  grep -E -c "Warning|Latch inferred" "$OUT/$name/yosys.log" | sed 's/^/  warning lines: /'
}

ALL=("$@")
w() { [ ${#ALL[@]} -eq 0 ] && return 0; for x in "${ALL[@]}"; do [ "$x" = "$1" ] && return 0; done; return 1; }

w rtl_clean       && yosys_run rtl_clean clean.v
w rtl_latch       && yosys_run rtl_latch latch.v
w rtl_undriven    && yosys_run rtl_undriven undriven.v
w rtl_multidriver && yosys_run rtl_multidriver multidriver.v
w gcd_relaxed     && orfs gcd_relaxed SDC_FILE=/eda/sdc/relaxed.sdc
w gcd_tight       && orfs gcd_tight   SDC_FILE=/eda/sdc/tight.sdc
w gcd_tighter     && orfs gcd_tighter SDC_FILE=/eda/sdc/tighter.sdc
w gcd_dense       && orfs gcd_dense   CORE_UTILIZATION=99 PLACE_DENSITY=0.99
echo "done: runs in eda/runs (evaluate with: python -m clustermedic.eda eval)"
