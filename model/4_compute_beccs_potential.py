# -*- coding: utf-8 -*-
"""Per-plant, per-city maximum BECCS (negative-emission) potential under three
resources considered separately (all other resources assumed unconstrained).

DEFINITION (per user): BECCS potential = the biogenic carbon (from biomass
combustion) that can be captured and stored. Coal-derived carbon is NOT counted
as BECCS negative emission. Generation is fixed at each plant's existing output.

Each resource limit is evaluated INDEPENDENTLY, assuming the other two resources
are UNCONSTRAINED (available as needed):

  - F_i      = fuel needed to keep the net generation E_i (MWh/yr)
               = E_i x HR_i / (1 - 0.01) / (1 - pen_ccs,i)  (GJ/yr)
               (the CCS factor is dropped when BECCS_CCS_PENALTY=0)
  - G_i      = full-cofiring ceiling: biogenic C captured if ALL generation fuel
               were biomass (other resources unlimited) = F_i x 0.112 x 0.90 /1e6
  - sto_phys_i = storage capacity / LIFE  (Mt CO2/yr)

  1) BIOMASS limit (other resources unlimited):
       biomass used b_i = min(B_100km_i, F_i)   (GJ/yr)
       M_B = b_i x 0.112 x 0.90 /1e6
  2) STORAGE limit (water & biomass unlimited; all generation from biomass):
       M_S = min(G_i, sto_phys_i)
  3) WATER limit (storage & biomass unlimited): the city's water after the
     environmental reserve and competing use, A = R(1-EFR) - U, is allocated
     to its plants in proportion to their generation, a_i = A x E_i / E_city
     (plus any EWR brine recovered at the plant).  A share f_i of the plant's
     generation runs as BECCS (full co-firing + CCS) and the rest stays coal
     without capture, so its water use W_coal,i + f_i (W_ccs,i - W_coal,i)
     must fit within a_i:
         f_i = clip((a_i - W_coal,i) / (W_ccs,i - W_coal,i), 0, 1)
     and M_W = f_i x G_i.  Because water is allocated by generation, a plant
     with above-average water intensity can be water-limited even in a city
     whose aggregate water balance is adequate (WSR <= 1).
  FINAL per plant = min(M_S, M_W, M_B)

Outputs: BECCS_potential_plant.xlsx, BECCS_potential_city.xlsx.
"""
import os
import numpy as np
import pandas as pd

import _cols

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get('BECCS_OUT_DIR', HERE)   # scenario output folder
os.makedirs(OUT_DIR, exist_ok=True)
SRC = os.path.join(HERE, 'plant level analysis data.xlsx')
# AGG is produced by 1_compute_aggregate_city.py INTO OUT_DIR, so it must be read
# from there as well -- otherwise an alternative basis would silently pick up the
# main folder's water table (different R / U).
AGG = os.path.join(OUT_DIR, 'plant_city_hswud_aggregated.xlsx')
OUT_P = os.path.join(OUT_DIR, 'BECCS_potential_plant.xlsx')
OUT_C = os.path.join(OUT_DIR, 'BECCS_potential_city.xlsx')

EFR = float(os.environ.get('BECCS_EFR', '0.50'))      # environmental-flow reserve (baseline 50%)
CAP = 0.90
BIO_EF = 0.112   # t CO2/GJ (biomass)
LIFE = float(os.environ.get('BECCS_LIFE', '20'))        # storage allocation horizon (yr)
BIO_FACTOR = float(os.environ.get('BECCS_BIO_FACTOR', '1.0'))  # biomass availability fraction
# biomass / storage buffer radius (see _cols.py): BECCS_BIO_RADIUS / BECCS_STO_RADIUS
BIO_COL = _cols.bio_col()          # biomass collection column (100/250/500 km)
STO_COL = _cols.sto_col()          # accessible storage volume column
INJ_COL = _cols.inj_col()          # annual injection-rate column
STO_FACTOR = float(os.environ.get('BECCS_STO_FACTOR', '1.0'))  # storage potential scaling (0.5/0.25)
GEN_FACTOR = float(os.environ.get('BECCS_GEN_FACTOR', '1.0'))  # generation scaling (0.5/0.25)
DESAL = os.environ.get('BECCS_DESAL', '0') == '1'        # coastal cities water unlimited
EWR = float(os.environ.get('BECCS_EWR', '0.0'))          # t water per t CO2 recovered (0=off)
CONSUMPTION = os.environ.get('BECCS_CONSUMPTION', '0') == '1'  # use consumption instead of withdrawal
EFF_PEN = 0.01

# coastal cities with desalination potential (water treated as unlimited)
COASTAL = ['上海','丹东','东营','东莞','中山','厦门','台州','大连','天津','威海','宁德','宁波','福州','泉州','漳州','潍坊','烟台','珠海','青岛','防城港','阳江','连云港','营口','葫芦岛','锦州','钦州','北海','茂名','莆田','温州','深圳','惠州','汕尾','汕头','江门','潮州','湛江','舟山','唐山','秦皇岛','儋州']


