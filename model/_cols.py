# -*- coding: utf-8 -*-
"""Shared column-name resolution for radius-dependent resource columns.

The master workbook `plant level analysis data.xlsx` stores the local-Thiessen
storage / injection potential for several buffer radii (100 / 250 / 500 km,
columns U/AL/AM for 250 km and the appended BN..BS for 100 / 500 km), plus
biomass collection buffers (100 / 250 / 500 km, columns S / T / BT).

These helpers map environment variables to the right column name so the same
pipeline can be re-run under a different radius without touching the code.

Environment variables
---------------------
BECCS_STO_RADIUS : '100' | '250' | '500'   (default '250', the paper basis)
BECCS_BIO_RADIUS : '100' | '250' | '500'   (default '100')
BECCS_BIO_COL    : explicit biomass column override (backwards compatible;
                   takes precedence over BECCS_BIO_RADIUS)

The 250 km storage columns keep their historical names (U/AL/AM) because they
are the paper basis and are referenced by cached formulas in the workbook.

Water table
-----------
BECCS_WATER_TABLE : explicit override, e.g. 'water_thiessen_cityclip.xlsx'.
                    When unset the table is inferred from BECCS_SHEET, because
                    the two must agree: the 'city clip' sheet is the
                    nationwide-Thiessen basis and pairs with
                    water_thiessen_cityclip.xlsx (sum of R = 16,084 亿m3), while
                    the other sheets are the local-Thiessen basis and pair with
                    water_thiessen_local.xlsx (sum of R = 22,620 亿m3).  Mixing
                    them silently changes every water-limited result, so the
                    inference is deliberate rather than a hard-coded default.

Plant and unit sheets
---------------------
The workbook holds each basis as two sheets: '<basis> (电厂)' / '<basis>-电厂'
with one row per plant, and '<basis> (机组)' / '<basis>-机组' with one row per
generating unit.  The unit rows do NOT line up with the plant rows, so unit
data must only ever be joined to plants through '电厂编号' -- never by row
position.  `read_plants`, `read_units` and `plant_water` below are the only
entry points, and they check the join.

BECCS_SHEET      : basis name, 'city clip' (default, the paper basis) or
                   '市域内比较'.
BECCS_CCS_PENALTY: '1' (default) applies the plant-specific CCS energy penalty
                   (workbook column '能源惩罚-比例') to the fuel demand at fixed
                   net output; '0' reproduces the pre-v2 results, which used
                   the coal-only heat rate.
"""
import os

import numpy as np
import pandas as pd

DEFAULT_STO_RADIUS = '250'
DEFAULT_BIO_RADIUS = '100'
DEFAULT_SHEET = 'city clip'

# basis -> (plant sheet, unit sheet)
SHEETS_BY_BASIS = {
    'city clip': ('city clip (电厂)', 'city clip (机组)'),
    '市域内比较': ('市域内比较-电厂', '市域内比较-机组'),
}
N_PLANTS = 2171

# basis sheet -> matching water table
WATER_TABLE_BY_SHEET = {
    'city clip': 'water_thiessen_cityclip.xlsx',
}
WATER_TABLE_DEFAULT = 'water_thiessen_local.xlsx'

COFIRE_PEN = 0.01          # co-firing efficiency penalty
COL_CCS_PEN = '能源惩罚-比例'  # IECM CCS energy penalty (fraction of gross output)


def basis():
    """Active basis name (BECCS_SHEET)."""
    return os.environ.get('BECCS_SHEET', DEFAULT_SHEET)


def water_table():
    """Water-endowment table matching the active BECCS_SHEET basis."""
    explicit = os.environ.get('BECCS_WATER_TABLE')
    if explicit:
        return explicit
    return WATER_TABLE_BY_SHEET.get(basis(), WATER_TABLE_DEFAULT)


def _sheets():
    b = basis()
    if b not in SHEETS_BY_BASIS:
        raise KeyError('unknown BECCS_SHEET %r; expected one of %s'
                       % (b, list(SHEETS_BY_BASIS)))
    return SHEETS_BY_BASIS[b]


def read_plants(path):
    """Plant sheet of the active basis: one row per plant, ids checked."""
    df = pd.read_excel(path, sheet_name=_sheets()[0])
    df = df[df['序号'].notna()].copy()
    pid = pd.to_numeric(df['电厂编号'], errors='coerce')
    if len(df) != N_PLANTS or pid.isna().any() or pid.duplicated().any():
        raise ValueError('plant sheet %r: expected %d rows with unique 电厂编号, '
                         'got %d rows' % (_sheets()[0], N_PLANTS, len(df)))
    return df


def read_units(path):
    """Unit sheet of the active basis: one row per generating unit."""
    u = pd.read_excel(path, sheet_name=_sheets()[1])
    return u[u['电厂编号'].notna()].copy()


