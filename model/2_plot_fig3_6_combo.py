# -*- coding: utf-8 -*-
"""Fig 3.6: Five-panel combo of resource states, emissions, and responsibility-
capacity mismatch.

Layout (3 rows):
  Row 1: (a) 4-D scatter of city BCR vs SER (colour = water status, size =
              CO2 emissions) [moved from Fig 3.4a]
  Row 2: (b) Eight-class resource-state face map (biomass x storage x water).
         (c) Summary bars per resource-state class (cities / capacity / emissions).
  Row 3: (d) Responsibility-capacity mismatch index (MI) face map.
         (e) Summary bars: burden-carrier vs capacity-surplus shares.

Outputs PNG, PDF, XLSX (same basename)."""
import os
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import geopandas as gpd
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Patch

import _cols

# ===================== embedded shared style =====================
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
    'font.size': 20,
    'axes.titlesize': 22,
    'axes.labelsize': 20,
    'xtick.labelsize': 18,
    'ytick.labelsize': 18,
    'legend.fontsize': 18,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'axes.linewidth': 0.6,
    'xtick.major.width': 0.6,
    'ytick.major.width': 0.6,
    'xtick.major.size': 2.5,
    'ytick.major.size': 2.5,
    'xtick.direction': 'out',
    'ytick.direction': 'out',
    'axes.grid': False,
    'axes.axisbelow': True,
    'axes.prop_cycle': plt.cycler(color=['#0072B2', '#D55E00', '#009E73',
                                         '#CC79A7', '#E69F00', '#56B4E9',
                                         '#F0E442', '#000000']),
    'savefig.bbox': 'tight',
})


def panel_label(ax, text, x=0.0, y=1.0, dx=0.0, dy=0.02, fontsize=26):
    ax.text(x + dx, y + dy, text, transform=ax.transAxes, fontsize=fontsize,
            fontweight='bold', va='bottom', ha='left')


def legend_below(ax, fig, handles, ncol, below=0.07, fontsize=16, center_x=None):
    pos = ax.get_position()
    # horizontal anchor: panel-a centre by default, or a figure-fraction x if given
    xc = pos.x0 + pos.width / 2.0 if center_x is None else center_x
    leg_top = pos.y0 - below
    ax.legend(handles=handles, loc='upper center', ncol=ncol, fontsize=fontsize,
              frameon=False, borderaxespad=0.0,
              bbox_to_anchor=(xc, leg_top), bbox_transform=fig.transFigure)
    return ax


def save(fig, out_base):
    fig.savefig(out_base + '.png', dpi=300, bbox_inches='tight')
    fig.savefig(out_base + '.pdf', bbox_inches='tight')
    plt.close(fig)


# ================ South China Sea inset ================
HERE = os.path.dirname(os.path.abspath(__file__))
BOUNDARY_SHP = os.path.join(HERE, 'china_maps', 'national_boundary.shp')
SCS_EXTENT = (105, 125, 3, 25)


def load_boundaries():
    bd = gpd.read_file(BOUNDARY_SHP, encoding='utf-8')
    if bd.crs is not None and not bd.crs.is_geographic:
        bd = bd.to_crs(epsg=4326)
    return bd


def add_scs_inset(fig, ax, bd=None, plot_layer=None,
                  frame_color='#555555', frame_lw=0.8):
    if bd is None:
        bd = load_boundaries()
    xmin, xmax, ymin, ymax = SCS_EXTENT
    iax = ax.inset_axes([0.76, 0.02, 0.26, 0.30])
    if plot_layer is not None:
        plot_layer(iax)
    bd_scs = bd.cx[xmin:xmax, ymin:ymax]
    bd_scs.plot(ax=iax, color='#333333', linewidth=0.5)
    iax.set_xlim(xmin, xmax)
    iax.set_ylim(ymin, ymax)
    for spine in iax.spines.values():
        spine.set_visible(True)
        spine.set_color(frame_color)
        spine.set_linewidth(frame_lw)
    iax.set_xticks([])
    iax.set_yticks([])
    iax.tick_params(length=0)
    return iax


