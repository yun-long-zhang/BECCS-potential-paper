# -*- coding: utf-8 -*-
"""Fig 3.3: Water resource endowment - CITY-LEVEL total-pressure WSR.

WSR_city = (W_coal_city + U_comp_city + EFR*R_city) / R_city
EFR scenarios: 20% / 50% (baseline) / 80%.
Five-panel combo (Fig 3.3 + Fig S3, one duplicate panel removed):
  Row 1: (a) prefecture face-fill WSR map (EFR50), (b) provincial WSR>1 share.
  Row 2: (c) city WSR ranked band (EFR 20-80%), (d) scenario share bars,
         (e) step-line WSR distribution (EFR 20/50/80).
Outputs PNG, PDF, XLSX."""
import os
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import _style
import geopandas as gpd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.cm import ScalarMappable

HERE = os.path.dirname(os.path.abspath(__file__))
SHAPE = os.path.join(HERE, 'china_maps', 'prefecture_boundaries.shp')
BOUNDARY_SHP = os.path.join(HERE, 'china_maps', 'national_boundary.shp')
SCS_EXTENT = (105, 125, 3, 25)  # lon_min, lon_max, lat_min, lat_max


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


def add_scs_inset(fig, ax, bd=None, plot_layer=None,
                  frame_color='#555555', frame_lw=0.8):
    """South China Sea (九段线) inset box at the lower-right of a map axes."""
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


SRC = os.path.join(HERE, 'plant level analysis data.xlsx')
OUT_DIR = os.environ.get('BECCS_OUT_DIR', HERE)
AGG = os.path.join(OUT_DIR, 'plant_city_hswud_aggregated.xlsx')
OUT = os.path.join(OUT_DIR, 'Fig3_3_water')

# city-level data (304 prefectures)
c = pd.read_excel(AGG, sheet_name='city_level')
for col in ['市级WSR_EFR20', '市级WSR_EFR50', '市级WSR_EFR80']:
    c[col] = pd.to_numeric(c[col], errors='coerce')

# join city lon/lat (use plant coordinates averaged per city)
p = pd.read_excel(SRC, sheet_name=os.environ.get('BECCS_SHEET', '市域内比较'))
p = p[p['序号'].notna()].copy()
p['经度'] = pd.to_numeric(p['经度'], errors='coerce')
p['纬度'] = pd.to_numeric(p['纬度'], errors='coerce')
city_ll = p.groupby('所在城市')[['经度', '纬度']].mean().reset_index()
# map the city name onto the aggregation's prefecture name (they match by
# original name)
c = c.merge(city_ll, left_on='地级市', right_on='所在城市', how='left')

c['prov'] = c['省份英文'].astype(str)
c = c.dropna(subset=['市级WSR_EFR20', '市级WSR_EFR50', '市级WSR_EFR80'])

scen = {'EFR 20%': c['市级WSR_EFR20'],
        'EFR 50%': c['市级WSR_EFR50'],
        'EFR 80%': c['市级WSR_EFR80']}
share = {k: 100 * (v > 1).mean() for k, v in scen.items()}
med = {k: v.median() for k, v in scen.items()}

