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
           per Mt CO2 per km:
               biomass  0.11   $/t/km  x 6.614e5 t /Mt  =  72,751
               CO2      0.035  $/t/km  x 1.000e6 t /Mt  =  35,000
               water    0.0085 $/m3/km x 4.82e6 m3/Mt  =  40,970
           The national potential is therefore set purely by feasibility, and
           the objective only selects the cheapest way to realise it.

  penalty  max  sum_i x_i - sum_k w_k * flow_k * d_k   (legacy formulation)
           with w_bio=1e-4, w_co2=2e-5, w_wat=1e-2.  Retained because the
           published figures were produced with it; both objectives reach the
           same national potential in every scenario.

LP (PuLP/CBC), sets cities i,j:
  x_j  realized BECCS (Mt/yr)
  B_ij biomass flow, C_ij CO2 flow, W_ij water flow (each with distance cost)
  constraints:
    x_j <= G_j                  own biomass-capture ceiling (city)
    x_j + sum_k B_jk <= B_j + sum_i B_ij     biomass (local + net imports)
    x_j <= W_j + sum_i W_ij     water (local + imports)
    x_j = l_j + sum_k C_jk      captured = stored locally + exported
    l_j + sum_i C_ij <= S_j     storage (local + imported CO2)
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
#     water    0.0085 $/m3/km x 4.82e6 m3/Mt   =   40,970
T_BIO_PER_MTCO2 = 1e6 / (BIO_EF * CAP) / BIOMASS_GJ_PER_T
M3_WAT_PER_MTCO2 = 4.82e6           # CCS + upstream, fleet mean
K_BIO = USD_BIO_T_KM * T_BIO_PER_MTCO2
K_CO2 = USD_CO2_T_KM * 1e6
K_WAT = USD_WAT_M3_KM * M3_WAT_PER_MTCO2
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


def build_solve(allow_bio, allow_co2, allow_wat):
    """Build the LP for one scenario and return the problem plus its variables.

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

    In 'cost' mode a demand constraint sum_i x_i >= T is added and T is raised
    until the LP becomes infeasible; the problem is returned together with its
    variables so the caller can re-solve at successive T.
    """
    prob = pulp.LpProblem('BECCS', pulp.LpMinimize if OBJECTIVE == 'cost'
                          else pulp.LpMaximize)
    x = pulp.LpVariable.dicts('x', range(n), lowBound=0)
    l = pulp.LpVariable.dicts('l', range(n), lowBound=0)   # local storage
    B = pulp.LpVariable.dicts('B', [(i, j) for i in range(n) for j in range(n) if i != j], lowBound=0) if allow_bio else {}
    C = pulp.LpVariable.dicts('C', [(i, j) for i in range(n) for j in range(n) if i != j], lowBound=0) if allow_co2 else {}
    Wv = pulp.LpVariable.dicts('W', [(i, j) for i in range(n) for j in range(n) if i != j], lowBound=0) if allow_wat else {}

    km_bio = pulp.lpSum(B[(i, j)] * dist[(i, j)] for (i, j) in B)
    km_co2 = pulp.lpSum(C[(i, j)] * dist[(i, j)] for (i, j) in C)
    km_wat = pulp.lpSum(Wv[(i, j)] * dist[(i, j)] for (i, j) in Wv)
    if OBJECTIVE == 'cost':
        # minimise real engineering transport cost (bn USD/yr); the potential
        # itself is imposed through the 'demand' constraint added below.
        prob += COST_SCALE * (K_BIO * km_bio + K_CO2 * km_co2 + K_WAT * km_wat)
    else:
        prob += (pulp.lpSum(x[i] for i in range(n))
                 - W_BIO * km_bio - W_CO2 * km_co2 - W_WAT * km_wat)

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

    if OBJECTIVE == 'cost':
        dem = pulp.LpConstraint(pulp.lpSum(x[i] for i in range(n)),
                                sense=pulp.LpConstraintGE, rhs=0.0, name='demand')
        prob += dem
    return prob, x, l, B, C, Wv


