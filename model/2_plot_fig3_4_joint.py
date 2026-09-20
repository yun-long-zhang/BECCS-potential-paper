# -*- coding: utf-8 -*-
"""Fig 3.4: Resource status x CO2 emissions - CITY-LEVEL.

Layout (2x2):
  Row 1: (a) donut chart of emission share by scarce class
             (0: 2.5%, 1: 23.6%, 2: 64.5%, 3: 9.4%)
         (b) CO2 emissions vs city BCR
  Row 2: (c) CO2 emissions vs city SER
         (d) CO2 emissions vs city WSR

Note: the 4-D scatter (formerly panel a) and the city-level Lorenz curves
(formerly panel c) were moved to Fig 3.6 and Fig 3.12 respectively.

Scarce count = (BCR<1)+(SER<1)+(WSR(EFR50)>1). Outputs PNG, PDF, XLSX."""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import _style

SRC = os.path.join(os.path.dirname(__file__), 'plant level analysis data.xlsx')
OUT_DIR = os.environ.get('BECCS_OUT_DIR', os.path.dirname(__file__))
AGG = os.path.join(OUT_DIR, 'plant_city_hswud_aggregated.xlsx')
OUT = os.path.join(OUT_DIR, 'Fig3_4_joint')

# sensitivity parameters
EFR = float(os.environ.get('BECCS_EFR', '0.50'))
LIFE = float(os.environ.get('BECCS_LIFE', '20'))
BIO_FACTOR = float(os.environ.get('BECCS_BIO_FACTOR', '1.0'))
EFR_TAG = 'EFR20' if EFR <= 0.21 else ('EFR80' if EFR >= 0.79 else 'EFR50')
WSR_COL = {'EFR20': '市级WSR_EFR20', 'EFR50': '市级WSR_EFR50', 'EFR80': '市级WSR_EFR80'}[EFR_TAG]
STO_FACTOR = float(os.environ.get('BECCS_STO_FACTOR', '1.0'))

# ---- city-level data ----
c = pd.read_excel(AGG, sheet_name='city_level')
for col in ['市级生物质掺烧比_BCR', '市级封存排放比_SER', WSR_COL, '地级市装机_MW']:
    c[col] = pd.to_numeric(c[col], errors='coerce')
c['BCR'] = pd.to_numeric(c['市级生物质掺烧比_BCR'], errors='coerce') * BIO_FACTOR
# NOTE: the aggregated city SER already embeds the storage horizon (LIFE) and
# STO_FACTOR, and is derived from min(accessible volume / LIFE, injection rate)
# divided by annual emissions.  Do NOT rescale it again here.
c['SER'] = pd.to_numeric(c['市级封存排放比_SER'], errors='coerce')
c['WSR'] = c[WSR_COL]
c['GW'] = c['地级市装机_MW'] / 1000.0

p = pd.read_excel(SRC, sheet_name=os.environ.get('BECCS_SHEET', '市域内比较'))
p = p[p['序号'].notna()].copy()
p['年碳排放Mt'] = pd.to_numeric(p['年碳排放Mt'], errors='coerce')
p['地级市'] = p['所在城市'].astype(str)
emis_city = p.groupby('地级市')['年碳排放Mt'].sum()
c = c.merge(emis_city.rename('emis_Mt'), left_on='地级市', right_index=True, how='left')
c['EMIS'] = pd.to_numeric(c['emis_Mt'], errors='coerce')
c = c.replace([np.inf, -np.inf], np.nan).dropna(subset=['BCR', 'SER', 'WSR', 'EMIS'])
c['EMIS_pct'] = 100 * c['EMIS'] / c['EMIS'].sum()

c['scarce'] = (c['BCR'] < 1).astype(int) + (c['SER'] < 1).astype(int) + (c['WSR'] > 1).astype(int)
c['water'] = np.where(c['WSR'] <= 1, 'adequate', 'constrained')

df_sc = c[(c['BCR'] > 0) & (c['SER'] > 0)].copy()
df_sc.loc[df_sc['BCR'] < 1e-3, 'BCR'] = 1e-3
df_sc.loc[df_sc['SER'] < 1e-3, 'SER'] = 1e-3


def _gini(vals):
    v = np.sort(np.asarray(vals, dtype=float))
    v = v[~np.isnan(v)]
    if len(v) == 0 or v.sum() == 0:
        return np.nan
    n = len(v)
    return 2 * np.sum(np.arange(1, n + 1) * v) / (n * v.sum()) - (n + 1) / n


def _lorenz(vals):
    v = np.sort(np.asarray(vals, dtype=float))
    v = v[~np.isnan(v)]
    if v.sum() == 0:
        return np.linspace(0, 1, len(v) + 1)
    csum = np.cumsum(v) / v.sum()
    return np.insert(csum, 0, 0.0)

sc_emis = c.groupby('scarce')['EMIS_pct'].sum().reindex([0, 1, 2, 3]).fillna(0)
sc_emis = sc_emis / sc_emis.sum() * 100
labels = ['0 (resource-rich)', '1 (resource-moderate)', '2 (resource-short)', '3 (resource-vacuum)']
colors = ['#1a9850', '#fee08b', '#fdae61', '#d73027']

