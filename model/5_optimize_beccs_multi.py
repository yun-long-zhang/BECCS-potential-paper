# -*- coding: utf-8 -*-
"""Unified multi-commodity BECCS coordination model.

Replaces 5_optimize_beccs_coordination.py (which was the S1 biomass-only case).

BECCS potential = biogenic carbon captured (Mt CO2/yr); generation is fixed at
each plant's existing output; biomass use is limited by min(biomass potential,
generation fuel). City limits (W/S/B/G) come from BECCS_potential_city.xlsx
(per the corrected definition) plus the city biomass-capture ceiling.

Scenarios:
  S0  local self-sufficient (no transport)
  S1  biomass transport only
  S2  CO2 transport only
  S3  biomass + CO2 transport
  S4  biomass + CO2 + water (inter-basin transfer, optional)

LP (PuLP/CBC), sets cities i,j:
  x_j  realized BECCS (Mt/yr)
  B_ij biomass flow, C_ij CO2 flow, W_ij water flow (each with distance cost)
  constraints:
    x_j <= W_j + sum_i W_ij     water
    x_j <= S_j + sum_i C_ij     storage (local + imported CO2)
    x_j <= B_j + sum_i B_ij     biomass (local + imported)
    x_j <= G_j                  own biomass-capture ceiling (city)
    sum_j B_ij <= B_i           biomass export balance
    sum_j C_ij <= max(0, S_i - BECCS_local_i)
    sum_j W_ij <= WAT_CAP

Outputs: BECCS_scenarios_summary.xlsx, BECCS_scenario_city.xlsx, and
BECCS_coordination_result.xlsx (S3 city potentials + flows, for the map).
"""
import os
import numpy as np
import pandas as pd
from math import radians, sin, cos, asin, sqrt
import pulp

import _cols

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get('BECCS_OUT_DIR', HERE)   # scenario output folder
os.makedirs(OUT_DIR, exist_ok=True)
SRC = os.path.join(HERE, 'plant level analysis data.xlsx')
# AGG is produced by 1_compute_aggregate_city.py INTO OUT_DIR (see 4_ for the
# same reasoning) -- read it from OUT_DIR so each basis uses its own water table.
AGG = os.path.join(OUT_DIR, 'plant_city_hswud_aggregated.xlsx')
POT = os.path.join(OUT_DIR, 'BECCS_potential_city.xlsx')
OUT_SUM = os.path.join(OUT_DIR, 'BECCS_scenarios_summary.xlsx')
OUT_CITY = os.path.join(OUT_DIR, 'BECCS_scenario_city.xlsx')
OUT_COORD = os.path.join(OUT_DIR, 'BECCS_coordination_result.xlsx')

W_BIO = 1.0e-4
W_CO2 = 2.0e-5
W_WAT = 1.0e-2
WAT_CAP = 20.0
EFR = float(os.environ.get('BECCS_EFR', '0.50'))           # environmental-flow reserve (baseline 50%)
CAP = 0.90
BIO_EF = 0.112
EFF_PEN = 0.01
LIFE = float(os.environ.get('BECCS_LIFE', '20'))           # storage horizon (yr)
BIO_FACTOR = float(os.environ.get('BECCS_BIO_FACTOR', '1.0'))  # biomass availability
# biomass / storage buffer radius (see _cols.py): BECCS_BIO_RADIUS / BECCS_STO_RADIUS
BIO_COL = _cols.bio_col()          # biomass collection column (100/250/500 km)
STO_COL = _cols.sto_col()          # accessible storage volume column
INJ_COL = _cols.inj_col()          # annual injection-rate column
STO_FACTOR = float(os.environ.get('BECCS_STO_FACTOR', '1.0'))  # storage potential scaling
GEN_FACTOR = float(os.environ.get('BECCS_GEN_FACTOR', '1.0'))  # generation scaling
DESAL = os.environ.get('BECCS_DESAL', '0') == '1'          # coastal cities water unlimited
EWR = float(os.environ.get('BECCS_EWR', '0.0'))            # t water per t CO2 recovered
CONSUMPTION = os.environ.get('BECCS_CONSUMPTION', '0') == '1'  # use consumption instead of withdrawal
# DIAGNOSTIC ONLY: set the water ceiling equal to the generation ceiling, i.e.
# pretend water is never limiting.  Used to test whether relaxing / transporting
# water could raise the coordinated potential at all (answer: it cannot, because
# biomass is the global binding constraint once transport is allowed).
NOWATERLIMIT = os.environ.get('BECCS_NOWATERLIMIT', '0') == '1'

