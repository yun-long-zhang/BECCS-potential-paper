# -*- coding: utf-8 -*-
"""Fig S16: Two-panel sensitivity summary.

(a) 100% stacked bars: share of cities in each of the 8 resource-state classes
    across all scenarios (baseline + 13 sensitivity scenarios).
(b) Stacked bars: self-sufficient BECCS (S0) plus near-distance transport
    (filled) and far-distance transport (outline only), split by commodity
    (biomass <=200 km, CO2 <=250 km, water <=10 km). Two rows of bars with the
    legend on the right in one vertical column; segment labels are absolute
    values in black.

Outputs PNG, PDF, XLSX. Reads the scenario folders under BECCS_RES_ROOT
(default `sensitivity_results/`), and the baseline from BECCS_OUT_DIR.
"""
import os
import glob
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import _style

HERE = os.path.dirname(os.path.abspath(__file__))
# figure outputs honour BECCS_OUT_DIR so a whole alternative basis can be
# written to a separate folder without touching the main results
OUT_DIR = os.environ.get('BECCS_OUT_DIR', HERE)
os.makedirs(OUT_DIR, exist_ok=True)

# scenario-result root.  Default to <OUT_DIR>/sensitivity_results rather than
# HERE/sensitivity_results: a run that only overrides BECCS_OUT_DIR (the common
# case for an alternative basis) would otherwise read the BASELINE row from
# OUT_DIR while reading every scenario row from the main folder -- silently
# mixing two bases into one figure.  Override explicitly with BECCS_RES_ROOT.
RES_ROOT = os.environ.get('BECCS_RES_ROOT',
                          os.path.join(OUT_DIR, 'sensitivity_results'))
OUT = os.path.join(OUT_DIR, 'FigS16_sensitivity_combined')

# 8-class labels (short) and colours (consistent with Fig 3.6)
CLASS_LABELS = {
    1: 'bio+sto+water-rich', 2: 'water-short', 3: 'bio+sto-short', 4: 'bio-short',
    5: 'sto-short', 6: 'bio+water-short', 7: 'sto+water-short', 8: 'resource vacuum',
}
CLASS_COLORS = {
    1: '#1a9850', 2: '#00b0f0', 3: '#a50f15', 4: '#8dd3c7',
    5: '#ffff33', 6: '#fd8d3c', 7: '#984ea3', 8: '#4d4d4d',
}

SCEN_ORDER = ['Baseline', 'EFR20', 'EFR80', 'BIO250', 'BIO500', 'BIO25', 'BIO50',
              'STO100', 'STO500', 'STOR25', 'STOR30', 'STOCAP50', 'STOCAP25',
              'GEN50', 'GEN25', 'DESAL', 'EWR', 'CONS']
SCEN_LABEL = {
    'Baseline': 'Baseline', 'EFR20': 'EFR 20%', 'EFR80': 'EFR 80%',
    'BIO25': 'Biomass 25%', 'BIO50': 'Biomass 50%', 'BIO250': 'Biomass 250km',
    'BIO500': 'Biomass 500km',
    'STO100': 'Storage 100km', 'STO500': 'Storage 500km',
    'STOR25': 'Storage 25yr', 'STOR30': 'Storage 30yr',
    'STOCAP50': 'Sto-cap 50%', 'STOCAP25': 'Sto-cap 25%',
    'GEN50': 'Gen 50%', 'GEN25': 'Gen 25%',
    'DESAL': 'Desalination', 'EWR': 'CO$_2$-EWR',
    'CONS': 'Consumption',
}


def load_8class(path):
    return pd.read_excel(path, sheet_name='city_8class')


def load_coord(path):
    return pd.read_excel(path, sheet_name='city')


# distance thresholds separating 'near' (filled) from 'far' (outline only)
DIST_TH = {'biomass': 200, 'co2': 250, 'water': 0.1}