# ================ paths ================
OUT_DIR = os.environ.get('BECCS_OUT_DIR', HERE)
C8 = os.path.join(OUT_DIR, 'Fig3_6_prefecture_8class.xlsx')
SRC = os.path.join(HERE, 'plant level analysis data.xlsx')
AGG = os.path.join(OUT_DIR, 'plant_city_hswud_aggregated.xlsx')
SHAPE_DIR = os.path.join(HERE, 'china_maps')
SHAPE = os.path.join(SHAPE_DIR, 'prefecture_boundaries.shp')
OUT = os.path.join(OUT_DIR, 'Fig3_6_combo')

# sensitivity parameters (shared with Fig 3.4)
EFR = float(os.environ.get('BECCS_EFR', '0.50'))
LIFE = float(os.environ.get('BECCS_LIFE', '20'))
BIO_FACTOR = float(os.environ.get('BECCS_BIO_FACTOR', '1.0'))
EFR_TAG = 'EFR20' if EFR <= 0.21 else ('EFR80' if EFR >= 0.79 else 'EFR50')
WSR_COL = {'EFR20': '市级WSR_EFR20', 'EFR50': '市级WSR_EFR50', 'EFR80': '市级WSR_EFR80'}[EFR_TAG]

# ---- city-level scatter data (from Fig 3.4a) ----
sc = pd.read_excel(AGG, sheet_name='city_level')
for col in ['市级生物质掺烧比_BCR', '市级封存排放比_SER', WSR_COL]:
    sc[col] = pd.to_numeric(sc[col], errors='coerce')
sc['BCR'] = pd.to_numeric(sc['市级生物质掺烧比_BCR'], errors='coerce') * BIO_FACTOR
# the aggregated SER already embeds the horizon and STO_FACTOR (see
# 1_compute_aggregate_city.py) - do not rescale here
sc['SER'] = pd.to_numeric(sc['市级封存排放比_SER'], errors='coerce')
sc['WSR'] = sc[WSR_COL]
dfp = pd.read_excel(SRC, sheet_name=os.environ.get('BECCS_SHEET', '市域内比较'))
dfp = dfp[dfp['序号'].notna()].copy()
dfp['年碳排放Mt'] = pd.to_numeric(dfp['年碳排放Mt'], errors='coerce')
dfp['地级市'] = dfp['所在城市'].astype(str)
emis_city = dfp.groupby('地级市')['年碳排放Mt'].sum()
sc = sc.merge(emis_city.rename('emis_Mt'), left_on='地级市', right_index=True, how='left')
sc['EMIS'] = pd.to_numeric(sc['emis_Mt'], errors='coerce')
sc = sc.replace([np.inf, -np.inf], np.nan).dropna(subset=['BCR', 'SER', 'WSR', 'EMIS'])
sc['water'] = np.where(sc['WSR'] <= 1, 'adequate', 'constrained')
sc_plot = sc[(sc['BCR'] > 0) & (sc['SER'] > 0)].copy()
sc_plot.loc[sc_plot['BCR'] < 1e-3, 'BCR'] = 1e-3
sc_plot.loc[sc_plot['SER'] < 1e-3, 'SER'] = 1e-3

# ================ shared shape + matcher ================
gdf = gpd.read_file(SHAPE, encoding='utf-8')
if gdf.crs is not None and not gdf.crs.is_geographic:
    gdf = gdf.to_crs(epsg=4326)


def norm(s):
    s = str(s).strip()
    s = re.sub(r'[（(].*?[)）]', '', s)
    for suf in ('自治州', '自治县', '自治旗', '地区', '盟', '林区', '市', '县', '区', '旗'):
        s = re.sub(suf + '$', '', s)
    return s


MANUAL = {
    '伊犁': '伊犁哈萨克', '延边': '延边朝鲜', '昌吉': '昌吉回族',
    '巴音郭楞': '巴音郭楞蒙古', '博尔塔拉': '博尔塔拉蒙古', '文山': '文山壮族苗族',
    '黔东南': '黔东南苗族侗族', '黔南': '黔南布依族苗族', '黔西南': '黔西南布依族苗族',
    '乐东': '乐东黎族', '海北藏族自治州': '海北藏族', '海西蒙古族藏族自治州': '海西蒙古族藏族',
    '红河哈尼族彝族自治州': '红河哈尼族彝族', '阿拉善盟': '阿拉善', '白杨': None,
}
sh_norm = {norm(c): c for c in gdf['CITY']}