COASTAL = ['上海','丹东','东营','东莞','中山','厦门','台州','大连','天津','威海','宁德','宁波','福州','泉州','漳州','潍坊','烟台','珠海','青岛','防城港','阳江','连云港','营口','葫芦岛','锦州','钦州','北海','茂名','莆田','温州','深圳','惠州','汕尾','汕头','江门','潮州','湛江','舟山','唐山','秦皇岛','儋州']

# ---- build city limits from source (all in biogenic-C Mt/yr) ----
# S = physical storage / LIFE (transport-independent ceiling, importable-fillable)
# G = full-cofiring capture ceiling (max biogenic C from the city's generation)
# B = local biomass capture (importable resource)
# W = water-limited capture (biogenic C within water-limited generation;
#     biomass importable -> fuel_wat x EF x CAP, capped by generation G)
df = pd.read_excel(SRC, sheet_name=os.environ.get('BECCS_SHEET', '市域内比较'))
df = df[df['序号'].notna()].copy()
df['city'] = df['所在城市'].astype(str)
df['C_MW'] = pd.to_numeric(df['电厂实际装机总功率MW'], errors='coerce')
df['hh'] = pd.to_numeric(df['发电小时'], errors='coerce')
df['hr'] = pd.to_numeric(df['煤电系统热耗-GJ/MWH'], errors='coerce')
df['ef'] = pd.to_numeric(df['碳排放因子t/GJ'], errors='coerce')
df['bio_GJ'] = pd.to_numeric(df[BIO_COL], errors='coerce') * BIO_FACTOR
df['sto'] = pd.to_numeric(df[STO_COL], errors='coerce')
df['inj'] = pd.to_numeric(df[INJ_COL], errors='coerce')
# water-use intensity: withdrawal (default) or consumption (BECCS_CONSUMPTION=1)
_wint = '煤电 ccs 系统单位耗水量 (l/MWh)' if CONSUMPTION else '煤电 ccs 系统单位取水量 (l/MWh)'
df['w_ccs'] = pd.to_numeric(df[_wint], errors='coerce') / 1000.0
df['gen_MWh'] = df['C_MW'] * df['hh'] * GEN_FACTOR
df['fuel'] = df['gen_MWh'] * df['hr'] / (1 - EFF_PEN)
df['S'] = df[['sto', 'inj']].apply(
    lambda r: min(r['sto'] / LIFE, r['inj']), axis=1) * STO_FACTOR
df['G'] = df['fuel'] * BIO_EF * CAP * 1e-6
# Biomass ceiling of a city = all residues collected within the biomass buffer
# (100 km by default).  A city may co-fire at most min(residues, its own fuel
# demand); the fuel-demand cap is applied by the generation-ceiling constraint
# (x <= G) rather than by truncating this term, because both are evaluated at
# the CITY scale.  Surplus biomass is free to be exported to deficit cities.
df['B'] = df['bio_GJ'] * BIO_EF * CAP * 1e-6

# city water surplus (m3/yr) & allocation by generation share -> water-limited gen
ag = pd.read_excel(AGG, sheet_name='city_level')
# city coal+CCS water use: withdrawal (default) or consumption (from raw plant data)
_ccs_col = '煤电-ccs-系统年有效取水总量-除去海水-亿立方米'
if CONSUMPTION:
    _ccs_col = '煤电 ccs 系统年耗水总量  立方米'