def extract(prob, x, l, B, C, Wv):
    """Pull the solved values out of the LP."""
    tot = float(sum(pulp.value(x[i]) for i in range(n)))
    bio_tot = float(sum(pulp.value(B[(i, j)]) for (i, j) in B)) if B else 0.0
    co2_tot = float(sum(pulp.value(C[(i, j)]) for (i, j) in C)) if C else 0.0
    wat_tot = float(sum(pulp.value(Wv[(i, j)]) for (i, j) in Wv)) if Wv else 0.0
    xv = [pulp.value(x[i]) for i in range(n)]
    flows_b = [(cities[i], cities[j], dist[(i, j)], pulp.value(B[(i, j)])) for (i, j) in B] if B else []
    flows_c = [(cities[i], cities[j], dist[(i, j)], pulp.value(C[(i, j)])) for (i, j) in C] if C else []
    flows_w = [(cities[i], cities[j], dist[(i, j)], pulp.value(Wv[(i, j)])) for (i, j) in Wv] if Wv else []
    return dict(status=pulp.LpStatus[prob.status], total=tot, bio=bio_tot,
                co2=co2_tot, wat=wat_tot, x=xv,
                f_bio=[f for f in flows_b if f[3] > 1e-6],
                f_co2=[f for f in flows_c if f[3] > 1e-6],
                f_wat=[f for f in flows_w if f[3] > 1e-6])


def cost_of(r):
    """Real engineering transport cost (USD/yr) of a solved configuration."""
    return float(K_BIO * sum(d * v for _, _, d, v in r['f_bio'])
                 + K_CO2 * sum(d * v for _, _, d, v in r['f_co2'])
                 + K_WAT * sum(d * v for _, _, d, v in r['f_wat']))


def run(allow_bio, allow_co2, allow_wat):
    """Solve one scenario.

    'penalty' mode solves once and returns the result.  'cost' mode first
    locates the maximum feasible potential T (grow by a fixed step, then
    bisect), then returns the least-cost configuration attaining it.
    """
    prob, x, l, B, C, Wv = build_solve(allow_bio, allow_co2, allow_wat)
    if OBJECTIVE != 'cost':
        prob.solve(pulp.PULP_CBC_CMD(msg=False))
        r = extract(prob, x, l, B, C, Wv)
        r['T_max'] = r['total']
        r['cost_usd'] = cost_of(r)
        return r

    # Upper bound on the national potential, from summing each balance over i.
    #   biomass :  x_i + out_i <= B_i + in_i,  and sum(out) = sum(in)
    #              => sum(x) <= sum(B)
    #   storage :  x_i = l_i + co2_out_i,  l_i + co2_in_i <= S_i,  sum(out)=sum(in)
    #              => sum(x) <= sum(S)
    #   generation: x_i <= G_i            => sum(x) <= sum(G)
    #   water   :  x_i <= W_i + wat_in_i  => sum(x) <= sum(W) + sum(exports)
    #              and exports are capped per city by WAT_CAP, so
    #              sum(x) <= sum(W) + n*WAT_CAP  when water may be transferred.
    #              WITHOUT water transfer the tighter sum(x) <= sum(W) holds.
    # Using min(sum B, sum S, sum W, sum G) here would be WRONG for S4: a city may
    # import water far beyond its own endowment, so sum(W) is not a ceiling then.
    # Getting this wrong truncates S4 in exactly the scenarios where water is the
    # scarcest resource (e.g. EFR80, GEN50, GEN25).
    bounds = [cc['B'].sum(), cc['S'].sum(), cc['G'].sum()]
    wat_bound = cc['W'].sum()
    if allow_wat:
        wat_bound += n * WAT_CAP
    bounds.append(wat_bound)
    UB = float(min(bounds))

    def feasible(T):
        prob.constraints['demand'].changeRHS(T)
        prob.solve(pulp.PULP_CBC_CMD(msg=False))
        return pulp.LpStatus[prob.status] == 'Optimal'

    # Fast path: the pooled bound UB is usually attainable (a nationwide transport
    # network makes the per-city ceilings non-binding in aggregate), so test it
    # first and skip the incremental walk + bisection entirely.  If the test
    # succeeds the LP is already solved at T = UB.
    if feasible(UB):
        r = extract(prob, x, l, B, C, Wv)
        r['T_max'] = UB
        r['T_infeasible'] = UB
        r['cost_usd'] = cost_of(r)
        return r

    # Otherwise bracket the ceiling between two known points and bisect:
    #   lo = the self-sufficient potential, which is always feasible (it needs
    #        no flows at all), and
    #   hi = the pooled-resource bound, which we just showed is infeasible.
    # This costs ~log2(range/T_TOL) solves, with no preliminary stepping walk.
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


