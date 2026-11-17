# -*- coding: utf-8 -*-
"""Sensitivity scenario runner.

For each sensitivity scenario, it:
  1. creates a folder named after the scenario under the results root,
  2. writes a `params.json` record of the parameters,
  3. runs the city aggregation, BECCS potential, coordination optimisation and
     8-class export with those parameters injected via environment variables,
  4. with --figs, regenerates the figures that depend on those parameters.

Scenarios (each varies ONE parameter from the baseline, others fixed at base):
  - EFR 20%    (environmental-flow reserve)          [BECCS_EFR=0.20]
  - EFR 80%    (environmental-flow reserve)          [BECCS_EFR=0.80]
  - biomass 25% availability                         [BECCS_BIO_FACTOR=0.25]
  - biomass 50% availability                         [BECCS_BIO_FACTOR=0.50]
  - biomass from 250-km buffer                       [BECCS_BIO_RADIUS=250]
  - biomass from 500-km buffer                       [BECCS_BIO_RADIUS=500]
  - storage 100-km buffer                            [BECCS_STO_RADIUS=100]
  - storage 500-km buffer                            [BECCS_STO_RADIUS=500]
  - storage 25-year horizon                          [BECCS_LIFE=25]
  - storage 30-year horizon                          [BECCS_LIFE=30]
  - storage potential 50% / 25%                      [BECCS_STO_FACTOR]
  - generation 50% / 25%                             [BECCS_GEN_FACTOR]
  - desalination                                     [BECCS_DESAL]
  - CO2-EWR water recovery                           [BECCS_EWR]
  - consumption-based water use                      [BECCS_CONSUMPTION]

Usage (from model/, with BECCS_OUT_DIR pointing at the baseline results):
  python run_sensitivity.py --all            # all scenarios, then Fig. S16
  python run_sensitivity.py EFR20 BIO50      # selected scenarios
  python run_sensitivity.py --all --figs     # also redraw each scenario's figures

Scenario folders go to $BECCS_RES_ROOT, default $BECCS_OUT_DIR/sensitivity_results.
By default only the computation is rerun per scenario; Fig. S16 needs just
Fig3_6_prefecture_8class.xlsx and BECCS_coordination_result.xlsx from each.
"""
import os
import sys
import json
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

BASE_PARAMS = {'BECCS_EFR': '0.50', 'BECCS_LIFE': '20', 'BECCS_BIO_FACTOR': '1.0'}

SCENARIOS = {
    'EFR20':    {'BECCS_EFR': '0.20', 'label': 'Environmental flow 20%'},
    'EFR80':    {'BECCS_EFR': '0.80', 'label': 'Environmental flow 80%'},
    'BIO25':    {'BECCS_BIO_FACTOR': '0.25', 'label': 'Biomass 25% available'},
    'BIO50':    {'BECCS_BIO_FACTOR': '0.50', 'label': 'Biomass 50% available'},
    'BIO250':   {'BECCS_BIO_RADIUS': '250', 'label': 'Biomass from 250-km buffer'},
    'BIO500':   {'BECCS_BIO_RADIUS': '500', 'label': 'Biomass from 500-km buffer'},
    'STO100':   {'BECCS_STO_RADIUS': '100', 'label': 'Storage from 100-km buffer'},
    'STO500':   {'BECCS_STO_RADIUS': '500', 'label': 'Storage from 500-km buffer'},
    'STOR25':   {'BECCS_LIFE': '25', 'label': 'Storage 25-year horizon'},
    'STOR30':   {'BECCS_LIFE': '30', 'label': 'Storage 30-year horizon'},
    'STOCAP50': {'BECCS_STO_FACTOR': '0.50', 'label': 'Storage potential 50%'},
    'STOCAP25': {'BECCS_STO_FACTOR': '0.25', 'label': 'Storage potential 25%'},
    'GEN50':    {'BECCS_GEN_FACTOR': '0.50', 'label': 'Generation 50%'},
    'GEN25':    {'BECCS_GEN_FACTOR': '0.25', 'label': 'Generation 25%'},
    'DESAL':    {'BECCS_DESAL': '1', 'label': 'Desalination (coastal water unlimited)'},
    'EWR':      {'BECCS_EWR': '1.0', 'label': 'CO2-EWR water recovery (1 t water/t CO2)'},
    'CONS':     {'BECCS_CONSUMPTION': '1', 'label': 'Consumption-based water use'},
}

# scenario output root.  Default to <BECCS_OUT_DIR>/sensitivity_results rather
# than HERE/sensitivity_results, so a run that only sets BECCS_OUT_DIR keeps its
# scenarios next to its own results instead of clobbering the main basis.
ROOT = os.environ.get('BECCS_RES_ROOT',
                      os.path.join(os.environ.get('BECCS_OUT_DIR', HERE),
                                   'sensitivity_results'))