df['w_city_亿m3'] = pd.to_numeric(df[_ccs_col], errors='coerce')
if CONSUMPTION:
    df['w_city_亿m3'] = df['w_city_亿m3'] / 1e8
plc = df.groupby('city')['w_city_亿m3'].sum().rename('coalccs_water')
ag = ag.merge(plc, left_on='地级市', right_index=True, how='left')
R = pd.to_numeric(ag['水资源总量_亿m3'], errors='coerce')
comp = pd.to_numeric(ag['最终竞争_亿m3'], errors='coerce')
ccs_w = ag['coalccs_water'].fillna(0)
ws = (R * (1 - EFR) - comp - ccs_w) * 1e8
df['city_wat'] = df['city'].map(dict(zip(ag['地级市'], ws))).fillna(0.0)
# DESAL: coastal cities with desalination potential -> water unlimited
if DESAL:
    df.loc[df['city'].isin(COASTAL), 'city_wat'] = 1e15
# EWR: brine water recovered from saline-aquifer storage (1 t water per t CO2 stored)
df['salt'] = pd.to_numeric(df['咸水层封存潜力'], errors='coerce').fillna(0.0) / LIFE
df['sto_phys'] = df['S']
df['ewr_cap'] = np.minimum(np.minimum(df['G'], df['sto_phys']), df['salt'])
df['ewr_m3'] = df['ewr_cap'] * EWR * 1e6
cgen = df.groupby('city')['gen_MWh'].sum()
df['walloc'] = (df['city_wat'] * df['gen_MWh'] / df['city'].map(cgen).replace(0, np.nan)
                + df['ewr_m3'])
df['E_wat'] = (df['walloc'] / df['w_ccs'].replace(0, np.nan)).clip(lower=0).clip(upper=df['gen_MWh'])
df['fuel_wat'] = df['E_wat'] * df['hr'] / (1 - EFF_PEN)
# W: biogenic C within water-limited generation, biomass importable
df['W'] = (df['fuel_wat'] * BIO_EF * CAP * 1e-6).clip(upper=df['G'])
if NOWATERLIMIT:
    # diagnostic: water imposes no ceiling at all
    df['W'] = df['G'].copy()

# city aggregates (biogenic-C Mt/yr)
# City-level resource ceilings (biogenic-C Mt/yr).  All four are evaluated at
# the SAME scale, which is the scale at which BCR / SER / WSR are defined.
cc = df.groupby('city').agg(S=('S', 'sum'), G=('G', 'sum'), B=('B', 'sum'),
                            W=('W', 'sum')).reset_index()
# Self-sufficient (S0) potential: no inter-city transfer at all, i.e. the
# zero-flow case of the unified model below.
cc['BECCS_local'] = cc[['S', 'G', 'B', 'W']].min(axis=1)
# attach city centroids (single merge -> keeps the lon/lat columns)
ll = df.groupby('city')[['经度', '纬度']].mean().reset_index()
cc = cc.merge(ll, on='city', how='left')
cc = cc.dropna(subset=['经度', '纬度']).reset_index(drop=True)
cities = cc['city'].tolist()
n = len(cities)