scenarios = [
    ('S0_local', False, False, False),
    ('S1_biomass', True, False, False),
    ('S2_co2', False, True, False),
    ('S3_biomass+co2', True, True, False),
    ('S4_biomass+co2+water', True, True, True),
]

rows, city_results, coord_flows = [], {}, {}
for name, ab, ac, aw in scenarios:
    r = run(ab, ac, aw)
    cm = r.get('cost_usd', 0.0) / 1e9        # bn USD/yr
    rows.append({'scenario': name, 'total_Mt_yr': r['total'],
                 'T_max_Mt_yr': r.get('T_max', r['total']),
                 'biomass_transport': r['bio'], 'co2_transport': r['co2'],
                 'water_transport': r['wat'],
                 'transport_cost_bnUSD_yr': cm,
                 'unit_cost_USD_per_tCO2': (cm * 1e9 / r['total'] / 1e6)
                                           if r['total'] > 1e-9 else 0.0,
                 'status': r['status']})
    city_results[name] = r['x']
    coord_flows[name] = {'bio': r['f_bio'], 'co2': r['f_co2'], 'wat': r['f_wat']}
    print(f'{name}: {r["total"]:.3f} Mt/yr  (bio={r["bio"]:.1f}, co2={r["co2"]:.1f}, '
          f'wat={r["wat"]:.1f})  cost={cm:.2f} bn$/yr', flush=True)

summary = pd.DataFrame(rows)
summary.to_excel(OUT_SUM, sheet_name='summary', index=False)

# ---- optional cost frontier (BECCS_COST_FRONTIER=1, cost mode only) ----
# Sweeps the potential target as a fraction of the feasible maximum and records
# the least cost of attaining it: the deployment-cost curve of the coordinated
# system.  Costs time proportional to the number of solves.
if OBJECTIVE == 'cost' and os.environ.get('BECCS_COST_FRONTIER', '0') == '1':
    CUTS = [0.50, 0.70, 0.85, 0.95, 1.00]
    fr_rows = []
    for name, ab, ac, aw in scenarios:
        Tmax = float(summary.loc[summary.scenario == name, 'T_max_Mt_yr'].iloc[0])
        if Tmax <= 1.0:
            continue
        prob, x, l, B, C, Wv = build_solve(ab, ac, aw)
        for f in CUTS:
            prob.constraints['demand'].changeRHS(f * Tmax)
            prob.solve(pulp.PULP_CBC_CMD(msg=False))
            rr = extract(prob, x, l, B, C, Wv)
            fr_rows.append({'scenario': name, 'frac': f,
                            'total': rr['total'],
                            'cost_usd': cost_of(rr),
                            'bio': rr['bio'], 'co2': rr['co2'], 'wat': rr['wat']})
        print(f'  frontier {name}: 5 points up to {Tmax:.1f} Mt', flush=True)
    OUT_FR = os.path.join(OUT_DIR, 'BECCS_cost_frontier.xlsx')
    pd.DataFrame(fr_rows).to_excel(OUT_FR, sheet_name='frontier', index=False)
    print('saved', OUT_FR)

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

print('\n--- 各情景全国 BECCS 潜力 (Mt/yr) ---')
print(summary[['scenario', 'total_Mt_yr', 'biomass_transport', 'co2_transport', 'water_transport']].to_string(index=False))
s3 = coord_flows['S3_biomass+co2']
print('\n--- S3 运输流 Top 10 (Mt/yr) ---')
for t in sorted(s3['bio'], key=lambda t: -t[3])[:5]:
    print(f'  bio {t[0]} -> {t[1]} ({t[2]:.0f}km): {t[3]:.1f}')
for t in sorted(s3['co2'], key=lambda t: -t[3])[:5]:
    print(f'  co2 {t[0]} -> {t[1]} ({t[2]:.0f}km): {t[3]:.1f}')
print('\nsaved', OUT_SUM, '&', OUT_CITY, '&', OUT_COORD)
