# -*- coding: utf-8 -*-
"""Supplementary figure: transport-distance distribution under full coordination.

For the fully coordinated scenario (S4), the cumulative share of each
commodity's transported mass (biomass, captured CO2, water) moved on links no
longer than a given distance, with the mass-weighted mean distance marked.

Shares rather than masses are plotted because the three commodities differ by
almost an order of magnitude in mass (water ~1,100 Mt, biomass ~180 Mt).

Input : BECCS_OUT_DIR/BECCS_coordination_result.xlsx, sheet 'S4_biomass+co2+water'
        (uses phys_Mt, the mass moved; older tables fall back to Mt_yr)
Output: BECCS_OUT_DIR/FigS_transport_distance.png / .pdf / .xlsx
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import _style

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get('BECCS_OUT_DIR', HERE)
RES = os.path.join(OUT_DIR, 'BECCS_coordination_result.xlsx')
OUT = os.path.join(OUT_DIR, 'FigS_transport_distance')
NEAR_KM = 250

fl = pd.read_excel(RES, sheet_name='S4_biomass+co2+water')
fl['km'] = pd.to_numeric(fl['km'], errors='coerce')
fl['mass'] = pd.to_numeric(fl['phys_Mt'] if 'phys_Mt' in fl.columns else fl['Mt_yr'],
                           errors='coerce')

# same commodity colours as Fig. 4; line styles so identity is not colour-only
COMM = [
    ('biomass', _style.C_BIO, '-', 'Biomass'),
    ('co2', _style.C_CO2, '--', 'CO$_2$'),
    ('water', _style.C_WAT, '-.', 'Water'),
]

thresholds = np.arange(0, 1301, 5)
series, rows = {}, []
for key, _, _, label in COMM:
    sub = fl[fl['commodity'] == key].sort_values('km')
    tot = sub['mass'].sum()
    if tot <= 0:
        series[key] = np.zeros_like(thresholds, dtype=float)
        continue
    cum = np.cumsum(sub['mass'].values) / tot * 100
    # share moved on links <= d : step function of the sorted link distances
    idx = np.searchsorted(sub['km'].values, thresholds, side='right')
    series[key] = np.where(idx > 0, cum[np.maximum(idx - 1, 0)], 0.0)
    rows.append({'commodity': key, 'links': len(sub), 'mass_Mt_yr': tot,
                 'mean_km_mass_weighted': (sub['mass'] * sub['km']).sum() / tot,
                 'max_km': sub['km'].max(),
                 'share_within_250km_pct': 100 * sub.loc[sub['km'] <= 250, 'mass'].sum() / tot,
                 'share_within_500km_pct': 100 * sub.loc[sub['km'] <= 500, 'mass'].sum() / tot})
summary = pd.DataFrame(rows).set_index('commodity')

with pd.ExcelWriter(OUT + '.xlsx') as xw:
    pd.DataFrame({'distance_km': thresholds,
                  **{'%s_cum_share_pct' % k: series[k] for k, *_ in COMM}}).to_excel(
        xw, sheet_name='cumulative_share', index=False)
    summary.to_excel(xw, sheet_name='summary')

fig, ax = plt.subplots(figsize=(11, 6.8))
ax.axvline(NEAR_KM, color='#888888', ls=':', lw=1.2, zorder=1)
ax.text(NEAR_KM + 8, 3, '%d km' % NEAR_KM, rotation=90, fontsize=12,
        color='#666666', va='bottom')
for key, color, ls, label in COMM:
    if key not in summary.index:
        continue
    m = summary.loc[key]
    ax.step(thresholds, series[key], where='post', color=color, ls=ls, lw=2.4, zorder=3,
            label='%s: %.0f Mt yr$^{-1}$, mean %.0f km' % (label, m['mass_Mt_yr'],
                                                           m['mean_km_mass_weighted']))
    ax.plot([m['mean_km_mass_weighted']], [np.interp(m['mean_km_mass_weighted'], thresholds,
                                                     series[key])],
            marker='o', ms=9, color=color, mec='white', mew=1.5, zorder=4)
ax.set_xlim(0, 1250)
ax.set_ylim(0, 102)
ax.set_xlabel('Transport-distance threshold (km)', fontsize=15)
ax.set_ylabel('Share of transported mass on links within threshold (%)', fontsize=15)
ax.tick_params(labelsize=13)
ax.grid(color='#e6e6e6', lw=0.6, zorder=0)
ax.legend(fontsize=13, loc='lower right', frameon=False, handlelength=2.6)

_style.save(fig, OUT)
print('saved', OUT + '.png/.pdf/.xlsx')
print(summary.round(1).to_string())
