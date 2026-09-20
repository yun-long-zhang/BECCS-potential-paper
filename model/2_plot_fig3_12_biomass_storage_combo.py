# -*- coding: utf-8 -*-
"""Fig 3.12: Combined biomass, CO2-storage, and water endowments (5-panel combo).

Layout (3 rows):
  Row 1: (a) Biomass spatial scatter (BCR, log, diverging green-red)
         (b) Storage spatial scatter (SER, log, diverging purple-blue)
  Row 2: (c) Prefecture WSR map (EFR 50%) [from Fig 3.3a]
         (d) City-level Lorenz curves + Gini [from Fig 3.4c]
  Row 3: (e) Cumulative distribution of BCR, SER and WSR on a shared symlog
             x-axis (full width; WSR curve merged from former panel f)

Each map panel has a South China Sea inset and an in-panel colourbar.
Outputs PNG, PDF, XLSX (same basename)."""
import os
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import geopandas as gpd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.colors import to_rgba
from matplotlib.cm import ScalarMappable

import _cols
import _style

HERE = os.path.dirname(os.path.abspath(__file__))
SHAPE = os.path.join(HERE, 'china_maps', 'prefecture_boundaries.shp')
BOUNDARY_SHP = os.path.join(HERE, 'china_maps', 'national_boundary.shp')
SCS_EXTENT = (105, 125, 3, 25)
SRC = os.path.join(HERE, 'plant level analysis data.xlsx')
OUT_DIR = os.environ.get('BECCS_OUT_DIR', HERE)
OUT = os.path.join(OUT_DIR, 'Fig3_12_biomass_storage_combo')
WATER_XLSX = os.path.join(OUT_DIR, 'Fig3_3_water.xlsx')
JOINT_XLSX = os.path.join(OUT_DIR, 'Fig3_4_joint.xlsx')
AGG = os.path.join(OUT_DIR, 'plant_city_hswud_aggregated.xlsx')

# sensitivity parameters applied to the main panels (a-d)
BIO_FACTOR = float(os.environ.get('BECCS_BIO_FACTOR', '1.0'))
STO_FACTOR = float(os.environ.get('BECCS_STO_FACTOR', '1.0'))
LIFE = float(os.environ.get('BECCS_LIFE', '20'))
GEN_FACTOR = float(os.environ.get('BECCS_GEN_FACTOR', '1.0'))

# biomass / storage buffer radius (see _cols.py): BECCS_BIO_RADIUS / BECCS_STO_RADIUS
COL_BIO = _cols.bio_col()
COL_STO = _cols.sto_col()
COL_INJ = _cols.inj_col()
# the workbook's cached BCR column (V = S/M) is tied to the 100-km biomass
# column, so it can only be used when the biomass radius is the baseline one
USE_WB_BCR = os.environ.get('BECCS_BIO_RADIUS', '100').strip() == '100'


def load_prefectures():
    gdf = gpd.read_file(SHAPE, encoding='utf-8')
    if gdf.crs is not None and not gdf.crs.is_geographic:
        gdf = gdf.to_crs(epsg=4326)
    return gdf


def load_boundaries():
    bd = gpd.read_file(BOUNDARY_SHP, encoding='utf-8')
    if bd.crs is not None and not bd.crs.is_geographic:
        bd = bd.to_crs(epsg=4326)
    return bd


def add_scs_inset(fig, ax, bd=None, plot_layer=None):
    if bd is None:
        bd = load_boundaries()
    xmin, xmax, ymin, ymax = SCS_EXTENT
    iax = ax.inset_axes([0.76, 0.02, 0.26, 0.30])
    if plot_layer is not None:
        plot_layer(iax)
    bd_scs = bd.cx[xmin:xmax, ymin:ymax]
    bd_scs.plot(ax=iax, color='#333333', linewidth=0.5)
    iax.set_xlim(xmin, xmax); iax.set_ylim(ymin, ymax)
    for spine in iax.spines.values():
        spine.set_visible(True); spine.set_color('#555555'); spine.set_linewidth(0.8)
    iax.set_xticks([]); iax.set_yticks([]); iax.tick_params(length=0)
    return iax


