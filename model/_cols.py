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
"""
import os

DEFAULT_STO_RADIUS = '250'
DEFAULT_BIO_RADIUS = '100'

# basis sheet -> matching water table
WATER_TABLE_BY_SHEET = {
    'city clip': 'water_thiessen_cityclip.xlsx',
}
WATER_TABLE_DEFAULT = 'water_thiessen_local.xlsx'


def water_table():
    """Water-endowment table matching the active BECCS_SHEET basis."""
    explicit = os.environ.get('BECCS_WATER_TABLE')
    if explicit:
        return explicit
    sheet = os.environ.get('BECCS_SHEET', '市域内比较')
    return WATER_TABLE_BY_SHEET.get(sheet, WATER_TABLE_DEFAULT)


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