def map_city_to_shape(name):
    n = norm(name)
    hit = sh_norm.get(n)
    if hit is not None:
        return hit
    if name in MANUAL:
        target = MANUAL[name]
        if target is None:
            return None
        for s, sn in zip(gdf['CITY'], gdf['CITY'].map(norm)):
            if target in sn:
                return s
    return None


# ================ (a)(b) 8-class ================
c8 = pd.read_excel(C8, sheet_name='city_8class')
c8 = c8[['city', 'class_id', 'class_label', 'GW', 'emissions_Mt']].rename(
    columns={'city': '地级市'})
c8['shape_city'] = c8['地级市'].map(map_city_to_shape)
matched8 = c8.dropna(subset=['shape_city'])
cls_lookup = dict(zip(matched8['shape_city'], matched8['class_id']))
gdf['class8'] = gdf['CITY'].map(cls_lookup)

# ---- GDP dimension (city-level, matched by prefecture name) ----
def _normgdp(s):
    s = str(s).strip()
    s = re.sub(r'[（(].*?[)）]', '', s)
    for suf in ('自治州', '自治县', '自治旗', '地区', '盟', '林区', '市', '县', '区', '旗'):
        s = re.sub(suf + '$', '', s)
    return s
_GDP_MAN = {'红河州': '红河', '昌吉州': '昌吉', '巴音郭楞州': '巴音郭楞',
            '伊犁州直属': '伊犁', '博尔塔拉州': '博尔塔拉', '黔东南州': '黔东南',
            '黔南州': '黔南', '黔西南州': '黔西南', '文山州': '文山',
            '海北州': '海北', '海西州': '海西', '延边州': '延边'}
_gdp = pd.read_excel(os.path.join(HERE, 'GDP data.xlsx'))
_gdp['key'] = _gdp['城市'].map(lambda s: _GDP_MAN.get(str(s), _normgdp(s)))
gdp_map = dict(zip(_gdp['key'], _gdp['GDP_亿元']))
c8['GDP'] = c8['地级市'].map(_normgdp).map(gdp_map)   # NaN for missing (e.g. 兵团城市)
tot_gdp8 = c8['GDP'].sum()

cls_colors = {
    1: '#1a9850', 2: '#00b0f0', 3: '#a50f15', 4: '#8dd3c7',
    5: '#ffff33', 6: '#fd8d3c', 7: '#984ea3', 8: '#4d4d4d',
}
cls_labels = {
    1: 'bio+sto+water-rich', 2: 'water-short', 3: 'bio+sto-short', 4: 'bio-short',
    5: 'sto-short', 6: 'bio+water-short', 7: 'sto+water-short', 8: 'resources vacuum',
}
tot_gw8 = c8['GW'].sum(); tot_emis8 = c8['emissions_Mt'].sum()
s8 = c8.groupby('class_id').agg(n=('地级市', 'size'), GW=('GW', 'sum'),
                                emis=('emissions_Mt', 'sum'),
                                GDP=('GDP', 'sum')).reindex(range(1, 9)).fillna(0)
s8['n_pct'] = 100 * s8['n'] / len(c8)
s8['GW_pct'] = 100 * s8['GW'] / tot_gw8
s8['emis_pct'] = 100 * s8['emis'] / tot_emis8
s8['GDP_pct'] = 100 * s8['GDP'] / tot_gdp8