def hav(lon1, lat1, lon2, lat2):
    R = 6371.0
    dlon = radians(lon2 - lon1); dlat = radians(lat2 - lat1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * asin(sqrt(a))


dist = {(i, j): hav(cc.loc[i, '经度'], cc.loc[i, '纬度'], cc.loc[j, '经度'], cc.loc[j, '纬度'])
        for i in range(n) for j in range(n) if i != j}


def solve(allow_bio, allow_co2, allow_wat):
    """One unified model for every scenario -- the scenarios differ ONLY in
    which commodities may be transferred between cities.

    x_i = realized BECCS (biogenic C captured) at city i
    l_i = CO2 stored locally at city i ; C_ij = CO2 transported i -> j
    B_ij = biomass transported i -> j ;  W_ij = water transported i -> j

    Constraints (identical in all scenarios; a disabled commodity simply has
    all its flow variables fixed to zero):
        x_i                       <= G_i                  generation ceiling
        x_i + sum_j B_ij          <= B_i + sum_k B_ki     biomass balance
        x_i                       <= W_i + sum_k W_ki      water
        x_i = l_i + sum_j C_ij                             CO2 balance
        l_i + sum_k C_ki          <= S_i                   storage

    S0 is therefore the zero-flow case of this same model, not a separate
    formulation.
    """
    prob = pulp.LpProblem('BECCS', pulp.LpMaximize)
    x = pulp.LpVariable.dicts('x', range(n), lowBound=0)
    l = pulp.LpVariable.dicts('l', range(n), lowBound=0)   # local storage
    B = pulp.LpVariable.dicts('B', [(i, j) for i in range(n) for j in range(n) if i != j], lowBound=0) if allow_bio else {}
    C = pulp.LpVariable.dicts('C', [(i, j) for i in range(n) for j in range(n) if i != j], lowBound=0) if allow_co2 else {}
    Wv = pulp.LpVariable.dicts('W', [(i, j) for i in range(n) for j in range(n) if i != j], lowBound=0) if allow_wat else {}

    obj = pulp.lpSum(x[i] for i in range(n))
    obj -= W_BIO * pulp.lpSum(B[(i, j)] * dist[(i, j)] for (i, j) in B)
    obj -= W_CO2 * pulp.lpSum(C[(i, j)] * dist[(i, j)] for (i, j) in C)
    obj -= W_WAT * pulp.lpSum(Wv[(i, j)] * dist[(i, j)] for (i, j) in Wv)
    prob += obj

    for i in range(n):
        prob += x[i] <= cc.loc[i, 'G']                  # generation ceiling
        wat_in = pulp.lpSum(Wv[(k, i)] for k in range(n) if k != i) if allow_wat else 0
        bio_in = pulp.lpSum(B[(k, i)] for k in range(n) if k != i) if allow_bio else 0
        bio_out = pulp.lpSum(B[(i, j)] for j in range(n) if j != i) if allow_bio else 0
        prob += x[i] <= cc.loc[i, 'W'] + wat_in         # water
        # biomass balance: local use + exports <= own biomass + imports.
        # A single coupled constraint, so the same tonne can never be counted
        # twice.  With allow_bio = False both flow sums vanish and this reduces
        # to x_i <= B_i (the self-sufficient case).
        prob += x[i] + bio_out <= cc.loc[i, 'B'] + bio_in
        # CO2 balance & storage
        co2_out = pulp.lpSum(C[(i, k)] for k in range(n) if k != i) if allow_co2 else 0
        co2_in = pulp.lpSum(C[(k, i)] for k in range(n) if k != i) if allow_co2 else 0
        prob += x[i] == l[i] + co2_out                  # captured = local + exported
        prob += l[i] + co2_in <= cc.loc[i, 'S']         # local + imports <= storage
        if allow_wat:
            prob += pulp.lpSum(Wv[(i, j)] for j in range(n) if j != i) <= WAT_CAP

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    tot = float(sum(pulp.value(x[i]) for i in range(n)))
    bio_tot = float(sum(pulp.value(B[(i, j)]) for (i, j) in B)) if B else 0.0
    co2_tot = float(sum(pulp.value(C[(i, j)]) for (i, j) in C)) if C else 0.0
    wat_tot = float(sum(pulp.value(Wv[(i, j)]) for (i, j) in Wv)) if Wv else 0.0
    xv = [pulp.value(x[i]) for i in range(n)]
    flows_b = [(cities[i], cities[j], dist[(i, j)], pulp.value(B[(i, j)])) for (i, j) in B] if B else []
    flows_c = [(cities[i], cities[j], dist[(i, j)], pulp.value(C[(i, j)])) for (i, j) in C] if C else []
    flows_w = [(cities[i], cities[j], dist[(i, j)], pulp.value(Wv[(i, j)])) for (i, j) in Wv] if Wv else []
    return dict(status=pulp.LpStatus[status], total=tot, bio=bio_tot,
                co2=co2_tot, wat=wat_tot, x=xv,
                f_bio=[f for f in flows_b if f[3] > 1e-6],
                f_co2=[f for f in flows_c if f[3] > 1e-6],
                f_wat=[f for f in flows_w if f[3] > 1e-6])


scenarios = [
    ('S0_local', False, False, False),
    ('S1_biomass', True, False, False),
    ('S2_co2', False, True, False),
    ('S3_biomass+co2', True, True, False),
    ('S4_biomass+co2+water', True, True, True),
]

rows, city_results, coord_flows = [], {}, {}
for name, ab, ac, aw in scenarios:
    r = solve(ab, ac, aw)
    rows.append({'scenario': name, 'total_Mt_yr': r['total'],
                 'biomass_transport': r['bio'], 'co2_transport': r['co2'],
                 'water_transport': r['wat'], 'status': r['status']})
    city_results[name] = r['x']
    coord_flows[name] = {'bio': r['f_bio'], 'co2': r['f_co2'], 'wat': r['f_wat']}
    print(f'{name}: {r["total"]:.0f} Mt/yr  (bio={r["bio"]:.0f}, co2={r["co2"]:.0f}, wat={r["wat"]:.0f})')

summary = pd.DataFrame(rows)
summary.to_excel(OUT_SUM, sheet_name='summary', index=False)

city_df = pd.DataFrame({'city': cities})
for name in [s[0] for s in scenarios]:
    city_df[name + '_Mt_yr'] = city_results[name]
city_df.to_excel(OUT_CITY, sheet_name='city', index=False)

# ---- coordination result (all scenarios) for the maps ----
# city table: local potential + each scenario's realized potential + limits
city_out = city_df.copy()
lim = cc[['city', 'W', 'S', 'B', 'G']].copy()
city_out = city_out.merge(lim, on='city', how='left')
# flow tables per scenario per commodity
with pd.ExcelWriter(OUT_COORD) as xw:
    city_out.to_excel(xw, sheet_name='city', index=False)
    for scen in ['S1_biomass', 'S2_co2', 'S3_biomass+co2', 'S4_biomass+co2+water']:
        fb = coord_flows[scen]['bio']
        fc = coord_flows[scen]['co2']
        fw = coord_flows[scen]['wat']
        # one combined table with a 'commodity' column
        rows_all = ([(a, b, d, v, 'biomass') for a, b, d, v in fb] +
                    [(a, b, d, v, 'co2') for a, b, d, v in fc] +
                    [(a, b, d, v, 'water') for a, b, d, v in fw])
        df_f = pd.DataFrame(rows_all, columns=['from', 'to', 'km', 'Mt_yr', 'commodity'])
        df_f.to_excel(xw, sheet_name=scen, index=False)

print('\n--- national BECCS potential by scenario (Mt/yr) ---')
print(summary[['scenario', 'total_Mt_yr', 'biomass_transport', 'co2_transport', 'water_transport']].to_string(index=False))
s3 = coord_flows['S3_biomass+co2']
print('\n--- S3 transport flows, top 10 (Mt/yr) ---')
for t in sorted(s3['bio'], key=lambda t: -t[3])[:5]:
    print(f'  bio {t[0]} -> {t[1]} ({t[2]:.0f}km): {t[3]:.1f}')
for t in sorted(s3['co2'], key=lambda t: -t[3])[:5]:
    print(f'  co2 {t[0]} -> {t[1]} ({t[2]:.0f}km): {t[3]:.1f}')
print('\nsaved', OUT_SUM, '&', OUT_CITY, '&', OUT_COORD)