# ---------------- data ----------------
df = pd.read_excel(SRC, sheet_name=os.environ.get('BECCS_SHEET', '市域内比较'), header=0)
df = df[df['序号'].notna()].copy()
df['prov'] = df['provinces'].astype(str)
for c in ['经度', '纬度', '假设生物质100%能用，最大掺烧比例',
          COL_STO, COL_INJ, '年碳排放Mt']:
    df[c] = pd.to_numeric(df[c], errors='coerce')
# BCR = biomass / fuel demand; fuel demand scales with generation (GEN_FACTOR).
# So a generation cut raises BCR by 1/GEN_FACTOR; biomass availability scales by BIO_FACTOR.
if USE_WB_BCR:
    # workbook cached V = (100-km biomass) / (plant fuel demand)
    df['BCR'] = (df['假设生物质100%能用，最大掺烧比例'] * BIO_FACTOR) / GEN_FACTOR
else:
    # recompute from the selected biomass column (cached V is tied to 100 km)
    df['BCR'] = (df[COL_BIO] / df['煤电系统所需能量GJ'].replace(0, np.nan)
                 * BIO_FACTOR / GEN_FACTOR)
# Annualised storage potential is limited by BOTH the accessible volume over the
# allocation horizon AND the annual injection-rate capability; the binding one
# applies.  Divided by annual emissions this reproduces the workbook column
# The workbook's storage-ratio column (Chinese header retained in the file)
# when LIFE = 20 and STO_FACTOR = 1.
df['SER'] = (np.minimum(df[COL_STO] / LIFE, df[COL_INJ])
             / df['年碳排放Mt'].replace(0, np.nan)) * STO_FACTOR
df = df.dropna(subset=['经度', '纬度', 'BCR', 'SER'])

df_bcr = df[df['BCR'] > 0].copy(); df_bcr.loc[df_bcr['BCR'] < 1e-3, 'BCR'] = 1e-3
df_ser = df[df['SER'] > 0].copy(); df_ser.loc[df_ser['SER'] < 1e-3, 'SER'] = 1e-3

prov_b = df.groupby('prov').agg(
    median_BCR=('BCR', 'median'), share_gt1_BCR=('BCR', lambda s: 100 * (s > 1).mean()),
).reset_index().sort_values('median_BCR')
prov_s = df.groupby('prov').agg(
    share_gt1_SER=('SER', lambda s: 100 * (s > 1).mean()), median_SER=('SER', 'median'),
).reset_index().sort_values('share_gt1_SER', ascending=False)

bcr_all = np.sort(df['BCR'].values)
ser_all = np.sort(df['SER'].values)
share = np.arange(1, len(bcr_all) + 1) / len(bcr_all)

# ---- water data: PLANT-level WSR (panels c, d, e) ---------------------------
# Panels a/b already use plant-level BCR/SER, so the water panels are put on the
# same footing: every plant carries its OWN WSR, computed from the water that is
# geographically attributable to it (local Thiessen cell ∩ its prefecture).
# `plant_city_hswud_aggregated.xlsx` -> plant_level has the plant-level column.
WATER_COL = '电厂级WSR_EFR50'
wpl = pd.read_excel(AGG, sheet_name='plant_level')
wpl['序号'] = pd.to_numeric(wpl['序号'], errors='coerce')
wpl[WATER_COL] = pd.to_numeric(wpl[WATER_COL], errors='coerce')
wpl = wpl.dropna(subset=['序号', WATER_COL])
df = df.merge(wpl[['序号', WATER_COL]], on='序号', how='left')
df = df.rename(columns={WATER_COL: 'WSR'})
n_missing_wsr = int(df['WSR'].isna().sum())

# city-level WSR is still read for the export sheet, as a cross-check
wcity = pd.read_excel(AGG, sheet_name='city_level')
for wcol in ['市级WSR_EFR20', '市级WSR_EFR50', '市级WSR_EFR80']:
    wcity[wcol] = pd.to_numeric(wcity[wcol], errors='coerce')
wcity = wcity.dropna(subset=['市级WSR_EFR20', '市级WSR_EFR50', '市级WSR_EFR80'])
w50 = wcity['市级WSR_EFR50'].sort_values().values


# ---- plant-level Lorenz curves + Gini (panel d) ---------------------------
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
    return np.insert(np.cumsum(v) / v.sum(), 0, 0.0)