# ================ (c)(d) mismatch ================
COL_BIO = _cols.bio_col()
COL_STO = _cols.sto_col()
df = pd.read_excel(SRC, sheet_name=os.environ.get('BECCS_SHEET', '市域内比较'))
df = df[df['序号'].notna()].copy()
for col in ['年碳排放Mt', COL_BIO, COL_STO, '电厂实际装机总功率MW']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df['地级市'] = df['所在城市'].astype(str)
city = df.groupby('地级市').agg(
    e=('年碳排放Mt', 'sum'), b=(COL_BIO, 'sum'),
    s=(COL_STO, 'sum'), GW=('电厂实际装机总功率MW', 'sum'),
).reset_index()
te, tb, ts = city['e'].sum(), city['b'].sum(), city['s'].sum()
city['e'] = 100 * city['e'] / te
city['b'] = 100 * city['b'] / tb
city['s'] = 100 * city['s'] / ts
city['MI'] = city['e'] - (city['b'] + city['s']) / 2.0
city['GW'] = city['GW'] / 1000.0
# attach GDP to the plant-level city aggregation
city['GDP'] = city['地级市'].map(_normgdp).map(gdp_map)
city['group'] = np.where(city['MI'] > 0, 'burden', 'surplus')
city['shape_city'] = city['地级市'].map(map_city_to_shape)
matched_mi = city.dropna(subset=['shape_city'])
mi_lookup = dict(zip(matched_mi['shape_city'], matched_mi['MI']))
gdf['MI'] = gdf['CITY'].map(mi_lookup)
sm = city.groupby('group').agg(
    n=('地级市', 'size'), GW=('GW', 'sum'), emis=('e', 'sum'),
    GDP=('GDP', 'sum')).reset_index()
sm = sm.set_index('group').reindex(['burden', 'surplus']).fillna(0)
sm['n_pct'] = 100 * sm['n'] / len(city)
sm['GW_pct'] = 100 * sm['GW'] / city['GW'].sum()
sm['emis_pct'] = sm['emis']
sm['GDP_pct'] = 100 * sm['GDP'] / sm['GDP'].sum()

# ================ export ================
with pd.ExcelWriter(OUT + '.xlsx') as xw:
    matched8[['地级市', 'shape_city', 'class_id', 'GW', 'emissions_Mt']].rename(
        columns={'地级市': 'city', 'shape_city': 'shape_name',
                 'class_id': 'class', 'emissions_Mt': 'emissions_Mt'}).to_excel(
        xw, sheet_name='city_class', index=False)
    s8[['n', 'n_pct', 'GW', 'GW_pct', 'emis_pct', 'GDP_pct']].to_excel(xw, sheet_name='summary_8class', index=True)
    matched_mi[['地级市', 'shape_city', 'e', 'b', 's', 'MI', 'GW', 'group']].rename(
        columns={'地级市': 'city', 'shape_city': 'shape_name', 'e': 'emis_share_pct',
                 'b': 'biomass_share_pct', 's': 'storage_share_pct',
                 'MI': 'mismatch_index', 'group': 'burden_or_surplus'}).to_excel(
        xw, sheet_name='city_mi', index=False)
    sm[['n', 'n_pct', 'GW', 'GW_pct', 'emis_pct', 'GDP_pct']].to_excel(xw, sheet_name='summary_mi', index=True)

# ================ figure 3-row ================
fig = plt.figure(figsize=(15, 19))
gs = fig.add_gridspec(3, 2, height_ratios=[0.95, 1.0, 1.0], width_ratios=[1.2, 1.0],
                      wspace=0.15, hspace=0.35,
                      left=0.04, right=0.97, top=0.96, bottom=0.05)
bd = load_boundaries()

# ---- (a) 4-D bubble plot (from Fig 3.4a), spans both columns of row 1 ----
ax = fig.add_subplot(gs[0, :])
smin, smax = sc['EMIS'].min(), sc['EMIS'].max()
sc_plot = sc_plot.copy()
sc_plot['size'] = 40 + 300 * (sc_plot['EMIS'] - smin) / (smax - smin)
# draw a soft halo (larger, very transparent) first, then the bubble body, to give
# a translucent, 3-D volumetric feel; overlap builds density

for status, colr in [('adequate', '#1a9850'), ('constrained', '#d73027')]:
    sub = sc_plot[sc_plot['water'] == status]
    size_base = np.sqrt(sub['size']) * 3.0
    ax.scatter(sub['BCR'], sub['SER'],
               s=size_base**2,
               c=colr, alpha=0.55,
               linewidths=0.6, edgecolor='white', zorder=3)
