# -*- coding: utf-8 -*-
"""Fig 3.7: BECCS deployment potential under the three resource constraints.

Four-panel prefecture face-fill maps (2x2):
  (a) Storage-constrained potential  (Mt CO2/yr)
  (b) Water-constrained potential    (Mt CO2/yr)
  (c) Biomass-constrained potential  (Mt CO2/yr)
  (d) Final BECCS potential = min of (a)(b)(c)  (Mt CO2/yr)

All panels show the annual CO2 that could be stored under each resource limit
computed at the plant level and aggregated to cities (see
4_compute_beccs_potential.py). Each panel uses its own colour scale because the
magnitudes differ by orders of magnitude. A shared colourbar annotation states
the unit (Mt CO2/yr). South China Sea inset on each map.

Outputs PNG, PDF, XLSX."""
import os
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import geopandas as gpd
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from matplotlib.cm import ScalarMappable
import _style

HERE = os.path.dirname(os.path.abspath(__file__))
SHAPE = os.path.join(HERE, 'china_maps', 'prefecture_boundaries.shp')
BOUNDARY_SHP = os.path.join(HERE, 'china_maps', 'national_boundary.shp')
SCS_EXTENT = (105, 125, 3, 25)
OUT_DIR = os.environ.get('BECCS_OUT_DIR', HERE)
POT = os.path.join(OUT_DIR, 'BECCS_potential_city.xlsx')
OUT = os.path.join(OUT_DIR, 'Fig3_7_potential')


def load_boundaries():
    bd = gpd.read_file(BOUNDARY_SHP, encoding='utf-8')
    if bd.crs is not None and not bd.crs.is_geographic:
        bd = bd.to_crs(epsg=4326)
    return bd


def add_scs_inset(fig, ax, bd=None, plot_layer=None):
    if bd is None:
        bd = load_boundaries()
    xmin, xmax, ymin, ymax = SCS_EXTENT
    iax = ax.inset_axes([0.78, 0.02, 0.24, 0.28])
    if plot_layer is not None:
        plot_layer(iax)
    bd_scs = bd.cx[xmin:xmax, ymin:ymax]
    bd_scs.plot(ax=iax, color='#555555', linewidth=0.6)
    iax.set_xlim(xmin, xmax)
    iax.set_ylim(ymin, ymax)
    for spine in iax.spines.values():
        spine.set_visible(True); spine.set_color('#333333'); spine.set_linewidth(0.8)
    iax.set_xticks([]); iax.set_yticks([]); iax.tick_params(length=0)
    return iax


# ---- load potential + shape ----
# Use the CITY-COORDINATED sheet: all three ceilings are evaluated at the city
# scale and combined there, so the resources of a city are shared among its
# plants.  The 'city_potential' sheet instead combines each plant's ceilings
# independently and then sums, which under-counts (min of sums < sum of mins);
# that variant is NOT the paper basis and would disagree with Fig. 3.7b.
pot = pd.read_excel(POT, sheet_name='city_coordinated')
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
sh_norm = {norm(cc): cc for cc in gdf['CITY']}


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


pot['shape_city'] = pot['city'].map(map_city_to_shape)
matched = pot.dropna(subset=['shape_city'])
print(f'matched: {len(matched)}/{len(pot)}')

panels = [
    ('sto_Mt_yr', 'a', 'BECCS potential with storage bound', '#7b3294'),
    ('wat_Mt_yr', 'b', 'BECCS potential with water limit', '#d7191c'),
    ('bio_Mt_yr', 'c', 'BECCS potential with biomass ceiling', '#8a8a8a'),
    ('BECCS_Mt_yr', 'd', 'Final BECCS potential', '#40b948'),
]
# per-panel colour scale: white -> panel colour
cmaps = {col: LinearSegmentedColormap.from_list(f'pot_{col}', ['#ffffff', clr])
         for col, _, _, clr in panels}

# ---- export xlsx ----
with pd.ExcelWriter(OUT + '.xlsx') as xw:
    pot[['city', 'GW', 'sto_Mt_yr', 'wat_Mt_yr', 'bio_Mt_yr',
         'BECCS_Mt_yr', 'limiting']].to_excel(xw, sheet_name='city_coordinated', index=False)

# ---- figure 2x2 ----
fig = plt.figure(figsize=(19, 14))
gs = fig.add_gridspec(2, 2, wspace=0.15, hspace=0.12,
                      left=0.05, right=0.93, top=0.96, bottom=0.06)
bd = load_boundaries()