# one common subset so all four curves share the same population of plants
_d = df.dropna(subset=['WSR', 'BCR', 'SER', '年碳排放Mt']).copy()
_d = _d[(_d['WSR'] > 0) & (_d['年碳排放Mt'] > 0)]
# WSR cumulative curve (plant level).  Defined here, before the data export, so
# the same array feeds both the export and panel (e).
wpl_all = np.sort(_d['WSR'].values)
wsr_share = np.arange(1, len(wpl_all) + 1) / len(wpl_all)
_lx = np.linspace(0, 1, len(_lorenz(_d['年碳排放Mt'].values)))
_pl = {'emis': _lorenz(_d['年碳排放Mt'].values),
       'bio': _lorenz(_d['BCR'].values),
       'sto': _lorenz(_d['SER'].values),
       'water_inv': _lorenz(1.0 / _d['WSR'].values)}
_plg = {'emis': _gini(_d['年碳排放Mt'].values), 'bio': _gini(_d['BCR'].values),
        'sto': _gini(_d['SER'].values), 'water_inv': _gini(1.0 / _d['WSR'].values)}
print('plant-level Lorenz population: %d plants (WSR missing for %d of %d)'
      % (len(_d), n_missing_wsr, len(df)))

# ---- export plot data ----
with pd.ExcelWriter(OUT + '.xlsx') as xw:
    # every plant is listed; BCR/SER = 0 means the plant has no accessible
    # biomass / storage resource (plotted as a grey dot in panels a and b)
    _exp = df[['经度', '纬度', 'BCR', 'SER']].copy()
    _exp['BCR_zero'] = _exp['BCR'] <= 0
    _exp['SER_zero'] = _exp['SER'] <= 0
    _exp.rename(columns={'经度': 'longitude', '纬度': 'latitude'}).to_excel(
        xw, sheet_name='ab', index=False)
    prov_b.to_excel(xw, sheet_name='c_province_BCR', index=False)
    prov_s.to_excel(xw, sheet_name='d_province_SER', index=False)
    # multi-horizon SER: min(volume / horizon, injection rate) / emissions; the
    # injection cap is horizon-independent, so these are recomputed, not scaled
    _vol = df[COL_STO]
    _inj = df[COL_INJ].fillna(0.0)
    _emi = df['年碳排放Mt'].replace(0, np.nan)
    ser25 = np.sort((np.minimum(_vol / 25.0, _inj) / _emi).fillna(0).values)
    ser30 = np.sort((np.minimum(_vol / 30.0, _inj) / _emi).fillna(0).values)
    pd.DataFrame({'BCR': bcr_all, 'SER': ser_all, 'cumulative_share': share,
                  'BCR_50pct': np.sort(df['BCR'].values * 0.5),
                  'BCR_25pct': np.sort(df['BCR'].values * 0.25),
                  'SER_25yr': ser25,
                  'SER_30yr': ser30,
                  }).to_excel(xw, sheet_name='e_cumulative', index=False)
    pd.DataFrame({'plant_rank': np.arange(1, len(_d) + 1),
                  'plant_share': np.arange(1, len(_d) + 1) / len(_d),
                  'WSR_EFR50_plant': np.sort(_d['WSR'].values)}).to_excel(
        xw, sheet_name='e_wsr_cdf_plant', index=False)
    pd.DataFrame({'city_rank': np.arange(1, len(w50) + 1),
                  'city_share': np.arange(1, len(w50) + 1) / len(w50),
                  'WSR_EFR50_city': w50}).to_excel(
        xw, sheet_name='e_wsr_cdf_city', index=False)
    pd.DataFrame({'cum_plants': _lx,
                  'emis': _pl['emis'], 'bio': _pl['bio'],
                  'sto': _pl['sto'], 'water_inv': _pl['water_inv']}).to_excel(
        xw, sheet_name='d_lorenz_plant', index=False)
    pd.DataFrame({'resource': ['emissions', 'biomass', 'storage', 'water(1/WSR)'],
                  'gini_plant': [_plg['emis'], _plg['bio'], _plg['sto'],
                                 _plg['water_inv']]}).to_excel(
        xw, sheet_name='d_gini_plant', index=False)
    # value of each cumulative curve at ratio = 1: the share of plants that fall
    # SHORT on that dimension (these are the numbers annotated in panel e)
    pd.DataFrame({'indicator': ['BCR', 'SER', 'WSR_EFR50'],
                  'share_below_1': [float(np.interp(1.0, bcr_all, share)),
                                    float(np.interp(1.0, ser_all, share)),
                                    float(np.interp(1.0, wpl_all, wsr_share))],
                  'n_plants': [len(bcr_all), len(ser_all), len(wpl_all)]}).to_excel(
        xw, sheet_name='e_curve_at_1', index=False)

