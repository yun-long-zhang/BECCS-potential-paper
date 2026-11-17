# -*- coding: utf-8 -*-
"""Supplementary figure: city-level Lorenz curves and Gini coefficients.

Fig. 1d of the main text is computed over the 2,171 PLANTS.  This figure gives
the same comparison over the 304 prefecture-level CITIES, in two forms:

  (a) resource indicators -- city BCR, SER and 1/WSR, as in Fig. 1d
  (b) absolute resource quantities -- accessible biomass energy, annualised
      storage capacity and water available after the environmental-flow reserve
      and competing withdrawals (negative values set to 0)

Coal-power CO2 emissions are shown in both panels for reference.  Panel (b)
is the check that the inequality ranking is not an artefact of the ratio form:
1/WSR is bounded above by 1/EFR, whereas BCR and SER are not.

Inputs  (BECCS_OUT_DIR): plant_city_hswud_aggregated.xlsx
        (model/)        : plant level analysis data.xlsx
Output  (BECCS_OUT_DIR): FigS_gini_city.png / .pdf / .xlsx
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import _cols
import _style

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'plant level analysis data.xlsx')
OUT_DIR = os.environ.get('BECCS_OUT_DIR', HERE)
AGG = os.path.join(OUT_DIR, 'plant_city_hswud_aggregated.xlsx')
OUT = os.path.join(OUT_DIR, 'FigS_gini_city')

EFR = float(os.environ.get('BECCS_EFR', '0.50'))
LIFE = float(os.environ.get('BECCS_LIFE', '20'))
WSR_COL = {0.2: '市级WSR_EFR20', 0.5: '市级WSR_EFR50', 0.8: '市级WSR_EFR80'}[round(EFR, 1)]

# same colours as Fig. 1d, plus a line style per series so identity is not
# carried by colour alone
STYLE = {
    'emis': ('Emissions', _style.C_S0, '--'),
    'bio': ('Biomass', _style.C_BIO, '-'),
    'sto': ('Storage', _style.C_CO2, '-.'),
    'wat': ('Water', _style.C_WAT, ':'),
}


def gini(v):
    v = np.sort(np.asarray(v, dtype=float))
    v = v[~np.isnan(v)]
    n = len(v)
    return 2 * np.sum(np.arange(1, n + 1) * v) / (n * v.sum()) - (n + 1) / n


def lorenz(v):
    v = np.sort(np.asarray(v, dtype=float))
    v = v[~np.isnan(v)]
    return (np.linspace(0, 1, len(v) + 1),
            np.insert(np.cumsum(v) / v.sum(), 0, 0.0))


# ---------------- data ----------------
p = _cols.read_plants(SRC)
p['city'] = p['所在城市'].astype(str)
for c in ['年碳排放Mt', _cols.bio_col(), _cols.sto_col(), _cols.inj_col()]:
    p[c] = pd.to_numeric(p[c], errors='coerce')
p['sto_ann'] = np.minimum(p[_cols.sto_col()] / LIFE, p[_cols.inj_col()])
cp = p.groupby('city').agg(emis=('年碳排放Mt', 'sum'), bio=(_cols.bio_col(), 'sum'),
                           sto=('sto_ann', 'sum'))

ag = pd.read_excel(AGG, sheet_name='city_level')
ag['city'] = ag['地级市'].astype(str)
ag = ag.set_index('city')
c = cp.join(ag[['市级生物质掺烧比_BCR', '市级封存排放比_SER', WSR_COL,
                '水资源总量_亿m3', '最终竞争_亿m3']])
c['BCR'] = c['市级生物质掺烧比_BCR']
c['SER'] = c['市级封存排放比_SER']
c['inv_WSR'] = 1.0 / c[WSR_COL]
c['water_avail'] = (c['水资源总量_亿m3'] * (1 - EFR) - c['最终竞争_亿m3']).clip(lower=0)
c = c.replace([np.inf, -np.inf], np.nan)

panels = {
    'a': [('emis', c['emis']), ('bio', c['BCR']), ('sto', c['SER']), ('wat', c['inv_WSR'])],
    'b': [('emis', c['emis']), ('bio', c['bio']), ('sto', c['sto']), ('wat', c['water_avail'])],
}
LAB = {
    'a': {'emis': 'Emissions', 'bio': 'Biomass (BCR)', 'sto': 'Storage (SER)',
          'wat': 'Water (1/WSR)'},
    'b': {'emis': 'Emissions', 'bio': 'Accessible biomass energy',
          'sto': 'Annualised storage capacity', 'wat': 'Available water'},
}
TITLE = {'a': 'Resource indicators', 'b': 'Absolute resource quantities'}

# ---------------- figure ----------------
fig, axs = plt.subplots(1, 2, figsize=(15, 6.6), gridspec_kw={'wspace': 0.18})
rows = []
for ax, key in zip(axs, ['a', 'b']):
    ax.plot([0, 1], [0, 1], color='#999999', lw=1.0, zorder=1)
    for k, v in panels[key]:
        name, col, ls = STYLE[k]
        x, y = lorenz(v)
        g = gini(v)
        ax.plot(x, y, color=col, ls=ls, lw=2.4, zorder=3,
                label='%s, Gini = %.2f' % (LAB[key][k], g))
        rows.append({'panel': key, 'series': LAB[key][k], 'gini': g,
                     'n_cities': int(v.notna().sum()),
                     'share_zero': float((v.fillna(0) <= 0).mean())})
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_aspect('equal')
    ax.set_xlabel('Cumulative share of cities', fontsize=15)
    ax.set_ylabel('Cumulative share of resource / emissions', fontsize=15)
    ax.set_title(TITLE[key], fontsize=16, pad=10)
    ax.tick_params(labelsize=13)
    ax.grid(color='#e6e6e6', lw=0.6, zorder=0)
    ax.legend(fontsize=12.5, loc='upper left', frameon=False, handlelength=2.6)
    _style.panel_label(ax, key, fontsize=22)

_style.save(fig, OUT)

with pd.ExcelWriter(OUT + '.xlsx') as xw:
    pd.DataFrame(rows).to_excel(xw, sheet_name='gini', index=False)
    c[['emis', 'BCR', 'SER', 'inv_WSR', 'bio', 'sto', 'water_avail']].rename(columns={
        'emis': 'emissions_Mt', 'inv_WSR': '1/WSR', 'bio': 'biomass_GJ',
        'sto': 'storage_Mt_per_yr', 'water_avail': 'available_water_1e8m3'}).to_excel(
        xw, sheet_name='city_values')
    pd.DataFrame({'item': ['level', 'EFR', 'storage horizon (yr)', 'available water'],
                  'value': ['304 prefecture-level cities', EFR, LIFE,
                            'R (1 - EFR) - competing withdrawal, negative set to 0']}).to_excel(
        xw, sheet_name='readme', index=False)

print('saved', OUT + '.png/.pdf/.xlsx')
for r in rows:
    print('  (%s) %-30s Gini = %.2f  zero share %.0f%%'
          % (r['panel'], r['series'], r['gini'], 100 * r['share_zero']))
