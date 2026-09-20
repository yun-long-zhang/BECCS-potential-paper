# -*- coding: utf-8 -*-
"""Export per-prefecture-city 8-class resource-state data for the 8-colour
prefecture-map (Fig 3.6 face-fill version).

8 classes = BCR (>=1 / <1) x SER (>=1 / <1) x water status (WSR<=1 / WSR>1):

  1  "bio+sto+water-rich"    BCR>=1, SER>=1, WSR<=1   (all adequate)
  2  "water-short"           BCR>=1, SER>=1, WSR>1    (only water short)
  3  "bio+sto short"         BCR<1,  SER<1,  WSR<=1   (only water adequate)
  4  "bio short"             BCR<1,  SER>=1, WSR<=1
  5  "sto short"             BCR>=1, SER<1,  WSR<=1
  6  "bio+water short"       BCR<1,  SER>=1, WSR>1
  7  "sto+water short"       BCR>=1, SER<1,  WSR>1
  8  "vacuum"                BCR<1,  SER<1,  WSR>1   (all short)

Outputs an Excel workbook (Fig3_6_prefecture_8class.xlsx) with:
  sheet 'city_8class' : one row per prefecture city (name, prov, lon, lat,
                        BCR, SER, WSR, class id, class label, scarce count)
  sheet 'class_stats'  : per-class city count / capacity / emission share
  sheet 'readme'       : class definition table
Also writes a CSV (prefecture_8class.csv) for easy mapping joins.
"""
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get('BECCS_OUT_DIR', HERE)
AGG = os.path.join(OUT_DIR, 'plant_city_hswud_aggregated.xlsx')
PLANT = os.path.join(HERE, 'plant level analysis data.xlsx')
OUT_X = os.path.join(OUT_DIR, 'Fig3_6_prefecture_8class.xlsx')
OUT_C = os.path.join(OUT_DIR, 'prefecture_8class.csv')

# sensitivity parameters
EFR = float(os.environ.get('BECCS_EFR', '0.50'))
LIFE = float(os.environ.get('BECCS_LIFE', '20'))
BIO_FACTOR = float(os.environ.get('BECCS_BIO_FACTOR', '1.0'))
EFR_TAG = 'EFR20' if EFR <= 0.21 else ('EFR80' if EFR >= 0.79 else 'EFR50')
WSR_COL = {'EFR20': '市级WSR_EFR20', 'EFR50': '市级WSR_EFR50', 'EFR80': '市级WSR_EFR80'}[EFR_TAG]
STO_FACTOR = float(os.environ.get('BECCS_STO_FACTOR', '1.0'))
DESAL = os.environ.get('BECCS_DESAL', '0') == '1'
EWR = float(os.environ.get('BECCS_EWR', '0.0'))
COASTAL = ['上海','丹东','东营','东莞','中山','厦门','台州','大连','天津','威海','宁德','宁波','福州','泉州','漳州','潍坊','烟台','珠海','青岛','防城港','阳江','连云港','营口','葫芦岛','锦州','钦州','北海','茂名','莆田','温州','深圳','惠州','汕尾','汕头','江门','潮州','湛江','舟山','唐山','秦皇岛','儋州']

# ---- load city-level resource ratios (water column selected by EFR) ----
c = pd.read_excel(AGG, sheet_name='city_level')
for col in ['市级生物质掺烧比_BCR', '市级封存排放比_SER', WSR_COL, '地级市装机_MW']:
    c[col] = pd.to_numeric(c[col], errors='coerce')
c['BCR'] = pd.to_numeric(c['市级生物质掺烧比_BCR'], errors='coerce') * BIO_FACTOR
# the aggregated city SER already embeds the storage horizon (LIFE) and
# STO_FACTOR, and uses min(volume / LIFE, injection rate) / emissions
c['SER'] = pd.to_numeric(c['市级封存排放比_SER'], errors='coerce')
c['WSR'] = c[WSR_COL]
c['GW'] = c['地级市装机_MW'] / 1000.0

# ---- DESAL / EWR adjustments to the classification WSR (without touching AGG) ----
if DESAL:
    c.loc[c['地级市'].isin(COASTAL), 'WSR'] = 0.5   # coastal water adequate (desalination)
if EWR > 0:
    # EWR: brine water recovered from saline-aquifer storage (1 t water per t CO2 stored)
    # approximate per-city: recovered water raises available water, lowering WSR.
    # Use plant-level saline capacity aggregated to city, scaled by WSR definition.
    p_salt = pd.read_excel(PLANT, sheet_name=os.environ.get('BECCS_SHEET', '市域内比较'))
    p_salt = p_salt[p_salt['序号'].notna()].copy()
    p_salt['地级市'] = p_salt['所在城市'].astype(str)
    salt = pd.to_numeric(p_salt['咸水层封存潜力'], errors='coerce').fillna(0.0) / LIFE
    city_salt = p_salt.groupby('地级市')['咸水层封存潜力'].apply(
        lambda s: pd.to_numeric(s, errors='coerce').fillna(0.0).sum() / LIFE).rename('salt_MT')
    c = c.merge(city_salt, left_on='地级市', right_index=True, how='left')
    # recovered water (m3/yr) = salt stored (Mt) * 1 t/t * 1e6; compare to R (10^8 m3)
    R_c = pd.to_numeric(c['水资源总量_亿m3'], errors='coerce').fillna(0.0)
    recovered_1e8m3 = c['salt_MT'].fillna(0.0) * EWR * 1e6 / 1e8
    # WSR' = WSR * R / (R + recovered)   (more water -> lower pressure)
    c['WSR'] = c['WSR'] * R_c / (R_c + recovered_1e8m3).replace(0, np.nan)
    c['WSR'] = c['WSR'].fillna(c[WSR_COL])