# ---------------- figure ----------------
_gdf = load_prefectures()
_bd = load_boundaries()

fig = plt.figure(figsize=(20, 22))
gs = fig.add_gridspec(3, 2, height_ratios=[1.0, 1.0, 1.0], wspace=0.18,
                      hspace=0.03, left=0.06, right=0.97, top=0.96, bottom=0.05)


def _nice_log_ticks(vmin, vmax, maxn=8):
    """Readable tick positions for a log10 axis, adapted to the range width.

    A 1-2-5 series (0.5, 1, 2, 5, 10, ...) is preferred because it resolves the
    top of the range.  On the wide BCR / SER ranges that would give 14-21 labels
    and overlap badly inside the narrow inset colourbar, so those fall back to
    whole decades (0.01, 0.1, 1, 10, ...) with the decade step widened as needed.
    Value 1 is always kept when in range: BCR = SER = WSR = 1 is the "resource is
    sufficient" threshold these panels are read against.
    """
    import math
    lo, hi = int(math.floor(vmin)), int(math.ceil(vmax))
    exps = [e for e in range(lo, hi + 1) if vmin - 1e-9 <= e <= vmax + 1e-9]
    if not exps:
        return [vmin, vmax]

    cand = sorted({math.log10(m * 10.0 ** e) for e in exps for m in (1, 2, 5)})
    cand = [c for c in cand if vmin - 1e-9 <= c <= vmax + 1e-9]
    if len(cand) <= maxn:
        pos = cand
    else:
        sel = exps
        for step in (1, 2, 5, 10):
            sel = [e for e in exps if (e - exps[0]) % step == 0]
            if len(sel) <= maxn:
                break
        if 0 in exps and 0 not in sel:
            sel = sorted(set(sel) | {0})
        pos = [float(e) for e in sel]

    if pos[0] > vmin + 1e-9:
        pos = [vmin] + pos                  # always mark the lower end of data
    return pos


def draw_map(ax, xs, ys, vals, cmap, norm, cbar_label, zero=None):
    """Plant scatter map.

    `vals` are log10 values and are coloured on the diverging scale.  Plants with
    a ZERO resource cannot be put on a log axis, so they are passed separately as
    `zero` = (xs0, ys0) and drawn as small neutral grey dots: they still mark
    where those plants are, without pretending they carry any resource.
    """
    _gdf.plot(ax=ax, color='#ffffff', edgecolor='#b4b4b4', linewidth=0.2)
    ax.set_xlim(73, 136); ax.set_ylim(17, 54)
    ax.set_aspect(1.0 / np.cos(np.radians(35)))
    sc = ax.scatter(xs, ys, c=vals, cmap=cmap, norm=norm, s=80, alpha=0.5,
                    linewidths=0, zorder=3)
    if zero is not None and len(zero[0]):
        ax.scatter(zero[0], zero[1], s=26, marker='o', c='#9e9e9e',
                   alpha=0.85, linewidths=0, zorder=2,
                   label='no resource (value = 0)')
        ax.legend(loc='lower left', fontsize=13, frameon=False,
                  handletextpad=0.3, borderpad=0.1)
    ax.set_xlabel('Longitude (°E)'); ax.set_ylabel('Latitude (°N)')
    ax.set_xlim(73, 136); ax.set_ylim(17, 54)
    ax.set_aspect(1.0 / np.cos(np.radians(35)))
    cb_ax = ax.inset_axes([0.06, 0.92, 0.50, 0.035])
    cb = fig.colorbar(sc, cax=cb_ax, orientation='horizontal')
    # values are plotted as log10(value); label the ticks back in the ORIGINAL
    # units.  Use %g, which trims only insignificant trailing zeros -- chaining
    # .rstrip('0') after %.4g turns 10 / 100 / 1000 into "1".
    cb.set_ticks(_nice_log_ticks(norm.vmin, norm.vmax))
    cb.ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{10 ** x:g}'))
    cb.set_label(cbar_label, fontsize=14)
    cb.ax.tick_params(labelsize=12, length=2)
    def _scs_layer(iax):
        _gdf.plot(ax=iax, color='#ffffff', edgecolor='#b8b4b4', linewidth=0.2)
    add_scs_inset(fig, ax, bd=_bd, plot_layer=_scs_layer)