def split_flows(flow_df, commodity=None):
    """Return (near_sum, far_sum) of transport volume split by distance.

    If commodity is given, only that commodity's flows are used so each
    stacked segment is split by its own threshold (e.g. water segment uses
    only water-link distances).
    """
    if flow_df is None or flow_df.empty or flow_df['Mt_yr'].sum() == 0:
        return 0.0, 0.0
    if commodity is not None:
        flow_df = flow_df[flow_df['commodity'] == commodity]
        if flow_df.empty:
            return 0.0, 0.0
    near_sum = 0.0
    for comm, th in DIST_TH.items():
        if commodity is not None and comm != commodity:
            continue
        sub = flow_df[flow_df['commodity'] == comm]
        if not sub.empty:
            near_sum += sub.loc[sub['km'] <= th, 'Mt_yr'].sum()
    return float(near_sum), float(flow_df['Mt_yr'].sum() - near_sum)


def load_flows(base_dir, sheet_name):
    """Load a flow sheet (S1_biomass / S3_biomass+co2 / S4_biomass+co2+water)."""
    try:
        return pd.read_excel(os.path.join(base_dir, 'BECCS_coordination_result.xlsx'),
                             sheet_name=sheet_name)
    except Exception:
        return None


FLOW_SHEETS = ['S1_biomass', 'S2_co2', 'S3_biomass+co2', 'S4_biomass+co2+water']


def collect():
    """Return list of dicts with scenario data (incl. near/far split)."""
    recs = []
    # baseline (load its own flows so the near/far split works)
    base_flows = {k: load_flows(OUT_DIR, k) for k in FLOW_SHEETS}
    recs.append({
        'name': 'Baseline',
        'c8': load_8class(os.path.join(OUT_DIR, 'Fig3_6_prefecture_8class.xlsx')),
        'cc': load_coord(os.path.join(OUT_DIR, 'BECCS_coordination_result.xlsx')),
        'flows': base_flows,
    })
    for d in sorted(glob.glob(os.path.join(RES_ROOT, '*/'))):
        name = os.path.basename(d.rstrip(os.sep))
        f8 = os.path.join(d, 'Fig3_6_prefecture_8class.xlsx')
        fc = os.path.join(d, 'BECCS_coordination_result.xlsx')
        if os.path.exists(f8) and os.path.exists(fc) and name in SCEN_LABEL:
            flows = {k: load_flows(d, k) for k in FLOW_SHEETS}
            recs.append({'name': name, 'c8': load_8class(f8), 'cc': load_coord(fc),
                         'flows': flows})
    # order
    order = {n: i for i, n in enumerate(SCEN_ORDER)}
    recs.sort(key=lambda r: order.get(r['name'], 99))
    # per-scenario near/far increments for panel (b)
    for r in recs:
        cc = r['cc']
        s0 = cc['S0_local_Mt_yr'].sum()
        s1 = cc['S1_biomass_Mt_yr'].sum()
        s3 = cc['S3_biomass+co2_Mt_yr'].sum()
        s4 = cc['S4_biomass+co2+water_Mt_yr'].sum()
        fl = r['flows']
        # per-commodity split, same convention as Fig 3.10 panel (a): the
        # biomass and CO2 increments of the fully coordinated bar (S4) are
        # split using the S4 (joint) flow sheet, so the two figures agree
        b_n, b_f = split_flows(fl.get('S4_biomass+co2+water'), 'biomass')
        c_n, c_f = split_flows(fl.get('S4_biomass+co2+water'), 'co2')
        w_n, w_f = split_flows(fl.get('S4_biomass+co2+water'), 'water')
        inc_bio = s1 - s0
        inc_co2 = s3 - s1
        inc_wat = s4 - s3
        r['bn'] = inc_bio * (b_n / (b_n + b_f) if (b_n + b_f) else 0)
        r['bf'] = inc_bio - r['bn']
        r['cn'] = inc_co2 * (c_n / (c_n + c_f) if (c_n + c_f) else 0)
        r['cf'] = inc_co2 - r['cn']
        r['wn'] = inc_wat * (w_n / (w_n + w_f) if (w_n + w_f) else 0)
        r['wf'] = inc_wat - r['wn']
    return recs


recs = collect()