# scripts that are (re)run inside each scenario folder
COMPUTE_SCRIPTS = [
    '1_compute_aggregate_city.py',   # scenario city-level BCR/SER/WSR (fig 4/5/6)
    '4_compute_beccs_potential.py',
    '5_optimize_beccs_multi.py',
    '3_export_8class.py',            # 8-class table for fig 6
]
# figures regenerated per scenario (depend on the scenario parameters)
FIG_SCRIPTS = [
    '2_plot_fig3_4_joint.py',            # joint resource endowment
    '2_plot_fig3_6_combo.py',            # 8-class + mismatch combo
    '2_plot_fig3_7_potential.py',        # BECCS potential (from 4_compute)
    '2_plot_fig3_10_five_panel.py',      # coordination result (from 5_optimize)
]
# scenarios that also refresh the water (Fig3) and biomass/storage combo (Fig12)
# main panels (those are affected by generation, storage-potential, desalination,
# or EWR water-recovery changes)
GEN_CAP_SCEN = ('STOCAP50', 'STOCAP25', 'GEN50', 'GEN25', 'DESAL', 'EWR', 'CONS')
FIG_SCRIPTS_EXTRA = [
    '2_plot_fig3_3_water.py',            # WSR (GEN/DESAL/EWR affect water)
    '2_plot_fig3_12_biomass_storage_combo.py',  # BCR/SER main panels (STOCAP/GEN)
]
# buffer-radius scenarios change the BCR (biomass radius) and/or SER (storage
# radius) panels of Fig 3.12, so those must be refreshed too (water is
# unaffected by the buffer radius, so Fig 3.3 is not re-run here).
RADIUS_SCEN = ('BIO250', 'BIO500', 'STO100', 'STO500')
FIG_SCRIPTS_RADIUS = [
    '2_plot_fig3_12_biomass_storage_combo.py',
]


def run(cmd, env, label):
    print(f'    >>> {label}: {" ".join(os.path.basename(c) for c in cmd)}', flush=True)
    r = subprocess.run(cmd, cwd=HERE, env=env)
    if r.returncode != 0:
        print(f'    !! FAILED {label} (exit {r.returncode})', flush=True)
    return r.returncode == 0


def run_scenario(name, overrides):
    params = dict(BASE_PARAMS)
    params.update(overrides)
    folder = os.path.join(ROOT, name)
    os.makedirs(folder, exist_ok=True)

    env = dict(os.environ)
    env['BECCS_OUT_DIR'] = folder
    for k, v in params.items():
        env[k] = v

    print('\n' + '=' * 70)
    print(f'SCENARIO: {name}  ({SCENARIOS[name]["label"]})')
    print('  params:', params)
    print('  folder:', folder)
    print('=' * 70, flush=True)

    # 1) save parameter record
    with open(os.path.join(folder, 'params.json'), 'w') as f:
        json.dump({'scenario': name, 'label': SCENARIOS[name]['label'],
                   'params': params}, f, indent=2)

    ok = True
    # 2) run computations
    for s in COMPUTE_SCRIPTS:
        ok = run([PY, s], env, s) and ok
    if not FIGS:
        return ok
    # 4) regenerate dependent figures
    for s in FIG_SCRIPTS:
        ok = run([PY, s], env, s) and ok
    # 5) storage-potential / generation scenarios also refresh Fig3 & Fig12 main panels
    if name in GEN_CAP_SCEN:
        for s in FIG_SCRIPTS_EXTRA:
            ok = run([PY, s], env, s) and ok
    if name in RADIUS_SCEN:
        for s in FIG_SCRIPTS_RADIUS:
            ok = run([PY, s], env, s) and ok

    return ok


FIGS = False


def main():
    global FIGS
    args = sys.argv[1:]
    FIGS = '--figs' in args
    args = [a for a in args if a != '--figs']
    if args and args[0] == '--all':
        names = list(SCENARIOS)
    elif args:
        unknown = [a for a in args if a not in SCENARIOS]
        if unknown:
            print('Unknown scenario(s):', unknown)
            print('Available:', ', '.join(SCENARIOS))
            sys.exit(2)
        names = list(args)
    else:
        names = list(SCENARIOS)

    all_ok = True
    for n in names:
        all_ok = run_scenario(n, SCENARIOS[n]) and all_ok

    # after running one or more scenarios, rebuild the combined sensitivity
    # summary (FigS16).  Uses the AMBIENT BECCS_OUT_DIR / BECCS_RES_ROOT so an
    # alternative basis (e.g. nationwide Thiessen) writes into its own folder
    # instead of clobbering the main-text figures.
    if len(names) > 1:
        env = dict(os.environ)
        env.setdefault('BECCS_OUT_DIR', HERE)
        env.setdefault('BECCS_RES_ROOT', ROOT)
        all_ok = run([PY, '2_plot_figS16_sensitivity_combined.py'],
                     env, 'FigS16 sensitivity combined') and all_ok

    print('\n' + '=' * 70)
    print('DONE' if all_ok else 'SOME SCENARIOS FAILED')
    print('Results under:', ROOT)
    print('=' * 70)
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