# Row 1: (a) biomass map, (b) storage map
# All plants are drawn: those with a positive resource are coloured on the log
# diverging scale, those with zero resource are grey dots.  Without the grey
# layer ~74% of plants (SER = 0) simply vanished from panel (b).
_ZERO_B = df[df['BCR'] <= 0]
ax = fig.add_subplot(gs[0, 0])
cmap_b = LinearSegmentedColormap.from_list('gwr', ['#d73027', '#ffffff', '#1a9850'])
logb = np.log10(df_bcr['BCR'].values)
norm_b = TwoSlopeNorm(vmin=np.log10(df_bcr['BCR'].min()), vcenter=0.0,
                      vmax=np.log10(df_bcr['BCR'].quantile(0.99)))
draw_map(ax, df_bcr['经度'], df_bcr['纬度'], logb, cmap_b, norm_b,
         'Biomass co-firing ratio (BCR)',
         zero=(_ZERO_B['经度'].values, _ZERO_B['纬度'].values))
_style.panel_label(ax, 'a', fontsize=24)

_ZERO_S = df[df['SER'] <= 0]
ax = fig.add_subplot(gs[0, 1])
cmap_s = LinearSegmentedColormap.from_list('bwp', ['#d73027', '#ffffff', '#7b3294'])
logs = np.log10(df_ser['SER'].values)
norm_s = TwoSlopeNorm(vmin=np.log10(df_ser['SER'].min()), vcenter=0.0,
                      vmax=np.log10(df_ser['SER'].quantile(0.99)))
draw_map(ax, df_ser['经度'], df_ser['纬度'], logs, cmap_s, norm_s,
         'Storage-to-emission ratio (SER)',
         zero=(_ZERO_S['经度'].values, _ZERO_S['纬度'].values))
_style.panel_label(ax, 'b', fontsize=24)

# Row 2: (c) plant-level WSR scatter, (d) plant-level Lorenz curves
# Panel (c) is now on the same footing as (a) and (b): a plant-level scatter of
# the concatenated plant-level WSR, using the same log/diverging treatment.
ax_c = fig.add_subplot(gs[1, 0])
cmap_pwb = LinearSegmentedColormap.from_list('pwb', ['#4575b4', '#ffffff', '#d73027'])
df_w = df.dropna(subset=['WSR']).copy()
_ZERO_W = df_w[df_w['WSR'] <= 0]
df_w = df_w[df_w['WSR'] > 0]
df_w.loc[df_w['WSR'] < 1e-3, 'WSR'] = 1e-3
vmax_w = float(np.log10(df_w['WSR'].quantile(0.99)))
norm_pwb = TwoSlopeNorm(vmin=np.log10(df_w['WSR'].min()), vcenter=0.0, vmax=vmax_w)
draw_map(ax_c, df_w['经度'], df_w['纬度'], np.log10(df_w['WSR'].values),
         cmap_pwb, norm_pwb, 'Water-stress ratio (WSR)',
         zero=(_ZERO_W['经度'].values, _ZERO_W['纬度'].values))
_style.panel_label(ax_c, 'c', fontsize=24)

ax = fig.add_subplot(gs[1, 1])
lx = _lx
curves_lz = [
    (_pl['emis'], 'Emissions', '#000000', _plg['emis']),
    (_pl['bio'], 'Biomass (BCR)', '#80e397', _plg['bio']),
    (_pl['sto'], 'Storage (SER)', '#d95f0e', _plg['sto']),
    (_pl['water_inv'], 'Water (1/WSR)', '#2b8cbe', _plg['water_inv']),
]
anchors_lz = {
    'Water (1/WSR)':  (0.45, -0.01),
    'Emissions':      (0.68, -0.02),
    'Biomass (BCR)':  (0.80, -0.02),
    'Storage (SER)':  (0.80, -0.02),
}
ax.plot([0, 1], [0, 1], ':', lw=2.0)
for lc, lab, colr, gval in curves_lz:
    ax.plot(lx, lc, lw=3, color=colr, label=lab)
    xa, dy = anchors_lz[lab]
    ya = np.interp(xa, lx, lc)
    ax.annotate(f'Gini = {gval:.2f}', xy=(xa, ya), xytext=(xa + 0.02, ya + dy),
                fontsize=16, color=colr, ha='left', va='center',
                arrowprops=dict(arrowstyle='-', color=colr, lw=2.0))
