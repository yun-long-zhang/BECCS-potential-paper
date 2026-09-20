# -*- coding: utf-8 -*-
"""Aggregate competitive water to PLANT-level prefecture cities, merging:
  - HSWUD sectoral withdrawal (dom+manu+irr, 2010-19 decadal mean) as primary,
  - Manual 2021 water-resources-bulletin data (agri+ind+dom) as supplement for
    cities HSWUD lacks, incl. Xinjiang Bingtuan cities mapped to their prefecture.

Competitive water per city = HSWUD if available, else manual (if available),
else 0 (for the few cities neither source covers).

Then compute plant-level TOTAL-PRESSURE WSR (EFR 0.37 baseline / 0.50 sensitivity)
and coal-available-water (R - competitive - EFR*R).

Output: plant_city_hswud_aggregated.xlsx (updated, sheets: city_level, plant_level,
mapping, coverage, readme).
"""
import os
import re
import numpy as np
import pandas as pd

import _cols

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get('BECCS_OUT_DIR', HERE)   # scenario output folder
os.makedirs(OUT_DIR, exist_ok=True)
PLANT = os.path.join(HERE, 'plant level analysis data.xlsx')
HSWUD_PREF = os.path.join(HERE, 'HSWUD_competitive_2010s_prefecture.csv')
MANUAL = os.path.join(HERE, 'prefecture_manual_water.xlsx')
MAP = os.path.join(HERE, 'hswud_city_mapping.csv')
OUT = os.path.join(OUT_DIR, 'plant_city_hswud_aggregated.xlsx')

# sensitivity parameters applied to city BCR / SER (for fig 4/5/6)
BIO_FACTOR = float(os.environ.get('BECCS_BIO_FACTOR', '1.0'))
LIFE = float(os.environ.get('BECCS_LIFE', '20'))
STO_FACTOR = float(os.environ.get('BECCS_STO_FACTOR', '1.0'))
GEN_FACTOR = float(os.environ.get('BECCS_GEN_FACTOR', '1.0'))

# input sub-sheet: '市域内比较' = local (per-prefecture) Thiessen basis, the one
# used in the paper; 'city clip' / 'Sheet2' are the earlier nationwide-Thiessen
# bases, kept for comparison.
SHEET = os.environ.get('BECCS_SHEET', '市域内比较')

# ---- water source -----------------------------------------------------------
# WATER_SRC = 'new'  : plant-level ChinaWR + HSWUD aggregated over each plant's
#                      LOCAL Thiessen cell ∩ own prefecture (1980-2020 mean)
#                      -> replaces BOTH the city-level R column and the
#                      competitive-use lookup, because the new table is per plant
# WATER_SRC = 'old'  : previous basis -- city-level R read from the workbook
#                      column below, competitive use from HSWUD 2010-2019
#                      decadal means / 2021 bulletins (see HSWUD_PREF, MANUAL)
WATER_SRC = os.environ.get('BECCS_WATER_SRC', 'new')
# Which plant-level water table to read when WATER_SRC = 'new':
#   water_thiessen_local.xlsx      local (per-prefecture) Thiessen  <- paper basis
#   water_thiessen_cityclip.xlsx   nationwide Thiessen x own prefecture
WATER_XLSX = os.path.join(
    HERE, os.environ.get('BECCS_WATER_TABLE', 'water_thiessen_local.xlsx'))

# --- columns used when WATER_SRC = 'old' ---
# COL_R_OLD : city-level total available water (1e8 m3), zeros mapped to the
#              minimum value 0.14  (city-level, workbook)
# --- columns used when WATER_SRC = 'new' ---
# plant_water sheet of water_thiessen_local.xlsx:
#   R_亿m3        available water resources   (ChinaWR TWR, 1980-2020 mean, 1e8 m3)
#   U_竞争_亿m3    competitive withdrawal      (HSWUD dom+manu+irr, same period)
COL_R = '地级市总可用水量（亿立方米）0值赋值为最低值0.14'
COL_R_NEW = 'R_亿m3'
COL_U_NEW = 'U_竞争_亿m3'
COL_W = '煤电-ccs-系统年有效取水总量-除去海水-亿立方米'
COL_CONS = '煤电 ccs 系统年耗水总量  立方米'   # consumption mode (use instead of withdrawal)
CONSUMPTION = os.environ.get('BECCS_CONSUMPTION', '0') == '1'  # water-use metric
if CONSUMPTION:
    COL_W = COL_CONS