# ---- export ----
with pd.ExcelWriter(OUT + '.xlsx') as xw:
    c[['BCR', 'SER', 'WSR', 'EMIS_pct', 'scarce', 'water']].rename(
        columns={'EMIS_pct': 'emis_share_pct'}).to_excel(xw, sheet_name='a_scatter', index=False)
    sc_emis.rename('emis_share_pct').to_frame().to_excel(xw, sheet_name='e_donut')
    for nm, col in [('b_BCR', 'BCR'), ('c_SER', 'SER'), ('d_WSR', 'WSR')]:
        c[['EMIS_pct', col]].rename(columns={'EMIS_pct': 'emis_share_pct'}).to_excel(
            xw, sheet_name=nm, index=False)
    # panel c: city-level Lorenz curves + Gini
    lx = np.linspace(0, 1, len(_lorenz(c['EMIS'].values)))
    pd.DataFrame({'cum_cities': lx,
                  'emis': _lorenz(c['EMIS'].values),
                  'bio': _lorenz(c['BCR'].values),
                  'sto': _lorenz(c['SER'].values),
                  'water_inv': _lorenz(1.0 / c['WSR'].values)}).to_excel(
        xw, sheet_name='c_lorenz', index=False)
    pd.DataFrame({'resource': ['emissions', 'biomass', 'storage', 'water(1/WSR)'],
                  'gini': [_gini(c['EMIS'].values), _gini(c['BCR'].values),
                           _gini(c['SER'].values), _gini(1.0 / c['WSR'].values)]}).to_excel(
        xw, sheet_name='c_gini', index=False)
# ---- figure (2x2, four panels) ----
fig = plt.figure(figsize=(15, 11))
gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.0],
                      wspace=0.22, hspace=0.28,
                      left=0.07, right=0.97, top=0.94, bottom=0.07)

# (a) donut - emission share by scarce class, labels placed in place with leader lines
ax = fig.add_subplot(gs[0, 0])
wedges, _ = ax.pie(sc_emis, colors=colors, startangle=90, counterclock=False, radius=1.8,
                   wedgeprops=dict(width=0.7, edgecolor='w'))
ax.text(0, -2.5, 'Emission share by scarce class', ha='center', va='center', fontsize=20)
frac = sc_emis.values / sc_emis.values.sum()
start = 90.0
mids = []
for f in frac:
    mids.append((start - f * 360.0 / 2.0) % 360.0)
    start -= f * 360.0

r_inner = 1.5
r_text = 1.5

for lab, v, mid in zip(labels, sc_emis, mids):
    ang = np.deg2rad(mid)
    xt = r_text * np.cos(ang)
    yt = r_text * np.sin(ang)
    num_part, desc_part = lab.split(maxsplit=1)
    desc_part = desc_part.strip()
    txt_content = f'{num_part}\n{desc_part}\n{v:.1f}%'
    deg = mid % 360
    if 40 < deg < 90:
        ha = "left"
    elif 90 < deg < 180:
        ha = "right"
    else:
        ha = "center"
    ax.text(xt, yt, txt_content, ha=ha, va="center",
            fontsize=16, color='#222222')
ax.set_xlim(-2.0, 2.0); ax.set_ylim(-2.0, 2.0)
_style.panel_label(ax, 'a')

# (b) emissions vs BCR
ax = fig.add_subplot(gs[0, 1])
ax.scatter(c['BCR'], c['EMIS_pct'], s=18, alpha=0.55, c='#2b8cbe', edgecolor='none')
ax.set_xscale('log')
ax.set_xlabel('City BCR (log)')
ax.set_ylabel('City emission share [%]')
ax.axvline(1, color='k', ls=':', lw=0.7)
_style.panel_label(ax, 'b')

# (c) emissions vs SER
ax = fig.add_subplot(gs[1, 0])
ax.scatter(c['SER'], c['EMIS_pct'], s=18, alpha=0.55, c='#d95f0e', edgecolor='none')
ax.set_xscale('log')
ax.set_xlabel('City SER (log)')
ax.set_ylabel('City emission share [%]')
ax.axvline(1, color='k', ls=':', lw=0.7)
_style.panel_label(ax, 'c')

# (d) emissions vs WSR
ax = fig.add_subplot(gs[1, 1])
ax.scatter(c['WSR'], c['EMIS_pct'], s=18, alpha=0.55, c='#756bb1', edgecolor='none')
ax.set_xscale('log')
ax.set_xlabel('City WSR (log)')
ax.set_ylabel('City emission share [%]')
ax.axvline(1, color='k', ls=':', lw=0.7)
_style.panel_label(ax, 'd')

_style.save(fig, OUT)
print('saved', OUT + '.png/.pdf/.xlsx')
print('  emission share by scarce: ', {int(k): round(v, 1) for k, v in sc_emis.items()})
print('  WSR>1 cities:', (c['WSR'] > 1).sum(), '| WSR<=1:', (c['WSR'] <= 1).sum())
