# -*- coding: utf-8 -*-
"""Fig 3.10: Five-panel combo — BECCS potential summary + transport flows.

Layout (3 rows):
  Row 1 (full width): (a) wide panel — national BECCS potential under local
      self-sufficiency vs. each transport scenario (bar chart with the
      realized potential and transport volumes).
  Row 2: (b) biomass-transport map, (c) CO2-transport map — the transport
      arrows are overlaid on a prefecture fill showing the city's NET FLOW
      (imports - exports, Mt/yr) on a diverging scale: orange = net sender,
      white = 0, blue = net receiver.
  Row 3: (d) the local BECCS potential (S3 partition, no arrows);
         (e) NET EMISSIONS remaining after the fully-coordinated scenario (S4),
      i.e. emissions minus captured BECCS, which can go negative.  The scale is
      diverging green -> white (0) -> brown, so zero sits at the middle.

Every map has a South China Sea inset box.

Data: BECCS_coordination_result.xlsx (city + per-scenario flow sheets) and
      plant level analysis data.xlsx (city emissions).
Outputs: PNG, PDF, XLSX.
"""
import os
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import geopandas as gpd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.cm import ScalarMappable
import _style

HERE = os.path.dirname(os.path.abspath(__file__))
SHAPE = os.path.join(HERE, 'china_maps', 'prefecture_boundaries.shp')
BOUNDARY_SHP = os.path.join(HERE, 'china_maps', 'national_boundary.shp')
SCS_EXTENT = (105, 125, 3, 25)
OUT_DIR = os.environ.get('BECCS_OUT_DIR', HERE)
RES = os.path.join(OUT_DIR, 'BECCS_coordination_result.xlsx')
OUT = os.path.join(OUT_DIR, 'Fig3_10_five_panel')

# ---- commodity style: same hue, saturation encodes flow amount ----
from matplotlib.colors import LinearSegmentedColormap as _LSC
COMM = {
    'biomass': dict(label='biomass', base='#7b3294',
                    cmap=_LSC.from_list('bio', ['#efe1f6', '#7b3294'])),
    'co2':     dict(label='CO$_2$', base='#d7191c',
                    cmap=_LSC.from_list('co2', ['#fcd4d4', '#d7191c'])),
    'water':   dict(label='water', base='#2c7bb6',
                    cmap=_LSC.from_list('wat', ['#cde3f6', '#2c7bb6'])),
}
SCEN = {
    'S1_biomass': ('S1', 'Biomass transport'),
    'S2_co2': ('S2', 'CO$_2$ transport'),
    'S3_biomass+co2': ('S3', 'Biomass + CO$_2$ transport'),
    'S4_biomass+co2+water': ('S4', 'Biomass + CO$_2$ + water transport'),
}


def load_boundaries():
    bd = gpd.read_file(BOUNDARY_SHP, encoding='utf-8')
    if bd.crs is not None and not bd.crs.is_geographic:
        bd = bd.to_crs(epsg=4326)
    return bd


def add_scs_inset(fig, ax, bd=None, plot_layer=None):
    if bd is None:
        bd = load_boundaries()
    xmin, xmax, ymin, ymax = SCS_EXTENT
    iax = ax.inset_axes([0.78, 0.02, 0.22, 0.26])
    if plot_layer is not None:
        plot_layer(iax)
    bd_scs = bd.cx[xmin:xmax, ymin:ymax]
    bd_scs.plot(ax=iax, color='#555555', linewidth=0.6)
    iax.set_xlim(xmin, xmax); iax.set_ylim(ymin, ymax)
    for spine in iax.spines.values():
        spine.set_visible(True); spine.set_color('#333333'); spine.set_linewidth(0.8)
    iax.set_xticks([]); iax.set_yticks([]); iax.tick_params(length=0)
    return iax


# ===================== data =====================
res = pd.read_excel(RES, sheet_name='city')
df = pd.read_excel(os.path.join(HERE, 'plant level analysis data.xlsx'),
                   sheet_name=os.environ.get('BECCS_SHEET', '市域内比较'))
df = df[df['序号'].notna()].copy()
df['city'] = df['所在城市'].astype(str)
ll = df.groupby('city')[['经度', '纬度']].mean()
res = res.merge(ll, left_on='city', right_index=True, how='left')

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


