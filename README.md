# BECCS resource-endowment analysis — code and data release

Reproducible code, inputs and outputs for the analysis of BECCS deployment
potential across China's coal-fired power fleet, on the **nationwide-Thiessen
basis** used in the manuscript.

This release covers the five figures that make up the paper's resource and
potential results, plus the standalone national sensitivity figure.

## Figures included

| Folder / file | Manuscript figure | What it shows |
|---|---|---|
| `figures/Fig3_6_combo.*` | Fig. 6 | Resource states and responsibility–capacity mismatch across cities |
| `figures/Fig3_7_potential.*` | Fig. 7 | City-level BECCS potential under each resource constraint, and their joint effect |
| `figures/Fig3_7b_waterfall_stats.*` | Fig. 7b | Stepwise decomposition of the potential; bottleneck composition |
| `figures/Fig3_10_five_panel.*` | Fig. 10 | Stranded potential under local self-sufficiency and its recovery under coordination |
| `figures/Fig3_12_biomass_storage_combo.*` | Fig. 12 | Plant-level biomass and storage endowment, inequality, and the water-stress distribution |
| `figures/FigS16_sensitivity_combined.*` | Fig. 16 | Sensitivity of resource states and coordinated potential to key assumptions |

Every figure is provided as `.png` (300 dpi), `.pdf` (vector) and `.xlsx`
(the numbers behind the panels).

## Layout

```
release_BECCS_potential_paper/
├── model/                  scripts + the input files they read
│   └── china_maps/           basemap layers (prefecture + national outline)
│   └── *.py, *.xlsx, *.csv
├── results/                intermediate results written by the model, and read by the figures
│   └── sensitivity_results/<SCENARIO>/    the two tables Fig. 16 needs per scenario
└── figures/                final outputs
```

`model/` and `results/` mirror the working layout the scripts expect:
scripts read source data from their own folder and read/write intermediate
results in a results folder selected by an environment variable.

### A note on language

The code, filenames and folder names are entirely in English. The **data files
are not**: the workbook `plant level analysis data.xlsx` has Chinese sheet names
(`市域内比较`, `city clip`, `Sheet2`) and Chinese column headers (e.g.
`所在城市`, `电厂编号`, `煤电系统热耗-GJ/MWH`), and several intermediate tables
inherit those headers. Scripts therefore still contain Chinese *identifiers*
wherever they name a sheet or column, because that is the literal key inside the
file. These are data keys, not prose — renaming them in the code alone would
break the read. Everything else (comments, docstrings, console output, axis
labels, legend text, the `readme` sheet written into the output workbook) is in
English.


## Environment

Python 3.9 with:

```
geopandas, shapely, pyogrio, rasterio, pandas, numpy, matplotlib, openpyxl, pulp
```

`scoi`/`scipy` is not used. The optimisation is solved with the CBC solver
shipped with `pulp`.

## Reproducing

All commands are run from `model/`.

```bash
cd model
export BECCS_OUT_DIR=../results          # where intermediate results live
export BECCS_SHEET="city clip"           # the nationwide-Thiessen sheet
export BECCS_WATER_TABLE=water_thiessen_cityclip.xlsx
```

### 1. Build the intermediate results

Run in this order (each step consumes the previous one):

```bash
python 1_compute_aggregate_city.py      # -> results/plant_city_hswud_aggregated.xlsx
python 4_compute_beccs_potential.py     # -> results/BECCS_potential_{plant,city}.xlsx
python 5_optimize_beccs_multi.py        # -> results/BECCS_coordination_result.xlsx etc.
python 3_export_8class.py               # -> results/Fig3_6_prefecture_8class.xlsx
```

`results/` already contains these files, so this step can be skipped unless the
inputs change.

### 2. Draw the figures

```bash
python 2_plot_fig3_3_water.py                  # input to Fig. 12
python 2_plot_fig3_4_joint.py                  # input to Fig. 12
python 2_plot_fig3_6_combo.py                  # Fig. 6
python 2_plot_fig3_7_potential.py              # Fig. 7 and Fig. 7b
python 2_plot_fig3_10_five_panel.py            # Fig. 10
python 2_plot_fig3_12_biomass_storage_combo.py # Fig. 12
python 2_plot_figS16_sensitivity_combined.py   # Fig. 16
```

Fig. 12 reads `Fig3_3_water.xlsx` and `Fig3_4_joint.xlsx`, so those two scripts
must run before it (both outputs are also in `results/`).

### 3. Fig. 16 inputs

`2_plot_figS16_sensitivity_combined.py` reads, for the baseline, the files in
`results/`, and for each sensitivity scenario two tables from
`results/sensitivity_results/<SCENARIO>/`:

```
Fig3_6_prefecture_8class.xlsx     resource-state classes per city
BECCS_coordination_result.xlsx    city-level potentials and transport flows
```

Only these two files are shipped per scenario (2.1 MB in total) — the full
scenario folders also contain re-drawn figures, which are not needed.

The 17 scenarios are: `EFR20`, `EFR80`, `BIO25`, `BIO50`, `BIO250`, `BIO500`,
`STO100`, `STO500`, `STOR25`, `STOR30`, `STOCAP50`, `STOCAP25`, `GEN50`,
`GEN25`, `DESAL`, `EWR`, `CONS`.

## Model summary

BECCS potential is the biogenic CO₂ captured and permanently stored, with each
plant's generation held at its current level; coal-derived CO₂ is not counted as
a negative emission. Three resource ceilings are evaluated per city:

- **biomass** — the smaller of the residues collected inside the plant's service
  territory and the fuel demand of the city's fleet;
- **storage** — the smaller of accessible storage volume annualised over the
  allocation horizon and the annual injection-rate capability;
- **water** — the generation supported by the city's water surplus after the
  environmental-flow reserve and competing sectoral demand.

The self-sufficient potential of a city is the minimum of the three. The
coordinated scenarios (S1–S4) are solved as a multi-commodity transport-linear
programme that allows biomass, CO₂ and water to move between cities.

Key baseline parameters: biomass emission factor 0.112 t CO₂/GJ, capture rate
0.90, co-firing energy penalty 1%, storage horizon 20 years, environmental-flow
reserve 50%, biomass buffer 100 km, storage buffer 250 km.

## Notes for readers re-running the code

- **`_style.read_map` simplifies the prefecture polygons for rendering only.**
  The layer carries 1.9 M vertices; drawn unsimplified, the PDFs reach 60–120 MB.
  Simplification is applied to the plotting copy, never to the data files. Set
  `BECCS_GEO_SIMPLIFY=0` to disable.
- **`BECCS_OUT_DIR` and `BECCS_SHEET` must both be set** to reproduce the
  manuscript basis. The defaults point at a different (local-Thiessen) basis.
- Figures are written to `BECCS_OUT_DIR`, so set it before running.