ax.axvline(1, color='k', ls=':', lw=0.8)
ax.axhline(1, color='k', ls=':', lw=0.8)
ax.set_xscale('log'); ax.set_yscale('log')
ax.set_xlabel('City biomass co-firing ratio (BCR)', fontsize=16)
ax.set_ylabel('City storage-to-emission ratio (SER)', fontsize=16)
ax.tick_params(labelsize=16)
h1 = plt.Line2D([], [], marker='o', ls='', color='#1a9850', label='WSR adequate')
h2 = plt.Line2D([], [], marker='o', ls='', color='#d73027', label='WSR constrained')
h3 = plt.Line2D([], [], marker='o', ls='', color='gray', markerfacecolor='gray',
                markersize=10, label='low emissions')
h4 = plt.Line2D([], [], marker='o', ls='', color='gray', markerfacecolor='gray',
                markersize=25, label='high emissions')
ax.legend(handles=[h1, h2, h4, h3], fontsize=16, ncol=4, frameon=True,
          loc='lower center', bbox_to_anchor=(0.5, -0.3))
panel_label(ax, 'a', fontsize=22)

# ---- (b) 8-class face map ----
ax_b = fig.add_subplot(gs[1, 0])
ax = ax_b
base = gdf.copy()
base['cls_fill'] = base['class8'].fillna(-1).astype(int)
colors_lut = {-1: '#e0e0e0'}
for k, v in cls_colors.items():
    colors_lut[k] = v
base['color'] = base['cls_fill'].map(colors_lut)
base.plot(color=base['color'], ax=ax, edgecolor='white', linewidth=0.3)
ax.set_xlim(73, 136); ax.set_ylim(17, 54)
ax.set_aspect('auto'); ax.set_position(ax.get_position())
ax.set_xlabel('Longitude (°E)', fontsize=16); ax.set_ylabel('Latitude (°N)', fontsize=16)
ax.tick_params(labelsize=16)
patches = [Patch(facecolor=cls_colors[k], label=f'{k}: {cls_labels[k]}')
           for k in sorted(cls_colors)]
patches.append(Patch(facecolor='#e0e0e0', label='no data'))
# two-row legend (9 items -> ncol 5); shared by panel (b); centred on the figure
legend_below(ax, fig, patches, ncol=5, fontsize=16, below=0.03, center_x=0.5)
def _scs8(iax):
    base.plot(color=base['color'], ax=iax, edgecolor='white', linewidth=0.2)
add_scs_inset(fig, ax, bd=bd, plot_layer=_scs8)
panel_label(ax, 'b', fontsize=22)

# ---- (c) stacked-share bars: 8 classes (columns = Cities/Capacity/Emissions/GDP) ----
ax_c = fig.add_subplot(gs[1, 1])
ax = ax_c
cats = ['Cities', 'Capacity', 'Emissions', 'GDP']
# rows are classes 1..8, columns are n_pct / GW_pct / emis_pct / GDP_pct
share8 = s8[['n_pct', 'GW_pct', 'emis_pct', 'GDP_pct']].loc[1:8]
x = np.arange(len(cats))
bottoms = np.zeros(len(cats))
seg_bottom = {ci: np.zeros(len(cats)) for ci in range(1, 9)}
for ci in range(1, 9):
    vals = share8.loc[ci].values
    ax.bar(x, vals, bottom=bottoms, width=0.55, color=cls_colors[ci],
           label=f'{ci}: {cls_labels[ci]}')
    seg_bottom[ci] = bottoms.copy()
    bottoms = bottoms + vals
# annotate the largest segment value on each column (white label on that segment)
for xi in x:
    col_vals = share8.iloc[:, xi]
    ci_max = col_vals.idxmax()
    vmax = col_vals.loc[ci_max]
    yc = seg_bottom[ci_max][xi] + vmax / 2.0
    ax.text(x[xi], yc, f'{vmax:.0f}%', ha='center', va='center',
            fontsize=13, color='white')
ax.set_xticks(x); ax.set_xticklabels(cats, fontsize=16)
ax.set_ylabel('Share [%]', fontsize=16)
ax.tick_params(labelsize=16)
ax.set_ylim(0, 100)
# no legend: colours match panel (b)'s shared legend
panel_label(ax, 'c', fontsize=22)