res['shape_city'] = res['city'].map(map_city_to_shape)
matched = res.dropna(subset=['shape_city'])
print('matched:', len(matched), '/', len(res))
lookup = dict(zip(matched['shape_city'], matched['S0_local_Mt_yr']))
gdf['base'] = gdf['CITY'].map(lookup)

cmap = LinearSegmentedColormap.from_list('pot', ["#ffffff", "#40b948"])
vmax = float(res['S0_local_Mt_yr'].quantile(0.97))

# flow tables
flows = {}
for s in SCEN:
    flows[s] = pd.read_excel(RES, sheet_name=s)

# ===================== city fills for panels b / c / e =====================
# panel b/c : NET flow through the city = imports - exports (Mt/yr), so a net
#             receiver is blue and a net sender is orange, with 0 at white
# panel e   : net emissions left after the scenario's BECCS capture, which can
#             go negative (the city captures more than it emits)
emis_by_city = df.groupby('city')['年碳排放Mt'].sum()


def flow_net_by_city(flow_df):
    """Net flow into each city: imports - exports (Mt yr-1).

    Positive => the city is a net receiver, negative => a net sender.
    """
    if flow_df is None or flow_df.empty:
        return pd.Series(dtype='float64')
    imp = flow_df.groupby('to')['Mt_yr'].sum()
    exp = flow_df.groupby('from')['Mt_yr'].sum()
    idx = imp.index.union(exp.index)
    return (imp.reindex(idx, fill_value=0.0)
            - exp.reindex(idx, fill_value=0.0))


def net_emissions_by_city(scen_key):
    """Emissions minus the scenario's captured BECCS (Mt CO2 yr-1)."""
    cap = res.set_index('city')[scen_key + '_Mt_yr']
    return emis_by_city - cap.reindex(emis_by_city.index).fillna(0.0)


def build_fill(series):
    """Attach a city-indexed Series onto the prefecture shapes.

    Several cities can share one prefecture polygon (e.g. the Bingtuan cities),
    so contributions are SUMMED rather than overwritten.
    """
    lut = {}
    for city, v in series.items():
        sc = map_city_to_shape(city)
        if sc is None:
            continue
        lut[sc] = lut.get(sc, 0.0) + float(v)
    return gdf['CITY'].map(lut)


def _diverging(vals, neg_col, pos_col):
    """Build a 0-centred three-colour ramp and a symmetric TwoSlopeNorm.

    The limit is symmetric so white lands exactly on 0 and both arms of the
    ramp span the same numeric range.
    """
    s = pd.Series(vals).dropna()
    lim = float(max(abs(s.min()) if len(s) else 1e-9,
                    abs(s.max()) if len(s) else 1e-9, 1e-9))
    cm = LinearSegmentedColormap.from_list(
        'div', [neg_col, '#ffffff', pos_col])
    return cm, TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim), lim


# --- panel b: biomass NET flow (S1) ---
# orange (net sender) -> white (0) -> pink (net receiver)
gdf['f_net_b'] = build_fill(flow_net_by_city(flows['S1_biomass']))
cmap_flow_b, norm_flow_b, lim_b = _diverging(gdf['f_net_b'].values,
                                             '#e08214', '#e7298a')

# --- panel c: CO2 NET flow (S2) ---
# orange (net sender) -> white (0) -> blue (net receiver)
gdf['f_net_c'] = build_fill(flow_net_by_city(flows['S2_co2']))
cmap_flow_c, norm_flow_c, lim_c = _diverging(gdf['f_net_c'].values,
                                             '#e08214', '#2c7bb6')

# --- panel e: net emissions after the fully-coordinated scenario (S4) ---
net_emis = net_emissions_by_city('S4_biomass+co2+water')
gdf['f_net'] = build_fill(net_emis)
_net_vals = pd.Series(gdf['f_net'].dropna().values)
NET_VMIN = float(min(_net_vals.min(), -1e-9))
NET_VMAX = float(max(_net_vals.max(), 1e-9))
net_norm = TwoSlopeNorm(vmin=NET_VMIN, vcenter=0.0, vmax=NET_VMAX)
# yellow (net-negative, captures more than it emits) -> white (0) -> brown
# (residual emissions).  Zero sits at the MIDDLE of the colour ramp.
cmap_net = LinearSegmentedColormap.from_list(
    'netemis', ['#f0e442', '#ffffff', '#8c510a'])

