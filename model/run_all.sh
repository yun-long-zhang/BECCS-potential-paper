#!/usr/bin/env bash
# Reproduce every result and figure of the paper into one results folder.
#
#   ./run_all.sh [OUT_DIR]        (default ../results; ~35 min)
#
# Order: baseline computation -> baseline figures -> 17 sensitivity scenarios
# -> Fig. 16.  Each step's console output goes to OUT_DIR/_log_<script>.txt.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-python}
export BECCS_OUT_DIR=${1:-../results}
export BECCS_SHEET="city clip"
unset BECCS_RES_ROOT BECCS_CCS_PENALTY BECCS_NEAR_KM BECCS_WATER_TABLE
mkdir -p "$BECCS_OUT_DIR"

run() {
    echo "=== $1"
    "$PY" "$@" > "$BECCS_OUT_DIR/_log_${1%.py}.txt" 2>&1 \
        || { echo "FAILED: $1 (see $BECCS_OUT_DIR/_log_${1%.py}.txt)"; exit 1; }
}

run 1_compute_aggregate_city.py
run 4_compute_beccs_potential.py
run 5_optimize_beccs_multi.py
run 6_tradeoff_frontiers.py
run 3_export_8class.py
run 2_plot_fig3_3_water.py
run 2_plot_fig3_4_joint.py
run 2_plot_fig3_6_combo.py
run 2_plot_fig3_7_potential.py
run 2_plot_fig3_10_five_panel.py
run 2_plot_fig3_12_biomass_storage_combo.py
run 2_plot_figS_gini_city.py
run 2_plot_figS_transport_distance.py
run 2_plot_figS12_water_efr.py
run 2_plot_figS_s4_flows.py
run 2_plot_fig5_tradeoff.py
run run_sensitivity.py --all          # also redraws Fig. 16 at the end
echo "done: $BECCS_OUT_DIR"