# ---- export ----
with pd.ExcelWriter(OUT + '.xlsx') as xw:
    df_a = c[['经度', '纬度', '市级WSR_EFR20', '市级WSR_EFR50', '市级WSR_EFR80']].rename(
        columns={'经度': 'longitude', '纬度': 'latitude',
                 '市级WSR_EFR20': 'WSR_EFR20', '市级WSR_EFR50': 'WSR_EFR50',
                 '市级WSR_EFR80': 'WSR_EFR80'})
    df_a.to_excel(xw, sheet_name='a', index=False)

    prov = c.groupby('prov').agg(
        share_20=('市级WSR_EFR20', lambda s: 100 * (s > 1).mean()),
        share_50=('市级WSR_EFR50', lambda s: 100 * (s > 1).mean()),
        share_80=('市级WSR_EFR80', lambda s: 100 * (s > 1).mean()),
    ).reset_index().sort_values('share_50', ascending=False)
    prov.to_excel(xw, sheet_name='b', index=False)

    wsr = c['市级WSR_EFR50'].dropna()
    counts, edges = np.histogram(wsr, bins=40)
    df_c = pd.DataFrame({'bin_low': edges[:-1], 'bin_high': edges[1:],
                         'count': counts})
    df_c.to_excel(xw, sheet_name='c', index=False)
    # panel c step-line data + tail
    bins_c = np.linspace(0, 4, 40)
    centres = (bins_c[:-1] + bins_c[1:]) / 2.0
    step_df = pd.DataFrame({'bin_centre': centres})
    for k, col in [('EFR 20%', '市级WSR_EFR20'), ('EFR 50%', '市级WSR_EFR50'), ('EFR 80%', '市级WSR_EFR80')]:
        counts_c, _ = np.histogram(c[col].dropna(), bins=bins_c)
        step_df[k] = counts_c
    step_df.to_excel(xw, sheet_name='c_step', index=False)
    tail_df = pd.DataFrame({'EFR情景': ['EFR 20%', 'EFR 50%', 'EFR 80%'],
                            'WSR>4城市数': [int((c[col] > 4).sum()) for col in ['市级WSR_EFR20', '市级WSR_EFR50', '市级WSR_EFR80']],
                            'WSR>4占比_%': [100 * (c[col] > 4).mean() for col in ['市级WSR_EFR20', '市级WSR_EFR50', '市级WSR_EFR80']]})
    tail_df.to_excel(xw, sheet_name='c_tail', index=False)
    pd.DataFrame({'EFR情景': list(scen.keys()),
                  'WSR>1占比_%': list(share.values()),
                  '中位数': list(med.values())}).to_excel(
        xw, sheet_name='summary', index=False)

# ---- prefecture face-fill data prep (match city WSR to prefecture polygons) ----
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

gdf = load_prefectures()
sh_norm = {norm(city): city for city in gdf['CITY']}


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


c['shape_city'] = c['地级市'].map(map_city_to_shape)
matched = c.dropna(subset=['shape_city'])
print(f'WSR matched: {len(matched)}/{len(c)}')
wsr_lookup = dict(zip(matched['shape_city'], matched['市级WSR_EFR50']))
gdf['WSR'] = gdf['CITY'].map(wsr_lookup)

# ---- figure: 5-panel combo (Fig 3.3 row1 + Fig S3 row2) ----
# row 1: (a) map + (b) province bars (full width)
# row 2: (c)(d)(e) three SI panels, uniformly narrowed & centered
fig = plt.figure(figsize=(18, 13))
gs_top = fig.add_gridspec(1, 2, width_ratios=[2.2, 1.0], wspace=0.10,
                          left=0.06, right=0.98, top=0.96, bottom=0.50)
gs_bot = fig.add_gridspec(1, 3, wspace=0.20,
                          left=0.135, right=0.98, top=0.42, bottom=0.06)

# ---- (a) prefecture face-fill WSR map (col 0, top) ----
ax = fig.add_subplot(gs_top[0, 0])
# diverging colormap centered at WSR=1 (1=white, >1 bluer, <1 pinker)
cmap_pwb = LinearSegmentedColormap.from_list('pwb', ['#4575b4', '#ffffff', '#d73027'])
vmax = min(4, float(np.nanquantile(gdf['WSR'].dropna(), 0.98)))
norm_pwb = TwoSlopeNorm(vmin=0.0, vcenter=1.0, vmax=vmax)
# prefecture face-fill of WSR (like the mismatch map)
gdf.plot(column='WSR', ax=ax, cmap=cmap_pwb, norm=norm_pwb,
         edgecolor="#c8c3c3", linewidth=0.3, missing_kwds={'color': '#dddddd'})
ax.set_xlim(73, 136); ax.set_ylim(17, 54)
ax.set_aspect(1.0 / np.cos(np.radians(35)))
ax.set_xlabel('Longitude (°E)', fontsize=16); ax.set_ylabel('Latitude (°N)', fontsize=16)
ax.tick_params(labelsize=16)
_style.panel_label(ax, 'a', fontsize=22)
# compact horizontal colorbar inside the top-left of panel a
cb_ax = ax.inset_axes([0.08, 0.93, 0.42, 0.035])
cb = fig.colorbar(ScalarMappable(norm=norm_pwb, cmap=cmap_pwb),
                  cax=cb_ax, orientation='horizontal')
cb.set_label('City water-supply ratio (EFR 50%)', fontsize=16)
cb.ax.tick_params(labelsize=16)
# South China Sea inset at bottom-right
_bd = load_boundaries()
def _scs_layer(iax):
    gdf.plot(column='WSR', ax=iax, cmap=cmap_pwb, norm=norm_pwb,
             edgecolor='#c8c3c3', linewidth=0.2, missing_kwds={'color': '#dddddd'})