print('panel b  biomass net flow: %.1f .. %.1f Mt/yr' % (-lim_b, lim_b))
print('panel c  CO2 net flow:     %.1f .. %.1f Mt/yr' % (-lim_c, lim_c))
print('面板e 净排放: %.1f .. %.1f Mt/yr | 净负值城市 %d'
      % (NET_VMIN, NET_VMAX, int((_net_vals < 0).sum())))

# ---- export plot data ----
with pd.ExcelWriter(OUT + '.xlsx') as xw:
    res[['city', 'S0_local_Mt_yr', 'S1_biomass_Mt_yr', 'S2_co2_Mt_yr',
         'S3_biomass+co2_Mt_yr', 'S4_biomass+co2+water_Mt_yr', 'W', 'S', 'B', 'G',
         '经度', '纬度']].rename(columns={'经度': 'lon', '纬度': 'lat'}).to_excel(
        xw, sheet_name='city', index=False)
    for s in SCEN:
        flows[s].to_excel(xw, sheet_name=s, index=False)

# ===================== figure =====================
def load_waterfall_data():
    """Decompose the city-coordinated limits into a waterfall:
    biomass ceiling -> -water-bound cities -> -storage-bound cities -> BECCS.
    Returns (steps, labels, colors, n_wat, n_sto)."""
    cc = pd.read_excel(os.path.join(OUT_DIR, 'BECCS_potential_city.xlsx'),
                       sheet_name='city_coordinated')
    cc['lim'] = cc[['sto_Mt_yr', 'wat_Mt_yr', 'bio_Mt_yr']].idxmin(axis=1)
    bio0 = cc['bio_Mt_yr'].sum()
    wat_cut = (cc.loc[cc['lim'] == 'wat_Mt_yr', 'bio_Mt_yr']
               - cc.loc[cc['lim'] == 'wat_Mt_yr', 'wat_Mt_yr']).sum()
    sto_cut = (cc.loc[cc['lim'] == 'sto_Mt_yr', 'bio_Mt_yr']
               - cc.loc[cc['lim'] == 'sto_Mt_yr', 'sto_Mt_yr']).sum()
    final = cc['BECCS_Mt_yr'].sum()
    n_wat = int((cc['lim'] == 'wat_Mt_yr').sum())
    n_sto = int((cc['lim'] == 'sto_Mt_yr').sum())
    steps = [bio0, -wat_cut, -sto_cut, final]
    labels = [f'Biomass\nceiling\n{bio0:.0f}',
              f'Water-bound\ncities ({n_wat})\n\u2212{wat_cut:.0f}',
              f'Storage-bound\ncities ({n_sto})\n\u2212{sto_cut:.0f}',
              f'S0 local\n{final:.0f}']
    colors = ["#B95A83", "#5199a5",
              '#8a8a8a', "#40b948"]
    return steps, labels, colors


bd = load_boundaries()
fig = plt.figure(figsize=(18, 16.5))
# 3 rows: (a) bars | (b, c) maps | (d, e) maps.  Every legend/colourbar lives
# INSIDE its own panel, placed in the blank area of the map:
#   panel a : top-left, two lines
#   panels b-e : colourbar in the upper-middle (see `cb_rect`)
# Because nothing sits between the rows any more, `hspace` can stay tight --
# it only has to clear panel (a)'s tick labels plus row 2's captions.
gs = fig.add_gridspec(3, 2, height_ratios=[1.0, 1.15, 1.15], wspace=0.06,
                      hspace=0.14, left=0.035, right=0.985, top=0.975,
                      bottom=0.025)

# ---------- (a) coordinated-potential bars (S0 .. S4) ----
# The waterfall decomposition now lives in Fig 3.7b; here we keep only the
# coordinated potential bars: S0 (self-sufficient) plus S1..S4 with the
# per-commodity near/far split (same convention as Fig S16): biomass / CO2 /
# water each in its own colour; links within the distance threshold are FILLED,
# longer links are OUTLINE only.
ax = fig.add_subplot(gs[0, :])
vals = [float(res['S0_local_Mt_yr'].sum()),
        float(res['S1_biomass_Mt_yr'].sum()),
        float(res['S2_co2_Mt_yr'].sum()),
        float(res['S3_biomass+co2_Mt_yr'].sum()),
        float(res['S4_biomass+co2+water_Mt_yr'].sum())]
s0 = vals[0]

