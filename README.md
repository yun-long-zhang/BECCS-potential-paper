# BECCS resource-endowment analysis — code and data release

Reproducible code, inputs and outputs for the analysis of BECCS deployment
potential across China's coal-fired power fleet, on the **nationwide-Thiessen
basis** used in the manuscript.

This release covers the five figures that make up the paper's resource and
potential results, plus the standalone national sensitivity figure.

> **Version 2 (2026-10).** The model was revised after a code review; the
> current results are in `results/`. The published (v1) outputs were
> replaced on 2026-11-14 and remain in the first git commit (`de3e94f`, folder
> `results/` of that commit).  What changed and why is listed under
> [Changes in v2](#changes-in-v2); the headline numbers are compared in
> [v1 vs v2](#v1-vs-v2-key-numbers).

## Figures included

`figures/` holds the v2 figures under the manuscript numbering, each as `.png`
(300 dpi), `.pdf` (vector) and `.xlsx` (the numbers behind the panels). The
second part of each file name is the script output it was copied from.

| File | Paper figure | What it shows | Script |
|---|---|---|---|
| `Fig1_Fig3_12_biomass_storage_combo.*` | Fig. 1 | Plant-level biomass, storage and water endowments, Lorenz curves | `2_plot_fig3_12_biomass_storage_combo.py` |
| `Fig2_Fig3_6_combo.*` | Fig. 2 | Resource states and responsibility–capacity mismatch across cities | `2_plot_fig3_6_combo.py` |
| `Fig3_Fig3_7b_waterfall_stats.*` | Fig. 3 | Local potential: stepwise decomposition and city distribution | `2_plot_fig3_7_potential.py` |
| `Fig4_Fig3_10_five_panel.*` | Fig. 4 | Coordinated potential (S0–S4, within 250 km), transport, flow maps | `2_plot_fig3_10_five_panel.py` |
| `Fig5_Fig5_tradeoff.*` | Fig. 5 | Coordination trade-offs (S1–S4): transport cost–potential, marginal cost and distance–potential frontiers | `6_tradeoff_frontiers.py` + `2_plot_fig5_tradeoff.py` |
| `Fig6_FigS16_sensitivity_combined.*` | Fig. 6 | Sensitivity of resource states and coordinated potential | `2_plot_figS16_sensitivity_combined.py` |
| `FigS11_FigS_transport_distance.*` | Fig. S11 | Transport-distance distribution under full coordination | `2_plot_figS_transport_distance.py` |
| `FigS12_FigS12_water_efr.*` | Fig. S12 | City-level WSR under EFR 20 / 50 / 80% | `2_plot_figS12_water_efr.py` |
| `FigS13_Fig3_7_potential.*` | Fig. S13 | City-level potential under each resource constraint | `2_plot_fig3_7_potential.py` |
| `FigS14_FigS_gini_city.*` | Fig. S14 | City-level Lorenz curves and Gini coefficients | `2_plot_figS_gini_city.py` |
| `FigS15_FigS_s4_flows.*` | Fig. S15 | Biomass, CO₂ and water links under full coordination (S4) | `2_plot_figS_s4_flows.py` |

The same files, together with the intermediate tables and the inputs to
Figs. 1 (`Fig3_3_water`, `Fig3_4_joint`), are written to `results/` by the
scripts.

## Layout

```
release_BECCS_potential_paper/
├── model/                  scripts + the input files they read
│   └── china_maps/           basemap layers (prefecture + national outline)
│   └── *.py, *.xlsx, *.csv
├── results/             current (v2) results, figures and run logs (_log_*.txt)
│   └── sensitivity_results/<SCENARIO>/    v2 sensitivity runs
└── figures/                v2 figures under the manuscript numbering
```

`model/` and `results/` mirror the working layout the scripts expect:
scripts read source data from their own folder and read/write intermediate
results in a results folder selected by an environment variable.

### A note on language

The code, filenames and folder names are entirely in English. The **data files
are not**: the workbook `plant level analysis data.xlsx` has Chinese sheet names
(`city clip (电厂)`, `city clip (机组)`, `市域内比较-电厂`, `市域内比较-机组`)
and Chinese column headers (e.g.
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

Everything — baseline results, all figures, the 17 sensitivity scenarios and
Fig. 5 — is reproduced by one script (about 35 minutes):

```bash
cd model
./run_all.sh ../results         # PY=/path/to/python ./run_all.sh to choose the interpreter
```

A from-scratch run reproduces the shipped `results/` exactly (all 433
tables identical). The individual steps are listed below; all commands are run
from `model/`.

```bash
cd model
export BECCS_OUT_DIR=../results       # where intermediate results live
export BECCS_SHEET="city clip"           # the nationwide-Thiessen basis (default)
```

`BECCS_SHEET` names the basis; the scripts read its plant sheet
(`city clip (电厂)`) and unit sheet (`city clip (机组)`) through `_cols.py`, and
the matching water table (`water_thiessen_cityclip.xlsx`) is selected
automatically.

### 1. Build the intermediate results

Run in this order (each step consumes the previous one):

```bash
python 1_compute_aggregate_city.py      # -> plant_city_hswud_aggregated.xlsx
python 4_compute_beccs_potential.py     # -> BECCS_potential_{plant,city}.xlsx
python 5_optimize_beccs_multi.py        # -> BECCS_coordination_result.xlsx etc. (~2 min)
python 3_export_8class.py               # -> Fig3_6_prefecture_8class.xlsx
```

`results/` already contains these files, so this step can be skipped unless
the inputs change.

### 2. Draw the figures

```bash
python 2_plot_fig3_3_water.py                  # input to Fig. 1
python 2_plot_fig3_4_joint.py                  # input to Fig. 1
python 2_plot_fig3_6_combo.py                  # Fig. 2
python 2_plot_fig3_7_potential.py              # Fig. 3 and Fig. S13
python 2_plot_fig3_10_five_panel.py            # Fig. 4
python 2_plot_fig3_12_biomass_storage_combo.py # Fig. 1
python 2_plot_figS16_sensitivity_combined.py   # Fig. 5 (after the sensitivity runs)
python 2_plot_figS_gini_city.py                # Fig. S14
python 2_plot_figS_transport_distance.py       # Fig. S11
```

Fig. 1 reads `Fig3_3_water.xlsx` and `Fig3_4_joint.xlsx`, so those two scripts
must run before it (both outputs are also in `results/`).

### 3. Sensitivity scenarios and Fig. 5

```bash
python run_sensitivity.py --all           # 17 scenarios (~30 min), then Fig. 5
python run_sensitivity.py EFR80 GEN25     # selected scenarios only
python run_sensitivity.py --all --figs    # also redraw each scenario's figures
```

Each scenario reruns step 1 of *Reproducing* into
`$BECCS_OUT_DIR/sensitivity_results/<SCENARIO>/` with one parameter changed
(recorded in its `params.json`).  `2_plot_figS16_sensitivity_combined.py` reads,
for the baseline, the files in `$BECCS_OUT_DIR`, and for each scenario two
tables from its folder:

```
Fig3_6_prefecture_8class.xlsx     resource-state classes per city
BECCS_coordination_result.xlsx    city-level potentials and transport flows
```

Only these two files are needed per scenario.

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
- **water** — the city's water left after the environmental-flow reserve and
  competing use, A = R(1 − EFR) − U, is allocated to its plants in proportion to
  generation, a_i = A · E_i / E_city. A share f_i of each plant's generation runs
  as BECCS (full biomass co-firing with CCS; the rest stays coal without capture),
  and its water use must fit the allocation, W_coal,i + f_i (W_ccs,i − W_coal,i) ≤ a_i,
  so f_i = clip((a_i − W_coal,i) / (W_ccs,i − W_coal,i), 0, 1) and the water
  ceiling is Σ_i f_i · G_i. Because water follows generation, a plant with
  above-average water intensity can be water-limited in a city whose aggregate
  balance is adequate (WSR ≤ 1; 25 cities under the baseline).

Fuel demand at fixed net output is generation × heat rate / (1 − 0.01) /
(1 − CCS energy penalty), using the plant-specific IECM penalty
(`能源惩罚-比例`); G is that fuel × 0.112 t CO₂/GJ × 0.90.

The self-sufficient potential of a city is the minimum of the three. The
coordinated scenarios (S1–S4) are solved as a multi-commodity transport-linear
programme that allows biomass, CO₂ and water to move between cities:

```
x_i <= G_i                                            generation ceiling
ob_i + Σ_j B_ij <= B_i,      x_i <= ob_i + Σ_k B_ki          biomass
x_i <= W_i + y_i,  ow_i + Σ_j W_ij <= E_i,  Δ_i y_i <= ow_i + Σ_k W_ki   water (Mt water)
x_i = l_i + Σ_j C_ij,        l_i + Σ_k C_ki <= S_i           CO2 and storage
```

W_i is the locally water-supported potential, E_i the water left in the plants'
allocations after their own BECCS share, and Δ_i the extra water needed per Mt
of BECCS beyond W_i (mean over the generation not yet converted). Exports come
only from a city's own endowment (no relaying of imports), so water and biomass
are conserved. Each coordinated scenario is also solved with every flow limited
to 250 km as a hard constraint (`<scenario>_250km`); Figs. 4a and 5b use
these runs for their within-250 km segments.

### How the coordinated scenarios are solved

`5_optimize_beccs_multi.py` minimises the **real engineering transport cost** of
inter-city flows and treats the national potential as a constraint rather than as
the objective:

```
minimise   Σ_k K_k · (flow_k · distance)
subject to Σ_i x_i ≥ T          (T raised until the LP becomes infeasible)
           + the resource balances above
```

Because a tonne of capture capacity displaced from one city is credited to the
receiving city through the same variable, the transport terms **cannot change the
maximum attainable potential** — they only choose the cheapest of the equivalent
optima. The reported potential is therefore set by resource feasibility, not by
the cost parameters.

Set `BECCS_COST_FRONTIER=1` to also write `$BECCS_OUT_DIR/BECCS_cost_frontier.xlsx`, the
least cost of reaching the potential at 50/70/85/95/100% of each scenario's
feasible maximum (five extra solves per scenario, so it is off by default).

Unit costs and the resulting cost coefficients (USD per Mt CO₂ per km), where the
coefficient is the unit cost times the physical mass moved per Mt CO₂:

| Commodity | Unit cost | Mass per Mt CO₂ | K_k |
|---|---|---|---|
| biomass | 0.11 \$ t⁻¹ km⁻¹ | 6.614×10⁵ t | 72,751 |
| captured CO₂ | 0.035 \$ t⁻¹ km⁻¹ | 1.000×10⁶ t | 35,000 |
| water | 0.0085 \$ m⁻³ km⁻¹ | flows in Mt water | 8,500 per Mt water |

The legacy penalty-weighted objective (`max Σx − Σ w_k·flow·distance`, with
`w_bio=1e-4`, `w_co2=2e-5`, `w_wat=1e-2/4.82` per Mt water) is retained behind
`BECCS_OBJECTIVE=penalty`. In v2 both objectives give the same national
potential in every scenario except `S4_biomass+co2+water_250km`, where the water
penalty makes the penalty mode stop 3.5 Mt short of the feasible maximum.
`cost` (the default) imposes the potential as a constraint and is the reference.

Key baseline parameters: biomass emission factor 0.112 t CO₂/GJ, capture rate
0.90, co-firing energy penalty 1%, plant-specific CCS energy penalty (median
14.4%), storage horizon 20 years, environmental-flow reserve 50%, biomass buffer
100 km, storage buffer 250 km, near-distance cap 250 km.

## Notes for readers re-running the code

- **Map layers are simplified for rendering only** (`_style.read_map`, and the
  same rule inside `2_plot_fig3_6_combo.py`), which keeps every PDF below 6 MB.
  The layer carries 1.9 M vertices; drawn unsimplified, the PDFs reach 30–130 MB,
  past GitHub's 100 MB per-file limit. Simplification is applied to the plotting
  copy, never to the data files. Set `BECCS_GEO_SIMPLIFY=0` to disable.
- **Set `BECCS_OUT_DIR`** before running; `BECCS_SHEET` defaults to the
  manuscript basis (`city clip`).
- **`BECCS_CCS_PENALTY=0`** drops the CCS energy penalty (coal-only heat rate,
  as in v1). **`BECCS_NEAR_KM`** sets the hard distance cap of the extra runs
  (default 250; `0` skips them).
- **`BECCS_OBJECTIVE` selects the coordination objective** — `cost` (default) or
  `penalty` (the legacy formulation). Both reproduce the published potentials.
- **Plant and unit data are in separate sheets.** `plant level analysis data.xlsx`
  holds, for each basis, a plant sheet (2,171 rows) and a unit sheet (5,442
  rows). Unit rows do not line up with plant rows; `_cols.py` joins them only
  through `电厂编号` and stops with an error if the join or the generation totals
  disagree. The v1 reduced workbook is kept as
  `plant level analysis data_reduced_backup.xlsx`.
- **Redrawing the v1 figures.** The figure scripts still read v1 results:
  check out the v1 commit next to this one (`git worktree add ../v1 de3e94f`),
  point `BECCS_OUT_DIR` at `../v1/results` and set `BECCS_CCS_PENALTY=0`. Without
  `_250km` columns, Figs. 4a and 5b fall back to the v1 split (each
  increment re-weighted by the share of its flows on links ≤ 250 km). The v1
  intermediates themselves cannot be regenerated with the v2 model code.
- **`city_centroids.csv`** holds the plant-count-weighted mean coordinates of
  each city's fleet. The figure scripts read it only when the workbook lacks the
  `经度`/`纬度` columns (as in the reduced release copy); against the full working
  workbook they use the workbook's own coordinates.
- Figures are written to `BECCS_OUT_DIR`, so set it before running.

## Changes in v2

| # | Issue in v1 | v1 effect | Fix in v2 |
|---|---|---|---|
| 1 | Water in the coordination LP was not conserved: the constraint was `x_i ≤ W_i + imports`, exports did not reduce a city's own supply, and every city could export up to a fixed 20 Mt CO₂-eq | In baseline S4, 66 of the 97 water-exporting cities had no water of their own (W = 0) yet supplied 339 of the 465 Mt CO₂-eq moved; in EFR80 / GEN50 / GEN25 this lifted S4 back to 1,146 | Water balance with exports from own endowment only, in physical units (`5_optimize_beccs_multi.py`) |
| 2 | The CCS water-use intensity was read from the unit-level columns of the plant rows; the unit table sat beside the plant table but its rows belong to other plants | 354 plants were given the intensity of an unrelated (often once-through or seawater-cooled) unit | Plant and unit data in separate sheets, joined by `电厂编号` (`_cols.water_use`) |
| 3 | Water surplus was computed after subtracting the fleet's coal + CCS use, and that surplus then had to cover CCS water again | CCS water counted twice | Generation-share allocation kept; each plant's allocation now covers its existing coal use plus the extra CCS water (see *Model summary*) |
| 4 | Fuel demand used the coal-only heat rate; the IECM CCS energy penalty in the workbook was never used | Fuel demand and G about 15% too low at fixed net output | `_cols.fuel_per_mwh`; switch with `BECCS_CCS_PENALTY` |
| 5 | The "within 250 km" potential was a post-hoc split, not an optimisation with a distance limit | 820 Mt CO₂ yr⁻¹ reported as near-distance potential | Hard 250 km cap with direct links only (`*_250km` scenarios) |
| 6 | Fig. 3b bin labels were shifted by one bin | Bar labelled "0" held the [0, 0.1) cities; "10–20" was really [20, 50] | Separate zero bin, one label per bin |
| 7 | Water flows were converted with a fleet-mean 4.82 m³ per t CO₂ | Physical water mass and cost approximate | Physical mass reported per flow (`phys_Mt`) |
| 8 | The 100 / 500 km storage columns and the 500 km biomass column came from a re-built Thiessen tessellation, while the 250 km baseline columns came from the original ArcGIS faces | Radii not nested: ~250 plants lost storage from 250 to 500 km (e.g. plant 15, Tianjin: 441 → 0 Mt/a); STO500 gave S0 = 264 < 275 baseline, STO100 gave 255 | Each 100 / 500 km column rebuilt as baseline 250 km value + radius increment on the re-built faces, so 100 ≤ 250 ≤ 500 km for every plant (`00 model/24_harmonise_radius_columns.py`; backup `plant level analysis data_backup_pre_radius_harmonise.xlsx`). STO100 S0 = 267, STO500 S0 = 275, BIO500 S4 = 1,163 |
| 9 | Figure labelling | Overlapping labels (Fig. 1a, 1d, 4a, 4b), "Biomass ceiling" in Fig. 3a, "Burden-carrier" in Fig. 2e, Fig. 5 tick names unlike Table S2 | Labels fixed; Fig. 3a bars named after the attribution used (cut in water- / storage-limited cities); Fig. 4b distance printed above bars instead of a twin axis |
| 10 | Colours | Red-green diverging maps, colours differing between figures | One colour-blind-safe palette in `_style.py` (Okabe-Ito categorical; ColorBrewer BrBG / PuOr / RdBu diverging): biomass #009E73, CO₂/storage #D55E00, water #0072B2, S0 #4D4D4D; Fig. 3b grouped instead of stacked bars on the log axis |
| 11 | Trade-off analysis (new) | Only the end points S0 and the coordinated maximum were reported | `6_tradeoff_frontiers.py` re-solves the least-cost model for 18 national targets (cost frontier) and 14 maximum link distances, 75–1,500 km (distance frontier); writes `results/tradeoff_frontiers.xlsx` (solves under `results/tradeoff/`). `BECCS_FRONTIER_CUTS` sets the frontier points in `5_optimize_beccs_multi.py` (default unchanged). Former Fig. 5 is now Fig. 6 |

## v1 vs v2 key numbers

Baseline, Mt CO₂ yr⁻¹ unless stated.

| Quantity | v1 (git `de3e94f`) | v2 (`results/`) |
|---|---|---|
| Full-co-firing ceiling ΣG | 4,789 | 5,505 |
| Locally balanced biomass potential | 1,016 | 1,035 |
| S0 self-sufficient | 197.9 | 274.6 |
| S1 biomass / S2 CO₂ | 606 / 591 | 898 / 741 |
| S3 = S4 (accessible-biomass ceiling) | 1,146 | 1,146 |
| S3, all flows ≤ 250 km | — (820 from the post-hoc split) | 974 |
| S4, all flows ≤ 250 km | — | 1,016 |
| S4 water transport | 2,240 Mt water (fleet-mean conversion) | 958 Mt water |
| Transport cost S3 / S4 (bn USD yr⁻¹) | 20.7 / 9.4 | 11.7 / 9.2 |
| Resource-rich / resource-vacuum cities | 3.9% / 25.3% | 3.6% / 25.3% |
| Transport share of the S4 potential, 17 sensitivity cases | 75–94% | 69–89% |
| S4 within 250 km, share of unrestricted, 17 sensitivity cases | — | 70–93% (lowest: generation 25%) |
| Sensitivity cases with S4 at 1,146 | 13 of 17 (EFR80, GEN50, GEN25 only through non-conserved water) | 13 of 17 (all with conserved water) |

The v2 sensitivity runs are in `results/sensitivity_results/`, and Fig. 6 in
`results/FigS16_sensitivity_combined.*`.
