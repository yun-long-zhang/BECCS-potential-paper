# -*- coding: utf-8 -*-
"""Coordination trade-offs (Fig. 5): transport cost-potential and
distance-potential frontiers.

Re-solves the least-cost coordination model of 5_optimize_beccs_multi.py

  (a) for a sequence of national potential targets between S0 and the
      coordinated maximum (cost frontier; BECCS_COST_FRONTIER=1 with a dense
      BECCS_FRONTIER_CUTS), and
  (b) under a series of maximum direct-link distances (BECCS_NEAR_KM).

Each solve runs in its own folder under $BECCS_OUT_DIR/tradeoff/, seeded with
the two baseline input tables, so the baseline results are not touched.

Output: $BECCS_OUT_DIR/tradeoff_frontiers.xlsx  (sheets 'cost', 'distance')
"""
import os
import shutil
import subprocess
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.abspath(os.environ.get('BECCS_OUT_DIR', os.path.join(HERE, '..', 'results')))
ROOT = os.path.join(OUT_DIR, 'tradeoff')
INPUTS = ['plant_city_hswud_aggregated.xlsx', 'BECCS_potential_city.xlsx']
CUTS = '0.24,0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90,0.93,0.96,0.98,1.00'
DISTANCES = [75, 100, 125, 150, 175, 200, 250, 300, 350, 400, 500, 750, 1000, 1500]


def run(folder, **env_extra):
    os.makedirs(folder, exist_ok=True)
    for f in INPUTS:
        shutil.copy(os.path.join(OUT_DIR, f), os.path.join(folder, f))
    env = dict(os.environ, BECCS_OUT_DIR=folder, **env_extra)
    with open(os.path.join(folder, '_log.txt'), 'w') as log:
        r = subprocess.run([sys.executable, '5_optimize_beccs_multi.py'], cwd=HERE,
                           env=env, stdout=log, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        raise RuntimeError('solve failed in %s' % folder)


# (a) cost frontier, unrestricted and 250 km
fdir = os.path.join(ROOT, 'cost_frontier')
run(fdir, BECCS_COST_FRONTIER='1', BECCS_FRONTIER_CUTS=CUTS, BECCS_NEAR_KM='250')
cost = pd.read_excel(os.path.join(fdir, 'BECCS_cost_frontier.xlsx'))
cost['cost_bnUSD_yr'] = cost['cost_usd'] / 1e9
print('cost frontier: %d points' % len(cost), flush=True)

# (b) distance frontier
rows = []
for d in DISTANCES:
    ddir = os.path.join(ROOT, 'dist_%d' % d)
    run(ddir, BECCS_NEAR_KM=str(d))
    s = pd.read_excel(os.path.join(ddir, 'BECCS_scenarios_summary.xlsx'))
    for _, r in s.iterrows():
        if r['scenario'].endswith('_%dkm' % d):
            rows.append({'max_km': d, 'scenario': r['scenario'].rsplit('_', 1)[0],
                         'potential_Mt_yr': r['T_max_Mt_yr'],
                         'cost_bnUSD_yr': r['transport_cost_bnUSD_yr']})
    print('distance %d km done' % d, flush=True)
dist = pd.DataFrame(rows)
base = pd.read_excel(os.path.join(OUT_DIR, 'BECCS_scenarios_summary.xlsx'))
s0 = float(base.loc[base.scenario == 'S0_local', 'T_max_Mt_yr'].iloc[0])
for _, r in base.iterrows():
    if r['scenario'] != 'S0_local' and not r['scenario'].endswith('km'):
        dist = pd.concat([dist, pd.DataFrame([{
            'max_km': float('inf'), 'scenario': r['scenario'],
            'potential_Mt_yr': r['T_max_Mt_yr'],
            'cost_bnUSD_yr': r['transport_cost_bnUSD_yr']}])])
qmax = dist[dist.max_km == float('inf')].set_index('scenario')['potential_Mt_yr']
dist['share_of_gain'] = [(p - s0) / (qmax[sc] - s0) for sc, p in
                         zip(dist['scenario'], dist['potential_Mt_yr'])]

with pd.ExcelWriter(os.path.join(OUT_DIR, 'tradeoff_frontiers.xlsx')) as xw:
    cost.to_excel(xw, sheet_name='cost', index=False)
    dist.to_excel(xw, sheet_name='distance', index=False)
    pd.DataFrame({'item': ['S0_Mt_yr', 'note'],
                  'value': [s0, 'costs are inter-city commodity transport only']}).to_excel(
        xw, sheet_name='readme', index=False)
print('saved', os.path.join(OUT_DIR, 'tradeoff_frontiers.xlsx'))