def plant_water(path, plants):
    """Per-plant annual water use (m3/yr) at base generation, by 电厂编号.

    Sums of the unit rows of each plant, for the coal-only system and for the
    coal + CCS system, by withdrawal (excluding seawater) and by consumption.
    The withdrawal totals equal the plant-sheet columns 25/26 exactly.  Scale
    by BECCS_GEN_FACTOR at the call site.

    Returns a DataFrame aligned row-for-row with `plants`, columns
    wd_coal, wd_ccs, cons_coal, cons_ccs.
    """
    u = read_units(path)
    for c in ['发电量 MWH', '煤电系统年取水总量 立方米-除去海水',
              '煤电 ccus 系统年取水总量 除去海水', '煤电系统年耗水总量 立方米',
              '煤电 ccs 系统年耗水总量  立方米']:
        u[c] = pd.to_numeric(u[c], errors='coerce').fillna(0.0)
    u['pid'] = pd.to_numeric(u['电厂编号'], errors='coerce')
    g = u.groupby('pid').agg(
        gen=('发电量 MWH', 'sum'),
        wd_coal=('煤电系统年取水总量 立方米-除去海水', 'sum'),
        wd_ccs=('煤电 ccus 系统年取水总量 除去海水', 'sum'),
        cons_coal=('煤电系统年耗水总量 立方米', 'sum'),
        cons_ccs=('煤电 ccs 系统年耗水总量  立方米', 'sum'))
    pid = pd.to_numeric(plants['电厂编号'], errors='coerce')
    missing = set(pid) - set(g.index)
    if missing:
        raise ValueError('%d plants have no unit rows, e.g. %s'
                         % (len(missing), sorted(missing)[:5]))
    g = g.reindex(pid.values)
    # unit generation must agree with the plant record it is joined to
    gen_p = (pd.to_numeric(plants['电厂实际装机总功率MW'], errors='coerce')
             * pd.to_numeric(plants['发电小时'], errors='coerce')).values
    dev = np.abs(g['gen'].values / gen_p - 1)
    if np.nanmax(dev) > 0.01:
        raise ValueError('unit vs plant generation differ by up to %.1f%%'
                         % (100 * np.nanmax(dev)))
    out = pd.DataFrame(index=plants.index)
    for k in ['wd_coal', 'wd_ccs', 'cons_coal', 'cons_ccs']:
        out[k] = g[k].values
    return out


def water_use(path, plants):
    """(coal-only, coal + CCS) annual water use per plant, m3/yr.

    Withdrawal by default, consumption when BECCS_CONSUMPTION=1; scaled by
    BECCS_GEN_FACTOR.
    """
    w = plant_water(path, plants)
    gf = float(os.environ.get('BECCS_GEN_FACTOR', '1.0'))
    if os.environ.get('BECCS_CONSUMPTION', '0') == '1':
        return w['cons_coal'] * gf, w['cons_ccs'] * gf
    return w['wd_coal'] * gf, w['wd_ccs'] * gf


def ccs_penalty_on():
    return os.environ.get('BECCS_CCS_PENALTY', '1') == '1'


def fuel_per_mwh(plants):
    """Fuel energy (GJ) per net MWh under BECCS operation.

    heat rate / (1 - co-firing penalty), and additionally / (1 - CCS energy
    penalty) when BECCS_CCS_PENALTY=1, so that net output stays fixed while
    the capture plant draws its energy.
    """
    hr = pd.to_numeric(plants['煤电系统热耗-GJ/MWH'], errors='coerce')
    f = hr / (1 - COFIRE_PEN)
    if ccs_penalty_on():
        f = f / (1 - pd.to_numeric(plants[COL_CCS_PEN], errors='coerce'))
    return f


def sto_radius():
    """Buffer radius (km, as a string) for the storage/injection columns."""
    return os.environ.get('BECCS_STO_RADIUS', DEFAULT_STO_RADIUS).strip()


def sto_col():
    """Accessible storage volume within the buffer (Mt)."""
    return '电厂周围%skm内总封存潜力MT' % sto_radius()


def inj_col():
    """Annual average injection-rate capability within the buffer (Mt/a)."""
    return '电厂周围%skm内总注入潜力MTa' % sto_radius()


def inj_max_col():
    """Annual maximum injection-rate capability within the buffer (Mt/a)."""
    return '电厂周围%skm内总最大注入潜力MTa' % sto_radius()


def bio_radius():
    """Buffer radius (km, as a string) for the biomass collection column."""
    return os.environ.get('BECCS_BIO_RADIUS', DEFAULT_BIO_RADIUS).strip()


def bio_col():
    """Biomass collection potential within the buffer (GJ)."""
    explicit = os.environ.get('BECCS_BIO_COL')
    if explicit:
        return explicit
    return '电厂周围-%skm总生物质潜力GJ' % bio_radius()