# ---- (d) MI face map ----
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm as _TSN
ax_d = fig.add_subplot(gs[2, 0])
ax = ax_d
vmax = max(abs(gdf['MI'].dropna().quantile(0.98)),
           abs(gdf['MI'].dropna().quantile(0.02)), 0.5)
norm_mi = _TSN(vmin=-vmax, vcenter=0, vmax=vmax)
# diverging colormap: -1 green (#70ceaa), 0 white, +1 red (#d06e69)
cmap_mi = LinearSegmentedColormap.from_list('mi', ['#70ceaa', '#ffffff', '#d06e69'])
gdf.plot(column='MI', ax=ax, cmap=cmap_mi, norm=norm_mi,
         edgecolor='white', linewidth=0.3, missing_kwds={'color': '#dddddd'})
ax.set_xlim(73, 136); ax.set_ylim(17, 54)
ax.set_aspect('auto'); ax.set_position(ax.get_position())
ax.set_xlabel('Longitude (°E)', fontsize=16); ax.set_ylabel('Latitude (°N)', fontsize=16)
ax.tick_params(labelsize=16)
_sm = plt.cm.ScalarMappable(norm=norm_mi, cmap=cmap_mi)
_pos = ax.get_position()
_cb_w = _pos.width * 0.35; _cb_h = 0.015
_cb_x = _pos.x0 + (_pos.width - _cb_w) * 0.95 / 2.0
_cb_y = _pos.y0 + 0.21
cax = fig.add_axes([_cb_x, _cb_y, _cb_w, _cb_h])
cbar = fig.colorbar(_sm, cax=cax, orientation='horizontal')
cbar.ax.xaxis.set_label_position('top')   # label above the colorbar
cbar.ax.xaxis.set_ticks_position('bottom')  # keep tick labels below the bar
cbar.set_label('Responsibility–capacity mismatch (%)', fontsize=16, labelpad=8)
cbar.ax.tick_params(labelsize=16)
def _scs_mi(iax):
    gdf.plot(column='MI', ax=iax, cmap=cmap_mi, norm=norm_mi,
             edgecolor='white', linewidth=0.2, missing_kwds={'color': '#dddddd'})
add_scs_inset(fig, ax, bd=bd, plot_layer=_scs_mi)
panel_label(ax, 'd', fontsize=22)

# ---- (e) stacked-share bars: burden vs surplus (columns = Cities/Capacity/Emissions/GDP) ----
ax_e = fig.add_subplot(gs[2, 1])
ax = ax_e
cats = ['Cities', 'Capacity', 'Emissions', 'GDP']
burden = [sm.loc['burden', 'n_pct'], sm.loc['burden', 'GW_pct'],
          sm.loc['burden', 'emis_pct'], sm.loc['burden', 'GDP_pct']]
surplus = [sm.loc['surplus', 'n_pct'], sm.loc['surplus', 'GW_pct'],
           sm.loc['surplus', 'emis_pct'], sm.loc['surplus', 'GDP_pct']]
x = np.arange(len(cats))
ax.bar(x, burden, width=0.5, color='#d06e69', label='Burden-carrier (MI>0)')
ax.bar(x, surplus, bottom=burden, width=0.5, color='#70ceaa', label='Capacity-surplus (MI<0)')
for xi, b, sp in zip(x, burden, surplus):
    ax.text(xi, b / 2, f'{b:.0f}%', ha='center', va='center', fontsize=14, color='white')
    ax.text(xi, b + sp / 2, f'{sp:.0f}%', ha='center', va='center', fontsize=14, color='white')
ax.set_xticks(x); ax.set_xticklabels(cats, fontsize=16)
ax.set_ylabel('Share [%]', fontsize=16)
ax.tick_params(labelsize=16)
ax.set_ylim(0, 100)
ax.legend(fontsize=13, loc='lower right')
panel_label(ax, 'e', fontsize=22)

save(fig, OUT)
print('saved', OUT + '.png/.pdf/.xlsx')
print('  8class:')
print(s8[['n', 'n_pct', 'GW', 'GW_pct', 'emis_pct']].round(1).to_string())
print('  mismatch:')
print(sm[['n', 'n_pct', 'GW', 'GW_pct', 'emis_pct']].round(1).to_string())