for (col, tag, title, clr), ax in zip(panels, [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]),
                                               fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])]):
    vals = pd.to_numeric(pot[col], errors='coerce')
    lookup = dict(zip(matched['shape_city'], matched[col]))
    gdf['v'] = gdf['CITY'].map(lookup)
    vmax = float(vals.quantile(0.97))
    use_cmap = cmaps[col]
    vmin = 0.0
    gdf.plot(column='v', ax=ax, cmap=use_cmap, vmin=vmin, vmax=vmax,
             edgecolor='#c3bebe', linewidth=0.2, missing_kwds={'color': '#e0e0e0'})
    ax.set_xlim(73, 136); ax.set_ylim(17, 54)
    ax.set_aspect('auto'); ax.set_position(ax.get_position())
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(title, fontsize=16, pad=6)
    _style.panel_label(ax, tag, fontsize=16)

    def _layer(iax, col=col, use_cmap=use_cmap, vmax=vmax, lookup=lookup):
        gg = gdf.copy()
        gg['v'] = gg['CITY'].map(lookup)
        gg.plot(column='v', ax=iax, cmap=use_cmap, vmin=vmin, vmax=vmax,
                edgecolor='#c3bebe', linewidth=0.1, missing_kwds={'color': '#e0e0e0'})
    add_scs_inset(fig, ax, bd=bd, plot_layer=_layer)

    # horizontal colour bar in the top-left of each panel
    pos = ax.get_position()
    cax = fig.add_axes([pos.x0 + 0.02, pos.y1 - 0.018, 0.16, 0.012])
    sm = ScalarMappable(norm=plt.Normalize(vmin, vmax), cmap=use_cmap)
    cb = fig.colorbar(sm, cax=cax, orientation='horizontal')
    cb.set_label('Mt CO$_2$ yr$^{-1}$', fontsize=16)
    cb.ax.tick_params(labelsize=16)

_style.save(fig, OUT)
print('saved', OUT + '.png/.pdf/.xlsx')
print('  national final potential: %.0f Mt/yr' % pot['BECCS_Mt_yr'].sum())

# ===================== Fig 3.7b: waterfall + bottleneck statistics =====================
# A companion statistical figure to the Fig 3.7 maps: a waterfall that
# decomposes the national BECCS potential from the biomass ceiling through the
# water- and storage-bound cities down to S0, next to a grouped bar chart of the
# bottleneck composition (cities / capacity / potential cut) per limiting
# resource. Outputs to its own basename, leaving Fig 3.7 untouched.
import pandas as _pd
import matplotlib.pyplot as _plt

OUT_B = os.path.join(OUT_DIR, 'Fig3_7b_waterfall_stats')
cc = _pd.read_excel(POT, sheet_name='city_coordinated')
cc['lim'] = cc[['sto_Mt_yr', 'wat_Mt_yr', 'bio_Mt_yr']].idxmin(axis=1)
cc['cut'] = cc['bio_Mt_yr'] - cc['BECCS_Mt_yr']

# ---- GDP dimension (matched to city) for the potential-vs-GDP panel ----
def _ng(s):
    s = str(s).strip()
    s = re.sub(r'[（(].*?[)）]', '', s)
    for suf in ('自治州', '自治县', '自治旗', '地区', '盟', '林区', '市', '县', '区', '旗'):
        s = re.sub(suf + '$', '', s)
    return s
_GDP_MAN = {'红河州': '红河', '昌吉州': '昌吉', '巴音郭楞州': '巴音郭楞',
            '伊犁州直属': '伊犁', '博尔塔拉州': '博尔塔拉', '黔东南州': '黔东南',
            '黔南州': '黔南', '黔西南州': '黔西南', '文山州': '文山',
            '海北州': '海北', '海西州': '海西', '延边州': '延边'}
_gdp = _pd.read_excel(os.path.join(HERE, 'GDP data.xlsx'))
_gdp['key'] = _gdp['城市'].map(lambda s: _GDP_MAN.get(str(s), _ng(s)))
_gdpmap = dict(zip(_gdp['key'], _gdp['GDP_亿元']))
cc['GDP'] = cc['city'].map(_ng).map(_gdpmap)   # NaN for missing (Bingtuan cities)

bio0 = cc['bio_Mt_yr'].sum()
wat_cut = cc.loc[cc['lim'] == 'wat_Mt_yr', 'cut'].sum()
sto_cut = cc.loc[cc['lim'] == 'sto_Mt_yr', 'cut'].sum()
final = cc['BECCS_Mt_yr'].sum()
n_wat = int((cc['lim'] == 'wat_Mt_yr').sum())
n_sto = int((cc['lim'] == 'sto_Mt_yr').sum())

figb, (axw, axs) = _plt.subplots(1, 2, figsize=(15, 6.5),
                                 gridspec_kw={'width_ratios': [1.0, 1.0],
                                              'wspace': 0.18})
# ---- waterfall (no coordination bars) ----
steps = [bio0, wat_cut, sto_cut, final]
wcum = [0.0, bio0, bio0 - wat_cut, bio0 - wat_cut - sto_cut]
wbot = [0.0, wcum[2], wcum[3], 0.0]
whei = [bio0, wat_cut, sto_cut, final]
wcol = ["#B95A83", "#5199a5", '#8a8a8a', "#40b948"]
for i, (hb, hh, col) in enumerate(zip(wbot, whei, wcol)):
    axw.bar(i, hh, 0.62, bottom=hb, color=col, alpha=0.9, zorder=3)
for i in range(3):
    xl = i + 0.31; xr = (i + 1) - 0.31
    axw.plot([xl, xr], [wcum[i + 1], wcum[i + 1]], color='#666666', lw=1.1, zorder=2)