# ---- join lon/lat + emissions (for map size + emission stats) ----
p = pd.read_excel(PLANT, sheet_name=os.environ.get('BECCS_SHEET', '市域内比较'))
p = p[p['序号'].notna()].copy()
p['经度'] = pd.to_numeric(p['经度'], errors='coerce')
p['纬度'] = pd.to_numeric(p['纬度'], errors='coerce')
p['年碳排放Mt'] = pd.to_numeric(p['年碳排放Mt'], errors='coerce')
p['地级市'] = p['所在城市'].astype(str)
city_ll = p.groupby('地级市')[['经度', '纬度']].mean().reset_index()
emis = p.groupby('地级市')['年碳排放Mt'].sum().rename('emis_Mt')
c = c.merge(city_ll, left_on='地级市', right_on='地级市', how='left')
c = c.merge(emis, on='地级市', how='left')
c = c.replace([np.inf, -np.inf], np.nan)
c = c.dropna(subset=['BCR', 'SER', 'WSR'])

# ---- 8-class assignment ----
def classify(row):
    b = 1 if row['BCR'] >= 1 else 0
    s = 1 if row['SER'] >= 1 else 0
    w = 1 if row['WSR'] <= 1 else 0  # 1 = water adequate
    key = (b, s, w)
    table = {
        (1, 1, 1): (1, 'bio+sto+water-rich'),
        (1, 1, 0): (2, 'water-short'),
        (0, 0, 1): (3, 'bio+sto-short'),
        (0, 1, 1): (4, 'bio-short'),
        (1, 0, 1): (5, 'sto-short'),
        (0, 1, 0): (6, 'bio+water-short'),
        (1, 0, 0): (7, 'sto+water-short'),
        (0, 0, 0): (8, 'vacuum'),
    }
    return table[key]

c[['class_id', 'class']] = c.apply(classify, axis=1, result_type='expand')
c['scarce'] = (c['BCR'] < 1).astype(int) + (c['SER'] < 1).astype(int) + (c['WSR'] > 1).astype(int)

# ---- per-class stats ----
tot_emis = c['emis_Mt'].sum()
stats = c.groupby('class').agg(
    n_cities=('地级市', 'size'),
    cap_GW=('GW', 'sum'),
    emis_Mt=('emis_Mt', 'sum'),
).reset_index()
stats['emis_pct'] = 100 * stats['emis_Mt'] / tot_emis
stats['cap_pct'] = 100 * stats['cap_GW'] / c['GW'].sum()
stats['city_pct'] = 100 * stats['n_cities'] / len(c)
stats = stats.sort_values('class_id') if 'class_id' in stats.columns else stats
# add class_id ordering
class_map = dict(zip(c['class'], c['class_id']))
stats['class_id'] = stats['class'].map(class_map)
stats = stats.sort_values('class_id')

# ---- readme ----
readme = pd.DataFrame({
    'class_id': [1, 2, 3, 4, 5, 6, 7, 8],
    'class': ['bio+sto+water-rich', 'water-short', 'bio+sto-short', 'bio-short',
              'sto-short', 'bio+water-short', 'sto+water-short', 'vacuum'],
    'BCR': ['>=1', '>=1', '<1', '<1', '>=1', '<1', '>=1', '<1'],
    'SER': ['>=1', '>=1', '<1', '>=1', '<1', '>=1', '<1', '<1'],
    'WSR': ['<=1', '>1', '<=1', '<=1', '<=1', '>1', '>1', '>1'],
    'scarce_count': [0, 1, 2, 1, 1, 2, 2, 3],
})

# ---- export ----
with pd.ExcelWriter(OUT_X, engine='openpyxl') as xw:
    c[['地级市', '省份', '省份英文', '经度', '纬度', 'BCR', 'SER', 'WSR',
       'class_id', 'class', 'scarce', 'GW', 'emis_Mt']].rename(
        columns={'地级市': 'city', '省份': 'province_cn', '省份英文': 'province_en',
                 '经度': 'longitude', '纬度': 'latitude', 'class': 'class_label',
                 'scarce': 'scarce_count', 'emis_Mt': 'emissions_Mt'}).to_excel(
        xw, sheet_name='city_8class', index=False)
    stats.to_excel(xw, sheet_name='class_stats', index=False)
    readme.to_excel(xw, sheet_name='readme', index=False)

c[['地级市', '省份', '省份英文', '经度', '纬度', 'BCR', 'SER', 'WSR',
   'class_id', 'class', 'scarce', 'GW', 'emis_Mt']].rename(
    columns={'地级市': 'city', '省份': 'province_cn', '省份英文': 'province_en',
             '经度': 'longitude', '纬度': 'latitude', 'class': 'class_label',
             'scarce': 'scarce_count', 'emis_Mt': 'emissions_Mt'}).to_csv(
    OUT_C, index=False, encoding='utf-8-sig')

print('saved:', OUT_X)
print('saved:', OUT_C)
print()
print('=== eight-class state distribution ===')
print(stats.to_string(index=False))
