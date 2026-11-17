# -*- coding: utf-8 -*-
"""Supplementary figure: resource flows under full coordination (S4).

Three maps, one per commodity (biomass, captured CO2, freshwater), for the
unrestricted S4 solution.  City fill = net physical inflow of that commodity
(imports - exports, Mt yr-1; orange = net exporter, purple = net importer);
arrows = individual city-to-city links, coloured by the commodity and
saturated in proportion to the amount moved.  Links shorter than 800 km are
drawn; the number of longer links omitted is printed and written to the xlsx.

Inputs : $BECCS_OUT_DIR/BECCS_coordination_result.xlsx (sheets 'city',
         'S4_biomass+co2+water'), plant workbook (city centroids).
Outputs: $BECCS_OUT_DIR/FigS_s4_flows.png/.pdf/.xlsx
"""
import os
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.cm import ScalarMappable

import _cols
import _style

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get('BECCS_OUT_DIR', HERE)
RES = os.path.join(OUT_DIR, 'BECCS_coordination_result.xlsx')
OUT = os.path.join(OUT_DIR, 'FigS_s4_flows')
SHAPE = os.path.join(HERE, 'china_maps', 'prefecture_boundaries.shp')
BOUNDARY_SHP = os.path.join(HERE, 'china_maps', 'national_boundary.shp')
SCS_EXTENT = (105, 125, 3, 25)
SCEN = 'S4_biomass+co2+water'
MAX_KM = 800.0
COMM = {
    'biomass': ('Biomass', _style.C_BIO, '#BFE6DA', 'Mt biomass yr$^{-1}$'),
    'co2': ('Captured CO$_2$', _style.C_CO2, '#F3CDB3', 'Mt CO$_2$ yr$^{-1}$'),
    'water': ('Freshwater', _style.C_WAT, '#BFD9EC', 'Mt water yr$^{-1}$'),
}

# ---- data ----
res = pd.read_excel(RES, sheet_name='city')
fl = pd.read_excel(RES, sheet_name=SCEN)
if 'phys_Mt' not in fl.columns:
    raise ValueError('flow table lacks phys_Mt (v2 results required)')
plants = _cols.read_plants(os.path.join(HERE, 'plant level analysis data.xlsx'))
plants['city'] = plants['所在城市'].astype(str)
ll = plants.groupby('city')[['经度', '纬度']].mean()
xy = {c: (r['经度'], r['纬度']) for c, r in ll.iterrows()}

gdf = _style.read_map(SHAPE, encoding='utf-8')
if gdf.crs is not None and not gdf.crs.is_geographic:
    gdf = gdf.to_crs(epsg=4326)
bd = _style.read_map(BOUNDARY_SHP, encoding='utf-8')
if bd.crs is not None and not bd.crs.is_geographic:
    bd = bd.to_crs(epsg=4326)


def norm(s):
    s = re.sub(r'[（(].*?[)）]', '', str(s).strip())
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


def to_shape(name):
    hit = sh_norm.get(norm(name))
    if hit is not None:
        return hit
    target = MANUAL.get(name)
    if target:
        for s, sn in zip(gdf['CITY'], gdf['CITY'].map(norm)):
            if target in sn:
                return s
    return None


def fill_from(series):
    lut = {}
    for city, v in series.items():
        sc = to_shape(city)
        if sc is not None:
            lut[sc] = lut.get(sc, 0.0) + float(v)
    return gdf['CITY'].map(lut)


def net_inflow(sub):
    imp = sub.groupby('to')['phys_Mt'].sum()
    exp = sub.groupby('from')['phys_Mt'].sum()
    idx = imp.index.union(exp.index)
    return imp.reindex(idx, fill_value=0.0) - exp.reindex(idx, fill_value=0.0)