ax.set_xlabel('Cumulative share of plants')
ax.set_ylabel('Cumulative share of\nresource / emissions')
ax.legend(fontsize=16, loc='upper left', frameon=False)
_style.panel_label(ax, 'd', fontsize=24)
# align panel (d) height with the map panel (c): the map is aspect-constrained,
# so its axes box is shorter; give (d) the same y-extent (centred in its grid cell)
pm = ax_c.get_position()
pd_ = ax.get_position()
ax.set_position([pd_.x0, pm.y0, pd_.width, pm.height])

# Row 3: (e) combined cumulative distribution of BCR, SER and WSR (full width)
ax_e = fig.add_subplot(gs[2, :])
ax = ax_e
is_scenario = (BIO_FACTOR != 1.0 or STO_FACTOR != 1.0 or LIFE != 20 or GEN_FACTOR != 1.0)
# baseline mode shows only the baseline curves (BCR 100%, SER 20-yr, WSR EFR 50%);
# sensitivity lines are handled in the dedicated sensitivity figure (Fig S16).
ax.plot(bcr_all, share, lw=3.0, color='#80e397', label='Biomass (BCR)')
ax.plot(ser_all, share, lw=3.0, color='#D55E00', label='Storage (SER)')
# all three curves are PLANT-level, so they share one population
# (wpl_all / wsr_share are built above, before the data export)
ax.plot(wpl_all, wsr_share, lw=3.0, color='#74add1', label='Water (WSR)')
if is_scenario:
    tag = []
    if GEN_FACTOR != 1.0: tag.append(f'generation {GEN_FACTOR:.0%}')
    if BIO_FACTOR != 1.0: tag.append(f'biomass {BIO_FACTOR:.0%}')
    if STO_FACTOR != 1.0: tag.append(f'storage {STO_FACTOR:.0%}')
    if LIFE != 20: tag.append(f'{LIFE:.0f}-yr')
    ax.set_title('Scenario: ' + ', '.join(tag), fontsize=16)
ax.axvline(1, color='k', ls='--', lw=2)
ax.text(1.2, 0.2, 'BCR = SER = WSR = 1', rotation=90, va='center', fontsize=16)
# mark where each curve crosses the ratio = 1 line: that ordinate is the share of
# plants falling SHORT on that dimension.  SER (0.82) and BCR (0.66) are close
# together, so their labels get a small vertical offset to avoid colliding.
for _v, _s, _c, _dy in [(bcr_all, share, '#80e397', -0.028),
                        (ser_all, share, '#D55E00', 0.028),
                        (wpl_all, wsr_share, '#74add1', 0.0)]:
    _y = float(np.interp(1.0, _v, _s))
    ax.plot([1.0], [_y], marker='o', ms=11, color=_c,
            markeredgecolor='white', markeredgewidth=1.5, zorder=6)
    ax.annotate(f'{_y:.2f}', xy=(1.0, _y),
                xytext=(0.45, _y + _dy), fontsize=17, color=_c,
                fontweight='bold', va='center', ha='left', zorder=6)
ax.set_xscale('symlog', linthresh=1e-2)
ax.set_xlim(-1e-3, None)
ax.set_xlabel('Biomass co-firing ratio (BCR) / Storage-to-emission ratio (SER) / Water-stress ratio (WSR)', fontsize=16)
ax.set_ylabel('Cumulative share of plants', fontsize=16)
ax.legend(fontsize=16, loc='lower right', ncol=1)
_style.panel_label(ax, 'e', fontsize=24)

# align panel (e) height with the map row (c): maps are aspect-constrained,
# so give (e) the same HEIGHT as the map row, keeping its own row-3 baseline
pm2 = ax_c.get_position()
pe = ax_e.get_position()
ax_e.set_position([pe.x0, pe.y0, pe.width, pm2.height])

_style.save(fig, OUT)
print('saved', OUT + '.png/.pdf/.xlsx')
print('  BCR median=%.3f, >1: %.1f%% | SER >1: %.1f%%' % (
    df['BCR'].median(), 100 * (df['BCR'] > 1).mean(), 100 * (df['SER'] > 1).mean()))