CONS_UNIT_1E8 = True if CONSUMPTION else False   # consumption column is in m3, so divide by 1e8 to get 1e8 m3
COL_CAP = '电厂实际装机总功率MW'
# biomass / storage buffer radius (see _cols.py): BECCS_BIO_RADIUS / BECCS_STO_RADIUS
COL_BIO = _cols.bio_col()
COL_STO = _cols.sto_col()
COL_INJ = _cols.inj_col()          # annual injection-rate capability
COL_E = '煤电系统所需能量GJ'
COL_EMIS = '年碳排放Mt'
EFR_ZERO = 0.00   # legacy (kept)
EFR_BASE = 0.37   # historical baseline (kept)
EFR_SENS = 0.50   # kept (also the new baseline)
EFR_LOW = 0.20    # new sensitivity
EFR_HIGH = 0.80   # new sensitivity

# Bingtuan city -> prefecture (manual data has prefecture totals incl. bingtuan)
BINGTUAN_TO_PREF = {
    '五家渠': '昌吉', '可克达拉': '伊犁', '阿拉尔': '阿克苏', '图木舒克': '喀什',
    '铁门关': '巴州', '双河': '博州', '白杨': '塔城', '北屯': '阿勒泰',
}


def norm(s):
    if not isinstance(s, str):
        return ''
    s = s.strip()
    # special: "市辖区(南通市)" / "市辖区(石嘴山市)" -> keep the inner city name
    if '市辖区(' in s and ')' in s:
        inner = s[s.index('(') + 1: s.index(')')]
        s = inner
    else:
        s = re.sub(r'[（(].*?[)）]', '', s)
    for suf in ('市', '地区', '自治州', '自治县', '自治旗', '盟', '州', '县', '区', '旗', '林区'):
        s = re.sub(suf + '$', '', s)
    return s