add_scs_inset(fig, ax, bd=_bd, plot_layer=_scs_layer)

# ---- (b) provincial WSR>1 share (col 1, top) ----
ax = fig.add_subplot(gs_top[0, 1])
# two-colour bars around the WSR>1 dividing line (50%): pink above, blue below
colors_b = ['#d73027' if v > 50 else '#4575b4' for v in prov['share_50']]
ax.barh(prov['prov'], prov['share_50'], color=colors_b, alpha=0.5, label='EFR 50%')
ax.axvline(50, color='k', ls=':', lw=0.8)
ax.set_xlabel('Water-constrained cities (WSR > 1) [%]', fontsize=16)
ax.tick_params(labelsize=16)
# tighten the province (y) axis: no extra blank space above Chongqing / below Tianjin
ax.set_ylim(-0.5, len(prov) - 0.5)
_style.panel_label(ax, 'b', fontsize=22)

# ---- (c) city WSR ranked band (S3-a) ----
ax = fig.add_subplot(gs_bot[0, 0])
w50 = scen['EFR 50%'].sort_values()
order = np.arange(len(w50))
lo = scen['EFR 20%'].sort_values().values
hi = scen['EFR 80%'].sort_values().values
ax.fill_between(order, lo, hi, color='#74add1', alpha=0.35, label='EFR 20–80%')
ax.plot(order, w50.values, color='#fdae61', lw=3.0, label='EFR 50%')
ax.axhline(1, color='k', ls='--', lw=0.8)
ax.set_xlabel('City rank', fontsize=16)
ax.set_ylabel('City-level WSR', fontsize=16)
ax.set_ylim(0, 3)
ax.tick_params(labelsize=16)
ax.legend(fontsize=16)
_style.panel_label(ax, 'c', fontsize=22)

# ---- (d) scenario share bars (S3-b) ----
ax = fig.add_subplot(gs_bot[0, 1])
colors_s = ['#74add1', '#fdae61', '#91e3a4']
bars = ax.bar(list(share.keys()), list(share.values()), color=colors_s, alpha=0.9)
ax.axhline(100, color='k', lw=0.6)
for b_, v_ in zip(bars, share.values()):
    ax.text(b_.get_x() + b_.get_width() / 2, v_ + 1, f'{v_:.1f}%',
            ha='center', fontsize=16)
ax.set_ylabel('Cities with WSR > 1 [%]', fontsize=16)
ax.set_ylim(0, 100)
ax.tick_params(labelsize=16)
_style.panel_label(ax, 'd', fontsize=22)

# ---- (e) step-line WSR distribution (S3-c) ----
ax = fig.add_subplot(gs_bot[0, 2])
bins = np.arange(0, 4.05, 0.25)
for k, color in [('EFR 20%', '#74add1'), ('EFR 50%', '#fdae61'), ('EFR 80%', '#91e3a4')]:
    counts, _ = np.histogram(scen[k], bins=bins)
    centres = (bins[:-1] + bins[1:]) / 2.0
    xs = np.concatenate([centres, [centres[-1] + (centres[-1] - centres[0])]])
    ys = np.concatenate([counts, [counts[-1]]])
    lw = 4.0 if k == 'EFR 50%' else 1.5  # baseline scenario emphasized
    ax.step(xs, ys, where='post', color=color, lw=lw, label=k)
ax.axvline(1, color='k', ls='--', lw=0.8)
ax.set_xlabel('City-level WSR', fontsize=16)
ax.set_ylabel('Number of cities', fontsize=16)
ax.set_xlim(0, 4)
n_tail = int((scen['EFR 50%'] > 4).sum())
pct_tail = 100 * (scen['EFR 50%'] > 4).mean()
ax.text(0.98, 0.95, f'{n_tail} cities ({pct_tail:.1f}%) with\nWSR > 4 not shown',
        transform=ax.transAxes, ha='right', va='top', fontsize=16, color='#555555')
ax.tick_params(labelsize=16)
ax.legend(fontsize=16)
_style.panel_label(ax, 'e', fontsize=22)

_style.save(fig, OUT)
print('saved', OUT + '.png/.pdf/.xlsx')
for k in scen:
    print(f'  {k}: share={share[k]:.1f}%, median={med[k]:.3f}')
