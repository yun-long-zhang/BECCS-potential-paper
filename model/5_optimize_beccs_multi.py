# -*- coding: utf-8 -*-
"""Unified multi-commodity BECCS coordination model.

Replaces 5_optimize_beccs_coordination.py (which was the S1 biomass-only case).

BECCS potential = biogenic carbon captured (Mt CO2/yr); generation is fixed at
each plant's existing output; biomass use is limited by min(biomass potential,
generation fuel). City limits (W/S/B/G) come from BECCS_potential_city.xlsx
(per the corrected '口径 X' definition) plus the city biomass-capture ceiling.

Scenarios:
  S0  local self-sufficient (no transport)
  S1  biomass transport only
  S2  CO2 transport only
  S3  biomass + CO2 transport
  S4  biomass + CO2 + water (inter-basin transfer, optional)

Two interchangeable objectives (BECCS_OBJECTIVE = 'cost' | 'penalty'):

  cost     min  sum_k K_k * flow_k * d_k * 1e-6      [bn USD/yr]
           subject to   sum_i x_i >= T,  where T is raised until the model
           becomes infeasible.  K_k are REAL engineering unit costs expressed
           per Mt moved per km:
               biomass  0.11   $/t/km  x 6.614e5 t /Mt CO2  =  72,751
               CO2      0.035  $/t/km  x 1.000e6 t /Mt CO2  =  35,000
               water    0.0085 $/m3/km x 1e6 m3 /Mt water   =   8,500
           The national potential is therefore set purely by feasibility, and
           the objective only selects the cheapest way to realise it.

  penalty  max  sum_i x_i - sum_k w_k * flow_k * d_k   (legacy formulation)
           with w_bio=1e-4, w_co2=2e-5, w_wat=1e-2/4.82 (per Mt water).

LP (PuLP/CBC), sets cities i,j:
  x_j  realized BECCS (Mt CO2/yr)
  B_ij biomass flow (Mt CO2-eq), C_ij CO2 flow (Mt), W_ij water flow (Mt water)
  constraints (see build_solve):
    x_j <= G_j                                  generation ceiling
    ob_j + sum_k B_jk <= B_j,  x_j <= ob_j + sum_i B_ij       biomass
    x_j <= W_j + y_j,  ow_j + sum_k W_jk <= E_j,  DELTA_j y_j <= ow_j + sum_i W_ij   water
    x_j = l_j + sum_k C_jk,    l_j + sum_i C_ij <= S_j        CO2 / storage
  Exports come only from a city's own endowment (no relay), and water is
  conserved.  Each coordinated scenario is also solved with all flows limited
  to BECCS_NEAR_KM (default 250 km) as a hard constraint ('<name>_250km').

v2 changes (vs the published version): water conserved and in physical units
(the published version let a city export up to 20 Mt CO2-eq of water without
reducing its own supply), water-use from the unit sheet joined by plant id,
no double counting of the coal fleet's water, CCS energy penalty in the fuel
demand (BECCS_CCS_PENALTY), no-relay flows, and the hard distance-cap runs.

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
W_WAT = 1.0e-2 / 4.82      # per Mt water (legacy weight was per Mt CO2-eq)

# ---- objective selection -------------------------------------------------
# 'cost'    -> minimise real engineering transport cost while forcing the
#              national potential up to its feasibility limit (default).
# 'penalty' -> legacy / published formulation (maximise potential net of small
#              distance-weighted penalties).  Both reach the same potential.
OBJECTIVE = os.environ.get('BECCS_OBJECTIVE', 'cost').lower()
assert OBJECTIVE in ('cost', 'penalty'), OBJECTIVE

# Real engineering unit costs (USD per unit per km), used by OBJECTIVE='cost'.
BIOMASS_GJ_PER_T = 15.0            # LHV of a crop/forest residue mix
USD_BIO_T_KM = 0.11               # biomass road/rail freight
USD_CO2_T_KM = 0.035              # pipeline / rail / ship
USD_WAT_M3_KM = 0.0085            # inter-basin transfer
# expressed in bn USD/yr so CBC keeps a well-scaled objective
COST_SCALE = 1e-9
# how finely the potential ceiling T is located in 'cost' mode (Mt/yr).
# Must be well below the reporting precision (0.01 Mt) so that the potential
# returned in cost mode matches the penalty-mode / pooled-bound value exactly.
T_TOL = float(os.environ.get('BECCS_T_TOL', '1e-4'))

EFR = float(os.environ.get('BECCS_EFR', '0.50'))           # environmental-flow reserve (baseline 50%)
CAP = 0.90
BIO_EF = 0.112

# Cost coefficients -> USD per Mt CO2 per km, i.e. the unit cost multiplied by
# the physical mass that must move per Mt of captured CO2.
#     biomass  0.11   $/t/km  x 6.614e5 t /Mt   =   72,751
#     CO2      0.035  $/t/km  x 1.000e6 t /Mt   =   35,000
#     water    0.0085 $/m3/km x 1e6 m3 per Mt water (water flows are physical)
T_BIO_PER_MTCO2 = 1e6 / (BIO_EF * CAP) / BIOMASS_GJ_PER_T
K_BIO = USD_BIO_T_KM * T_BIO_PER_MTCO2
K_CO2 = USD_CO2_T_KM * 1e6
K_WAT = USD_WAT_M3_KM * 1e6
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
# W = water-limited capture under self-sufficiency, sum of f_i x G_i over the
#     city's plants, with the city's water allocated by generation (see 4_)
# Water is transported in PHYSICAL units (Mt water): a city can export E, the
# water its plants' allocations leave over after their own BECCS share, and
# needs DELTA Mt of water per Mt of BECCS beyond W (the mean extra CCS water of
# the generation not yet converted).
df = _cols.read_plants(SRC)
df['city'] = df['所在城市'].astype(str)
df['C_MW'] = pd.to_numeric(df['电厂实际装机总功率MW'], errors='coerce')
df['hh'] = pd.to_numeric(df['发电小时'], errors='coerce')
df['ef'] = pd.to_numeric(df['碳排放因子t/GJ'], errors='coerce')
df['bio_GJ'] = pd.to_numeric(df[BIO_COL], errors='coerce') * BIO_FACTOR
df['sto'] = pd.to_numeric(df[STO_COL], errors='coerce')
df['inj'] = pd.to_numeric(df[INJ_COL], errors='coerce')
df['gen_MWh'] = df['C_MW'] * df['hh'] * GEN_FACTOR
df['fuel'] = df['gen_MWh'] * _cols.fuel_per_mwh(df)
df['S'] = df[['sto', 'inj']].apply(
    lambda r: min(r['sto'] / LIFE, r['inj']), axis=1) * STO_FACTOR
df['G'] = df['fuel'] * BIO_EF * CAP * 1e-6
# Biomass ceiling of a city = all residues collected within the biomass buffer
# (100 km by default).  A city may co-fire at most min(residues, its own fuel
# demand); the fuel-demand cap is applied by the generation-ceiling constraint
# (x <= G) rather than by truncating this term, because both are evaluated at
# the CITY scale.  Surplus biomass is free to be exported to deficit cities.
df['B'] = df['bio_GJ'] * BIO_EF * CAP * 1e-6

# annual water use (m3/yr) of the coal-only and coal + CCS systems, from the
# unit sheet joined by 电厂编号 (withdrawal or consumption, scaled by GEN_FACTOR)
df['w_coal'], df['w_ccs'] = _cols.water_use(SRC, df)
# EWR: brine water recovered from saline-aquifer storage (EWR t water per t CO2)
df['salt'] = pd.to_numeric(df['咸水层封存潜力'], errors='coerce').fillna(0.0) / LIFE
df['ewr_cap'] = np.minimum(np.minimum(df['G'], df['S']), df['salt'])
df['ewr_m3'] = df['ewr_cap'] * EWR * 1e6

# plant-level water: the city's available water A = R(1-EFR) - U is allocated
# by generation share (identical to 4_compute_beccs_potential.py)
ag = pd.read_excel(AGG, sheet_name='city_level')
R = pd.to_numeric(ag['水资源总量_亿m3'], errors='coerce') * 1e8
comp = pd.to_numeric(ag['最终竞争_亿m3'], errors='coerce') * 1e8
city_avail = dict(zip(ag['地级市'], R * (1 - EFR) - comp))
city_gen = df.groupby('city')['gen_MWh'].transform('sum')
df['alloc'] = (df['city'].map(city_avail).astype(float).fillna(0.0)
               * df['gen_MWh'] / city_gen.replace(0, np.nan)).fillna(0.0) + df['ewr_m3']
df['extra'] = df['w_ccs'] - df['w_coal']                # extra water at full BECCS
f = ((df['alloc'] - df['w_coal']) / df['extra'].where(df['extra'] > 0)).clip(0, 1)
f = f.where(df['extra'] > 0, 1.0)                      # CCS needs no extra water
if DESAL:
    f[df['city'].isin(COASTAL)] = 1.0                  # desalination covers own needs
if NOWATERLIMIT:
    f[:] = 1.0                                         # diagnostic only
df['f'] = f
df['W'] = df['f'] * df['G']
# water left over in the plant's allocation after its own BECCS share (m3/yr)
df['left'] = (df['alloc'] - df['w_coal'] - df['f'] * df['extra']).clip(lower=0)
if DESAL:
    df.loc[df['city'].isin(COASTAL), 'left'] = 0.0     # desalinated water is not exported
# generation not yet converted, and the extra water it would need
df['G_rest'] = (1 - df['f']) * df['G']
df['w_rest'] = (1 - df['f']) * df['extra'].clip(lower=0)

# city aggregates (biogenic-C Mt/yr; water in Mt/yr)
cc = df.groupby('city').agg(S=('S', 'sum'), G=('G', 'sum'), B=('B', 'sum'),
                            W=('W', 'sum'), left=('left', 'sum'),
                            G_rest=('G_rest', 'sum'), w_rest=('w_rest', 'sum')).reset_index()
cc['E_wat'] = cc['left'] / 1e6
cc['DELTA'] = (cc['w_rest'] / 1e6 / cc['G_rest'].replace(0, np.nan)).fillna(0.0)
# Self-sufficient (S0) potential: no inter-city transfer at all, i.e. the
# zero-flow case of the unified model below.
cc['BECCS_local'] = cc[['S', 'G', 'B', 'W']].min(axis=1)
# attach city centroids (single merge -> keeps 经度/纬度 columns)
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


def build_solve(allow_bio, allow_co2, allow_wat, dmax=None):
    """Build the LP for one scenario and return the problem plus its variables.

    x_i  = realized BECCS (biogenic C captured) at city i
    l_i  = CO2 stored locally at city i ; C_ij = CO2 transported i -> j
    ob_i = own biomass used at i        ; B_ij = biomass transported i -> j
    ow_i = own leftover water used at i ; W_ij = water transported i -> j (Mt water)
    y_i  = BECCS at i beyond the local water-supported level W_i

    Constraints (a disabled commodity has no flow variables):
        x_i                    <= G_i                    generation ceiling
        ob_i + sum_j B_ij      <= B_i                    biomass: own stock
        x_i                    <= ob_i + sum_k B_ki      biomass: supply
        x_i                    <= W_i + y_i              water: local level + extra
        ow_i + sum_j W_ij      <= E_i                    water: own leftover
        DELTA_i y_i            <= ow_i + sum_k W_ki      water: supply of the extra
        x_i = l_i + sum_j C_ij                           CO2 balance
        l_i + sum_k C_ki       <= S_i                    storage

    Exports come only from a city's OWN endowment, so imported biomass or
    water cannot be passed on (no relay); with a distance cap dmax this makes
    every flow a direct origin-destination link no longer than dmax.  Water is
    conserved: what a city exports it can no longer use itself.

    In 'cost' mode a demand constraint sum_i x_i >= T is added and T is raised
    until the LP becomes infeasible.
    """
    prob = pulp.LpProblem('BECCS', pulp.LpMinimize if OBJECTIVE == 'cost'
                          else pulp.LpMaximize)
    arcs = [a for a, d in dist.items() if dmax is None or d <= dmax]
    out = {i: [] for i in range(n)}
    inn = {i: [] for i in range(n)}
    for (i, j) in arcs:
        out[i].append((i, j))
        inn[j].append((i, j))
    x = pulp.LpVariable.dicts('x', range(n), lowBound=0)
    l = pulp.LpVariable.dicts('l', range(n), lowBound=0)   # local storage
    ob = pulp.LpVariable.dicts('ob', range(n), lowBound=0) if allow_bio else {}
    ow = pulp.LpVariable.dicts('ow', range(n), lowBound=0) if allow_wat else {}
    y = pulp.LpVariable.dicts('y', range(n), lowBound=0) if allow_wat else {}
    B = pulp.LpVariable.dicts('B', arcs, lowBound=0) if allow_bio else {}
    C = pulp.LpVariable.dicts('C', arcs, lowBound=0) if allow_co2 else {}
    Wv = pulp.LpVariable.dicts('W', arcs, lowBound=0) if allow_wat else {}

    def s(V, L):
        return pulp.lpSum(V[a] for a in L) if V else 0

    km_bio = pulp.lpSum(B[a] * dist[a] for a in B)
    km_co2 = pulp.lpSum(C[a] * dist[a] for a in C)
    km_wat = pulp.lpSum(Wv[a] * dist[a] for a in Wv)
    if OBJECTIVE == 'cost':
        # minimise real engineering transport cost (bn USD/yr); the potential
        # itself is imposed through the 'demand' constraint added below.
        prob += COST_SCALE * (K_BIO * km_bio + K_CO2 * km_co2 + K_WAT * km_wat)
    else:
        prob += (pulp.lpSum(x[i] for i in range(n))
                 - W_BIO * km_bio - W_CO2 * km_co2 - W_WAT * km_wat)

    for i in range(n):
        prob += x[i] <= cc.loc[i, 'G']                  # generation ceiling
        if allow_bio:
            prob += ob[i] + s(B, out[i]) <= cc.loc[i, 'B']
            prob += x[i] <= ob[i] + s(B, inn[i])
        else:
            prob += x[i] <= cc.loc[i, 'B']
        if allow_wat:
            # BECCS beyond the local water-supported level W needs extra water
            prob += x[i] <= cc.loc[i, 'W'] + y[i]
            prob += ow[i] + s(Wv, out[i]) <= cc.loc[i, 'E_wat']
            prob += cc.loc[i, 'DELTA'] * y[i] <= ow[i] + s(Wv, inn[i])
        else:
            prob += x[i] <= cc.loc[i, 'W']
        # CO2 balance & storage
        prob += x[i] == l[i] + s(C, out[i])             # captured = local + exported
        prob += l[i] + s(C, inn[i]) <= cc.loc[i, 'S']   # local + imports <= storage

    if OBJECTIVE == 'cost':
        dem = pulp.LpConstraint(pulp.lpSum(x[i] for i in range(n)),
                                sense=pulp.LpConstraintGE, rhs=0.0, name='demand')
        prob += dem
    return prob, x, l, B, C, Wv


def extract(prob, x, l, B, C, Wv):
    """Pull the solved values out of the LP.

    Flow tables carry Mt CO2-eq (the BECCS potential the flow supports: biomass
    and CO2 directly, water divided by the receiving city's DELTA) plus the
    physical mass moved (phys_Mt).
    """
    tot = float(sum(pulp.value(x[i]) for i in range(n)))
    xv = [pulp.value(x[i]) for i in range(n)]

    def rows(V, comm):
        r = []
        for (i, j) in V:
            v = pulp.value(V[(i, j)])
            if v is None or v <= 1e-6:
                continue
            if comm == 'biomass':
                eq, phys = v, v * T_BIO_PER_MTCO2 / 1e6
            elif comm == 'co2':
                eq, phys = v, v
            else:
                dj = cc.loc[j, 'DELTA']
                eq, phys = (v / dj if dj > 0 else 0.0), v
            r.append((cities[i], cities[j], dist[(i, j)], eq, phys))
        return r
    f_bio, f_co2, f_wat = rows(B, 'biomass'), rows(C, 'co2'), rows(Wv, 'water')
    return dict(status=pulp.LpStatus[prob.status], total=tot,
                bio=sum(f[3] for f in f_bio), co2=sum(f[3] for f in f_co2),
                wat=sum(f[3] for f in f_wat), wat_phys=sum(f[4] for f in f_wat),
                x=xv, f_bio=f_bio, f_co2=f_co2, f_wat=f_wat)


def cost_of(r):
    """Real engineering transport cost (USD/yr) of a solved configuration."""
    return float(K_BIO * sum(d * v for _, _, d, v, _ in r['f_bio'])
                 + K_CO2 * sum(d * v for _, _, d, v, _ in r['f_co2'])
                 + K_WAT * sum(d * p for _, _, d, _, p in r['f_wat']))


def run(allow_bio, allow_co2, allow_wat, dmax=None):
    """Solve one scenario.

    'penalty' mode solves once and returns the result.  'cost' mode first
    locates the maximum feasible potential T (test the pooled bound, else
    bisect), then returns the least-cost configuration attaining it.
    """
    prob, x, l, B, C, Wv = build_solve(allow_bio, allow_co2, allow_wat, dmax)
    if OBJECTIVE != 'cost':
        prob.solve(pulp.PULP_CBC_CMD(msg=False))
        r = extract(prob, x, l, B, C, Wv)
        r['T_max'] = r['total']
        r['cost_usd'] = cost_of(r)
        return r

    # Upper bound on the national potential, from summing each balance over i:
    #   biomass  sum(x) <= sum(B);  storage  sum(x) <= sum(S);  sum(x) <= sum(G)
    #   water without transfer: sum(x) <= sum(W).  With water transfer the water
    #   balance bounds sum(DELTA x), not sum(x), so it gives no bound on sum(x).
    bounds = [cc['B'].sum(), cc['S'].sum(), cc['G'].sum()]
    if not allow_wat:
        bounds.append(cc['W'].sum())
    UB = float(min(bounds))

    def feasible(T):
        prob.constraints['demand'].changeRHS(T)
        prob.solve(pulp.PULP_CBC_CMD(msg=False))
        return pulp.LpStatus[prob.status] == 'Optimal'

    # Fast path: the pooled bound UB is often attainable, so test it first.
    if feasible(UB):
        r = extract(prob, x, l, B, C, Wv)
        r['T_max'] = UB
        r['T_infeasible'] = UB
        r['cost_usd'] = cost_of(r)
        return r

    # Otherwise bisect between the self-sufficient potential (always feasible)
    # and the pooled bound (just shown infeasible).
    lo = float(cc['BECCS_local'].sum())
    hi = UB
    while hi - lo > T_TOL:
        mid = 0.5 * (lo + hi)
        if feasible(mid):
            lo = mid
        else:
            hi = mid
    prob.constraints['demand'].changeRHS(lo)
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    r = extract(prob, x, l, B, C, Wv)
    r['T_max'] = lo
    r['T_infeasible'] = hi
    r['cost_usd'] = cost_of(r)
    return r


BASE_SCEN = [
    ('S0_local', False, False, False),
    ('S1_biomass', True, False, False),
    ('S2_co2', False, True, False),
    ('S3_biomass+co2', True, True, False),
    ('S4_biomass+co2+water', True, True, True),
]
# Each coordinated scenario is also solved with every flow restricted to
# NEAR_KM (hard constraint, direct links only).  BECCS_NEAR_KM=0 disables.
NEAR_KM = float(os.environ.get('BECCS_NEAR_KM', '250'))
scenarios = [(nm, ab, ac, aw, None) for nm, ab, ac, aw in BASE_SCEN]
if NEAR_KM > 0:
    scenarios += [('%s_%dkm' % (nm, NEAR_KM), ab, ac, aw, NEAR_KM)
                  for nm, ab, ac, aw in BASE_SCEN[1:]]

rows, city_results, coord_flows = [], {}, {}
for name, ab, ac, aw, dmax in scenarios:
    r = run(ab, ac, aw, dmax)
    cm = r.get('cost_usd', 0.0) / 1e9        # bn USD/yr
    rows.append({'scenario': name, 'max_km': dmax if dmax else np.nan,
                 'total_Mt_yr': r['total'],
                 'T_max_Mt_yr': r.get('T_max', r['total']),
                 'biomass_transport': r['bio'], 'co2_transport': r['co2'],
                 'water_transport': r['wat'],
                 'water_transport_Mt_water': r['wat_phys'],
                 'transport_cost_bnUSD_yr': cm,
                 'unit_cost_USD_per_tCO2': (cm * 1e9 / r['total'] / 1e6)
                                           if r['total'] > 1e-9 else 0.0,
                 'status': r['status']})
    city_results[name] = r['x']
    coord_flows[name] = {'bio': r['f_bio'], 'co2': r['f_co2'], 'wat': r['f_wat']}
    print(f'{name}: {r["total"]:.3f} Mt/yr  (bio={r["bio"]:.1f}, co2={r["co2"]:.1f}, '
          f'wat={r["wat"]:.1f} Mt CO2-eq / {r["wat_phys"]:.0f} Mt water)  '
          f'cost={cm:.2f} bn$/yr', flush=True)

summary = pd.DataFrame(rows)
summary.to_excel(OUT_SUM, sheet_name='summary', index=False)

# ---- optional cost frontier (BECCS_COST_FRONTIER=1, cost mode only) ----
# Sweeps the potential target as a fraction of the feasible maximum and records
# the least cost of attaining it: the deployment-cost curve of the coordinated
# system.  Costs time proportional to the number of solves.
if OBJECTIVE == 'cost' and os.environ.get('BECCS_COST_FRONTIER', '0') == '1':
    # BECCS_FRONTIER_CUTS: comma-separated fractions of T_max (default 5 points)
    CUTS = [float(v) for v in os.environ.get(
        'BECCS_FRONTIER_CUTS', '0.50,0.70,0.85,0.95,1.00').split(',')]
    fr_rows = []
    for name, ab, ac, aw, dmax in scenarios:
        Tmax = float(summary.loc[summary.scenario == name, 'T_max_Mt_yr'].iloc[0])
        if Tmax <= 1.0:
            continue
        prob, x, l, B, C, Wv = build_solve(ab, ac, aw, dmax)
        for f in CUTS:
            prob.constraints['demand'].changeRHS(f * Tmax)
            prob.solve(pulp.PULP_CBC_CMD(msg=False))
            rr = extract(prob, x, l, B, C, Wv)
            fr_rows.append({'scenario': name, 'frac': f,
                            'total': rr['total'],
                            'cost_usd': cost_of(rr),
                            'bio': rr['bio'], 'co2': rr['co2'], 'wat': rr['wat']})
        print(f'  frontier {name}: {len(CUTS)} points up to {Tmax:.1f} Mt', flush=True)
    OUT_FR = os.path.join(OUT_DIR, 'BECCS_cost_frontier.xlsx')
    pd.DataFrame(fr_rows).to_excel(OUT_FR, sheet_name='frontier', index=False)
    print('saved', OUT_FR)

city_df = pd.DataFrame({'city': cities})
for name in [s[0] for s in scenarios]:
    city_df[name + '_Mt_yr'] = city_results[name]
city_df.to_excel(OUT_CITY, sheet_name='city', index=False)

# ---- coordination result (all scenarios) for the maps ----
# city table: each scenario's realized potential + limits
city_out = city_df.copy()
lim = cc[['city', 'W', 'S', 'B', 'G', 'E_wat', 'DELTA']].copy()
city_out = city_out.merge(lim, on='city', how='left')
# flow tables per scenario: Mt_yr = Mt CO2-eq supported, phys_Mt = mass moved
with pd.ExcelWriter(OUT_COORD) as xw:
    city_out.to_excel(xw, sheet_name='city', index=False)
    for scen in [s[0] for s in scenarios if s[0] != 'S0_local']:
        rows_all = ([(a, b, d, v, p, 'biomass') for a, b, d, v, p in coord_flows[scen]['bio']] +
                    [(a, b, d, v, p, 'co2') for a, b, d, v, p in coord_flows[scen]['co2']] +
                    [(a, b, d, v, p, 'water') for a, b, d, v, p in coord_flows[scen]['wat']])
        df_f = pd.DataFrame(rows_all, columns=['from', 'to', 'km', 'Mt_yr', 'phys_Mt', 'commodity'])
        df_f.to_excel(xw, sheet_name=scen, index=False)

print('\n--- national BECCS potential by scenario (Mt/yr) ---')
print(summary[['scenario', 'total_Mt_yr', 'biomass_transport', 'co2_transport',
               'water_transport', 'water_transport_Mt_water']].to_string(index=False))
print('\nsaved', OUT_SUM, '&', OUT_CITY, '&', OUT_COORD)