df = _cols.read_plants(SRC)
df['city'] = df['所在城市'].astype(str)
df['plant_id'] = pd.to_numeric(df['电厂编号'], errors='coerce')
df['C_MW'] = pd.to_numeric(df['电厂实际装机总功率MW'], errors='coerce')
df['GW'] = df['C_MW'] / 1000.0
df['hh'] = pd.to_numeric(df['发电小时'], errors='coerce')
df['hr'] = pd.to_numeric(df['煤电系统热耗-GJ/MWH'], errors='coerce')
df['bio_GJ'] = pd.to_numeric(df[BIO_COL], errors='coerce') * BIO_FACTOR
df['sto_MT'] = pd.to_numeric(df[STO_COL], errors='coerce')
df['inj_MTa'] = pd.to_numeric(df[INJ_COL], errors='coerce')
df['salt_MT'] = pd.to_numeric(df['咸水层封存潜力'], errors='coerce').fillna(0.0)
# annual water use (m3/yr) of the coal-only and the coal + CCS system, from the
# unit sheet joined by 电厂编号; withdrawal or consumption, scaled by GEN_FACTOR
df['w_coal_m3'], df['w_ccs_m3'] = _cols.water_use(SRC, df)

# ---- fixed generation & fuel, biomass use (dual limit) ----
df['gen_MWh'] = df['C_MW'] * df['hh'] * GEN_FACTOR        # generation scaled by GEN_FACTOR
df['fuel_GJ'] = df['gen_MWh'] * _cols.fuel_per_mwh(df)
# NOTE: the per-plant biomass term is NOT computed here -- the biomass ceiling
# is evaluated at the CITY scale further below (see the BIOMASS limit block), so
# that residues can be shared among the plants of the same city.

# ---- city water available to the coal fleet (m3/yr) ----
ag = pd.read_excel(AGG, sheet_name='city_level')
R = pd.to_numeric(ag['水资源总量_亿m3'], errors='coerce') * 1e8
comp = pd.to_numeric(ag['最终竞争_亿m3'], errors='coerce') * 1e8
city_avail = dict(zip(ag['地级市'], R * (1 - EFR) - comp))

# =====================================================================
# 1) BIOMASS limit: all residues collected within the buffer, with the city
#    sharing them among its plants.  A city can therefore co-fire at most
#    min(total residues, total fuel demand).  Using the city scale keeps this
#    ceiling consistent with the city-level indices (BCR / SER / WSR).
# =====================================================================
B_CITY = (np.minimum(df.groupby('city')['bio_GJ'].sum(),
                     df.groupby('city')['fuel_GJ'].sum())
          * BIO_EF * CAP * 1e-6)
df['bio_Mt_yr'] = df['city'].map(B_CITY)

# =====================================================================
# 2) STORAGE limit: water & biomass unconstrained -> all generation from
#    biomass (full co-firing); biogenic C = G_i capped by storage capacity
# =====================================================================
df['G_Mt'] = df['fuel_GJ'] * BIO_EF * CAP * 1e-6          # full-cofiring biogenic C
# annualised storage potential: limited by BOTH the accessible volume over the
# allocation horizon AND the annual injection-rate capability (the binding one
# applies).  For LIFE = 20 this reproduces the workbook's AN ratio column.
df['sto_vol_yr'] = df['sto_MT'] / LIFE                     # volume / horizon
df['sto_phys'] = df[['sto_vol_yr', 'inj_MTa']].min(axis=1) * STO_FACTOR
df['sto_Mt_yr'] = df[['G_Mt', 'sto_phys']].min(axis=1)

# =====================================================================
# 2b) EWR: brine water recovered from saline-aquifer storage, 1 t water per t CO2
#     stored. Each plant first uses its own saline-aquifer capacity (annual),
#     recovering water proportional to the biogenic carbon actually stored there
#     (capped by storage & fuel). Recovered water is added to the city's
#     available water, raising the water-limited share below.
# =====================================================================
df['salt_yr_MT'] = df['salt_MT'] / LIFE                     # annual saline capacity (Mt/yr)
df['sto_c'] = df[['G_Mt', 'sto_phys']].min(axis=1)          # annual biogenic C stored (Mt)
df['ewr_cap_MT'] = np.minimum(df['sto_c'], df['salt_yr_MT'])  # annual C stored in saline (Mt)
df['ewr_m3'] = df['ewr_cap_MT'] * EWR * 1e6                 # recovered water (m3/yr), EWR t/t

# =====================================================================
# 3) WATER limit (see docstring): the city's available water is allocated to
#    its plants by generation share; each plant's BECCS share f_i is what its
#    allocation allows after its existing coal-power use.  Recovered brine
#    (EWR) adds to the plant's allocation; DESAL treats coastal cities as
#    unconstrained.
# =====================================================================
city_gen = df.groupby('city')['gen_MWh'].transform('sum')
df['wat_alloc_m3'] = (df['city'].map(city_avail).astype(float).fillna(0.0)
                      * df['gen_MWh'] / city_gen.replace(0, np.nan)).fillna(0.0)