wlab = [f'Biomass\nceiling',
        f'Water\nlimit',
        f'Storage\nbound',
        f'self-sufficient\n(S0)']
axw.set_xticks(range(4)); axw.set_xticklabels(wlab, rotation=30, fontsize=16, ha='right')
for i, (hb, hh) in enumerate(zip(wbot, whei)):
    axw.text(i, hb + hh + 12, f'{abs(hh):.0f}', ha='center', va='bottom',
             fontsize=16, fontweight='bold', color=wcol[i])
axw.set_xlabel('Downscaling of BECCS potential under resource constraints', fontsize=16)
axw.set_ylabel('National BECCS potential (Mt CO$_2$ yr$^{-1}$)', fontsize=16)
axw.set_ylim(0, 1200)
axw.tick_params(labelsize=16)
_style.panel_label(axw, 'a', fontsize=20)

# ---- (b) statistical distribution of the final (joint-constrained) BECCS ----
# potential: binned histogram of city potential (log-spaced bins because the
# distribution is strongly right-skewed), stacked by the limiting resource,
# with a cumulative curve of the national total.
lim_col = {'bio_Mt_yr': "#B95A83", 'wat_Mt_yr': "#5199a5", 'sto_Mt_yr': '#8a8a8a'}
bins = [0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0]
bin_lab = ['0', '0–0.1', '0.1–0.5', '0.5–1', '1–2', '2–5', '5–10', '10–20']
# histogram counts per bin per limiting resource
hist = {}
for lk in lim_col:
    hist[lk] = np.histogram(cc.loc[cc['lim'] == lk, 'BECCS_Mt_yr'], bins=bins)[0]
bin_c = 0.5 * (np.array(bins[:-1]) + np.array(bins[1:]))
xr = np.arange(len(bins) - 1)
# stacked bars (bottom-up: biomass, water, storage)
bot = np.zeros(len(xr))
for lk, colr in lim_col.items():
    axs.bar(xr, hist[lk], width=0.7, bottom=bot, color=colr,
            edgecolor='white', lw=0.4, alpha=0.9, label=f'{lk.split("_")[0]}-limited')
    bot = bot + hist[lk]
# cumulative potential curve (right y-axis) — one curve per city rank
pot_bin = np.array([cc.loc[(cc['BECCS_Mt_yr'] >= bins[i]) & (cc['BECCS_Mt_yr'] < bins[i + 1]),
                            'BECCS_Mt_yr'].sum() for i in range(len(bins) - 1)])
cum_bin = np.cumsum(pot_bin)
ax2b = axs.twinx()
ax2b.plot(xr, cum_bin, color='k', lw=2.0, marker='o', ms=4, label='Cumulative potential')
ax2b.set_ylabel('Cumulative potential (Mt CO$_2$ yr$^{-1}$)', fontsize=16)
ax2b.set_ylim(0, cum_bin.max() * 1.25)
ax2b.tick_params(labelsize=16)
ax2b.legend(fontsize=14, loc='center right', bbox_to_anchor=(0.72, 0.70), frameon=False)
# annotations (consistent with the histogram's first bin [0, 0.1))
n_zero = int((cc['BECCS_Mt_yr'] < 0.1).sum())   # matches the first bar
n_city = len(cc)
bio_share = 100 * cc.loc[cc['lim'] == 'bio_Mt_yr', 'BECCS_Mt_yr'].sum() / cc['BECCS_Mt_yr'].sum()
axs.text(0.15, 0.97, f'{n_zero} cities ({(100 * n_zero / n_city):.0f}%) with potential < 0.1 Mt yr$^{{-1}}$\n',
         transform=axs.transAxes, ha='left', va='top', fontsize=13, color='#333333')
# the city counts span more than two orders of magnitude (249 down to 3), so a
# linear axis makes every bar but the first invisible -> use a log scale.  The
# lower bound sits just under the smallest occupied bin so its bar is visible;
# zero-height bars simply do not render.
axs.set_yscale('log')
axs.set_ylim(0.7, 600)
axs.set_xticks(xr); axs.set_xticklabels(bin_lab, fontsize=16, rotation=30, ha='right')
axs.set_xlabel('City BECCS potential (Mt CO$_2$ yr$^{-1}$)', fontsize=16)
axs.set_ylabel('Number of cities', fontsize=16)
axs.tick_params(labelsize=16)
from matplotlib.patches import Patch as _P
axs.legend(handles=[_P(facecolor=lim_col['bio_Mt_yr'], label='Biomass-limited'),
                    _P(facecolor=lim_col['wat_Mt_yr'], label='Water-limited'),
                    _P(facecolor=lim_col['sto_Mt_yr'], label='Storage-limited')],
           fontsize=14, loc='center right', bbox_to_anchor=(0.65, 0.60), frameon=False)
axs.set_title('', fontsize=16)
_style.panel_label(axs, 'b', fontsize=20)

_style.save(figb, OUT_B)
print('saved', OUT_B + '.png/.pdf/.xlsx')