DIST_TH = {'biomass': 200, 'co2': 250, 'water': 10}
EDGE_LW = 1.2
S0_COL = '#40b948'
COMM_COL = {'biomass': '#7b3294', 'co2': '#d7191c', 'water': '#2c7bb6'}
scen_keys = ['S0_local', 'S1_biomass', 'S2_co2', 'S3_biomass+co2', 'S4_biomass+co2+water']
scen_inc = {
    'S0_local': [],
    'S1_biomass': [('biomass', vals[1] - vals[0])],
    'S2_co2': [('co2', vals[2] - vals[0])],
    'S3_biomass+co2': [('biomass', vals[1] - vals[0]), ('co2', vals[3] - vals[1])],
    'S4_biomass+co2+water': [('biomass', vals[1] - vals[0]), ('co2', vals[3] - vals[1]),
                             ('water', vals[4] - vals[3])],
}


def near_share_of(fl, comm):
    """Fraction of commodity 'comm' tonnage on links within its distance threshold."""
    sub = fl[fl['commodity'] == comm] if (not fl.empty and 'commodity' in fl.columns) else fl.iloc[0:0]
    tot = sub['Mt_yr'].sum()
    if tot <= 0:
        return 0.0
    return sub.loc[sub['km'] <= DIST_TH[comm], 'Mt_yr'].sum() / tot


for i, key in enumerate(scen_keys):
    fl = flows[key] if key != 'S0_local' else flows['S1_biomass']
    # precompute near/far per commodity
    seg = {comm: (inc * near_share_of(fl, comm), inc * (1 - near_share_of(fl, comm)))
           for comm, inc in scen_inc[key]}
    # S0 base (filled green)
    ax.bar(i, s0, 0.62, color=S0_COL, edgecolor=S0_COL,
           linewidth=EDGE_LW, zorder=3)
    # 1) all NEAR segments (filled) stacked directly above S0
    bottom = s0
    for comm, _inc in scen_inc[key]:
        near, _far = seg[comm]
        if near > 0:
            ax.bar(i, near, 0.62, bottom=bottom, color=COMM_COL[comm],
                   edgecolor=COMM_COL[comm], linewidth=EDGE_LW, zorder=3)
        bottom += near
    # 2) all FAR segments (outline only) stacked on top
    bottom = s0 + sum(seg[c][0] for c, _ in scen_inc[key])
    for comm, _inc in scen_inc[key]:
        _near, far = seg[comm]
        if far > 0:
            ax.bar(i, far, 0.62, bottom=bottom, facecolor='none',
                   edgecolor=COMM_COL[comm], linewidth=EDGE_LW, zorder=3)
        bottom += far

# value labels
for i, v in enumerate(vals):
    ax.text(i, v + 14, f'{v:.0f}', ha='center', va='bottom',
            fontsize=16, fontweight='bold', color='#222222')
    if i == 0:
        continue
    fl = flows[scen_keys[i]]
    seg = {comm: (inc * near_share_of(fl, comm), inc * (1 - near_share_of(fl, comm)))
           for comm, inc in scen_inc[scen_keys[i]]}
    # near segment labels (filled, white text)
    bottom = s0
    for comm, _inc in scen_inc[scen_keys[i]]:
        near, _far = seg[comm]
        if near > 25:
            ax.text(i, bottom + near * 0.5, f'+{100 * near / s0:.0f}%', ha='center',
                    va='center', fontsize=16, color='white', fontweight='bold', zorder=4)
        bottom += near
    # far segment labels (outline, coloured text)
    bottom = s0 + sum(seg[c][0] for c, _ in scen_inc[scen_keys[i]])
    for comm, _inc in scen_inc[scen_keys[i]]:
        _near, far = seg[comm]
        if far > 25:
            ax.text(i, bottom + far * 0.5, f'+{100 * far / s0:.0f}%', ha='center',
                    va='center', fontsize=16, color=COMM_COL[comm], fontweight='bold', zorder=4)
        bottom += far

ax.set_xticks(np.arange(5))
xt = ['S0:local', 'S1:biomass', 'S2:CO$_2$', 'S3:bio+CO$_2$', 'S4:bio+CO$_2$+water']
ax.set_xticklabels(xt, fontsize=16)
ax.set_ylabel('National BECCS potential (Mt CO$_2$ yr$^{-1}$)', fontsize=16)
ax.set_ylim(0, 1800)
ax.tick_params(labelsize=16)
ax.set_title(' ',
             fontsize=16, pad=8)