df['wat_alloc_m3'] += df['ewr_m3']
extra = df['w_ccs_m3'] - df['w_coal_m3']          # extra water at full BECCS
f = ((df['wat_alloc_m3'] - df['w_coal_m3']) / extra.where(extra > 0)).clip(0, 1)
f = f.where(extra > 0, 1.0)                       # CCS needs no extra water
if DESAL:
    f[df['city'].isin(COASTAL)] = 1.0
df['wat_f'] = f
df['wat_Mt_yr'] = df['wat_f'] * df['G_Mt']

# =====================================================================
# FINAL per plant
# =====================================================================
df['BECCS_Mt_yr'] = df[['sto_Mt_yr', 'wat_Mt_yr', 'bio_Mt_yr']].min(axis=1)
df['limiting'] = df[['sto_Mt_yr', 'wat_Mt_yr', 'bio_Mt_yr']].idxmin(axis=1)

# ---- exports ----
pf = df[['city', 'plant_id', 'GW', 'gen_MWh', 'hr', 'w_ccs_m3', 'wat_f',
         'sto_Mt_yr', 'wat_Mt_yr', 'bio_Mt_yr', 'BECCS_Mt_yr', 'limiting']].copy()
pf.columns = ['city', 'plant_id', 'GW', 'gen_MWh', 'heat_rate', 'ccs_water_m3_yr', 'water_beccs_share',
              'sto_Mt_yr', 'wat_Mt_yr', 'bio_Mt_yr', 'BECCS_Mt_yr', 'limiting']
pf.to_excel(OUT_P, sheet_name='plant_potential', index=False)

cc = pf.groupby('city').agg(
    GW=('GW', 'sum'),
    sto_Mt_yr=('sto_Mt_yr', 'sum'),
    wat_Mt_yr=('wat_Mt_yr', 'sum'),
    BECCS_Mt_yr=('BECCS_Mt_yr', 'sum'),
).reset_index()
# bio_Mt_yr is a CITY-level ceiling (unique per city), so it must NOT be summed
# over the plants of that city -- take it once per city instead.
cc = cc.merge(pd.DataFrame({'city': list(B_CITY.index),
                            'bio_Mt_yr': list(B_CITY.values)}),
              on='city', how='left')
cc['limiting'] = cc[['sto_Mt_yr', 'wat_Mt_yr', 'bio_Mt_yr']].idxmin(axis=1)
cc = cc.sort_values('BECCS_Mt_yr', ascending=False).reset_index(drop=True)

# ---- City-coordinated version: allow intra-city resource sharing ----
# All three resources are evaluated at the CITY scale, so a plant's shortfall can
# be met by other plants in the same city:
#   storage : min(sum of full-cofiring biogenic C, sum of accessible storage/yr)
#   biomass : min(total residues, total fuel demand)                     (B_CITY)
#   water   : city surplus allocated by generation share
cG = df.groupby('city')['G_Mt'].sum().rename('G_city')
cS = df.groupby('city')['sto_phys'].sum().rename('sto_city')
cc2 = cc.merge(cG, on='city', how='left').merge(cS, on='city', how='left')
cc2['sto_Mt_yr'] = cc2[['G_city', 'sto_city']].min(axis=1)
cc2['BECCS_Mt_yr'] = cc2[['sto_Mt_yr', 'wat_Mt_yr', 'bio_Mt_yr']].min(axis=1)
cc2['limiting'] = cc2[['sto_Mt_yr', 'wat_Mt_yr', 'bio_Mt_yr']].idxmin(axis=1)
cc2 = cc2[['city', 'GW', 'sto_Mt_yr', 'wat_Mt_yr', 'bio_Mt_yr', 'BECCS_Mt_yr', 'limiting']]
cc2 = cc2.sort_values('BECCS_Mt_yr', ascending=False).reset_index(drop=True)

with pd.ExcelWriter(OUT_C) as xw:
    cc.to_excel(xw, sheet_name='city_potential', index=False)       # plant-level independent
    cc2.to_excel(xw, sheet_name='city_coordinated', index=False)     # intra-city coordinated

emis_total = (df['gen_MWh'] * df['hr'] * pd.to_numeric(df['煤电系统热耗-GJ/MWH'], errors='coerce')
              * 1e-6).sum()  # placeholder unused
emis_total = df['gen_MWh'] * df['hr'] * BIO_EF * 0  # no-op

print('plants:', len(pf), '| cities:', len(cc))
print('national: storage %.0f | water %.0f | biomass %.0f Mt/yr' % (
    cc['sto_Mt_yr'].sum(), cc['wat_Mt_yr'].sum(), cc['bio_Mt_yr'].sum()))
print('=== final annual BECCS potential (min of three limits; biogenic C only; fixed generation) ===')
print('  national: %.0f Mt CO2/yr' % cc['BECCS_Mt_yr'].sum())
print('\nlimiting resource (cities):')
print(cc['limiting'].value_counts().to_string())
print('\ntop 10 cities by potential:')
print(cc.head(10)[['city', 'GW', 'sto_Mt_yr', 'wat_Mt_yr', 'bio_Mt_yr', 'BECCS_Mt_yr']].round(2).to_string(index=False))
print('\nsaved', OUT_P, '&', OUT_C)
