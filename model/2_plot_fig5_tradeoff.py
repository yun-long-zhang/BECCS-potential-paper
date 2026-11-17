# -*- coding: utf-8 -*-
"""Fig. 5: cost and geographical trade-offs of inter-city coordination.

(a) Minimum inter-city transport cost as a function of the national BECCS
    potential target (S1-S4).
(b) Marginal transport cost along the S4 frontier (USD per t CO2).
(c) Share of the coordination gain (potential above S0) recovered under a
    maximum direct-link distance, for S1-S4.

Input : $BECCS_OUT_DIR/tradeoff_frontiers.xlsx (from 6_tradeoff_frontiers.py)
Output: $BECCS_OUT_DIR/Fig5_tradeoff.png/.pdf/.xlsx
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
SRC = os.path.join(OUT_DIR, 'tradeoff_frontiers.xlsx')
OUT = os.path.join(OUT_DIR, 'Fig5_tradeoff')

cost = pd.read_excel(SRC, sheet_name='cost')
dist = pd.read_excel(SRC, sheet_name='distance')
s0 = float(pd.read_excel(SRC, sheet_name='readme').set_index('item').loc['S0_Mt_yr', 'value'])

STY = {
    'S1_biomass': ('S1: biomass', _style.C_BIO, '-', 'o'),
    'S2_co2': ('S2: CO$_2$', _style.C_CO2, '--', 's'),
    'S3_biomass+co2': ('S3: biomass + CO$_2$', '#CC79A7', '-.', '^'),
    'S4_biomass+co2+water': ('S4: biomass + CO$_2$ + water', '#0072B2', '-', 'D'),
}


def frontier(name):
    f = cost[cost.scenario == name].copy()
    f = f[f.total >= s0 - 1].sort_values('total')
    f = f.drop_duplicates('total')
    # anchor the curve at S0 with zero transport cost
    return pd.concat([pd.DataFrame({'total': [s0], 'cost_bnUSD_yr': [0.0]}),
                      f[['total', 'cost_bnUSD_yr']]]).reset_index(drop=True)


fig, axes = plt.subplots(1, 3, figsize=(22, 6.8),
                         gridspec_kw={'wspace': 0.28, 'width_ratios': [1.1, 1.0, 1.1]})
rows_out = {}

# ---- (a) cost-potential frontier ----
ax = axes[0]
for name, lab_extra, ls in [('S1_biomass', '', None),
                            ('S2_co2', '', None),
                            ('S3_biomass+co2', '', None),
                            ('S4_biomass+co2+water', '', None)]:
    base = name.replace('_250km', '')
    lab, col, ls0, mk = STY[base]
    f = frontier(name)
    rows_out[name] = f
    ax.plot(f['total'], f['cost_bnUSD_yr'], ls=ls or ls0, color=col, lw=2.6,
            marker=mk, ms=5, label=lab + lab_extra)
ax.axvline(s0, color=_style.C_ZERO, lw=1.0, ls=':')
ax.text(s0 + 8, 0.25, 'S0', fontsize=14, color='#555555', va='bottom')
ax.set_xlabel('National BECCS potential target (Mt CO$_2$ yr$^{-1}$)', fontsize=16)
ax.set_ylabel('Minimum transport cost (billion US\\$ yr$^{-1}$)', fontsize=16)
ax.tick_params(labelsize=14)
ax.set_xlim(200, 1200)
YA = 12.5                                           # S1 runs off the top; noted in text
ax.set_ylim(0, YA)
f1 = rows_out['S1_biomass']
x_exit = np.interp(YA, f1['cost_bnUSD_yr'], f1['total'])
ax.text(x_exit + 15, YA * 0.985, '↑ S1 off scale, reaching\n   %.1f billion US\\$ yr$^{-1}$\n   at %.0f Mt CO$_2$ yr$^{-1}$'
        % (f1['cost_bnUSD_yr'].iloc[-1], f1['total'].iloc[-1]),
        ha='left', va='top', fontsize=12, color=_style.C_BIO)
ax.legend(fontsize=13, frameon=False, loc='upper left')
_style.panel_label(ax, 'a', fontsize=22)

# ---- (b) marginal cost along the S4 frontier ----
ax = axes[1]
mc_max = {}
for name in ['S1_biomass', 'S2_co2', 'S3_biomass+co2', 'S4_biomass+co2+water']:
    lab, col, ls, mk = STY[name]
    f = rows_out[name]
    dq = np.diff(f['total'].values)
    dc = np.diff(f['cost_bnUSD_yr'].values) * 1e3     # million USD
    ok = dq > 1.0
    mc = dc[ok] / dq[ok]                                # USD per t CO2
    xm = 0.5 * (f['total'].values[1:] + f['total'].values[:-1])[ok]
    ax.step(np.r_[f['total'].values[:-1][ok], f['total'].values[1:][ok][-1]],
            np.r_[mc, mc[-1]], where='post', color=col, lw=2.4, ls=ls, label=lab)
    mc_max[name] = (mc[-1], f['total'].values[-1])
    if name == 'S1_biomass':                         # left edge of first step above 50
        mc_x50 = f['total'].values[:-1][ok][np.argmax(mc > 50)]
    rows_out[name + '_marginal'] = pd.DataFrame({'midpoint_Mt': xm, 'marginal_USD_per_t': mc})
ax.set_xlabel('National BECCS potential target (Mt CO$_2$ yr$^{-1}$)', fontsize=16)
ax.set_ylabel('Marginal transport cost (US\\$ t$^{-1}$ CO$_2$)', fontsize=16)
ax.tick_params(labelsize=14)
ax.set_xlim(200, 1200)
ax.set_ylim(0, 50)
ax.text(mc_x50 + 15, 50 * 0.985, '↑ S1 off scale, reaching\n   %.0f US\\$ t$^{-1}$\n   at %.0f Mt CO$_2$ yr$^{-1}$'
        % mc_max['S1_biomass'], ha='left', va='top', fontsize=12, color=_style.C_BIO)
# no legend: same line styles as panel a (legend would cross the S1 steps)
_style.panel_label(ax, 'b', fontsize=22)

# ---- (c) distance-potential frontier ----
ax = axes[2]
d_fin = dist[np.isfinite(dist.max_km)]
x_inf = 2500.0                                     # plotting position of "unrestricted"
for name, (lab, col, ls, mk) in STY.items():
    g = d_fin[d_fin.scenario == name].sort_values('max_km')
    if g.empty:
        continue
    u = dist[(dist.scenario == name) & ~np.isfinite(dist.max_km)]
    xs = np.r_[g['max_km'].values, x_inf]
    ys = 100 * np.r_[g['share_of_gain'].values, u['share_of_gain'].values]
    ax.plot(xs, ys, color=col, ls=ls, marker=mk, ms=6, lw=2.4, label=lab)
ax.axvline(250, color=_style.C_ZERO, lw=1.0, ls=':')
ax.set_xscale('log')
ticks = [100, 250, 500, 1000, x_inf]
ax.set_xticks(ticks)
ax.set_xticklabels(['100', '250', '500', '1,000', 'no\nlimit'])
ax.minorticks_off()
ax.set_xlim(65, 3200)
ax.set_ylim(0, 105)
ax.set_xlabel('Maximum direct-link distance (km)', fontsize=16)
ax.set_ylabel('Coordination gain recovered (%)', fontsize=16)
ax.tick_params(labelsize=14)
ax.legend(fontsize=13, frameon=False, loc='lower right')
_style.panel_label(ax, 'c', fontsize=22)

_style.save(fig, OUT)
with pd.ExcelWriter(OUT + '.xlsx') as xw:
    for k, v in rows_out.items():
        v.to_excel(xw, sheet_name=k.replace('+', '_')[:31], index=False)
    dist.to_excel(xw, sheet_name='c_distance', index=False)
print('saved', OUT + '.png/.pdf/.xlsx')