_style.panel_label(ax, 'a', fontsize=24)


# ---------- helper: draw one scenario map ----------
def draw_scenario(ax, scen_key, tag, fill_col='base', fill_cmap=None, fill_norm=None,
                  fill_vmin=None, fill_vmax=None, show_flows=True, title=None,
                  cb_label=None, cb_ticks=None, cb_ticklabels=None, cb_rect=None):
    """Draw a scenario map.

    fill_col / fill_cmap / fill_norm decide what the prefectures are coloured
    by; show_flows toggles the transport arrows; title overrides the default
    scenario caption.  cb_* draws a small colourbar INSIDE the panel, in the
    blank upper-middle part of the map.
    """
    if fill_cmap is None:
        fill_cmap = cmap
    if fill_norm is not None:
        gdf.plot(column=fill_col, ax=ax, cmap=fill_cmap, norm=fill_norm,
                 edgecolor="#c3bebe", linewidth=0.2,
                 missing_kwds={'color': '#e8e8e8'})
    else:
        gdf.plot(column=fill_col, ax=ax, cmap=fill_cmap,
                 vmin=0 if fill_vmin is None else fill_vmin,
                 vmax=(vmax if fill_vmax is None else fill_vmax),
                 edgecolor="#c3bebe", linewidth=0.2,
                 missing_kwds={'color': '#e8e8e8'})
    ax.set_xlim(73, 136); ax.set_ylim(17, 54)
    ax.set_aspect('auto'); ax.set_position(ax.get_position())
    ax.set_xticks([]); ax.set_yticks([])

    # flows: thin curved arcs, small solid arrowheads, color saturation ∝ amount
    if show_flows:
        fb = flows[scen_key]
        ll_from = dict(zip(res['city'], zip(res['经度'], res['纬度'])))
        for comm in ['biomass', 'co2', 'water']:
            sub = fb[fb['commodity'] == comm]
            if sub.empty:
                continue
            mx = sub['Mt_yr'].max()
            cmapc = COMM[comm]['cmap']
            for _, r in sub.iterrows():
                # skip routes beyond 800 km to declutter long-distance links
                if (r['from'] in ll_from and r['to'] in ll_from
                        and r['Mt_yr'] > 1.0 and r['km'] <= 800.0):
                    (x0, y0) = ll_from[r['from']]; (x1, y1) = ll_from[r['to']]
                    frac = r['Mt_yr'] / mx
                    col = cmapc(0.15 + 0.85 * frac)   # light -> saturated
                    ax.annotate('', xy=(x1, y1), xytext=(x0, y0),
                                arrowprops=dict(arrowstyle='-|>', color=col, lw=1.0,
                                                connectionstyle='arc3,rad=0.18',
                                                mutation_scale=6,
                                                shrinkA=2, shrinkB=2))

    ax.set_title(title if title is not None
                 else f"{SCEN[scen_key][0]}: {SCEN[scen_key][1]}",
                 fontsize=16, pad=4)
    _style.panel_label(ax, tag, fontsize=22)

    def _layer(iax):
        if fill_norm is not None:
            gdf.plot(column=fill_col, ax=iax, cmap=fill_cmap, norm=fill_norm,
                     edgecolor="#c3bebe", linewidth=0.1,
                     missing_kwds={'color': '#e8e8e8'})
        else:
            gdf.plot(column=fill_col, ax=iax, cmap=fill_cmap,
                     vmin=0 if fill_vmin is None else fill_vmin,
                     vmax=(vmax if fill_vmax is None else fill_vmax),
                     edgecolor="#c3bebe", linewidth=0.1,
                     missing_kwds={'color': '#e8e8e8'})
    add_scs_inset(fig, ax, bd=bd, plot_layer=_layer)

    # colourbar for the fill, placed in the panel's blank UPPER-MIDDLE area.
    # `cb_rect` is [x, y, width, height] in AXES fractions, so raising `y`
    # moves the bar up towards the top of the map.  The default y = 0.90 sits
    # just under the panel caption.
    if cb_label is not None:
        rect = cb_rect if cb_rect is not None else [0.33, 0.85, 0.34, 0.022]
        cax = ax.inset_axes(rect)
        sm = ScalarMappable(norm=(fill_norm if fill_norm is not None
                                  else plt.Normalize(0, vmax if fill_vmax is None
                                                     else fill_vmax)),
                            cmap=fill_cmap)
        cbar = fig.colorbar(sm, cax=cax, orientation='horizontal')
        if cb_ticks is not None:
            cbar.set_ticks(cb_ticks)
        if cb_ticklabels is not None:
            cbar.set_ticklabels(cb_ticklabels)
        cbar.ax.tick_params(labelsize=16, length=2, pad=1)
        cax.set_title(cb_label, fontsize=16, pad=5)


