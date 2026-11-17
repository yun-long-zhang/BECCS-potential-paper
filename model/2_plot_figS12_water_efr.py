# -*- coding: utf-8 -*-
"""Fig S3: CITY-LEVEL total-pressure WSR under three EFR scenarios
(EFR 20% / 50% / 80%). Sensitivity / SI companion to Fig 3.3.

Panels: (A) city WSR scatter under EFR50 (same as main) with EFR20/80 range,
        (B) share of water-constrained cities (WSR>1) per scenario,
        (C) step-line distribution of city WSR under the three scenarios
        (lines, no fill, so scenarios never overlap/occlude).
Outputs PNG, PDF, XLSX."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
# figure outputs honour BECCS_OUT_DIR so a whole alternative basis can be
# written to a separate folder without touching the main results
OUT_DIR = os.environ.get('BECCS_OUT_DIR', HERE)
os.makedirs(OUT_DIR, exist_ok=True)

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import _style

AGG = os.path.join(OUT_DIR, 'plant_city_hswud_aggregated.xlsx')
OUT = os.path.join(OUT_DIR, 'FigS12_water_efr')

c = pd.read_excel(AGG, sheet_name='city_level')
for col in ['市级WSR_EFR20', '市级WSR_EFR50', '市级WSR_EFR80']:
    c[col] = pd.to_numeric(c[col], errors='coerce')
c['prov'] = c['省份英文'].astype(str)
c = c.dropna(subset=['市级WSR_EFR20', '市级WSR_EFR50', '市级WSR_EFR80'])

scen = {
    'EFR 20%': c['市级WSR_EFR20'],
    'EFR 50%': c['市级WSR_EFR50'],
    'EFR 80%': c['市级WSR_EFR80'],
}
share = {k: 100 * (v > 1).mean() for k, v in scen.items()}
med = {k: v.median() for k, v in scen.items()}

# ---- export ----
with pd.ExcelWriter(OUT + '.xlsx') as xw:
    c[['地级市', '省份英文', '市级WSR_EFR20', '市级WSR_EFR50', '市级WSR_EFR80']].to_excel(
        xw, sheet_name='city_WSR', index=False)
    pd.DataFrame({'EFR情景': list(scen.keys()),
                  'WSR>1占比_%': list(share.values()),
                  '中位数': list(med.values())}).to_excel(xw, sheet_name='summary', index=False)
    # panel C step-line data (bin centres + counts per scenario)
    bins = np.arange(0, 4.05, 0.25)
    centres = (bins[:-1] + bins[1:]) / 2.0
    step_df = pd.DataFrame({'bin_centre': centres})
    for k in scen:
        counts, _ = np.histogram(scen[k], bins=bins)
        step_df[k] = counts
    step_df.to_excel(xw, sheet_name='c_step', index=False)
    # tail counts (WSR > 4) per scenario
    tail_df = pd.DataFrame({'EFR情景': list(scen.keys()),
                            'WSR>4城市数': [int((v > 4).sum()) for v in scen.values()],
                            'WSR>4占比_%': [100 * (v > 4).mean() for v in scen.values()]})
    tail_df.to_excel(xw, sheet_name='c_tail', index=False)

# ---- figure ----
fig, axes = plt.subplots(1, 3, figsize=(15, 5.4),
                         gridspec_kw={'width_ratios': [1.0, 1.0, 1.0],
                                      'wspace': 0.30})
ax = axes[0]
w50 = scen['EFR 50%'].sort_values()
order = np.arange(len(w50))
lo = scen['EFR 20%'].sort_values().values
hi = scen['EFR 80%'].sort_values().values
ax.fill_between(order, lo, hi, color='#56B4E9', alpha=0.35, label='EFR 20–80%')
ax.plot(order, w50.values, color='#0072B2', lw=3.0, label='EFR 50%')
ax.axhline(1, color='k', ls='--', lw=0.8)
ax.set_xlabel('City rank')
ax.set_ylabel('City-level WSR')
ax.set_ylim(0, 3)
ax.legend(fontsize=16)
_style.panel_label(ax, 'a')

ax = axes[1]
colors = ['#56B4E9', '#0072B2', '#003F6B']
bars = ax.bar([k.replace('EFR ', '') for k in share], list(share.values()), color=colors, alpha=0.9)
ax.axhline(100, color='k', lw=0.6)
for b, v in zip(bars, share.values()):
    ax.text(b.get_x() + b.get_width() / 2, v + 1, f'{v:.1f}%', ha='center', fontsize=16)
ax.set_ylabel('Cities with WSR > 1 [%]')
ax.set_xlabel('Environmental-flow reserve (EFR)')
ax.set_ylim(0, 100)
_style.panel_label(ax, 'b')

ax = axes[2]
bins = np.arange(0, 4.05, 0.25)
for k, color in [('EFR 20%', '#56B4E9'), ('EFR 50%', '#0072B2'), ('EFR 80%', '#003F6B')]:
    counts, _ = np.histogram(scen[k], bins=bins)
    # step line: use bin centres; add a trailing point to close the last bin
    centres = (bins[:-1] + bins[1:]) / 2.0
    xs = np.concatenate([centres, [centres[-1] + (centres[-1] - centres[0])]])
    ys = np.concatenate([counts, [counts[-1]]])
    lw = 4.0 if k == 'EFR 50%' else 1.5  # baseline scenario emphasized
    ax.step(xs, ys, where='post', color=color, lw=lw, label=k)
ax.axvline(1, color='k', ls='--', lw=0.8)
ax.set_xlabel('City-level WSR')
ax.set_ylabel('Number of cities')
ax.set_xlim(0, 4)
# annotate truncated tail (cities with WSR > 4)
n_tail = int((scen['EFR 50%'] > 4).sum())
pct_tail = 100 * (scen['EFR 50%'] > 4).mean()
ax.text(0.98, 0.95, f'{n_tail} cities ({pct_tail:.1f}%) with\nWSR > 4 not shown',
        transform=ax.transAxes, ha='right', va='top', fontsize=16, color='#555555')
ax.legend(fontsize=16)
_style.panel_label(ax, 'c')

_style.save(fig, OUT)
print('saved', OUT + '.png/.pdf/.xlsx')
for k in scen:
    print(f'  {k}: share={share[k]:.1f}%, median={med[k]:.3f}')
