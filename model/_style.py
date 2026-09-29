# -*- coding: utf-8 -*-
"""Shared Nature-style plotting configuration for all figures."""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import geopandas as gpd

# ---- Nature/journal style ----
plt.rcParams.update({
    # font
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
    # spines / ticks
    'axes.linewidth': 0.6,
    'xtick.major.width': 0.6,
    'ytick.major.width': 0.6,
    'xtick.major.size': 2.5,
    'ytick.major.size': 2.5,
    'xtick.direction': 'out',
    'ytick.direction': 'out',
    # no grid by default
    'axes.grid': False,
    'axes.axisbelow': True,
    # colors
    'axes.prop_cycle': plt.cycler(color=['#0072B2', '#D55E00', '#009E73',
                                         '#CC79A7', '#E69F00', '#56B4E9',
                                         '#F0E442', '#000000']),
    # margins
    'savefig.bbox': 'tight',
})


def panel_label(ax, text, x=0.0, y=1.0, dx=0.0, dy=0.02, fontsize=26):
    """Add a bold (a)/(b)/(c) panel label at the top-left, inside the axes.

    dx=0 keeps every label starting at the same left edge of its panel, so
    labels across panels are vertically aligned (left-aligned column).
    fontsize default 26 (matches other figures); pass 16 for combo figures.
    """
    ax.text(x + dx, y + dy, text, transform=ax.transAxes, fontsize=fontsize,
            fontweight='bold', va='bottom', ha='left')


def legend_below(ax, fig, handles, ncol, below=0.07, fontsize=16):
    """Place a legend centered below an axes, outside the frame and below the
    x-axis title, using FIGURE coordinates so positioning is deterministic and
    identical across figures (panel (a) map panels).

    below : distance (in figure fraction) between the axes bottom edge and the
            top of the legend; xlabel sits roughly ~0.05 below the axes, so
            0.07 clears it. Make sure the figure bottom margin leaves room.
    """
    pos = ax.get_position()
    xc = pos.x0 + pos.width / 2.0
    leg_top = pos.y0 - below
    ax.legend(handles=handles, loc='upper center', ncol=ncol, fontsize=fontsize,
              frameon=False, borderaxespad=0.0,
              bbox_to_anchor=(xc, leg_top), bbox_transform=fig.transFigure)
    return ax


def setup_panel(ax, xlabel=None, ylabel=None, title=None):
    """Apply uniform spines (box on), subtle grid off."""
    for spine in ax.spines.values():
        spine.set_linewidth(0.6)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)


def read_map(path, tol=None, **kwargs):
    """Read a polygon layer and simplify it *for rendering only*.

    Why this exists: the prefecture layer carries 1.9 M vertices across its 371
    polygons.  Drawing them as vector paths produced PDFs of 60-120 MB, past
    GitHub's 100 MB per-file limit.  Rasterising the layer instead shrank the
    file but turned the map into a bitmap (62 MB at 300 dpi) and lost crispness
    on zoom.  Simplifying the geometry is strictly better: the PDF stays fully
    vector at ~5 MB, and at the default tolerance the largest possible
    displacement is far below one pixel.

    Tolerance in degrees.  At 0.01 deg the map spans ~63 deg over ~12 in, so the
    shift is ~0.002 in ~= 0.14 pt, i.e. invisible at 300 dpi (~4 px/pt).  The
    underlying data files are NOT modified -- only the plotting copy.
    """
    g = gpd.read_file(path, **kwargs)
    if tol is None:
        tol = float(os.environ.get('BECCS_GEO_SIMPLIFY', '0.01'))
    if tol > 0:
        g['geometry'] = g.geometry.simplify(tol, preserve_topology=True)
    return g


def save(fig, out_base):
    """Write PNG + PDF + (caller writes XLSX)."""
    fig.savefig(out_base + '.png', dpi=300, bbox_inches='tight')
    fig.savefig(out_base + '.pdf', bbox_inches='tight')
    plt.close(fig)