# ---------------- export data ----------------
with pd.ExcelWriter(OUT + '.xlsx') as xw:
    rows_a = []
    rows_b = []
    for r in recs:
        c8 = r['c8']; cc = r['cc']
        n = len(c8)
        dist = {cid: 100 * (c8['class_id'] == cid).mean() for cid in range(1, 9)}
        rows_a.append({'scenario': r['name'], **{f'class_{cid}': dist[cid] for cid in range(1, 9)}})
        s0 = cc['S0_local_Mt_yr'].sum()
        s1 = cc['S1_biomass_Mt_yr'].sum()
        s2 = cc['S2_co2_Mt_yr'].sum()
        s3 = cc['S3_biomass+co2_Mt_yr'].sum()
        s4 = cc['S4_biomass+co2+water_Mt_yr'].sum()
        fl = r['flows']
        # near/far split of each transport increment (S1-S0, S3-S1, S4-S3);
        # biomass & CO2 split with the S4 (joint) flow sheet, matching Fig 3.10
        b_n, b_f = split_flows(fl.get('S4_biomass+co2+water'), 'biomass')
        c_n, c_f = split_flows(fl.get('S4_biomass+co2+water'), 'co2')
        w_n, w_f = split_flows(fl.get('S4_biomass+co2+water'), 'water')
        inc_bio = s1 - s0
        inc_co2 = s3 - s1
        inc_wat = s4 - s3
        # scale each commodity increment by its near share
        bio_near = inc_bio * (b_n / (b_n + b_f) if (b_n + b_f) else 0)
        co2_near = inc_co2 * (c_n / (c_n + c_f) if (c_n + c_f) else 0)
        wat_near = inc_wat * (w_n / (w_n + w_f) if (w_n + w_f) else 0)
        rows_b.append({
            'scenario': r['name'], 'S0_local': s0,
            'bio_near': bio_near, 'bio_far': inc_bio - bio_near,
            'co2_near': co2_near, 'co2_far': inc_co2 - co2_near,
            'wat_near': wat_near, 'wat_far': inc_wat - wat_near,
            'S1_biomass': s1, 'S2_co2': s2, 'S3_combined': s3, 'S4_combined': s4,
        })
    pd.DataFrame(rows_a).to_excel(xw, sheet_name='a_8class_share', index=False)
    pd.DataFrame(rows_b).to_excel(xw, sheet_name='b_potential_stack', index=False)

# ---------------- figure ----------------
# two rows: panel (a) on top, panel (b) below; legends on the right in one column
fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(17, 13.5),
                                 gridspec_kw={'hspace': 0.12})

# ---- (a) 100% stacked bars: 8-class city share ----
names = [SCEN_LABEL[r['name']] for r in recs]
x = np.arange(len(recs))
# precompute the 8-class share matrix (rows = scenarios, cols = classes 1..8)
share_mat = np.array([[100 * (r['c8']['class_id'] == cid).mean() for cid in range(1, 9)]
                      for r in recs])
bottoms = np.zeros(len(recs))
for cid in range(1, 9):
    ax_a.bar(x, share_mat[:, cid - 1], 0.62, bottom=bottoms,
             color=CLASS_COLORS[cid], label=CLASS_LABELS[cid],
             edgecolor='white', lw=0.3)
    bottoms = bottoms + share_mat[:, cid - 1]
# solid separators on the x-axis: EFR group (x=1,2) and Biomass group (x=3,4)

# label the top-3 classes of each scenario bar in black
cum = np.cumsum(share_mat, axis=1)
prev = np.concatenate([np.zeros((len(recs), 1)), cum[:, :-1]], axis=1)
for i in range(len(recs)):
    top3 = np.argsort(share_mat[i])[::-1][:3]
    for k in top3:
        v = share_mat[i, k]
        if v >= 5.0:   # skip tiny segments to avoid clutter
            yc = prev[i, k] + v / 2.0
            ax_a.text(x[i], yc, f'{v:.0f}%', ha='center', va='center',
                      fontsize=11, color='black', fontweight='bold', zorder=4)
# panel (a) shares the x-axis labels with panel (b): hide its own tick labels
# use the SAME tick positions and x-limits as panel (b) so the bars align
ax_a.set_xticks(x)
ax_a.set_xticklabels([''] * len(recs))
ax_a.set_ylabel('Share of cities (%)', fontsize=16)
ax_a.set_xlim(left=-1.0, right=len(recs))
ax_a.set_ylim(0, 100)
ax_a.legend(fontsize=13, ncol=1, loc='center left', bbox_to_anchor=(1.01, 0.5),
            frameon=False, title='')
ax_a.tick_params(labelsize=15, length=0)
_style.panel_label(ax_a, 'a', fontsize=20)