def main():
    # ---- load ----
    m = pd.read_csv(MAP)
    df = pd.read_excel(PLANT, sheet_name=SHEET)
    df = df[df['序号'].notna()].copy()
    for c in [COL_R, COL_W, COL_CAP, COL_BIO, COL_STO, COL_INJ, COL_E, COL_EMIS]:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    # ---- plant-level water (new basis) --------------------------------------
    # R and U come from water_thiessen_local.xlsx, aggregated over each plant's
    # LOCAL Thiessen cell ∩ its own prefecture: R = ChinaWR TWR (1980-2020 mean,
    #  1e8 m3), U = HSWUD dom+manu+irr (same period).  Both are PER PLANT, so they
    # replace the city-level workbook column and the HSWUD/manual lookups.
    water_new = None
    if WATER_SRC == 'new':
        df['pid'] = pd.to_numeric(df['电厂编号'], errors='coerce')
        w = pd.read_excel(WATER_XLSX, sheet_name='plant_water')
        w['pid'] = pd.to_numeric(w['pid'], errors='coerce')
        w = w[['pid', COL_R_NEW, COL_U_NEW]].dropna(subset=['pid'])
        water_new = dict(zip(w['pid'], zip(w[COL_R_NEW], w[COL_U_NEW])))
        df['R_plant'] = df['pid'].map({p: v[0] for p, v in water_new.items()})
        df['U_plant'] = df['pid'].map({p: v[1] for p, v in water_new.items()})
        n_hit = int(df['R_plant'].notna().sum())
        print('water: new basis (ChinaWR TWR + HSWUD, plant Thiessen) -> '
              '%d / %d plants matched' % (n_hit, len(df)))
        if n_hit < len(df):
            miss = df.loc[df['R_plant'].isna(), '电厂编号'].tolist()
            print('  WARNING: no water row for plants %s -> treated as 0' % miss[:10])
        df[['R_plant', 'U_plant']] = df[['R_plant', 'U_plant']].fillna(0.0)
    # coal+CCS water demand scales with generation (GEN_FACTOR)
    if COL_W in df.columns:
        df[COL_W] = df[COL_W] * GEN_FACTOR
    # consumption column is in m3; convert to 1e8 m3 to match the WSR formulation
    if CONSUMPTION:
        df[COL_W] = df[COL_W] / 1e8
    df['city_n'] = df['所在城市'].map(norm)
    df['prov_n'] = df['所在省'].map(norm)
    # English province name for labels
    df['prov_en'] = df['provinces'].astype(str)

    # ---- HSWUD / manual lookups (only needed for the OLD water basis) ----
    hswud_comp, manual_comp, manual = {}, {}, None
    if WATER_SRC != 'new':
        h = pd.read_csv(HSWUD_PREF)
        manual = pd.read_excel(MANUAL)
        m['hswud_n'] = m['hswud_city'].map(norm)
        m['plant_n'] = m['plant_city'].map(norm)
        unit2city = dict(zip(m['hswud_n'], m['plant_n']))
        h['plant_n'] = h['prefecture'].map(norm).map(unit2city)
        hswud_agg = h.dropna(subset=['plant_n']).groupby('plant_n')[
            ['domestic_1e8m3', 'manufacturing_1e8m3', 'irrigation_1e8m3',
             'competitive_1e8m3']].sum().reset_index()
        hswud_comp = dict(zip(hswud_agg['plant_n'], hswud_agg['competitive_1e8m3']))
        manual['city_n'] = manual['city'].map(norm)
        manual['competitive'] = manual['agri'] + manual['ind'] + manual['dom']
        manual_comp = dict(zip(manual['city_n'], manual['competitive']))

    # ---- all 304 plant cities; the ORIGINAL city column is the canonical name ----
    # CITY-LEVEL water = SUM of the plants' own plant-level values (new basis),
    # or the single city-level workbook value (old basis).
    if WATER_SRC == 'new':
        city_tab = df.groupby('city_n').agg(
            R_亿m3=('R_plant', 'sum'), U_竞争_亿m3=('U_plant', 'sum')).reset_index()
        city_tab = city_tab.merge(
            df[['所在城市', 'city_n', 'prov_n', 'prov_en']].drop_duplicates('city_n'),
            on='city_n', how='right')
        city_tab['R_亿m3'] = city_tab['R_亿m3'].fillna(0.0)
        city_tab['U_竞争_亿m3'] = city_tab['U_竞争_亿m3'].fillna(0.0)
        city_tab['数据来源'] = 'ChinaWR+HSWUD(plant Thiessen)'
    else:
        city_tab = df[['所在城市', 'city_n', 'prov_n', 'prov_en', COL_R]].drop_duplicates('city_n').copy()
        city_tab['R_亿m3'] = pd.to_numeric(city_tab[COL_R], errors='coerce')
    cap_city = df.groupby('city_n')[COL_CAP].sum().rename('cap_city')
    n_city = df.groupby('city_n').size().rename('n_city')
    city_tab = city_tab.merge(cap_city, on='city_n').merge(n_city, on='city_n')

    # ---- city-level BCR / SER (aggregate resources & demand per city) ----
    # Annual storage potential per plant is limited by BOTH the accessible
    # physical volume (storage / LIFE) and the annual injection rate; the
    # binding one is taken.  For LIFE = 20 this equals the workbook's
    # '假设封存20年，最大封存或注入比例' (AN) column times annual emissions.
    city_res = df.groupby('city_n').agg(
        bio_sum=(COL_BIO, 'sum'),
        e_sum=('煤电系统所需能量GJ', 'sum'),
        sto_sum=(COL_STO, 'sum'),
        inj_sum=(COL_INJ, 'sum'),
        emis_sum=('年碳排放Mt', 'sum'),
    ).reset_index()
    # plant-level annualised storage potential (then aggregated per city)
    df['sto_annual'] = np.minimum(df[COL_STO] / LIFE, df[COL_INJ])
    sto_ann_city = df.groupby('city_n')['sto_annual'].sum().rename('sto_annual')
    city_res = city_res.merge(sto_ann_city, on='city_n', how='left')
    # BCR = biomass / fuel demand; fuel demand scales with generation, so a
    # generation cut makes biomass relatively more abundant (BCR rises by 1/GEN_FACTOR).
    city_res['BCR_city'] = (city_res['bio_sum'] / city_res['e_sum']) * BIO_FACTOR / GEN_FACTOR
    city_res['SER_city'] = (city_res['sto_annual'] / city_res['emis_sum']) * STO_FACTOR
    city_tab = city_tab.merge(city_res[['city_n', 'BCR_city', 'SER_city']], on='city_n', how='left')

    # competitive water: new basis already carried per plant (summed to city);
    # old basis uses HSWUD first, else manual, else bingtuan, else 0.
    if WATER_SRC == 'new':
        city_tab['U_hswud'] = np.nan
        city_tab['U_manual'] = np.nan
        city_tab['U_bingtuan'] = np.nan
    else:
        city_tab['U_hswud'] = city_tab['city_n'].map(hswud_comp)
        city_tab['U_manual'] = city_tab['city_n'].map(manual_comp)
        # bingtuan cities -> their prefecture's manual value; if prefecture absent
        # (白杨->塔城, 北屯->阿勒泰) fall back to the Xinjiang-wide per-capacity proxy:
        xj_total = manual.loc[manual['city'] == '全疆', 'competitive']
        xj_mean_city = float(xj_total.iloc[0]) / 13 if len(xj_total) else None
        bingtuan_val = {}
        for b, p in BINGTUAN_TO_PREF.items():
            v = manual_comp.get(norm(p))
            if v is None:
                v = xj_mean_city if xj_mean_city is not None else np.nan
            bingtuan_val[b] = v
        city_tab['U_bingtuan'] = city_tab['city_n'].map(bingtuan_val)
        city_tab['数据来源'] = np.where(city_tab['U_hswud'].notna(), 'HSWUD',
                                 np.where(city_tab['U_manual'].notna(), '手工年报',
                                 np.where(city_tab['U_bingtuan'].notna(), '兵团->地州', '缺(设为0)')))
        city_tab['U_竞争_亿m3'] = city_tab['U_hswud'].fillna(city_tab['U_manual']).fillna(
            city_tab['U_bingtuan']).fillna(0.0)

    # ---- city total coal+CCS water withdrawal ----
    W_city = df.groupby('city_n')[COL_W].sum().rename('W_煤电_亿m3')
    city_tab = city_tab.merge(W_city, on='city_n', how='left')
    city_tab['W_煤电_亿m3'] = city_tab['W_煤电_亿m3'].fillna(0.0)

    # ---- CITY-LEVEL total-pressure WSR (EFR 20 / 37 / 50 / 80) ----
    #   WSR_city = (W_coal_city + U_comp_city + EFR*R_city) / R_city
    for efr, tag in [(EFR_LOW, 'EFR20'), (EFR_ZERO, 'EFR00'),
                     (EFR_BASE, 'EFR37'), (EFR_SENS, 'EFR50'),
                     (EFR_HIGH, 'EFR80')]:
        city_tab[f'WSR_市_{tag}'] = (
            city_tab['W_煤电_亿m3'] + city_tab['U_竞争_亿m3'] + efr * city_tab['R_亿m3']
        ) / city_tab['R_亿m3']
        city_tab[f'煤电可用水_{tag}'] = city_tab['R_亿m3'] - city_tab['U_竞争_亿m3'] - efr * city_tab['R_亿m3']

    # ---- plant-level merge (plants inherit their city's WSR, BCR, SER) ----
    df = df.merge(city_tab[['city_n', 'R_亿m3', 'U_竞争_亿m3', '数据来源',
                            'BCR_city', 'SER_city',
                            'WSR_市_EFR20', 'WSR_市_EFR00', 'WSR_市_EFR37',
                            'WSR_市_EFR50', 'WSR_市_EFR80',
                            'cap_city', 'n_city']], on='city_n')

    # ================= PLANT-LEVEL BCR / SER / WSR =========================
    # Same three quantities as above, but computed for each plant from its OWN
    # resources rather than from its city totals.
    #
    #   BCR_i = biomass_i / energy_i                 (all GJ)
    #   SER_i = min(storage_i / LIFE, injection_i) / emissions_i     (Mt, Mt/a)
    #   WSR_i = (W_i + U_i + EFR * R_i) / R_i        (1e8 m3)
    #
    # The city-level columns stay exactly as they were (molecular sums over the
    # city), because the figures and the 8-class export read them.
    df['BCR_plant'] = (df[COL_BIO] / df[COL_E].replace(0, np.nan)) * BIO_FACTOR / GEN_FACTOR
    df['SER_plant'] = (df['sto_annual'] / df[COL_EMIS].replace(0, np.nan)) * STO_FACTOR
    if WATER_SRC == 'new':
        # R and U are already per plant
        R_pl, U_pl = df['R_plant'], df['U_plant']
    else:
        # old basis: apportion the city totals by capacity, so a plant gets its
        # capacity share of the prefecture's water and competitive withdrawal
        R_pl = df['R_亿m3'] * df[COL_CAP] / df['cap_city'].replace(0, np.nan)
        U_pl = df['U_竞争_亿m3'] * df[COL_CAP] / df['cap_city'].replace(0, np.nan)
    df['R_plant_used'] = R_pl
    df['U_plant_used'] = U_pl
    for efr, tag in [(EFR_LOW, 'EFR20'), (EFR_ZERO, 'EFR00'),
                     (EFR_BASE, 'EFR37'), (EFR_SENS, 'EFR50'),
                     (EFR_HIGH, 'EFR80')]:
        df[f'WSR_plant_{tag}'] = (
            df[COL_W] + U_pl + efr * R_pl
        ) / R_pl.replace(0, np.nan)
        df[f'煤电可用水_plant_{tag}'] = R_pl - U_pl - efr * R_pl

    # ---- city summary of the PLANT-level ratios -----------------------------
    # Two readings per city, both reported:
    #   * _city   : molecular sums over the city (the original definition)
    #   * plant_mean / _capw : mean of the plant-level ratios, unweighted and
    #                          weighted by capacity -- shows within-city spread
    g = df.groupby('city_n').agg(
        BCR_plant_mean=('BCR_plant', 'mean'),
        SER_plant_mean=('SER_plant', 'mean'),
        WSR_plant_mean=('WSR_plant_EFR50', 'mean'),
        BCR_plant_med=('BCR_plant', 'median'),
        SER_plant_med=('SER_plant', 'median'),
        WSR_plant_med=('WSR_plant_EFR50', 'median'),
        BCR_plant_gt1=('BCR_plant', lambda s: 100 * (s > 1).mean()),
        SER_plant_gt1=('SER_plant', lambda s: 100 * (s > 1).mean()),
        WSR_plant_gt1=('WSR_plant_EFR50', lambda s: 100 * (s > 1).mean()),
    ).reset_index()
    city_tab = city_tab.merge(g, on='city_n', how='left')

    # ---- summary ----
    n = len(df)
    print(f'plants: {n}, prefecture cities: {len(city_tab)}')
    print('data-source breakdown:')
    print(city_tab['数据来源'].value_counts().to_string())
    print('\ncity-level total-pressure WSR (EFR 20/37/50/80):')
    for tag in ['EFR20', 'EFR00', 'EFR37', 'EFR50', 'EFR80']:
        w = city_tab[f'WSR_市_{tag}'].dropna()
        print(f'  {tag}: WSR>1 = {100*(w>1).mean():.1f}% | median {w.median():.3f}')
    print('\nwater basis:')
    if WATER_SRC == 'new':
        print('  new %s | plant-level R=%s, U=%s (ChinaWR TWR + HSWUD dom+manu+irr, 1980-2020 mean)'
              % (os.path.basename(WATER_XLSX), COL_R_NEW, COL_U_NEW))
        print('  city value = sum of its plants\' own values (not the whole-city total)')
    else:
        print('  old | city-level R=%s | U = HSWUD (2010-19) / manual bulletins (2021)' % COL_R)
    print('  sum R=%.0f 1e8 m3   sum U=%.0f 1e8 m3'
          % (city_tab['R_亿m3'].sum(), city_tab['U_竞争_亿m3'].sum()))
    print('\ncity-level BCR/SER:')
    bcr_gt1 = 100 * (city_tab['BCR_city'] > 1).mean()
    ser_gt1 = 100 * (city_tab['SER_city'] > 1).mean()
    print(f'  BCR_city>1: {bcr_gt1:.1f}% | SER_city>1: {ser_gt1:.1f}%')

    # ---- plant-level vs city-level comparison ----
    # Three different readings, labelled explicitly because they answer
    # different questions:
    #   plant-level  : share of PLANTS whose own ratio > 1
    #   city, by city: share of CITIES whose aggregate ratio > 1
    #   city, by plant: share of PLANTS in a city whose aggregate > 1
    print('\nplant-level vs city-level (three ratios):')
    print('  %-6s %10s %14s %14s' % ('', 'plant', 'city (by city)', 'city (by plant)'))
    cmp_specs = [('BCR', 'BCR_plant', 'BCR_city'),
                 ('SER', 'SER_plant', 'SER_city'),
                 ('WSR50', 'WSR_plant_EFR50', 'WSR_市_EFR50')]
    for nm, pc, cc in cmp_specs:
        pv = pd.to_numeric(df[pc], errors='coerce')
        cv_p = pd.to_numeric(df[cc], errors='coerce')          # per plant row
        cv_c = pd.to_numeric(city_tab[cc], errors='coerce')    # per city
        print('  %-6s %9.1f%% %13.1f%% %13.1f%%' % (
            nm, 100 * (pv > 1).mean(), 100 * (cv_c > 1).mean(), 100 * (cv_p > 1).mean()))
    print('  note: plant-level uses each plant\'s own resources; city-level sums the\n'
      '        city\'s resources and demands separately before dividing')

    # ---- export (the prefecture key uses the ORIGINAL city name) ----
    city_out = city_tab[['所在城市', 'prov_n', 'prov_en', 'R_亿m3', 'U_hswud', 'U_manual',
                         'U_bingtuan', 'U_竞争_亿m3', '数据来源',
                         'BCR_city', 'SER_city',
                         'WSR_市_EFR20', 'WSR_市_EFR00', 'WSR_市_EFR37',
                         'WSR_市_EFR50', 'WSR_市_EFR80',
                         'BCR_plant_mean', 'SER_plant_mean', 'WSR_plant_mean',
                         'BCR_plant_med', 'SER_plant_med', 'WSR_plant_med',
                         'BCR_plant_gt1', 'SER_plant_gt1', 'WSR_plant_gt1',
                         'cap_city', 'n_city']].rename(
        columns={'所在城市': '地级市', 'prov_n': '省份', 'prov_en': '省份英文',
                 'R_亿m3': '水资源总量_亿m3',
                 'U_hswud': 'HSWUD竞争_亿m3', 'U_manual': '手工竞争_亿m3',
                 'U_bingtuan': '兵团地州竞争_亿m3', 'U_竞争_亿m3': '最终竞争_亿m3',
                 'BCR_city': '市级生物质掺烧比_BCR', 'SER_city': '市级封存排放比_SER',
                 'WSR_市_EFR20': '市级WSR_EFR20', 'WSR_市_EFR00': '市级WSR_EFR00',
                 'WSR_市_EFR37': '市级WSR_EFR37', 'WSR_市_EFR50': '市级WSR_EFR50',
                 'WSR_市_EFR80': '市级WSR_EFR80',
                 'BCR_plant_mean': '市级_电厂BCR均值', 'SER_plant_mean': '市级_电厂SER均值',
                 'WSR_plant_mean': '市级_电厂WSR50均值',
                 'BCR_plant_med': '市级_电厂BCR中位', 'SER_plant_med': '市级_电厂SER中位',
                 'WSR_plant_med': '市级_电厂WSR50中位',
                 'BCR_plant_gt1': '市级_电厂BCR>1占比%', 'SER_plant_gt1': '市级_电厂SER>1占比%',
                 'WSR_plant_gt1': '市级_电厂WSR50>1占比%',
                 'cap_city': '地级市装机_MW', 'n_city': '地级市电厂数'})
    plant_out = df[['序号', '所在省', '所在城市', '经度', '纬度', COL_CAP, COL_W,
                    '数据来源', 'BCR_city', 'SER_city',
                    'WSR_市_EFR20', 'WSR_市_EFR00', 'WSR_市_EFR37',
                    'WSR_市_EFR50', 'WSR_市_EFR80',
                    'BCR_plant', 'SER_plant', 'R_plant_used', 'U_plant_used',
                    'WSR_plant_EFR20', 'WSR_plant_EFR00', 'WSR_plant_EFR37',
                    'WSR_plant_EFR50', 'WSR_plant_EFR80']].rename(
        columns={COL_CAP: '装机_MW', COL_W: '电厂取水含CCS_亿m3',
                 'BCR_city': '市级BCR', 'SER_city': '市级SER',
                 'WSR_市_EFR20': '市级WSR_EFR20', 'WSR_市_EFR00': '市级WSR_EFR00',
                 'WSR_市_EFR37': '市级WSR_EFR37', 'WSR_市_EFR50': '市级WSR_EFR50',
                 'WSR_市_EFR80': '市级WSR_EFR80',
                 'BCR_plant': '电厂级BCR', 'SER_plant': '电厂级SER',
                 'R_plant_used': '电厂可用水_亿m3', 'U_plant_used': '电厂竞争水_亿m3',
                 'WSR_plant_EFR20': '电厂级WSR_EFR20', 'WSR_plant_EFR00': '电厂级WSR_EFR00',
                 'WSR_plant_EFR37': '电厂级WSR_EFR37', 'WSR_plant_EFR50': '电厂级WSR_EFR50',
                 'WSR_plant_EFR80': '电厂级WSR_EFR80'})
    with pd.ExcelWriter(OUT, engine='openpyxl') as xw:
        city_out.to_excel(xw, sheet_name='city_level', index=False)
        plant_out.to_excel(xw, sheet_name='plant_level', index=False)
        m[['hswud_city', 'plant_city']].to_excel(xw, sheet_name='mapping', index=False)
        city_tab[['所在城市', '数据来源']].rename(columns={'所在城市': '地级市'}).to_excel(
            xw, sheet_name='coverage', index=False)
        rd = pd.DataFrame({
            'parameter': ['EFR scenario', 'competitive-use source', 'available-water source',
                          'water spatial scale',
                          'WSR definition', 'BCR/SER scale', 'plant-level columns',
                          'city-level columns'],
            'value': ['0% / 37% baseline / 50% (environmental-flow reserve)',
                      ('ChinaWR TWR + HSWUD dom+manu+irr, 1980-2020 mean (plant level)'
                       if WATER_SRC == 'new' else 'mainly HSWUD (2010-19), supplemented by manual bulletins (2021)'),
                      ('column %s of water_thiessen_local.xlsx (plant local Thiessen intersected with its own prefecture, 1980-2020 mean)'
                       % COL_R_NEW if WATER_SRC == 'new' else COL_R),
                      ('plant level (each plant\'s own Thiessen territory water)' if WATER_SRC == 'new'
                       else 'prefecture level (apportioned to plants by installed capacity)'),
                      'WSR = (coal-CCS withdrawal + competitive use + EFR*R) / R',
                      'both plant-level and city-level are provided',
                      'plant BCR / plant SER / plant WSR_EFR00-80 / plant available water / plant competitive water',
                      'city aggregates (numerator and denominator summed separately) + plant-based mean / median / share>1']})
        rd.to_excel(xw, sheet_name='readme', index=False)
    print('\nsaved:', OUT)


if __name__ == '__main__':
    main()