# Row 2: S1 (fill = biomass NET flow, arrows kept), S2 (CO2 NET flow)
draw_scenario(fig.add_subplot(gs[1, 0]), 'S1_biomass', 'b',
              fill_col='f_net_b', fill_cmap=cmap_flow_b, fill_norm=norm_flow_b,
              show_flows=True,
              title='S1: biomass transport',
              cb_label='biomass net flow  (Mt yr$^{-1}$)',
              cb_ticks=[-lim_b, 0, lim_b],
              cb_ticklabels=['%.0f' % -lim_b, '0', '%.0f' % lim_b])
draw_scenario(fig.add_subplot(gs[1, 1]), 'S2_co2', 'c',
              fill_col='f_net_c', fill_cmap=cmap_flow_c, fill_norm=norm_flow_c,
              show_flows=True,
              title='S2: CO$_2$ transport',
              cb_label='CO$_2$ net flow  (Mt yr$^{-1}$)',
              cb_ticks=[-lim_c, 0, lim_c],
              cb_ticklabels=['%.0f' % -lim_c, '0', '%.0f' % lim_c])

# Row 3: S3 partition only (no arrows), S4 net emissions (diverging colour)
draw_scenario(fig.add_subplot(gs[2, 0]), 'S3_biomass+co2', 'd',
              show_flows=False,
              title='local BECCS potential (no transport)',
              cb_label='local BECCS potential  (Mt CO$_2$ yr$^{-1}$)',
              cb_ticks=[0, vmax], cb_ticklabels=['0', '%.0f' % vmax])
draw_scenario(fig.add_subplot(gs[2, 1]), 'S4_biomass+co2+water', 'e',
              fill_col='f_net', fill_cmap=cmap_net, fill_norm=net_norm,
              show_flows=False,
              title='net emissions after coordination',
              cb_label='net emissions  (Mt CO$_2$ yr$^{-1}$)',
              cb_ticks=[NET_VMIN, 0, NET_VMAX],
              cb_ticklabels=['%.0f' % NET_VMIN, '0', '%.0f' % NET_VMAX])

# ---------------------------------------------------------------------------
# Legend.  Only panel (a) still needs one -- it documents the stacked-bar
# colour code.  The map panels carry their own colourbar (drawn inside
# `draw_scenario`, see `cb_rect`), and the flow arrows are self-explanatory
# once the fill scale is labelled, so the b/c arrow keys were removed.
# ---------------------------------------------------------------------------
import matplotlib.patches as mpatches

# panel (a): resource colour key, two lines, top-left blank corner
handles_a = [
    mpatches.Patch(facecolor=S0_COL, edgecolor='none', label='S0 local'),
    mpatches.Patch(facecolor=COMM_COL['biomass'], edgecolor='none',
                   label='biomass \u2264 200 km'),
    mpatches.Patch(facecolor='none', edgecolor=COMM_COL['biomass'],
                   label='biomass > 200 km'),
    mpatches.Patch(facecolor=COMM_COL['co2'], edgecolor='none',
                   label='CO$_2$ \u2264 250 km'),
    mpatches.Patch(facecolor='none', edgecolor=COMM_COL['co2'],
                   label='CO$_2$ > 250 km'),
    mpatches.Patch(facecolor='none', edgecolor=COMM_COL['water'],
                   label='water (if transferable)'),
]
ax.legend(handles=handles_a, loc='upper left', bbox_to_anchor=(0.005, 0.995),
          ncol=2, frameon=True, framealpha=0.92, edgecolor='#cccccc',
          fontsize=16, handlelength=1.6, columnspacing=1.1, labelspacing=0.35,
          borderpad=0.5).set_zorder(10)

_style.save(fig, OUT)
print('saved', OUT + '.png/.pdf/.xlsx')
print('  S0=%.0f S1=%.0f S2=%.0f S3=%.0f S4=%.0f Mt/yr' % tuple(vals))