fig, axes = plt.subplots(3, 1, figsize=(11, 25))
fig.subplots_adjust(hspace=0.10, left=0.02, right=0.98, top=0.98, bottom=0.01)
rows = []
for ax, (comm, (label, base, light, unit)) in zip(axes, COMM.items()):
    sub = fl[fl['commodity'] == comm]
    net = net_inflow(sub)
    gdf['v'] = fill_from(net)
    lim = float(max(net.abs().max(), 1e-9))
    nrm = TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim)
    cm = LinearSegmentedColormap.from_list('div', ['#B35806', '#F7F7F7', '#542788'])
    gdf.plot(column='v', ax=ax, cmap=cm, norm=nrm, edgecolor='#c3bebe',
             linewidth=0.2, missing_kwds={'color': '#e8e8e8'})
    ax.set_xlim(73, 136); ax.set_ylim(17, 54)
    ax.set_aspect(1.0 / np.cos(np.radians(35)))
    ax.set_xticks([]); ax.set_yticks([])

    arrow = LinearSegmentedColormap.from_list('a', [light, base])
    mx = sub['phys_Mt'].max()
    n_far = 0
    for _, r in sub.sort_values('phys_Mt').iterrows():
        if r['from'] not in xy or r['to'] not in xy:
            continue
        if r['km'] > MAX_KM:
            n_far += 1
            continue
        frac = r['phys_Mt'] / mx
        ax.annotate('', xy=xy[r['to']], xytext=xy[r['from']],
                    arrowprops=dict(arrowstyle='-|>', color=arrow(0.2 + 0.8 * frac),
                                    lw=0.6 + 1.6 * frac, mutation_scale=7,
                                    connectionstyle='arc3,rad=0.18',
                                    shrinkA=2, shrinkB=2), zorder=4)
    tot = sub['phys_Mt'].sum()
    mean_km = (sub['km'] * sub['phys_Mt']).sum() / tot if tot > 0 else 0.0
    ax.set_title('%s: %.0f %s, %d links, mass-weighted mean %.0f km'
                 % (label, tot, unit.replace(' yr$^{-1}$', ' yr$^{-1}$'),
                    len(sub), mean_km), fontsize=15, pad=6)
    _style.panel_label(ax, 'abc'[len(rows)], fontsize=22)

    cax = ax.inset_axes([0.30, 0.90, 0.40, 0.025])
    cb = fig.colorbar(ScalarMappable(norm=nrm, cmap=cm), cax=cax, orientation='horizontal')
    cb.set_ticks([-lim, 0, lim]); cb.set_ticklabels(['%.0f' % -lim, '0', '%.0f' % lim])
    cb.ax.tick_params(labelsize=13, length=2, pad=1)
    cax.set_title('net inflow (%s)' % unit, fontsize=13, pad=4)

    iax = ax.inset_axes([0.80, 0.02, 0.20, 0.26])
    gdf.plot(column='v', ax=iax, cmap=cm, norm=nrm, edgecolor='#c3bebe',
             linewidth=0.1, missing_kwds={'color': '#e8e8e8'})
    xmin, xmax, ymin, ymax = SCS_EXTENT
    bd.cx[xmin:xmax, ymin:ymax].plot(ax=iax, color='#555555', linewidth=0.6)
    iax.set_xlim(xmin, xmax); iax.set_ylim(ymin, ymax)
    iax.set_xticks([]); iax.set_yticks([])
    rows.append({'commodity': comm, 'mass_Mt_yr': tot, 'links': len(sub),
                 'mean_km_mass_weighted': mean_km,
                 'links_over_%dkm_not_drawn' % MAX_KM: n_far,
                 'net_inflow_range_Mt_yr': lim})
    print('%-8s %.0f Mt, %d links, mean %.0f km, %d links > %.0f km not drawn'
          % (comm, tot, len(sub), mean_km, n_far, MAX_KM))

_style.save(fig, OUT)
with pd.ExcelWriter(OUT + '.xlsx') as xw:
    pd.DataFrame(rows).to_excel(xw, sheet_name='summary', index=False)
    fl.to_excel(xw, sheet_name='S4_links', index=False)
print('saved', OUT + '.png/.pdf/.xlsx')