# ---- (b) stacked BECCS potential: S0 + near (filled) + far (outline) ----
s0s = np.array([r['cc']['S0_local_Mt_yr'].sum() for r in recs])
s4s = np.array([r['cc']['S4_biomass+co2+water_Mt_yr'].sum() for r in recs])
bn = np.array([r['bn'] for r in recs]); bf = np.array([r['bf'] for r in recs])
cn = np.array([r['cn'] for r in recs]); cf = np.array([r['cf'] for r in recs])
wn = np.array([r['wn'] for r in recs]); wf = np.array([r['wf'] for r in recs])
# col for each commodity: base colors, filled for near, same-color outline for far
bio_col, co2_col, wat_col = '#7b3294', '#d7191c', '#2c7bb6'
EDGE_LW = 1.2
# near (filled) segments: S0, biomass, co2, water
ax_b.bar(x, s0s, 0.62, color='#40b948', edgecolor='#40b948', lw=EDGE_LW,
         label='Self-sufficient (S0)')
b1 = s0s
ax_b.bar(x, bn, 0.62, bottom=b1, color=bio_col, edgecolor=bio_col, lw=EDGE_LW,
         label='biomass, \u2264 200 km')
b2 = b1 + bn
ax_b.bar(x, cn, 0.62, bottom=b2, color=co2_col, edgecolor=co2_col, lw=EDGE_LW,
         label='CO$_2$, \u2264 250 km')
b3 = b2 + cn
#ax_b.bar(x, wn, 0.62, bottom=b3, color=wat_col, edgecolor=wat_col, lw=EDGE_LW,
 #        label='+ water, \u2264 10 km')
b4 = b3 + wn
# far (outline only, no fill) segments
ax_b.bar(x, bf, 0.62, bottom=b4, facecolor='none', edgecolor=bio_col, lw=EDGE_LW,
         label='biomass, > 200 km')
ax_b.bar(x, cf, 0.62, bottom=b4 + bf, facecolor='none', edgecolor=co2_col, lw=EDGE_LW,
         label='CO$_2$, > 250 km')
ax_b.bar(x, wf, 0.62, bottom=b4 + bf + cf, facecolor='none', edgecolor=wat_col, lw=EDGE_LW,
         label='water, (if transferable)')
# absolute values (black) inside each segment; no total labels
for i in range(len(recs)):
    segs = [
        (0, s0s[i]), (b1[i], bn[i]), (b2[i], cn[i]), (b3[i], wn[i]),
        (b4[i], bf[i]), (b4[i] + bf[i], cf[i]), (b4[i] + bf[i] + cf[i], wf[i]),
    ]
    for bottom, h in segs:
        if h > 30:
            ax_b.text(i, bottom + h * 0.5, f'{h:.0f}',
                      ha='center', va='center', fontsize=12,
                      color='black', fontweight='bold', zorder=4)
ax_b.set_xticks(x); ax_b.set_xticklabels(names, rotation=90, ha='center', fontsize=16)
ax_b.set_xlim(left=-1.0, right=len(recs))
ax_b.set_ylim(0, 1800)
ax_b.set_ylabel('BECCS potential (Mt CO$_2$ yr$^{-1}$)', fontsize=16)
ax_b.legend(fontsize=13, ncol=1, loc='center left', bbox_to_anchor=(1.01, 0.5),
            frameon=False, title='')
ax_b.tick_params(labelsize=15)
# group separators drawn BELOW the x-axis of panel (b), not inside the panels:
# Baseline and the 250-km biomass (BIO250) each form their own group; then the
# EFR group (x=2,3), Biomass group (x=4,5) and the storage groups follow.
# Lines go from the axis bottom (y=0) downward into the label area.
for xd in (-0.5, 0.5, 2.5, 4.5, 6.5, 8.5, 10.5, 12.5, 14.5, 15.5, 16.5, 17.5):
    ax_b.plot([xd, xd], [0.0, -0.28],
              transform=ax_b.get_xaxis_transform(),
              clip_on=False, color='#666666', lw=1.4)
_style.panel_label(ax_b, 'b', fontsize=20)

_style.save(fig, OUT)
print('saved', OUT + '.png/.pdf/.xlsx')
print('  scenarios:', len(recs))
